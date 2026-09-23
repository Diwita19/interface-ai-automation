import re

from playwright.sync_api import (
    BrowserContext,
    Page,
    Request,
    Route,
    WebSocketRoute,
)
from playwright.sync_api import Error as PlaywrightError

from automation.policy import Policy, PolicyViolation
from automation.session_control import (
    HandoffExpired,
    OwnershipError,
    SessionControl,
)


class NetworkGuard:
    """Enforce browser request policy and scoped human review."""

    def __init__(
        self,
        policy: Policy,
        control: SessionControl | None = None,
    ) -> None:
        self.policy = policy
        self.control = (
            control if control is not None else SessionControl()
        )

        self.blocked_requests: list[dict[str, str | bool]] = []
        self.transport_failures = 0

        self._review_page: Page | None = None
        self._review_url: str | None = None

    def install(self, context: BrowserContext) -> None:
        context.route("**/*", self._handle_request)
        context.route_web_socket("**/*", self._block_websocket)

    def allow_human_review(
        self,
        *,
        page: Page,
        member_id: str,
    ) -> None:
        """Permit one review submission during human ownership."""

        self.control.require_human()

        if self._review_url is not None:
            raise OwnershipError(
                "A review submission permission is already active."
            )

        if re.fullmatch(r"[0-9]{5}", member_id) is None:
            raise ValueError("Invalid review member ID.")

        origin = self.policy.config.allowed_origin.rstrip("/")
        review_url = (
            f"{origin}/members/{member_id}/accounts/savings"
        )

        self.policy.check_url(review_url)

        if page.url != review_url:
            raise PolicyViolation(
                "Human review must start on the expected account page."
            )

        self._review_page = page
        self._review_url = review_url

    def revoke_human_review(self) -> None:
        """Remove any unused review submission permission."""

        self._review_page = None
        self._review_url = None

    def _consume_review_permission(
        self,
        request: Request,
    ) -> bool:
        """Accept only the designated page's review form submission."""

        if self._review_page is None or self._review_url is None:
            return False

        try:
            self.control.require_human()
        except (OwnershipError, HandoffExpired):
            self.revoke_human_review()
            return False

        if request.method != "POST":
            return False

        if request.url != self._review_url:
            return False

        if not request.is_navigation_request():
            return False

        try:
            if request.frame != self._review_page.main_frame:
                return False
        except PlaywrightError:
            return False

        content_type = (
            request.headers.get("content-type", "")
            .split(";", 1)[0]
            .strip()
            .lower()
        )

        if content_type != "application/x-www-form-urlencoded":
            return False

        origin = self.policy.config.allowed_origin.rstrip("/")

        if request.headers.get("origin") != origin:
            return False

        # Consume before sending: a failed submission is not retried
        # automatically, because its server-side outcome may be unknown.
        self.revoke_human_review()
        return True

    def _block_request(self, route: Route, reason: str) -> None:
        self.blocked_requests.append(
            {
                "reason": reason,
                "navigation": route.request.is_navigation_request(),
            }
        )

        route.abort("blockedbyclient")

    def _handle_request(self, route: Route) -> None:
        request = route.request

        try:
            self.policy.check_url(request.url)

            if request.method == "POST":
                if not self._consume_review_permission(request):
                    raise PolicyViolation(
                        "POST requires an active human review permission."
                    )

            elif request.method not in self.policy.config.allowed_methods:
                raise PolicyViolation("HTTP method is not permitted.")

        except PolicyViolation as error:
            self._block_request(route, str(error))
            return

        try:
            response = route.fetch(
                max_redirects=0,
                max_retries=0,
                timeout=5000,
            )

        except PlaywrightError:
            self.transport_failures += 1
            route.abort("failed")
            return

        try:
            if 300 <= response.status < 400:
                self._block_request(
                    route,
                    "Redirect responses are not supported.",
                )
                return

            route.fulfill(response=response)

        finally:
            response.dispose()

    def _block_websocket(self, websocket: WebSocketRoute) -> None:
        self.blocked_requests.append(
            {
                "reason": "WebSocket connections are not supported.",
                "navigation": False,
            }
        )

        websocket.close()
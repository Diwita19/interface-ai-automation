from collections.abc import Mapping
from datetime import datetime, timezone
from time import perf_counter
from playwright.sync_api import Locator, Page, expect

from automation.contracts import (
    Action,
    ClickAction,
    FillAction,
    LabelTarget,
    ReadAction,
    RoleTarget,
    TableValueTarget,
)
from automation.policy import Policy
from automation.session_control import SessionControl


class TargetResolutionError(RuntimeError):
    """A target could not be resolved safely, with sanitized diagnostics."""

    MESSAGES = {
        "target_not_found": "No matching target was found after waiting.",
        "target_ambiguous": "Multiple matching targets were found after waiting.",
        "target_unstable": "The target count changed after the count check failed.",
        "target_visibility_failed": "Target visibility could not be verified.",
    }

    def __init__(
        self,
        *,
        code: str,
        match_count: int,
        target_kind: str,
        component: str,
        step_number: int | None,
        action_kind: str | None,
    ) -> None:
        self.code = code
        self.safe_message = self.MESSAGES[code]

        # Store structural metadata only, never target names or values.
        self.details = {
            "step_number": step_number,
            "planned_action": action_kind,
            "target_kind": target_kind,
            "component": component,
            "match_count_after_failure": match_count,
        }

        super().__init__(self.safe_message)


class BrowserExecutor:
    """Execute validated actions against an existing browser page."""

    def __init__(
        self,
        page: Page,
        policy: Policy,
        control: SessionControl | None = None,
    ) -> None:
        self.page = page
        self.policy = policy
        self.control = (
            control if control is not None else SessionControl()
        )

        self._step_number: int | None = None
        self._action_kind: str | None = None

    def _resolution_error(
        self,
        locator: Locator,
        *,
        target_kind: str,
        component: str,
        fallback_code: str,
    ) -> TargetResolutionError:
        """Classify a failed assertion using a fresh count observation."""

        count = locator.count()

        if count == 0:
            code = "target_not_found"
        elif count > 1:
            code = "target_ambiguous"
        else:
            code = fallback_code

        return TargetResolutionError(
            code=code,
            match_count=count,
            target_kind=target_kind,
            component=component,
            step_number=self._step_number,
            action_kind=self._action_kind,
        )

    def _record_readiness_event(
        self,
        *,
        event: str,
        condition: str,
        target_kind: str,
        component: str,
        initial_state: str,
        elapsed_seconds: float | None = None,
    ) -> None:
        """Record structural readiness context without target values."""

        entry = {
            "event": event,
            "condition": condition,
            "target_kind": target_kind,
            "component": component,
            "initial_state": initial_state,
            "reason": "Wait for the saved target to satisfy readiness.",
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }

        if self._step_number is not None:
            entry["step"] = str(self._step_number)

        if self._action_kind is not None:
            entry["action"] = self._action_kind

        if elapsed_seconds is not None:
            entry["elapsed_seconds"] = f"{elapsed_seconds:.3f}"

        self.control.events.append(entry)

    def _require_one(
        self,
        locator: Locator,
        *,
        target_kind: str,
        component: str,
    ) -> None:
        """Wait for a unique target and record observed recovery."""

        initial_count = locator.count()
        initially_ready = initial_count == 1
        initial_state = (
            "missing" if initial_count == 0 else "ambiguous"
        )
        started = perf_counter()

        if not initially_ready:
            self._record_readiness_event(
                event="readiness_wait_started",
                condition="unique_target",
                target_kind=target_kind,
                component=component,
                initial_state=initial_state,
            )

        try:
            # Preserve the existing retrying assertion and timeout.
            expect(locator).to_have_count(1)

        except AssertionError:
            self._record_readiness_event(
                event="readiness_wait_failed",
                condition="unique_target",
                target_kind=target_kind,
                component=component,
                initial_state=(
                    "unique" if initially_ready else initial_state
                ),
                elapsed_seconds=perf_counter() - started,
            )

            raise self._resolution_error(
                locator,
                target_kind=target_kind,
                component=component,
                fallback_code="target_unstable",
            ) from None

        if not initially_ready:
            self._record_readiness_event(
                event="readiness_recovered",
                condition="unique_target",
                target_kind=target_kind,
                component=component,
                initial_state=initial_state,
                elapsed_seconds=perf_counter() - started,
            )

    def _require_visible(
        self,
        locator: Locator,
        *,
        target_kind: str,
        component: str,
    ) -> None:
        """Wait for visibility and record an observed hidden-to-visible change."""

        initially_visible = locator.is_visible()
        started = perf_counter()

        if not initially_visible:
            self._record_readiness_event(
                event="readiness_wait_started",
                condition="visible_target",
                target_kind=target_kind,
                component=component,
                initial_state="not_visible",
            )

        try:
            expect(locator).to_be_visible()

        except AssertionError:
            self._record_readiness_event(
                event="readiness_wait_failed",
                condition="visible_target",
                target_kind=target_kind,
                component=component,
                initial_state=(
                    "visible" if initially_visible else "not_visible"
                ),
                elapsed_seconds=perf_counter() - started,
            )

            raise self._resolution_error(
                locator,
                target_kind=target_kind,
                component=component,
                fallback_code="target_visibility_failed",
            ) from None

        if not initially_visible:
            self._record_readiness_event(
                event="readiness_recovered",
                condition="visible_target",
                target_kind=target_kind,
                component=component,
                initial_state="not_visible",
                elapsed_seconds=perf_counter() - started,
            )

    def resolve_target(
        self,
        target: LabelTarget | RoleTarget | TableValueTarget,
    ) -> Locator:
        """Resolve a target description to one visible element."""

        component = "element"

        if isinstance(target, LabelTarget):
            locator = self.page.get_by_label(
                target.name,
                exact=True,
            )

        elif isinstance(target, RoleTarget):
            locator = self.page.get_by_role(
                target.role,
                name=target.name,
                exact=True,
            )

        elif isinstance(target, TableValueTarget):
            row = self.page.get_by_role("row").filter(
                has=self.page.get_by_role(
                    "rowheader",
                    name=target.row_label,
                    exact=True,
                )
            )

            self._require_one(
                row,
                target_kind=target.kind,
                component="table_row",
            )

            locator = row.get_by_role("cell")
            component = "value_cell"

        else:
            raise TypeError("Unsupported target type.")

        self._require_one(
            locator,
            target_kind=target.kind,
            component=component,
        )

        self._require_visible(
            locator,
            target_kind=target.kind,
            component=component,
        )

        return locator

    def execute(
        self,
        action: Action,
        inputs: Mapping[str, str],
        outputs: dict[str, str],
        *,
        step_number: int | None = None,
    ) -> None:
        """Perform one action with optional replay-step diagnostics."""

        self.control.require_automation()

        self._step_number = step_number
        self._action_kind = action.kind

        try:
            self.policy.check_url(self.page.url)
            self.policy.check_action(action)

            if isinstance(action, FillAction):
                if action.input_name not in inputs:
                    raise ValueError(
                        f"Missing required input: {action.input_name}"
                    )

                value = inputs[action.input_name]

                if not isinstance(value, str):
                    raise TypeError(
                        f"Input must be a string: {action.input_name}"
                    )

                locator = self.resolve_target(action.target)
                locator.fill(value)

            elif isinstance(action, ClickAction):
                locator = self.resolve_target(action.target)
                locator.click()

            elif isinstance(action, ReadAction):
                if action.output_name in outputs:
                    raise ValueError(
                        f"Output already exists: {action.output_name}"
                    )

                locator = self.resolve_target(action.target)

                outputs[action.output_name] = (
                    locator.inner_text().strip()
                )

            else:
                raise TypeError("Unsupported action type.")

        finally:
            # Later checkpoint reads must not inherit a stale action.
            self._step_number = None
            self._action_kind = None
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

from automation.contracts import (
    ClickAction,
    RoleTarget,
    TableValueTarget,
)
from automation.executor import BrowserExecutor
from automation.network_guard import NetworkGuard
from automation.policy import Policy
from automation.replay import check_network
from automation.session_control import (
    OwnershipError,
    SessionControl,
)


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]

    policy = Policy.from_file(
        project_root / "config" / "policy.json"
    )

    control = SessionControl()
    member_id = "10002"

    origin = policy.config.allowed_origin.rstrip("/")
    review_url = (
        f"{origin}/members/{member_id}/accounts/savings"
    )

    policy.check_url(review_url)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)

        try:
            context = browser.new_context(
                service_workers="block",
                accept_downloads=False,
            )

            guard = NetworkGuard(policy, control)
            guard.install(context)

            page = context.new_page()
            page.set_default_timeout(5000)
            page.set_default_navigation_timeout(10000)

            executor = BrowserExecutor(page, policy, control)

            page.goto(review_url)
            check_network(guard)

            expect(
                page.get_by_role(
                    "heading",
                    name="Manual review required",
                    exact=True,
                )
            ).to_be_visible()

            # An automation-owned session cannot grant review permission.
            try:
                guard.allow_human_review(
                    page=page,
                    member_id=member_id,
                )
            except OwnershipError:
                print(
                    "PASS: Automation cannot open human review permission."
                )
            else:
                raise AssertionError(
                    "Review permission opened without human ownership."
                )

            control.begin_handoff(timeout_seconds=180)

            # Test an ordinary policy-approved action. Ownership must
            # reject it before the executor tries to find its target.
            try:
                executor.execute(
                    action=ClickAction(
                        target=RoleTarget(
                            role="button",
                            name="Search",
                        )
                    ),
                    inputs={},
                    outputs={},
                )
            except OwnershipError:
                print(
                    "PASS: Executor actions are blocked during handoff."
                )
            else:
                raise AssertionError(
                    "The executor acted during human ownership."
                )

            guard.allow_human_review(
                page=page,
                member_id=member_id,
            )

            print(
                "\nHUMAN CONTROL: In the opened Playwright browser, "
                "check the acknowledgement and click Confirm review."
            )
            print("Complete the review within 180 seconds.", flush=True)

            try:
                # Playwright remains active while waiting, so its
                # network routing callbacks can process your submission.
                expect(
                    page.get_by_role(
                        "heading",
                        name="Savings account",
                        exact=True,
                    )
                ).to_be_visible(timeout=180_000)

                check_network(guard)

                control.begin_resume_verification()
                guard.revoke_human_review()

                expect(page).to_have_url(review_url)

                expect(
                    executor.resolve_target(
                        TableValueTarget(row_label="Member ID")
                    )
                ).to_have_text(member_id)

                expect(
                    executor.resolve_target(
                        TableValueTarget(row_label="Available balance")
                    )
                ).to_have_text("987.65")

                check_network(guard)
                control.complete_resume()
                control.require_automation()

                print(
                    "PASS: Human review completed in the same browser."
                )
                print(
                    "PASS: Automation ownership restored after verification."
                )

            except Exception:
                control.stop(reason="execution_failed")
                raise

            finally:
                guard.revoke_human_review()

        finally:
            browser.close()


if __name__ == "__main__":
    main()
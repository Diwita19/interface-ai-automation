from collections.abc import Callable
from queue import Empty, Queue
from threading import Thread
from uuid import uuid4
from datetime import datetime, timezone

from playwright.sync_api import Page

from automation.network_guard import NetworkGuard
from automation.session_control import (
    HandoffExpired,
    SessionOwner,
)


class HandoffCancelled(RuntimeError):
    """The operator cancelled the handoff."""


# This script observes only the demo's review controls.
# It never fills the checkbox or initiates approval by itself.
CAPTURE_SCRIPT = """
(bindingName) => {
    const checkbox = document.querySelector(
        'input[type="checkbox"][name="reviewed"]'
    );
    const form = checkbox?.form;

    if (!checkbox || !form) {
        throw new Error("Expected review controls were not found.");
    }

    let pending = Promise.resolve();
    let submitting = false;

    checkbox.addEventListener("change", (event) => {
        if (!event.isTrusted) return;

        const kind = checkbox.checked
            ? "review_checked"
            : "review_unchecked";

        pending = pending.then(() => window[bindingName](kind));
    });

    form.addEventListener("submit", (event) => {
        event.preventDefault();

        if (!event.isTrusted || submitting) return;
        submitting = true;

        // Record the human's submission before navigation destroys
        // this document. Then forward that same form submission.
        pending = pending
            .then(() => window[bindingName]("review_submitted"))
            .then(() => HTMLFormElement.prototype.submit.call(form))
            .catch(() => {
                submitting = false;
                const message = document.createElement("p");
                message.textContent =
                    "Review recording failed. Cancel this run.";
                form.appendChild(message);
            });
    });
}
"""


def wait_for_human_review(
    *,
    page: Page,
    guard: NetworkGuard,
    member_id: str,
    step_number: int,
    verify_resume: Callable[[], None],
    timeout_seconds: int = 180,
) -> None:
    """Pause replay, capture review events, and verify before resuming."""

    control = guard.control
    review_url = page.url
    commands: Queue[str] = Queue()
    captured: list[str] = []
    binding_name = f"recordReview_{uuid4().hex}"

    def check_guard() -> None:
        if guard.blocked_requests or guard.transport_failures:
            raise RuntimeError(
                "A browser request failed during human review."
            )

    def record_event(source: dict, kind: object) -> None:
        control.require_human()

        if (
            source["page"] != page
            or source["frame"] != page.main_frame
            or page.url != review_url
        ):
            raise RuntimeError("Unexpected review event source.")

        if not isinstance(kind, str) or kind not in {
            "review_checked",
            "review_unchecked",
            "review_submitted",
        }:
            raise ValueError("Unsupported review event.")

        if len(captured) >= 30:
            raise RuntimeError("Too many review events.")

        captured.append(kind)

        control.events.append(
            {
                "event": "human_action",
                "action": kind,
                "step": str(step_number),
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    def read_command() -> None:
        # This thread only reads terminal input.
        # All Playwright operations remain on the main thread.
        while True:
            try:
                command = input(
                    "After approving in the browser, type resume "
                    "(or cancel): "
                ).strip().lower()
            except EOFError:
                commands.put("cancel")
                return

            if command in {"resume", "cancel"}:
                commands.put(command)
                return

            print("Enter resume or cancel.", flush=True)

    try:
        control.begin_handoff(timeout_seconds=timeout_seconds)

        # This handoff implements the known savings-review workflow.
        # Keep the goal generic: never include member IDs or page URLs.
        control.events.append(
            {
                "event": "intervention_requested",
                "capability_id": "get_savings_balance",
                "goal": "Retrieve the requested member's savings balance.",
                "step": str(step_number),
                "state": "manual_review_required",
                "owner": control.owner.value,
                "reason": "manual_review_required",
                "required_action": (
                    "Review the request, acknowledge it, and submit "
                    "in the browser; then enter resume or cancel."
                ),
                "resume_condition": (
                    "Captured acknowledgement and submission, followed "
                    "by successful page and member-identity verification."
                ),
                "timeout_seconds": str(timeout_seconds),
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            }
        )

        page.expose_binding(binding_name, record_event)
        page.evaluate(CAPTURE_SCRIPT, binding_name)

        guard.allow_human_review(
            page=page,
            member_id=member_id,
        )

        print(
            f"\nHUMAN CONTROL at replay step {step_number}.",
            flush=True,
        )
        print(
            "Complete the review in this browser, then return here.",
            flush=True,
        )

        Thread(target=read_command, daemon=True).start()

        while True:
            control.require_human()
            check_guard()

            if page.is_closed():
                raise RuntimeError("The review browser was closed.")

            try:
                command = commands.get_nowait()
            except Empty:
                # A short Playwright wait services browser callbacks.
                # This is command polling, not a page-readiness delay.
                page.wait_for_timeout(100)
                continue

            if command == "cancel":
                raise HandoffCancelled("The operator cancelled review.")

            control.events.append(
                {
                    "event": "human_command",
                    "action": "resume_requested",
                    "step": str(step_number),
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                }
            )

            control.begin_resume_verification()
            guard.revoke_human_review()

            # Require a checked acknowledgement followed by submission.
            if (
                len(captured) < 2
                or captured[-2:] != [
                    "review_checked",
                    "review_submitted",
                ]
            ):
                raise AssertionError(
                    "The expected human review actions were not captured."
                )

            # The caller verifies the artifact's expected checkpoint,
            # including the member identity shown in the UI.
            verify_resume()
            check_guard()

            control.complete_resume()

            print(
                "RESUMED: Expected page and member identity verified.",
                flush=True,
            )
            return

    except HandoffExpired:
        # require_human() already recorded the timeout transition.
        raise

    except HandoffCancelled:
        control.stop(reason="handoff_cancelled")
        raise

    except Exception:
        reason = (
            "resume_verification_failed"
            if control.owner == SessionOwner.STOPPED
            else "execution_failed"
        )
        control.stop(reason=reason)
        raise

    finally:
        guard.revoke_human_review()
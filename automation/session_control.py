from enum import Enum
from time import monotonic


class SessionOwner(str, Enum):
    AUTOMATION = "automation"
    HUMAN = "human"
    STOPPED = "stopped"


class OwnershipError(RuntimeError):
    """An operation was attempted by the wrong session owner."""


class HandoffExpired(RuntimeError):
    """The human handoff exceeded its time limit."""


class SessionControl:
    """Track browser ownership and record ownership transitions."""

    def __init__(self) -> None:
        self._owner = SessionOwner.AUTOMATION
        self._deadline: float | None = None
        self.events: list[dict[str, str]] = []
        self._resume_verification_pending = False

    @property
    def owner(self) -> SessionOwner:
        return self._owner

    def require_automation(self) -> None:
        """Reject browser actions while automation lacks ownership."""

        if self._owner != SessionOwner.AUTOMATION:
            raise OwnershipError(
                "Automation does not own the browser session."
            )

    def require_human(self) -> None:
        """Check human ownership and the handoff deadline."""

        if self._owner != SessionOwner.HUMAN:
            raise OwnershipError(
                "The browser session is not under human control."
            )

        if self._deadline is None:
            raise OwnershipError("The handoff has no deadline.")

        if monotonic() >= self._deadline:
            self.stop(reason="handoff_timeout")
            raise HandoffExpired("The human handoff expired.")

    def begin_handoff(self, *, timeout_seconds: int = 180) -> None:
        """Transfer ownership from automation to the human."""

        self.require_automation()

        if (
            type(timeout_seconds) is not int
            or not 1 <= timeout_seconds <= 600
        ):
            raise ValueError(
                "The handoff timeout must be 1–600 whole seconds."
            )

        self._deadline = monotonic() + timeout_seconds
        self._transition(
            SessionOwner.HUMAN,
            reason="manual_review_required",
        )

    def begin_resume_verification(self) -> None:
        """End human control before checking whether replay can resume."""

        self.require_human()

        self._deadline = None
        self._resume_verification_pending = True
        self._transition(
            SessionOwner.STOPPED,
            reason="resume_verification_started",
        )

    def complete_resume(self) -> None:
        """Restore automation ownership after successful verification."""

        if (
            self._owner != SessionOwner.STOPPED
            or not self._resume_verification_pending
        ):
            raise OwnershipError(
                "Resume verification has not been started."
            )

        self._resume_verification_pending = False

        self._transition(
            SessionOwner.AUTOMATION,
            reason="resume_verified",
        )

    def stop(self, *, reason: str) -> None:
        """Revoke ownership after cancellation, timeout, or failure."""

        allowed_reasons = {
            "handoff_timeout",
            "handoff_cancelled",
            "resume_verification_failed",
            "execution_failed",
        }

        if reason not in allowed_reasons:
            raise ValueError("Unsupported stop reason.")

        self._resume_verification_pending = False
        self._deadline = None
        self._transition(SessionOwner.STOPPED, reason=reason)

    def _transition(
        self,
        new_owner: SessionOwner,
        *,
        reason: str,
    ) -> None:
        previous_owner = self._owner
        self._owner = new_owner

        self.events.append(
            {
                "event": "ownership_changed",
                "from": previous_owner.value,
                "to": new_owner.value,
                "reason": reason,
            }
        )
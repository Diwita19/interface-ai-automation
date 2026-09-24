"""Value-free diagnostics for replay assertions."""

from contextlib import contextmanager
from typing import Iterator


CHECKS = {
    "checkpoint_url": (
        "URL matches the checkpoint.",
        "URL did not match the checkpoint.",
    ),
    "checkpoint_heading": (
        "Checkpoint heading is visible.",
        "Heading visibility assertion failed.",
    ),
    "checkpoint_identity": (
        "Displayed identity matches the runtime input.",
        "Displayed text did not match the runtime input.",
    ),
    "filled_value": (
        "Field contains the runtime input.",
        "Field value did not match the runtime input.",
    ),
    "output_fields": (
        "Extracted fields match the declared output fields.",
        "Extracted output field set differed.",
    ),
    "output_input": (
        "Output matches its referenced runtime input.",
        "Output differed from its runtime input.",
    ),
    "output_literal": (
        "Output matches its required literal.",
        "Output differed from its required literal.",
    ),
    "output_format": (
        "Output matches its declared format.",
        "Output did not match its declared format.",
    ),
    "output_page": (
        "Final page text matches the extracted output.",
        "Final page text did not match the extracted output.",
    ),
    "review_outcome_count": (
        "Exactly one supported outcome heading exists.",
        "Outcome heading count assertion failed.",
    ),
    "review_outcome_visibility": (
        "Supported outcome heading is visible.",
        "Outcome heading visibility assertion failed.",
    ),
}

PHASES = {
    "before_action",
    "after_action",
    "resume_verification",
    "final_checkpoint",
    "final_outputs",
    "action_verification",
    "review_detection",
}

SAFE_FIELDS = {
    "member_id",
    "account_type",
    "available_balance",
    "currency",
}


class VerificationError(AssertionError):
    """A verification failure described only by approved metadata."""

    def __init__(
        self,
        *,
        check: str,
        phase: str,
        step_number: int | None = None,
        field: str | None = None,
    ) -> None:
        expected, observed = CHECKS[check]

        if phase not in PHASES:
            raise ValueError("Unsupported verification phase.")

        self.details: dict[str, object] = {
            "check": check,
            "phase": phase,
            "step_number": step_number,
            "expected": expected,
            "observed": observed,
        }

        if field is not None:
            self.details["field"] = (
                field if field in SAFE_FIELDS else "[REDACTED]"
            )

        super().__init__("A replay verification check failed.")


@contextmanager
def verification_check(
    *,
    check: str,
    phase: str,
    step_number: int | None = None,
    field: str | None = None,
) -> Iterator[None]:
    """Keep assertion retries; replace raw assertion text on failure."""

    if check not in CHECKS or phase not in PHASES:
        raise ValueError(
            "Unsupported verification check or phase."
        )

    try:
        yield

    except AssertionError:
        raise VerificationError(
            check=check,
            phase=phase,
            step_number=step_number,
            field=field,
        ) from None
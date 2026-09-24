import json
import traceback
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from automation.model_errors import ModelRequestError

from playwright.sync_api import (
    Error as PlaywrightError,
    TimeoutError as PlaywrightTimeoutError,
)
from pydantic import ValidationError

from automation.executor import TargetResolutionError
from automation.handoff import HandoffCancelled
from automation.policy import PolicyViolation
from automation.session_control import HandoffExpired, OwnershipError
from automation.verification import VerificationError


def failure_result(error: Exception) -> dict[str, object]:
    """Convert an exception into a structured, value-free report."""

    if isinstance(error, TargetResolutionError):
        code = error.code
        message = error.safe_message

    elif isinstance(error, ModelRequestError):
        code = "model_provider_error"
        message = "The model API request failed. See provider diagnostics."

    elif isinstance(error, HandoffCancelled):
        code = "handoff_cancelled"
        message = "The operator cancelled the browser handoff."

    elif isinstance(error, HandoffExpired):
        code = "handoff_timeout"
        message = "The browser handoff exceeded its time limit."

    elif isinstance(error, OwnershipError):
        code = "ownership_violation"
        message = (
            "An operation was attempted without session ownership."
        )

    elif isinstance(error, ValidationError):
        code = "invalid_artifact"
        message = "The capability failed schema validation."

    elif isinstance(error, PolicyViolation):
        code = "policy_violation"
        message = "The operation was rejected by policy."

    elif isinstance(error, PlaywrightTimeoutError):
        code = "browser_timeout"
        message = "A browser operation exceeded its timeout."

    elif isinstance(error, PlaywrightError):
        code = "browser_error"
        message = "A browser operation failed."

    elif isinstance(error, AssertionError):
        # VerificationError inherits AssertionError, preserving this code.
        code = "verification_failed"
        message = (
            "A checkpoint, output rule, or test assertion failed."
        )

    elif isinstance(error, ValueError):
        code = "invalid_input_or_configuration"
        message = "An input or configuration value was invalid."

    elif isinstance(error, OSError):
        code = "io_error"
        message = (
            "A required file or operating-system operation failed."
        )

    else:
        code = "unexpected_error"
        message = "An unexpected execution error occurred."

    locations = []

    for frame in traceback.extract_tb(error.__traceback__):
        path = Path(frame.filename)

        if path.parent.name == "automation":
            locations.append(
                {
                    "file": path.name,
                    "function": frame.name,
                    "line": frame.lineno,
                }
            )

    error_details: dict[str, object] = {
        "code": code,
        "type": type(error).__name__,
        "message": message,
        "locations": locations,
    }

    if isinstance(error, TargetResolutionError):
        error_details["target_resolution"] = dict(error.details)

    if isinstance(error, VerificationError):
        error_details["verification"] = dict(error.details)

    if isinstance(error, ModelRequestError):
        error_details["provider"] = dict(error.details)

    return {
        "status": "failed",
        "mode": "deterministic_replay",
        "outputs": {},
        "error": error_details,
    }


def save_run_report(
    result: dict[str, object],
    directory: Path,
) -> Path:
    """Save a run report with extracted output values redacted."""

    run_id = uuid4().hex

    # Copy the result so console output remains unchanged.
    report = dict(result)

    outputs = result.get("outputs", {})

    if isinstance(outputs, dict):
        report["outputs"] = {
            name: "[REDACTED]"
            for name in outputs
        }

    report["report_version"] = 1
    report["run_id"] = run_id
    report["recorded_at"] = datetime.now(
        timezone.utc
    ).isoformat()
    report["output_values_redacted"] = True

    directory.mkdir(parents=True, exist_ok=True)

    report_path = directory / f"replay-{run_id}.json"

    with report_path.open(
        "x",
        encoding="utf-8",
    ) as report_file:
        json.dump(
            report,
            report_file,
            indent=2,
            ensure_ascii=False,
        )
        report_file.write("\n")

    return report_path
"""Sanitized discovery telemetry, separate from the compilation record."""

import json
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from automation.contracts import ClickAction, FillAction, ReadAction


ROW_LABELS = {
    "member_id": "Member ID",
    "account_type": "Account type",
    "available_balance": "Available balance",
    "currency": "Currency",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_model_name(value: str) -> str:
    """Retain a conventional Gemini model identifier."""

    if re.fullmatch(r"gemini-[a-z0-9.-]{1,80}", value):
        return value

    return "[REDACTED]"


def safe_page_path(path: str) -> str:
    """Return known templates without preserving concrete member IDs."""

    if path in {"/", "/search"}:
        return path

    if re.fullmatch(r"/members/[0-9]{5}", path):
        return "/members/{member_id}"

    if re.fullmatch(r"/members/[0-9]{5}/accounts/savings", path):
        return "/members/{member_id}/accounts/savings"

    return "[REDACTED]"


def safe_action(action) -> dict[str, object]:
    """Copy only fixed demo labels and field names."""

    if isinstance(action, FillAction):
        known = action.target.name == "Member ID"

        return {
            "kind": "fill",
            "target": {
                "kind": "label",
                "name": "Member ID" if known else "[REDACTED]",
            },
            "input_name": (
                "member_id"
                if action.input_name == "member_id"
                else "[REDACTED]"
            ),
            "purpose": "Enter the runtime member ID in the search field.",
        }

    if isinstance(action, ClickAction):
        purposes = {
            ("button", "Search"): "Submit the member search.",
            ("link", "Open member"): (
                "Open the member returned by the search."
            ),
            ("link", "View savings"): (
                "Open the member's savings account."
            ),
        }

        key = (action.target.role, action.target.name)

        return {
            "kind": "click",
            "target": {
                "kind": "role",
                "role": action.target.role,
                "name": key[1] if key in purposes else "[REDACTED]",
            },
            "purpose": purposes.get(
                key,
                "Activate a proposed control, subject to policy.",
            ),
        }

    if isinstance(action, ReadAction):
        label = action.target.row_label

        return {
            "kind": "read",
            "target": {
                "kind": "table_value",
                "row_label": (
                    label
                    if label in ROW_LABELS.values()
                    else "[REDACTED]"
                ),
            },
            "output_name": (
                action.output_name
                if action.output_name in ROW_LABELS
                else "[REDACTED]"
            ),
            "purpose": (
                "Read a declared account field from the visible table."
            ),
        }

    raise TypeError("Unsupported discovery action.")


class DiscoveryLog:
    """Keep stage history when a later model call or UI action fails."""

    def __init__(self) -> None:
        self.run_id = uuid4().hex
        self.started_at = utc_now()
        self.started = perf_counter()
        self.model = "not_configured"
        self.events: list[dict[str, object]] = []
        self.completed_steps = 0
        self.failure_context: dict[str, object] | None = None

    @contextmanager
    def stage(
        self,
        phase: str,
        *,
        step: int | None = None,
    ):
        # Callers supply fixed phase names and integer step numbers.
        details: dict[str, object] = {"phase": phase}

        if step is not None:
            details["step"] = step

        self.events.append(
            {
                **details,
                "event": "stage_started",
                "recorded_at": utc_now(),
            }
        )

        started = perf_counter()

        try:
            yield

        except Exception:
            self.failure_context = dict(details)

            self.events.append(
                {
                    **details,
                    "event": "stage_failed",
                    "recorded_at": utc_now(),
                    "elapsed_seconds": round(
                        perf_counter() - started,
                        3,
                    ),
                }
            )

            raise

        else:
            self.events.append(
                {
                    **details,
                    "event": "stage_completed",
                    "recorded_at": utc_now(),
                    "elapsed_seconds": round(
                        perf_counter() - started,
                        3,
                    ),
                }
            )

    def observed(self, step: int, path: str) -> None:
        self.events.append(
            {
                "event": "page_observed",
                "step": step,
                "page_path_template": safe_page_path(path),
                "recorded_at": utc_now(),
            }
        )

    def proposed(self, step: int, action) -> None:
        self.events.append(
            {
                "event": "action_proposed",
                "step": step,
                "action": safe_action(action),
                "purpose_source": (
                    "static action-purpose description; "
                    "not model reasoning"
                ),
                "recorded_at": utc_now(),
            }
        )

    def save(
        self,
        result: dict[str, object],
        directory: Path,
    ) -> Path:
        payload = {
            "evidence_version": 1,
            "record_type": "sanitized_discovery_log",
            "run_id": self.run_id,
            "status": result["status"],
            "model": self.model,
            "started_at": self.started_at,
            "recorded_at": utc_now(),
            "elapsed_seconds": round(
                perf_counter() - self.started,
                3,
            ),
            "steps_executed": self.completed_steps,
            "failure_context": self.failure_context,
            "events": self.events,
            "outputs": {
                name: "[REDACTED]"
                for name in result.get("outputs", {})
                if name in ROW_LABELS
            },
            "redaction_policy": (
                "discovery_fixed_labels_and_templates_v1"
            ),
            "compilation_source": False,
            "limitations": [
                "Planning events record calls to the planner, "
                "not provider attestations.",
                "Action purposes are static descriptions, "
                "not recorded model reasoning.",
            ],
        }

        # These fields come from the existing sanitized reporters.
        for name in ("error", "failure_evidence"):
            if name in result:
                payload[name] = result[name]

        directory.mkdir(parents=True, exist_ok=True)

        path = directory / f"discovery-log-{self.run_id}.json"

        with path.open("x", encoding="utf-8") as stream:
            json.dump(
                payload,
                stream,
                indent=2,
                ensure_ascii=False,
            )
            stream.write("\n")

        return path
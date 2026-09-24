import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Literal

from pydantic import Field

from automation.capability import (
    Capability,
    CapabilityStep,
    PageCheckpoint,
    StringInput,
    StringOutput,
)
from automation.contracts import (
    Action,
    ReadAction,
    StrictModel,
    TableValueTarget,
)
from automation.discovery_logging import safe_action, safe_model_name


class RecordedStep(StrictModel):
    """One successfully executed action from discovery."""

    step: int = Field(ge=1)
    page_path_before: str
    action: Action


class DiscoveryRecord(StrictModel):
    """The saved discovery record accepted by this converter."""

    record_version: Literal[1]
    record_type: Literal["verified_discovery_run"]

    run_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    status: Literal["passed"]

    model: str
    goal: str
    input_names: list[str]

    history: list[RecordedStep] = Field(
        min_length=1,
        max_length=12,
    )

    outputs: dict[str, str]


def checkpoint_for(
    path: str,
    member_id: str,
) -> PageCheckpoint:
    """Convert a known observed path into a reusable checkpoint."""

    pages = {
        "/": (
            "/",
            "Member search",
        ),
        "/search": (
            "/search",
            "Search results",
        ),
        f"/members/{member_id}": (
            "/members/{member_id}",
            "Member details",
        ),
        f"/members/{member_id}/accounts/savings": (
            "/members/{member_id}/accounts/savings",
            "Savings account",
        ),
    }

    if path not in pages:
        raise ValueError(
            "The record contains an unsupported page path."
        )

    template, heading = pages[path]

    input_checks = {}

    # Member-specific pages must display the requested member ID.
    if template.startswith("/members/"):
        input_checks["member_id"] = TableValueTarget(
            row_label="Member ID"
        )

    return PageCheckpoint(
        path_template=template,
        heading=heading,
        input_checks=input_checks,
    )


def compile_record(
    record: DiscoveryRecord,
    source_hash: str,
) -> Capability:
    """Build a capability from a validated discovery record."""

    if record.input_names != ["member_id"]:
        raise ValueError(
            "This compiler expects one member_id input."
        )

    labels = {
        "member_id": "Member ID",
        "account_type": "Account type",
        "available_balance": "Available balance",
        "currency": "Currency",
    }

    if set(record.outputs) != set(labels):
        raise ValueError(
            "The recorded output fields are unexpected."
        )

    member_id = record.outputs["member_id"]

    if re.fullmatch(r"[0-9]{5}", member_id) is None:
        raise ValueError("The recorded member ID is invalid.")

    if (
        record.outputs["account_type"] != "Savings"
        or record.outputs["currency"] != "USD"
    ):
        raise ValueError(
            "The recorded account type or currency is unexpected."
        )

    if re.fullmatch(
        r"-?[0-9]+\.[0-9]{2}",
        record.outputs["available_balance"],
    ) is None:
        raise ValueError(
            "The recorded balance has an invalid format."
        )

    expected_numbers = list(
        range(1, len(record.history) + 1)
    )

    if [
        entry.step for entry in record.history
    ] != expected_numbers:
        raise ValueError(
            "The recorded step numbers are not consecutive."
        )

    if record.history[0].page_path_before != "/":
        raise ValueError(
            "Discovery must start at the search page."
        )

    final_path = (
        f"/members/{member_id}/accounts/savings"
    )

    last = record.history[-1]

    if (
        last.page_path_before != final_path
        or not isinstance(last.action, ReadAction)
    ):
        raise ValueError(
            "The record must finish with a read on the savings page."
        )

    checkpoints = [
        checkpoint_for(entry.page_path_before, member_id)
        for entry in record.history
    ]

    success = checkpoint_for(final_path, member_id)

    output_definitions = {
        name: StringOutput(
            source=TableValueTarget(row_label=label)
        )
        for name, label in labels.items()
    }

    # Store reusable rules rather than this run's extracted values.
    output_definitions["member_id"].equals_input = "member_id"
    output_definitions["account_type"].equals_literal = "Savings"
    output_definitions["currency"].equals_literal = "USD"

    output_definitions["available_balance"].pattern = (
        r"-?[0-9]+\.[0-9]{2}"
    )

    steps = []

    for index, entry in enumerate(record.history):
        # The next observation supplies this action's resulting state.
        if index + 1 < len(checkpoints):
            after = checkpoints[index + 1]
        else:
            after = success

        steps.append(
            CapabilityStep(
                before=checkpoints[index],
                action=entry.action,
                after=after,
            )
        )

    return Capability(
        capability_id="get_savings_balance",
        capability_version=1,
        source_run_id=record.run_id,
        source_record_sha256=source_hash,
        inputs={
            "member_id": StringInput(
                pattern=r"[0-9]{5}"
            )
        },
        outputs=output_definitions,
        steps=steps,
        success=success,
    )


def build_discovery_evidence(
    *,
    record: DiscoveryRecord,
    capability: Capability,
    source_hash: str,
) -> dict[str, object]:
    """Create a sanitized derivative of a verified discovery record."""

    action_reasons = {
        "fill": "Supply a runtime input through the observed field.",
        "click": "Navigate using an observed control.",
        "read": "Collect a requested output from the observed page.",
    }

    history = []

    for recorded_step, compiled_step in zip(
        record.history,
        capability.steps,
        strict=True,
    ):
        action = recorded_step.action

        if action.kind not in action_reasons:
            raise ValueError("Unsupported evidence action kind.")

        target_kind = action.target.kind

        if target_kind not in {"label", "role", "table_value"}:
            raise ValueError("Unsupported evidence target kind.")

        # Preserve fixed demo labels; redact unknown target names.
        history.append(
            {
                "step": recorded_step.step,
                "page_path_template_before": (
                    compiled_step.before.path_template
                ),
                "action": safe_action(action),
                "decision_context": action_reasons[action.kind],
                "decision_context_source": (
                    "static action description; not model reasoning"
                ),
                "execution_status": "completed",
            }
        )

    return {
        "evidence_version": 2,
        "record_type": "sanitized_discovery_evidence",
        "source_run_id": record.run_id,
        "source_record_sha256": source_hash,
        "source_record_status": record.status,
        "model": safe_model_name(record.model),
        "capability_id": capability.capability_id,
        "capability_version": capability.capability_version,
        "goal": (
            "Retrieve the requested member's savings account balance."
        ),
        "input_names": ["member_id"],
        "steps_executed": len(history),
        "history": history,
        "outputs": {
            name: "[REDACTED]"
            for name in sorted(capability.outputs)
        },
        "redaction_policy": (
            "discovery_fixed_labels_and_templates_v1"
        ),
        "compilation_source": False,
        "limitations": [
            "This is a sanitized derivative of the source record.",
            "The source hash identifies the original bytes; it does not "
            "independently prove that a browser or model run occurred.",
            "Decision context describes action purpose and is not "
            "a recorded model explanation.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Convert a successful savings discovery record "
            "into a typed capability."
        )
    )

    parser.add_argument(
        "--record",
        type=Path,
        required=True,
        help="Path to the original discovery JSON.",
    )

    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path for the new capability JSON.",
    )

    parser.add_argument(
        "--evidence-output",
        type=Path,
        help="Optional path for sanitized discovery evidence.",
    )

    args = parser.parse_args()

    # Check destinations before writing either artifact.
    destinations = [args.output]

    if args.evidence_output is not None:
        destinations.append(args.evidence_output)

    resolved_destinations = [
        path.resolve()
        for path in destinations
    ]

    if len(set(resolved_destinations)) != len(resolved_destinations):
        parser.error(
            "Capability and evidence destinations must differ."
        )

    if args.record.resolve() in resolved_destinations:
        parser.error("An output cannot replace the source record.")

    for path in destinations:
        if path.exists():
            parser.error(
                "An output destination already exists. "
                "Choose a new filename."
            )

    # Hash the exact original bytes for traceability.
    source_bytes = args.record.read_bytes()
    source_hash = hashlib.sha256(source_bytes).hexdigest()

    record = DiscoveryRecord.model_validate_json(source_bytes)

    capability = compile_record(
        record=record,
        source_hash=source_hash,
    )

    payload = capability.model_dump_json(
        indent=2,
        exclude_none=True,
    )

    restored = Capability.model_validate_json(payload)

    if restored != capability:
        raise AssertionError(
            "Capability JSON round-trip validation failed."
        )

    # Serialize evidence before writing either destination.
    evidence_payload = None

    if args.evidence_output is not None:
        evidence = build_discovery_evidence(
            record=record,
            capability=capability,
            source_hash=source_hash,
        )

        evidence_payload = json.dumps(
            evidence,
            indent=2,
            ensure_ascii=False,
        )

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with args.output.open(
        "x",
        encoding="utf-8",
    ) as output_file:
        output_file.write(payload + "\n")

    if (
        args.evidence_output is not None
        and evidence_payload is not None
    ):
        args.evidence_output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with args.evidence_output.open(
            "x",
            encoding="utf-8",
        ) as evidence_file:
            evidence_file.write(evidence_payload + "\n")

    result = {
        "status": "artifact_created",
        "capability_id": capability.capability_id,
        "capability_version": capability.capability_version,
        "steps": len(capability.steps),
        "capability_path": str(args.output.resolve()),
    }

    if args.evidence_output is not None:
        result["evidence_path"] = str(
            args.evidence_output.resolve()
        )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
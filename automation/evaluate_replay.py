import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


CASES = [
    {
        "name": "original_member",
        "arguments": [
            "--member-id", "10001",
            "--expected-balance", "1250.50",
        ],
        "status": "passed",
        "exit_code": 0,
        "steps": 8,
        "outputs": {
            "member_id": "10001",
            "account_type": "Savings",
            "available_balance": "1250.50",
            "currency": "USD",
        },
    },
    {
        "name": "different_member",
        "arguments": [
            "--member-id", "10002",
            "--expected-balance", "987.65",
        ],
        "status": "passed",
        "exit_code": 0,
        "steps": 8,
        "outputs": {
            "member_id": "10002",
            "account_type": "Savings",
            "available_balance": "987.65",
            "currency": "USD",
        },
    },
    {
        "name": "member_not_found",
        "arguments": ["--member-id", "99999"],
        "status": "not_found",
        "exit_code": 0,
        "steps": 2,
        "reason_code": "member_not_found",
        "outputs": {},
    },
    {
        "name": "incorrect_expected_balance",
        "arguments": [
            "--member-id", "10002",
            "--expected-balance", "1250.50",
        ],
        "status": "failed",
        "exit_code": 1,
        "error_code": "verification_failed",
        "outputs": {},
    },
    {
        "name": "invalid_member_format",
        "arguments": ["--member-id", "abc"],
        "status": "failed",
        "exit_code": 1,
        "error_code": "invalid_input_or_configuration",
        "outputs": {},
    },
]


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def evaluate_case(
    case: dict,
    project_root: Path,
    evidence_dir: Path,
) -> dict[str, str]:
    command = [
        sys.executable,
        "-m",
        "automation.replay_without_model",
        *case["arguments"],
        "--handoff-timeout",
        "5",
        "--report-dir",
        str(evidence_dir),
    ]

    completed = subprocess.run(
        command,
        cwd=project_root,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=90,
        check=False,
    )

    check(
        completed.returncode == case["exit_code"],
        "Unexpected process exit code.",
    )

    check(
        "Model isolation enabled:" in completed.stdout,
        "The model-isolation entry point did not announce startup.",
    )

    _, marker, result_text = completed.stdout.partition(
        "Replay result:"
    )

    check(bool(marker), "No structured replay result was printed.")

    # Read the JSON object while allowing the isolation PASS line
    # that can appear after it.
    result, _ = json.JSONDecoder().raw_decode(result_text.lstrip())

    check(
        result.get("status") == case["status"],
        "Unexpected replay status.",
    )

    check(
        result.get("outputs") == case["outputs"],
        "Unexpected replay outputs.",
    )

    if "steps" in case:
        check(
            result.get("steps_executed") == case["steps"],
            "Unexpected executed step count.",
        )

    if "reason_code" in case:
        check(
            result.get("reason_code") == case["reason_code"],
            "Unexpected business outcome.",
        )

    if "error_code" in case:
        check(
            result.get("error", {}).get("code") == case["error_code"],
            "Unexpected failure classification.",
        )

    if case["exit_code"] == 0:
        check(
            "PASS: Replay completed with model imports blocked"
            in completed.stdout,
            "The final model-isolation check did not complete.",
        )

    report_path = Path(result["report_path"])
    saved = json.loads(report_path.read_text(encoding="utf-8"))

    check(
        saved.get("status") == case["status"],
        "The saved report has the wrong status.",
    )

    expected_saved_outputs = {
        name: "[REDACTED]"
        for name in case["outputs"]
    }

    check(
        saved.get("outputs") == expected_saved_outputs,
        "Saved output values were not redacted as expected.",
    )

    # Ordinary replay records operation/readiness events.
    # These cases must not enter the human-handoff flow.
    events = result.get("events")

    check(
        isinstance(events, list),
        "Replay events must be a list.",
    )

    check(
        all(
            isinstance(event, dict)
            and isinstance(event.get("event"), str)
            for event in events
        ),
        "Replay events contain an invalid entry.",
    )

    handoff_event_types = {
        "ownership_changed",
        "intervention_requested",
        "human_action",
        "human_command",
    }

    check(
        not any(
            event["event"] in handoff_event_types
            for event in events
        ),
        "Ordinary replay unexpectedly recorded handoff events.",
    )

    check(
        saved.get("events") == events,
        "Saved events do not match the replay result.",
    )

    return {
        "case": case["name"],
        "evaluation": "passed",
        "report_file": report_path.name,
    }


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    evidence_dir = project_root / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    results = []

    for case in CASES:
        print(f"Evaluating: {case['name']}", flush=True)

        try:
            outcome = evaluate_case(
                case,
                project_root,
                evidence_dir,
            )

        except AssertionError as error:
            outcome = {
                "case": case["name"],
                "evaluation": "failed",
                "reason": str(error),
            }

        except Exception as error:
            # Avoid persisting raw subprocess output or exception text.
            outcome = {
                "case": case["name"],
                "evaluation": "failed",
                "reason": "The evaluation could not complete.",
                "error_type": type(error).__name__,
            }

        results.append(outcome)
        print(
            f"{outcome['evaluation'].upper()}: {case['name']}",
            flush=True,
        )

    passed = sum(
        item["evaluation"] == "passed"
        for item in results
    )

    summary = {
        "evaluation_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "passed": passed,
        "total": len(CASES),
        "cases": results,
    }

    summary_path = evidence_dir / "evaluation-replay.json"
    summary_path.write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"\nEvaluation: {passed}/{len(CASES)} passed.")
    print(f"Summary: {summary_path}")

    if passed != len(CASES):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
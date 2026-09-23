import argparse
import json
from pathlib import Path
from time import perf_counter

from playwright.sync_api import sync_playwright

from automation.capability import Capability
from automation.network_guard import NetworkGuard
from automation.policy import Policy
from automation.replay import replay
from automation.business_outcomes import MemberNotFound
from automation.run_reporting import failure_result, save_run_report
from automation.session_control import SessionControl
from automation.failure_evidence import capture_failure_evidence

def run_demo(
    *,
    capability_path: Path,
    member_id: str,
    expected_balance: str | None,
    events: list[dict[str, str]] | None = None,
    handoff_timeout_seconds: int = 180,
    evidence_dir: Path | None = None,
) -> dict[str, object]:
    if (
        type(handoff_timeout_seconds) is not int
        or not 1 <= handoff_timeout_seconds <= 600
    ):
        raise ValueError(
            "The handoff timeout must be 1–600 whole seconds."
        )
    project_root = Path(__file__).resolve().parents[1]

    if evidence_dir is None:
        evidence_dir = project_root / "runs"

    # Loading validates the artifact before opening a browser.
    capability = Capability.model_validate_json(
        capability_path.read_text(encoding="utf-8")
    )

    policy = Policy.from_file(
        project_root / "config" / "policy.json"
    )

    inputs = {"member_id": member_id}
    started = perf_counter()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=False,
            slow_mo=250,
        )

        page = None
        try:
            context = browser.new_context(
                service_workers="block",
                accept_downloads=False,
            )

            control = SessionControl()

            if events is not None:
                control.events = events

            guard = NetworkGuard(policy, control)
            guard.install(context)

            page = context.new_page()
            page.set_default_timeout(5000)
            page.set_default_navigation_timeout(10000)

            try:
                outputs = replay(
                    page=page,
                    capability=capability,
                    inputs=inputs,
                    policy=policy,
                    guard=guard,
                    handoff_timeout_seconds=handoff_timeout_seconds,
                )

            except MemberNotFound as outcome:
                # A fixture expecting a balance must still fail
                # if the application cannot find its member.
                if expected_balance is not None:
                    raise AssertionError(
                        "The test expected an account balance, "
                        "but the member was not found."
                    ) from None

                return {
                    "status": "not_found",
                    "mode": "deterministic_replay",
                    "reason_code": "member_not_found",
                    "capability_id": capability.capability_id,
                    "capability_version": capability.capability_version,
                    "steps_executed": outcome.steps_executed,
                    "outputs": {},
                    "elapsed_seconds": round(
                        perf_counter() - started,
                        2,
                    ),
                }

            # Optional fixture assertion for development.
            # This value is never passed to the replay engine.
            if expected_balance is not None:
                if outputs["available_balance"] != expected_balance:
                    raise AssertionError(
                        "The extracted balance does not match "
                        "the expected test balance."
                    )

            return {
                "status": "passed",
                "mode": "deterministic_replay",
                "capability_id": capability.capability_id,
                "capability_version": capability.capability_version,
                "steps_executed": len(capability.steps),
                "outputs": outputs,
                "elapsed_seconds": round(
                    perf_counter() - started,
                    2,
                ),
            }

        except Exception as error:
            # Build the error result while the browser is still open.
            result = failure_result(error)

            result["capability_id"] = capability.capability_id
            result["capability_version"] = capability.capability_version
            result["elapsed_seconds"] = round(
                perf_counter() - started,
                2,
            )

            result["failure_evidence"] = capture_failure_evidence(
                page=page,
                directory=evidence_dir,
            )

            return result

        finally:
            browser.close()


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]

    parser = argparse.ArgumentParser(
        description="Replay a saved browser capability without an LLM."
    )

    parser.add_argument(
        "--capability",
        type=Path,
        default=(
            project_root
            / "capabilities"
            / "get_savings_balance.v1.json"
        ),
        help="Path to the capability JSON.",
    )

    parser.add_argument(
        "--member-id",
        required=True,
        help="Synthetic member ID to retrieve.",
    )

    parser.add_argument(
        "--expected-balance",
        help="Optional expected balance for a development assertion.",
    )

    parser.add_argument(
        "--report-dir",
        type=Path,
        default=project_root / "runs",
        help="Directory for redacted JSON run reports.",
    )

    parser.add_argument(
        "--handoff-timeout",
        type=int,
        default=180,
        help="Maximum human-control time in seconds, from 1 to 600.",
    )

    args = parser.parse_args()
    events: list[dict[str, str]] = []

    try:
        result = run_demo(
            capability_path=args.capability,
            member_id=args.member_id,
            expected_balance=args.expected_balance,
            events=events,
            handoff_timeout_seconds=args.handoff_timeout,
            evidence_dir=args.report_dir,
        )

    except Exception as error:
        # This is the CLI boundary: convert an execution failure
        # into a report, then return a nonzero process exit code.
        result = failure_result(error)

    result["events"] = events
    report_failed = False

    try:
        report_path = save_run_report(
            result=result,
            directory=args.report_dir,
        )

        result["report_path"] = str(report_path.resolve())

    except OSError:
        # Preserve the execution outcome if evidence writing fails.
        report_failed = True

        result["report_error"] = {
            "code": "report_write_failed",
            "message": "The run report could not be saved.",
        }

    print("\nReplay result:")
    print(json.dumps(result, indent=2))

    if result["status"] == "failed" or report_failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
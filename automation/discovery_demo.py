import argparse
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from google import genai
from playwright.sync_api import Page, expect, sync_playwright

from automation.contracts import TableValueTarget
from automation.discovery_logging import DiscoveryLog, safe_model_name
from automation.executor import BrowserExecutor
from automation.failure_evidence import capture_failure_evidence
from automation.network_guard import NetworkGuard
from automation.observer import observe_page
from automation.planner import propose_action
from automation.policy import Policy
from automation.run_reporting import failure_result


BASE_URL = "http://127.0.0.1:8000"

DEFAULT_GOAL = "Retrieve the member's savings account balance."

# The executor and compiler currently support this workflow only.
SUPPORTED_GOALS = {
    "retrieve the member's savings account balance",
    "get the member's savings account balance",
    "find the member's savings account balance",
}

OUTPUT_REQUIREMENTS = (
    "Use the runtime member_id input to identify the member. "
    "Collect these output fields: member_id, account_type, "
    "available_balance, and currency."
)

MAX_STEPS = 12
MODEL_REQUEST_GAP_SECONDS = 15

REQUIRED_OUTPUTS = {
    "member_id",
    "account_type",
    "available_balance",
    "currency",
}


class DiscoveryRequestError(ValueError):
    """A rejected discovery input with a safe, predefined reason."""

    MESSAGES = {
        "invalid_member_id": (
            "The member ID must contain exactly five ASCII digits."
        ),
        "unsupported_goal": (
            "The goal is outside the supported savings-balance workflow."
        ),
        "invalid_entry_point": (
            "The entry point must be the policy-approved root page."
        ),
    }

    def __init__(self, code: str) -> None:
        self.code = code
        self.safe_message = self.MESSAGES[code]
        super().__init__(self.safe_message)


def validate_discovery_request(
    *,
    member_id: str,
    goal: str,
    entry_point: str,
    policy: Policy,
) -> tuple[str, str]:
    """Validate the supported workflow before browser or model use."""

    if (
        not isinstance(member_id, str)
        or re.fullmatch(r"[0-9]{5}", member_id) is None
    ):
        raise DiscoveryRequestError("invalid_member_id")

    if not isinstance(goal, str) or len(goal) > 300:
        raise DiscoveryRequestError("unsupported_goal")

    normalized_goal = " ".join(goal.strip().split())
    goal_key = normalized_goal.casefold().removesuffix(".")

    if goal_key not in SUPPORTED_GOALS:
        raise DiscoveryRequestError("unsupported_goal")

    origin = policy.config.allowed_origin.rstrip("/")

    if (
        not isinstance(entry_point, str)
        or entry_point not in {origin, origin + "/"}
    ):
        raise DiscoveryRequestError("invalid_entry_point")

    validated_entry_point = origin + "/"
    policy.check_url(validated_entry_point)

    planner_goal = (
        normalized_goal.rstrip(".")
        + ". "
        + OUTPUT_REQUIREMENTS
    )

    return planner_goal, validated_entry_point


def verify_result(
    *,
    page: Page,
    executor: BrowserExecutor,
    outputs: dict[str, str],
    member_id: str,
) -> None:
    """Verify the requested record against the current UI."""

    if set(outputs) != REQUIRED_OUTPUTS:
        raise AssertionError(
            "The output fields are incomplete or unexpected."
        )

    expected_identity = {
        "member_id": member_id,
        "account_type": "Savings",
        "currency": "USD",
    }

    for name, expected_value in expected_identity.items():
        if outputs[name] != expected_value:
            raise AssertionError(
                f"The extracted {name} does not match the requested record."
            )

    # Validate money without converting it to a binary float.
    if re.fullmatch(
        r"-?[0-9]+\.[0-9]{2}",
        outputs["available_balance"],
    ) is None:
        raise AssertionError("The balance has an unexpected format.")

    expect(
        page.get_by_role(
            "heading",
            name="Savings account",
            exact=True,
        )
    ).to_be_visible()

    row_labels = {
        "member_id": "Member ID",
        "account_type": "Account type",
        "available_balance": "Available balance",
        "currency": "Currency",
    }

    # Confirm the extracted values still match the final page.
    for output_name, row_label in row_labels.items():
        cell = executor.resolve_target(
            TableValueTarget(row_label=row_label)
        )

        expect(cell).to_have_text(outputs[output_name])


def discovery_failure(
    *,
    error: Exception,
    page: Page | None,
    directory: Path,
) -> dict[str, object]:
    """Describe failure without exposing raw exception text."""

    result = failure_result(error)
    result["mode"] = "llm_discovery_demo"

    if isinstance(error, DiscoveryRequestError):
        result["error"] = {
            "code": error.code,
            "type": "DiscoveryRequestError",
            "message": error.safe_message,
        }

    result["failure_evidence"] = capture_failure_evidence(
        page=page,
        directory=directory,
    )

    return result


def check_discovery_network(guard: NetworkGuard) -> None:
    """Stop if a guarded browser request was blocked or failed."""

    if guard.blocked_requests:
        raise RuntimeError(
            "The network guard blocked a browser request."
        )

    if guard.transport_failures:
        raise RuntimeError("A guarded browser request failed.")


def run_demo(
    member_id: str,
    *,
    goal: str = DEFAULT_GOAL,
    entry_point: str = BASE_URL,
    evidence_dir: Path | None = None,
) -> dict[str, object]:
    """Run discovery and save sanitized telemetry for either outcome."""

    if evidence_dir is None:
        evidence_dir = (
            Path(__file__).resolve().parents[1] / "evidence"
        )

    log = DiscoveryLog()

    try:
        result = _run_discovery(
            member_id,
            goal=goal,
            entry_point=entry_point,
            evidence_dir=evidence_dir,
            log=log,
        )

    except Exception as error:
        result = discovery_failure(
            error=error,
            page=None,
            directory=evidence_dir,
        )

    result["discovery_run_id"] = log.run_id
    result["steps_executed"] = log.completed_steps
    result["discovery_events"] = list(log.events)
    result["failure_context"] = log.failure_context

    try:
        path = log.save(result, evidence_dir)
        result["discovery_log_path"] = str(path.resolve())

    except OSError:
        result["telemetry_error"] = {
            "code": "discovery_log_write_failed",
            "message": "The sanitized discovery log could not be saved.",
        }

        # A successful workflow without its required log is incomplete.
        if result["status"] == "passed":
            result["status"] = "failed"
            result["outputs"] = {}
            result["error"] = result["telemetry_error"]

    return result


def _run_discovery(
    member_id: str,
    *,
    goal: str,
    entry_point: str,
    evidence_dir: Path,
    log: DiscoveryLog,
) -> dict[str, object]:
    project_root = Path(__file__).resolve().parents[1]

    with log.stage("validation"):
        policy = Policy.from_file(
            project_root / "config" / "policy.json"
        )

        planner_goal, validated_entry_point = (
            validate_discovery_request(
                member_id=member_id,
                goal=goal,
                entry_point=entry_point,
                policy=policy,
            )
        )

    with log.stage("configuration"):
        load_dotenv(project_root / ".env", override=False)

        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        model_name = os.getenv("GEMINI_MODEL", "").strip()

        if not api_key:
            raise ValueError("GEMINI_API_KEY is missing.")

        if not model_name:
            raise ValueError("GEMINI_MODEL is missing.")

    log.model = safe_model_name(model_name)

    print("Discovery model configured.")
    print("Supported workflow: savings balance retrieval.")

    inputs = {"member_id": member_id}
    outputs: dict[str, str] = {}

    with log.stage("model_client_setup"):
        client = genai.Client(api_key=api_key)

    try:
        with sync_playwright() as playwright:
            with log.stage("browser_launch"):
                browser = playwright.chromium.launch(
                    headless=False,
                    slow_mo=250,
                )

            page = None

            try:
                with log.stage("browser_setup"):
                    context = browser.new_context(
                        service_workers="block",
                        accept_downloads=False,
                    )

                    network_guard = NetworkGuard(policy)
                    network_guard.install(context)

                    page = context.new_page()
                    page.set_default_timeout(5000)
                    page.set_default_navigation_timeout(10000)

                with log.stage("navigation"):
                    page.goto(validated_entry_point)

                    expect(
                        page.get_by_role(
                            "heading",
                            name="Member search",
                            exact=True,
                        )
                    ).to_be_visible()

                    check_discovery_network(network_guard)

                executor = BrowserExecutor(
                    page,
                    policy,
                    network_guard.control,
                )

                history: list[dict[str, object]] = []

                for step_number in range(1, MAX_STEPS + 1):
                    print(f"\nDiscovery step {step_number}")

                    if step_number > 1:
                        print(
                            f"\nWaiting {MODEL_REQUEST_GAP_SECONDS} seconds "
                            "before the next model request..."
                        )
                        time.sleep(MODEL_REQUEST_GAP_SECONDS)

                    # Observe after the delay so the model sees fresh state.
                    with log.stage("observation", step=step_number):
                        check_discovery_network(network_guard)
                        policy.check_url(page.url)

                        observation = observe_page(page)

                        log.observed(
                            step_number,
                            observation.page_path,
                        )

                    # with log.stage("planning", step=step_number):
                    #     action = propose_action(
                    #         client=client,
                    #         model_name=model_name,
                    #         goal=planner_goal,
                    #         observation=observation,
                    #         input_names=list(inputs),
                    #         history=history,
                    #         outputs=outputs,
                    #     )

                    with log.stage("planning", step=step_number):
                        action = propose_action(
                            client=client,
                            model_name=model_name,
                            goal=planner_goal,
                            observation=observation,
                            input_names=list(inputs),
                            history=history,
                            outputs=outputs,
                            on_event=lambda event: log.events.append(
                                {
                                    **event,
                                    "step": step_number,
                                }
                            ),
                        )

                    log.proposed(step_number, action)

                    print(f"Validated model action: {action.kind}")

                    with log.stage("execution", step=step_number):
                        # Reject unexpected output names before execution.
                        if (
                            action.kind == "read"
                            and action.output_name not in REQUIRED_OUTPUTS
                        ):
                            raise ValueError(
                                "The planner requested an unexpected "
                                "output name."
                            )

                        executor.execute(
                            action=action,
                            inputs=inputs,
                            outputs=outputs,
                            step_number=step_number,
                        )

                        check_discovery_network(network_guard)
                        policy.check_url(page.url)

                    # Compilation history contains only completed actions.
                    history.append(
                        {
                            "step": step_number,
                            "page_path_before": observation.page_path,
                            "action": action.model_dump(),
                        }
                    )

                    log.completed_steps = len(history)

                    print(
                        "Output fields collected: "
                        f"{len(outputs)}/{len(REQUIRED_OUTPUTS)}"
                    )

                    if set(outputs) == REQUIRED_OUTPUTS:
                        with log.stage(
                            "verification",
                            step=step_number,
                        ):
                            verify_result(
                                page=page,
                                executor=executor,
                                outputs=outputs,
                                member_id=member_id,
                            )

                        # Keep the compilation record at version 1.
                        # Detailed telemetry is stored separately.
                        run_id = log.run_id

                        record = {
                            "record_version": 1,
                            "record_type": "verified_discovery_run",
                            "run_id": run_id,
                            "status": "passed",
                            "model": model_name,
                            "goal": planner_goal,
                            "input_names": list(inputs),
                            "history": history,
                            "outputs": outputs,
                        }

                        with log.stage(
                            "record_save",
                            step=step_number,
                        ):
                            runs_directory = project_root / "runs"

                            runs_directory.mkdir(
                                parents=True,
                                exist_ok=True,
                            )

                            record_path = (
                                runs_directory
                                / f"discovery-{run_id}.json"
                            )

                            with record_path.open(
                                "x",
                                encoding="utf-8",
                            ) as record_file:
                                json.dump(
                                    record,
                                    record_file,
                                    indent=2,
                                    ensure_ascii=False,
                                )
                                record_file.write("\n")

                        return {
                            "status": "passed",
                            "mode": "llm_discovery_demo",
                            "model": model_name,
                            "steps_executed": len(history),
                            "outputs": outputs,
                            "record_path": str(record_path),
                        }

                with log.stage("step_limit"):
                    raise RuntimeError(
                        "Discovery did not complete within "
                        f"{MAX_STEPS} steps."
                    )

            except Exception as error:
                # Capture evidence before the browser closes.
                result = discovery_failure(
                    error=error,
                    page=page,
                    directory=evidence_dir,
                )

                result["events"] = (
                    list(network_guard.control.events)
                    if page is not None
                    else []
                )

                return result

            finally:
                browser.close()

    finally:
        client.close()


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]

    parser = argparse.ArgumentParser(
        description=(
            "Discover the supported savings-balance workflow using Gemini."
        )
    )

    parser.add_argument(
        "--member-id",
        required=True,
        help="Synthetic member ID containing five ASCII digits.",
    )

    parser.add_argument(
        "--goal",
        default=DEFAULT_GOAL,
        help="Supported savings-account balance retrieval goal.",
    )

    parser.add_argument(
        "--entry-point",
        default=BASE_URL,
        help="The policy-approved application's root URL.",
    )

    parser.add_argument(
        "--report-dir",
        type=Path,
        default=project_root / "evidence",
        help=(
            "Directory for sanitized discovery logs, "
            "failure reports, and snapshots."
        ),
    )

    args = parser.parse_args()

    try:
        result = run_demo(
            member_id=args.member_id,
            goal=args.goal,
            entry_point=args.entry_point,
            evidence_dir=args.report_dir,
        )

    except Exception as error:
        result = discovery_failure(
            error=error,
            page=None,
            directory=args.report_dir,
        )

    public_result = dict(result)

    outputs = result.get("outputs", {})

    if isinstance(outputs, dict):
        public_result["outputs"] = {
            name: "[REDACTED]"
            for name in outputs
        }

    if result["status"] == "failed":
        report_id = uuid4().hex

        report = {
            **public_result,
            "report_version": 1,
            "report_id": report_id,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            args.report_dir.mkdir(
                parents=True,
                exist_ok=True,
            )

            report_path = (
                args.report_dir
                / f"discovery-failure-{report_id}.json"
            )

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

            public_result["report_path"] = str(
                report_path.resolve()
            )

        except OSError:
            public_result["report_error"] = {
                "code": "report_write_failed",
                "message": (
                    "The discovery failure report could not be saved."
                ),
            }

    print("\nDiscovery result:")
    print(json.dumps(public_result, indent=2))

    if result["status"] == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
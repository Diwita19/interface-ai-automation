import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from playwright.sync_api import expect, sync_playwright

from automation.executor import BrowserExecutor
from automation.network_guard import NetworkGuard
from automation.observer import observe_page
from automation.planner import propose_action
from automation.policy import Policy


BASE_URL = "http://127.0.0.1:8000"

GOAL = (
    "Find the savings account for the member identified by the "
    "runtime member_id input. Collect these output fields: "
    "member_id, account_type, available_balance, and currency."
)


def run_demo(member_id: str) -> dict[str, object]:
    project_root = Path(__file__).resolve().parents[1]

    load_dotenv(project_root / ".env", override=False)

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model_name = os.getenv("GEMINI_MODEL", "").strip()

    if not api_key:
        raise SystemExit("FAIL: GEMINI_API_KEY is missing.")

    if not model_name:
        raise SystemExit("FAIL: GEMINI_MODEL is missing.")

    policy = Policy.from_file(
        project_root / "config" / "policy.json"
    )
    policy.check_url(BASE_URL)

    inputs = {"member_id": member_id}
    outputs: dict[str, str] = {}

    client = genai.Client(api_key=api_key)

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=False,
                slow_mo=250,
            )

            try:
                context = browser.new_context(
                    service_workers="block",
                    accept_downloads=False,
                )

                network_guard = NetworkGuard(policy)
                network_guard.install(context)

                page = context.new_page()
                page.set_default_timeout(5000)
                page.set_default_navigation_timeout(10000)

                page.goto(BASE_URL)

                expect(
                    page.get_by_role(
                        "heading",
                        name="Member search",
                        exact=True,
                    )
                ).to_be_visible()

                # Observe the actual page currently open in the browser.
                observation = observe_page(page)

                print("\nCurrent page observation:")
                print(observation.aria_snapshot)

                print("\nAsking Gemini for one action...")

                action = propose_action(
                    client=client,
                    model_name=model_name,
                    goal=GOAL,
                    observation=observation,
                    input_names=list(inputs),
                )

                print("\nValidated model proposal:")
                print(action.model_dump_json(indent=2))

                # The executor applies our existing policy checks.
                executor = BrowserExecutor(page, policy)

                executor.execute(
                    action=action,
                    inputs=inputs,
                    outputs=outputs,
                )

                # Independent checkpoint for this initial-page test.
                # This assertion is not included in the model prompt.
                expect(
                    page.get_by_label(
                        "Member ID",
                        exact=True,
                    )
                ).to_have_value(member_id)

                return {
                    "status": "passed",
                    "mode": "llm_single_step_demo",
                    "action": action.model_dump(),
                    "checkpoint": "member_id_field_matches_input",
                }

            finally:
                browser.close()

    finally:
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ask Gemini to choose and execute one browser action."
    )

    parser.add_argument(
        "--member-id",
        required=True,
        help="Synthetic member ID for this test.",
    )

    args = parser.parse_args()

    result = run_demo(member_id=args.member_id)

    print("\nTest result:")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
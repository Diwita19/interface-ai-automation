import argparse
import json

from playwright.sync_api import expect, sync_playwright
from automation.network_guard import NetworkGuard
from automation.contracts import ACTION_ADAPTER, ClickAction
from automation.executor import BrowserExecutor
from automation.observer import observe_page
from pathlib import Path
from automation.policy import Policy

BASE_URL = "http://127.0.0.1:8000"


RAW_ACTIONS = [
    {
        "kind": "fill",
        "target": {
            "kind": "label",
            "name": "Member ID",
        },
        "input_name": "member_id",
    },
    {
        "kind": "click",
        "target": {
            "kind": "role",
            "role": "button",
            "name": "Search",
        },
    },
    {
        "kind": "click",
        "target": {
            "kind": "role",
            "role": "link",
            "name": "Open member",
        },
    },
    {
        "kind": "click",
        "target": {
            "kind": "role",
            "role": "link",
            "name": "View savings",
        },
    },
    {
        "kind": "read",
        "target": {
            "kind": "table_value",
            "row_label": "Member ID",
        },
        "output_name": "member_id",
    },
    {
        "kind": "read",
        "target": {
            "kind": "table_value",
            "row_label": "Account type",
        },
        "output_name": "account_type",
    },
    {
        "kind": "read",
        "target": {
            "kind": "table_value",
            "row_label": "Available balance",
        },
        "output_name": "available_balance",
    },
    {
        "kind": "read",
        "target": {
            "kind": "table_value",
            "row_label": "Currency",
        },
        "output_name": "currency",
    },
]

def run_demo(
    member_id: str,
    expected_balance: str,
) -> dict[str, str]:
    # Validate every action before opening the browser.
    actions = [
        ACTION_ADAPTER.validate_python(raw_action)
        for raw_action in RAW_ACTIONS
    ]

    inputs = {"member_id": member_id}
    outputs: dict[str, str] = {}

    # Load permissions and check the starting URL before opening the browser.
    project_root = Path(__file__).resolve().parents[1]

    policy = Policy.from_file(
        project_root / "config" / "policy.json"
    )

    policy.check_url(BASE_URL)

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

            initial_observation = observe_page(page)

            print("\nInitial page observation:")
            print(initial_observation.aria_snapshot)

            executor = BrowserExecutor(page, policy)

            for step_number, action in enumerate(actions, start=1):
                print(f"Step {step_number}: {action.kind}")

                executor.execute(
                    action=action,
                    inputs=inputs,
                    outputs=outputs,
                )

                # Inspect the page after each navigation-producing click.
                if isinstance(action, ClickAction):
                    observation = observe_page(page)

                    print(f"\nObservation after step {step_number}:")
                    print(f"Path: {observation.page_path}")
                    print(f"Title: {observation.title}")
                    print(observation.aria_snapshot)

            # This demonstration still supplies its checkpoint in Python.
            expect(
                page.get_by_role(
                    "heading",
                    name="Savings account",
                    exact=True,
                )
            ).to_be_visible()

            expected_outputs = {
                "member_id": member_id,
                "account_type": "Savings",
                "available_balance": expected_balance,
                "currency": "USD",
            }

            # Compare the values actually extracted from the page.
            if outputs != expected_outputs:
                raise AssertionError(
                    "Extracted outputs do not match the expected test record."
                )

            return outputs

        finally:
            browser.close()

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Exercise the typed browser action executor."
    )

    parser.add_argument("--member-id", required=True)
    parser.add_argument("--expected-balance", required=True)

    args = parser.parse_args()

    outputs = run_demo(
        member_id=args.member_id,
        expected_balance=args.expected_balance,
    )

    print(
        json.dumps(
            {
                "status": "passed",
                "mode": "hand_authored_executor_demo",
                "outputs": outputs,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
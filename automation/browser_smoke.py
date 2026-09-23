import argparse
import json

from playwright.sync_api import Locator, Page, expect, sync_playwright


BASE_URL = "http://127.0.0.1:8000"


def value_cell(page: Page, label: str) -> Locator:
    """Find the single value cell beside a specific table row heading."""

    row = page.get_by_role("row").filter(
        has=page.get_by_role(
            "rowheader",
            name=label,
            exact=True,
        )
    )

    # Ambiguous matches should fail rather than silently choosing one.
    expect(row).to_have_count(1)

    cell = row.get_by_role("cell")
    expect(cell).to_have_count(1)

    return cell

def run_smoke_test(
    member_id: str,
    expected_balance: str,
) -> dict[str, str]:
    """Exercise the known workflow using synthetic test data."""

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=False,
            slow_mo=250,
        )

        try:
            # A fresh context isolates this run from personal browser sessions.
            context = browser.new_context()
            page = context.new_page()

            page.set_default_timeout(5000)
            page.set_default_navigation_timeout(10000)

            # Step 1: Open the application and verify the starting page.
            page.goto(BASE_URL)

            expect(
                page.get_by_role(
                    "heading",
                    name="Member search",
                    exact=True,
                )
            ).to_be_visible()

            # Step 2: Search using the input's visible label.
            page.get_by_label(
                "Member ID",
                exact=True,
            ).fill(member_id)

            page.get_by_role(
                "button",
                name="Search",
                exact=True,
            ).click()

            expect(
                page.get_by_role(
                    "heading",
                    name="Search results",
                    exact=True,
                )
            ).to_be_visible()

            # Step 3: Open the member and verify their identity.
            page.get_by_role(
                "link",
                name="Open member",
                exact=True,
            ).click()

            expect(
                page.get_by_role(
                    "heading",
                    name="Member details",
                    exact=True,
                )
            ).to_be_visible()

            expect(value_cell(page, "Member ID")).to_have_text(member_id)

            # Step 4: Open savings.
            page.get_by_role(
                "link",
                name="View savings",
                exact=True,
            ).click()

            expect(
                page.get_by_role(
                    "heading",
                    name="Savings account",
                    exact=True,
                )
            ).to_be_visible()

            # Step 5: Verify identity, account type, currency and balance.
            expect(value_cell(page, "Member ID")).to_have_text(member_id)
            expect(value_cell(page, "Account type")).to_have_text("Savings")
            expect(value_cell(page, "Currency")).to_have_text("USD")
            expect(value_cell(page, "Available balance")).to_have_text(
                expected_balance
            )

            # Extract the values from the actual UI.
            return {
                "status": "passed",
                "mode": "scripted_smoke",
                "member_id": value_cell(page, "Member ID").inner_text().strip(),
                "account_type": value_cell(
                    page, "Account type"
                ).inner_text().strip(),
                "available_balance": value_cell(
                    page, "Available balance"
                ).inner_text().strip(),
                "currency": value_cell(page, "Currency").inner_text().strip(),
            }

        finally:
            # Close the browser even if a check fails.
            browser.close()

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a scripted browser check against the demo application."
    )

    parser.add_argument(
        "--member-id",
        required=True,
        help="Synthetic member ID to search for.",
    )

    parser.add_argument(
        "--expected-balance",
        required=True,
        help="Expected synthetic balance for this test.",
    )

    args = parser.parse_args()

    result = run_smoke_test(
        member_id=args.member_id,
        expected_balance=args.expected_balance,
    )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
from pathlib import Path

from playwright.sync_api import sync_playwright
from playwright.sync_api import Error as PlaywrightError

from automation.network_guard import NetworkGuard
from automation.policy import Policy


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]

    policy = Policy.from_file(
        project_root / "config" / "policy.json"
    )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)

        try:
            context = browser.new_context(
                service_workers="block",
                accept_downloads=False,
            )

            guard = NetworkGuard(policy)
            guard.install(context)

            page = context.new_page()
            page.set_default_navigation_timeout(10000)

            page.goto("http://127.0.0.1:8000")

            print("PASS: Browser can open the permitted application.")

            blocked_cases = [
                (
                    "different origin",
                    "http://127.0.0.1:9000/",
                    "Application origin is not permitted.",
                ),
                (
                    "unapproved route",
                    "http://127.0.0.1:8000/admin",
                    "Application route is not permitted.",
                ),
            ]

            for label, url, expected_reason in blocked_cases:
                previous_count = len(guard.blocked_requests)

                try:
                    page.goto(url)

                except PlaywrightError:
                    new_blocks = guard.blocked_requests[previous_count:]

                    expected_block_recorded = any(
                        event["navigation"]
                        and event["reason"] == expected_reason
                        for event in new_blocks
                    )

                    if not expected_block_recorded:
                        # Do not mistake an unrelated browser error for success.
                        raise

                    print(f"PASS: Browser navigation blocked for {label}.")

                else:
                    raise AssertionError(
                        f"Browser unexpectedly navigated to {label}."
                    )

        finally:
            browser.close()


if __name__ == "__main__":
    main()
from urllib.parse import urlsplit

from playwright.sync_api import Page, expect

from automation.contracts import Observation


def observe_page(page: Page) -> Observation:
    """Read the current page without performing UI actions."""

    # Appropriate for our current server-rendered application.
    page.wait_for_load_state(
        "domcontentloaded",
        timeout=5000,
    )

    body = page.locator("body")
    expect(body).to_be_visible(timeout=5000)

    snapshot = body.aria_snapshot(timeout=5000)

    return Observation(
        page_path=urlsplit(page.url).path,
        title=page.title(),
        aria_snapshot=snapshot,
    )
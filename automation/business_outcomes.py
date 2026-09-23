import re
from urllib.parse import urlencode

from playwright.sync_api import Page, expect

from automation.policy import Policy


class MemberNotFound(Exception):
    """The application explicitly reported no matching member."""

    def __init__(self, steps_executed: int) -> None:
        super().__init__("The requested member was not found.")
        self.steps_executed = steps_executed


def member_not_found_on_search(
    *,
    page: Page,
    member_id: str,
    policy: Policy,
) -> bool:
    """Recognize a negative result for this exact member search."""

    origin = policy.config.allowed_origin.rstrip("/")

    expected_url = (
        origin
        + "/search?"
        + urlencode({"member_id": member_id})
    )

    # Confirm that this response belongs to the requested search.
    expect(page).to_have_url(expected_url)
    policy.check_url(page.url)

    # Wait for exactly one supported terminal search state.
    search_state = page.get_by_role(
        "heading",
        name=re.compile(r"^(Search results|Member not found)$"),
    )

    expect(search_state).to_have_count(1)
    expect(search_state).to_be_visible()

    not_found_heading = page.get_by_role(
        "heading",
        name="Member not found",
        exact=True,
    )

    if not not_found_heading.is_visible():
        return False

    # Confirm the application's explicit negative-result message.
    expect(
        page.get_by_text(
            "No member matches that ID.",
            exact=True,
        )
    ).to_be_visible()

    # A negative result must not also offer a member to open.
    expect(
        page.get_by_role(
            "link",
            name="Open member",
            exact=True,
        )
    ).to_have_count(0)

    return True
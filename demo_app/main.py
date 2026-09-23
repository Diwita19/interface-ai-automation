# Escape text before inserting it into HTML.
from html import escape
import os

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from demo_app.review import approve_review, review_gate
from demo_app.ui import render_page

# Create the application with API documentation and schema endpoints disabled.
app = FastAPI(
    title="Demo Credit Union",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# Synthetic application data, keyed by member ID.
MEMBERS = {
    "10001": {
        "display_name": "Demo Member One",
        "savings_balance": "1250.50",
        "currency": "USD",
    },
    "10002": {
        "display_name": "Demo Member Two",
        "savings_balance": "987.65",
        "currency": "USD",
    },
}


# def render_page(title: str, body: str) -> str:
#     # Treat the title as plain text so HTML characters render safely.
#     safe_title = escape(title)

#     # Wrap each page's content in a shared HTML layout.
#     # The body contains HTML and must be constructed from trusted markup,
#     # with any user-provided values escaped before insertion.
#     return f"""
#     <!DOCTYPE html>
#     <html lang="en">
#         <head>
#             <meta charset="utf-8">
#             <title>{safe_title}</title>
#         </head>
#         <body>
#             <h1>Demo Credit Union</h1>
#             <p>Synthetic training application. No real customer data.</p>

#             <hr>

#             {body}
#         </body>
#     </html>
#     """


# Serve the search form as an HTML page.
@app.get("/", response_class=HTMLResponse)
def home() -> str:
    # Submitting the form sends the input as a query parameter:
    # /search?member_id=10001
    # The input's "name" matches the search_member function's parameter.
    body = """
    <h2>Member search</h2>

    <form action="/search" method="get">
        <label for="member-id">Member ID</label>

        <input
            id="member-id"
            name="member_id"
            type="text"
            required
        >

        <button type="submit">Search</button>
    </form>
    """

    return render_page("Member search", body)


# Read member_id from the URL query string; default to empty if omitted.
@app.get("/search", response_class=HTMLResponse)
def search_member(member_id: str = "") -> str:
    # Validate on the server, since browser validation can be bypassed.
    # Require exactly five ASCII digits (0–9); isdigit() alone also
    # accepts some non-ASCII digit characters.
    valid_format = (
        len(member_id) == 5
        and member_id.isascii()
        and member_id.isdigit()
    )

    if not valid_format:
        # Reject IDs that do not meet the required format.
        body = """
        <h2>Invalid member ID</h2>
        <p>Enter exactly five digits.</p>
        """

    elif member_id not in MEMBERS:
        # The format is valid, but the ID is absent from the demo records.
        body = """
        <h2>Member not found</h2>
        <p>No member matches that ID.</p>
        """

    else:
        # Escape the value before displaying it in HTML.
        safe_member_id = escape(member_id)

        body = f"""
        <h2>Search results</h2>

        <table>
            <thead>
                <tr>
                    <th>Member ID</th>
                    <th>Action</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>{safe_member_id}</td>
                    <td>
                        <a href="/members/{safe_member_id}">
                            Open member
                        </a>
                    </td>
                </tr>
            </tbody>
        </table>
        """

    # Include a return link for every search outcome.
    body += '<p><a href="/">Back to search</a></p>'

    return render_page("Search result", body)

@app.get("/members/{member_id}", response_class=HTMLResponse)
def member_details(member_id: str) -> str:
    # A user can open this URL directly, so check existence again.
    member = MEMBERS.get(member_id)

    if member is None:
        return render_page(
            "Member not found",
            """
            <h2>Member not found</h2>
            <p>No member matches that ID.</p>
            <p><a href="/">Back to search</a></p>
            """,
        )

    safe_member_id = escape(member_id)
    safe_name = escape(member["display_name"])

    ui_variant = os.getenv("DEMO_UI_VARIANT", "normal")

    if ui_variant not in {
        "normal",
        "renamed_link",
        "duplicate_link",
        "delayed_link",
        "late_link",
    }:
        raise ValueError("Unsupported demo UI variant.")

    savings_label = (
        "Open savings"
        if ui_variant == "renamed_link"
        else "View savings"
    )

    savings_links = f"""
    <p>
        <a href="/members/{safe_member_id}/accounts/savings">
            {escape(savings_label)}
        </a>
    </p>
    """

    if ui_variant == "duplicate_link":
        savings_links += f"""
        <p>
            <a href="/members/{safe_member_id}/accounts/savings">
                View savings
            </a>
        </p>
        """

    if ui_variant in {"delayed_link", "late_link"}:
        delay_ms = (
            2000
            if ui_variant == "delayed_link"
            else 15000
        )

        # Template contents are initially outside the rendered page.
        # JavaScript inserts the existing link after the fixture delay.
        savings_links = f"""
        <template id="pending-savings-links">
            {savings_links}
        </template>

        <div id="savings-links"></div>

        <script>
            window.setTimeout(() => {{
                const template = document.getElementById(
                    "pending-savings-links"
                );

                const container = document.getElementById(
                    "savings-links"
                );

                container.appendChild(
                    template.content.cloneNode(true)
                );

                template.remove();
            }}, {delay_ms});
        </script>
        """

    body = f"""
    <h2>Member details</h2>

    <table>
        <tbody>
            <tr>
                <th scope="row">Member ID</th>
                <td>{safe_member_id}</td>
            </tr>
            <tr>
                <th scope="row">Name</th>
                <td>{safe_name}</td>
            </tr>
        </tbody>
    </table>

    <h3>Accounts</h3>

    {savings_links}

    <p><a href="/">Back to search</a></p>
    """

    return render_page("Member details", body)

@app.get(
    "/members/{member_id}/accounts/savings",
    response_class=HTMLResponse,
)
def savings_account(
    member_id: str,
    request: Request,
) -> HTMLResponse:
    member = MEMBERS.get(member_id)

    if member is None:
        return HTMLResponse(
            content=render_page(
                "Member not found",
                """
                <h2>Member not found</h2>
                <p>No member matches that ID.</p>
                <p><a href="/">Back to search</a></p>
                """,
            ),
            status_code=404,
        )

    # print(
    #     "REVIEW DEBUG:",
    #     "file =", __file__,
    #     "enabled =", review_gate.__globals__["review_enabled"](),
    #     flush=True,
    # )

    gate = review_gate(request, member_id)

    if gate is not None:
        return gate

    safe_member_id = escape(member_id)
    safe_balance = escape(member["savings_balance"])
    safe_currency = escape(member["currency"])

    body = f"""
    <h2>Savings account</h2>

    <table>
        <tbody>
            <tr>
                <th scope="row">Member ID</th>
                <td>{safe_member_id}</td>
            </tr>
            <tr>
                <th scope="row">Account type</th>
                <td>Savings</td>
            </tr>
            <tr>
                <th scope="row">Available balance</th>
                <td>{safe_balance}</td>
            </tr>
            <tr>
                <th scope="row">Currency</th>
                <td>{safe_currency}</td>
            </tr>
        </tbody>
    </table>

    <p>
        <a href="/members/{safe_member_id}">
            Back to member
        </a>
    </p>

    <p><a href="/">Back to search</a></p>
    """

    return HTMLResponse(
        content=render_page("Savings account", body),
        headers={"Cache-Control": "no-store"},
    )

@app.post(
    "/members/{member_id}/accounts/savings",
    response_class=HTMLResponse,
)
async def confirm_savings_review(
    member_id: str,
    request: Request,
) -> HTMLResponse:
    if member_id not in MEMBERS:
        return HTMLResponse(
            content=render_page(
                "Member not found",
                "<h2>Member not found</h2>",
            ),
            status_code=404,
        )

    approved = await approve_review(request, member_id)

    if not approved:
        return HTMLResponse(
            content=render_page(
                "Review rejected",
                """
                <h2>Review rejected</h2>
                <p>
                    The review session expired or the form was invalid.
                    Open the savings page again to start a new review.
                </p>
                <p><a href="/">Back to search</a></p>
                """,
            ),
            status_code=403,
        )

    # Render the account in the same browser session.
    # No redirect is needed.
    return savings_account(
        member_id=member_id,
        request=request,
    )
import os
import secrets
from dataclasses import dataclass
from html import escape
from time import monotonic
from urllib.parse import parse_qs
from demo_app.ui import render_page
from fastapi import Request
from fastapi.responses import HTMLResponse


COOKIE_NAME = "demo_review_session"
SESSION_SECONDS = 600
EXPECTED_ORIGIN = "http://127.0.0.1:8000"


@dataclass
class ReviewSession:
    member_id: str
    csrf_token: str
    expires_at: float
    approved: bool = False


# In-memory state for this single-process synthetic demo.
SESSIONS: dict[str, ReviewSession] = {}


def review_enabled() -> bool:
    return os.getenv("DEMO_REQUIRE_REVIEW", "0") == "1"


def current_session(
    request: Request,
    member_id: str,
) -> ReviewSession | None:
    """Find an unexpired session belonging to this member."""

    now = monotonic()

    expired_tokens = [
        token
        for token, session in SESSIONS.items()
        if session.expires_at <= now
    ]

    for token in expired_tokens:
        del SESSIONS[token]

    token = request.cookies.get(COOKIE_NAME, "")
    session = SESSIONS.get(token)

    if session is None or session.member_id != member_id:
        return None

    return session


def review_gate(
    request: Request,
    member_id: str,
) -> HTMLResponse | None:
    """Return the review screen unless this session is approved."""

    if not review_enabled():
        return None

    session = current_session(request, member_id)

    if session is not None and session.approved:
        return None

    # Reuse an existing pending session when the page is refreshed.
    token = request.cookies.get(COOKIE_NAME, "")

    if session is None:
        token = secrets.token_urlsafe(32)

        session = ReviewSession(
            member_id=member_id,
            csrf_token=secrets.token_urlsafe(32),
            expires_at=monotonic() + SESSION_SECONDS,
        )

        SESSIONS[token] = session

    safe_member_id = escape(member_id)
    safe_csrf_token = escape(session.csrf_token, quote=True)

    body = f"""
    <h2>Manual review required</h2>

    <div class="review-note">
        <p>
            Review the request to view savings for member
            <strong>{safe_member_id}</strong>.
        </p>
        <p>
            This is a synthetic acknowledgement.
            It does not authorize a financial transaction.
        </p>
    </div>

    <form
        method="post"
        action="/members/{safe_member_id}/accounts/savings"
    >
        <input
            type="hidden"
            name="csrf_token"
            value="{safe_csrf_token}"
        >

        <label class="review-check">
            <input
                type="checkbox"
                name="reviewed"
                value="yes"
                required
            >
            <span>I have reviewed this request</span>
        </label>

        <button type="submit">Confirm review</button>
    </form>
    """

    response = HTMLResponse(
        content=render_page("Manual review required", body),
        headers={"Cache-Control": "no-store"},
    )

    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=SESSION_SECONDS,
        httponly=True,
        samesite="strict",
        secure=False,  # This demo runs on local HTTP.
        path="/",
    )

    return response

async def approve_review(
    request: Request,
    member_id: str,
) -> bool:
    """Validate the submitted form before approving this session."""

    if not review_enabled():
        return False

    session = current_session(request, member_id)

    if session is None:
        return False

    if request.headers.get("origin") != EXPECTED_ORIGIN:
        return False

    content_type = (
        request.headers.get("content-type", "")
        .split(";", 1)[0]
        .strip()
        .lower()
    )

    if content_type != "application/x-www-form-urlencoded":
        return False

    # Bound the body while reading it.
    body = bytearray()

    async for chunk in request.stream():
        body.extend(chunk)

        if len(body) > 2048:
            return False

    try:
        form = parse_qs(
            body.decode("utf-8"),
            keep_blank_values=True,
            strict_parsing=True,
            max_num_fields=2,
        )
    except (UnicodeDecodeError, ValueError):
        return False

    if set(form) != {"csrf_token", "reviewed"}:
        return False

    if form["reviewed"] != ["yes"]:
        return False

    submitted_tokens = form["csrf_token"]

    if len(submitted_tokens) != 1:
        return False

    if not secrets.compare_digest(
        submitted_tokens[0],
        session.csrf_token,
    ):
        return False

    session.approved = True
    return True
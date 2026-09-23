from pathlib import Path

from automation.contracts import ClickAction, RoleTarget
from automation.policy import Policy, PolicyViolation


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]

    policy = Policy.from_file(
        project_root / "config" / "policy.json"
    )

    # These checks do not visit any website.
    policy.check_url(
        "http://127.0.0.1:8000/search?member_id=10001"
    )
    print("PASS: Normal search URL is permitted.")

    blocked_urls = [
        ("external website", "https://example.com/"),
        ("different port", "http://127.0.0.1:9000/"),
        ("unapproved route", "http://127.0.0.1:8000/admin"),
        (
            "unapproved query",
            "http://127.0.0.1:8000/search?redirect=elsewhere",
        ),
    ]

    for label, url in blocked_urls:
        try:
            policy.check_url(url)
        except PolicyViolation:
            print(f"PASS: Blocked {label}.")
        else:
            raise AssertionError(f"Policy unexpectedly allowed {label}.")

    risky_action = ClickAction(
        target=RoleTarget(
            role="button",
            name="Transfer funds",
        )
    )

    try:
        policy.check_action(risky_action)
    except PolicyViolation:
        print("PASS: Unapproved transfer control is blocked.")
    else:
        raise AssertionError("Policy unexpectedly allowed the transfer control.")


if __name__ == "__main__":
    main()
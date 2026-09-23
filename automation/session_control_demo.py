import json

from automation.session_control import (
    OwnershipError,
    SessionControl,
    SessionOwner,
)


def main() -> None:
    control = SessionControl()

    control.require_automation()
    print("PASS: Automation initially owns the session.")

    control.begin_handoff(timeout_seconds=180)
    control.require_human()

    try:
        control.require_automation()
    except OwnershipError:
        print("PASS: Automation is blocked during human control.")
    else:
        raise AssertionError(
            "Automation was incorrectly permitted during handoff."
        )

    control.begin_resume_verification()

    if control.owner != SessionOwner.STOPPED:
        raise AssertionError(
            "The session must be stopped during resume verification."
        )

    try:
        control.require_automation()
    except OwnershipError:
        print("PASS: Automation stays blocked during verification.")
    else:
        raise AssertionError(
            "Automation resumed before verification completed."
        )

    # In the browser integration, checkpoint checks go here.
    control.complete_resume()
    control.require_automation()
    print("PASS: Ownership can return after verification.")

    cancelled = SessionControl()
    cancelled.begin_handoff()
    cancelled.stop(reason="handoff_cancelled")

    try:
        cancelled.complete_resume()
    except OwnershipError:
        print("PASS: A cancelled handoff cannot resume.")
    else:
        raise AssertionError("A cancelled handoff incorrectly resumed.")

    print("\nOwnership events:")
    print(json.dumps(control.events, indent=2))


if __name__ == "__main__":
    main()
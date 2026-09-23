from pydantic import ValidationError

from automation.contracts import ACTION_ADAPTER


def main() -> None:
    # This is hand-authored example data, not LLM output.
    raw_action = {
        "kind": "fill",
        "target": {
            "kind": "label",
            "name": "Member ID",
        },
        "input_name": "member_id",
    }

    # Validate the dictionary and construct a typed action.
    action = ACTION_ADAPTER.validate_python(raw_action)

    print("Validated action type:", type(action).__name__)

    # Convert the typed action into JSON.
    serialized = action.model_dump_json(indent=2)

    print("\nSerialized action:")
    print(serialized)

    # Reconstruct the typed action from that JSON.
    restored = ACTION_ADAPTER.validate_json(serialized)

    if restored != action:
        raise AssertionError("The action changed during serialization.")

    print("\nPASS: JSON round-trip preserved the action.")

    # An unsupported action must be rejected.
    unsupported_action = {
        "kind": "execute_python",
        "code": "pass",
    }

    try:
        ACTION_ADAPTER.validate_python(unsupported_action)
    except ValidationError:
        print("PASS: Unsupported action was rejected.")
    else:
        raise AssertionError("An unsupported action was accepted.")


if __name__ == "__main__":
    main()
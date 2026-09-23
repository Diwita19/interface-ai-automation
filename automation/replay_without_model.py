import os
import sys
from importlib.abc import MetaPathFinder


BLOCKED_MODULES = (
    "automation.planner",
    "google.genai",
)


def is_model_module(name: str) -> bool:
    return any(
        name == blocked or name.startswith(blocked + ".")
        for blocked in BLOCKED_MODULES
    )


class RejectModelImports(MetaPathFinder):
    """Fail immediately if replay tries to import a model dependency."""

    def find_spec(self, fullname, path=None, target=None):
        if is_model_module(fullname):
            raise ImportError(
                f"Model dependency forbidden during replay: {fullname}"
            )

        # Allow Python's normal import machinery to handle other modules.
        return None


def check_loaded_modules() -> None:
    """Also detect a blocked module already present in memory."""

    if any(is_model_module(name) for name in sys.modules):
        raise RuntimeError(
            "A model dependency was loaded during replay."
        )


def main() -> None:
    # These changes affect only this Python process.
    # They do not edit .env or your Windows environment settings.
    os.environ.pop("GEMINI_API_KEY", None)
    os.environ.pop("GOOGLE_API_KEY", None)

    check_loaded_modules()
    sys.meta_path.insert(0, RejectModelImports())

    print(
        "Model isolation enabled: planner and Gemini SDK imports blocked."
    )

    # Import replay only after the restriction is installed.
    from automation.replay_demo import main as replay_main

    replay_main()

    check_loaded_modules()

    print(
        "\nPASS: Replay completed with model imports blocked "
        "and Gemini environment credentials removed."
    )


if __name__ == "__main__":
    main()
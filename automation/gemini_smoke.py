import json
import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai


def main() -> None:
    # Locate the project folder from this script's location.
    project_root = Path(__file__).resolve().parents[1]

    # Load local settings without replacing existing environment variables.
    load_dotenv(project_root / ".env", override=False)

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model_name = os.getenv("GEMINI_MODEL", "").strip()

    # Catch missing settings before making a network request.
    if not api_key:
        raise SystemExit("FAIL: GEMINI_API_KEY is missing.")

    if not model_name:
        raise SystemExit("FAIL: GEMINI_MODEL is missing.")

    client = genai.Client(api_key=api_key)

    try:
        # This is a real model request with a harmless test prompt.
        response = client.interactions.create(
            model=model_name,
            input="Reply with the single word READY.",
            store=False,
        )

        reply = (response.output_text or "").strip()

        if not reply:
            raise SystemExit("FAIL: Gemini returned no text.")

        print(
            json.dumps(
                {
                    "status": "passed",
                    "mode": "llm_connection_test",
                    "model": model_name,
                    "reply": reply,
                },
                indent=2,
            )
        )

    finally:
        # Release the client's network resources even if the request fails.
        client.close()


if __name__ == "__main__":
    main()
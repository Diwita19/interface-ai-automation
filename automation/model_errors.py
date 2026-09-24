"""Provider error metadata without importing the Gemini SDK."""


class ModelRequestError(RuntimeError):
    """A model API failure with sanitized diagnostic fields."""

    def __init__(
        self,
        *,
        http_status: int | None,
        attempts: int,
        retryable: bool,
    ) -> None:
        self.details = {
            "provider": "gemini",
            "http_status": http_status,
            "attempts": attempts,
            "retryable_status": retryable,
            "retries_exhausted": retryable and attempts >= 3,
        }

        super().__init__("The model API request failed.")
import re
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from automation.contracts import (
    Action,
    ClickAction,
    FillAction,
    ReadAction,
    RoleTarget,
    StrictModel,
)


class PolicyViolation(Exception):
    """Raised when an operation is outside the configured permissions."""


class PolicyConfig(StrictModel):
    allowed_origin: str
    allowed_methods: list[str]
    allowed_path_patterns: list[str]
    allowed_query_keys: dict[str, list[str]]
    allowed_actions: list[str]
    allowed_fill_labels: list[str]
    allowed_clicks: list[RoleTarget]
    allowed_read_labels: list[str]

class Policy:
    def __init__(self, config: PolicyConfig) -> None:
        self.config = config

        origin = urlsplit(config.allowed_origin)

        self.allowed_origin = (
            origin.scheme,
            origin.hostname,
            origin.port,
        )

        # Compile trusted configuration once, rather than on every action.
        self.path_patterns = [
            re.compile(pattern)
            for pattern in config.allowed_path_patterns
        ]

    @classmethod
    def from_file(cls, path: Path) -> "Policy":
        config = PolicyConfig.model_validate_json(
            path.read_text(encoding="utf-8")
        )

        return cls(config)

    def check_url(self, url: str) -> None:
        # Reject ambiguous characters before parsing.
        if "\\" in url or any(
            character.isspace() or ord(character) < 32
            for character in url
        ):
            raise PolicyViolation("URL contains unsupported characters.")

        try:
            parsed = urlsplit(url)

            actual_origin = (
                parsed.scheme,
                parsed.hostname,
                parsed.port,
            )
        except ValueError:
            raise PolicyViolation("Malformed URL.") from None

        if parsed.username is not None or parsed.password is not None:
            raise PolicyViolation("Credentials in URLs are not permitted.")

        if actual_origin != self.allowed_origin:
            raise PolicyViolation("Application origin is not permitted.")

        if parsed.fragment:
            raise PolicyViolation("URL fragments are not supported.")

        path = parsed.path or "/"

        if not any(
            pattern.fullmatch(path)
            for pattern in self.path_patterns
        ):
            raise PolicyViolation("Application route is not permitted.")

        allowed_keys = self.config.allowed_query_keys.get(path, [])

        try:
            query_items = parse_qsl(
                parsed.query,
                keep_blank_values=True,
                strict_parsing=True,
                max_num_fields=10,
            )
        except ValueError:
            raise PolicyViolation("Malformed query parameters.") from None

        seen_keys: set[str] = set()

        for key, _value in query_items:
            if key not in allowed_keys:
                raise PolicyViolation("Query parameter is not permitted.")

            if key in seen_keys:
                raise PolicyViolation("Duplicate query parameters are not permitted.")

            seen_keys.add(key)

    def check_action(self, action: Action) -> None:
        if action.kind not in self.config.allowed_actions:
            raise PolicyViolation("Action type is not permitted.")

        if isinstance(action, FillAction):
            if action.target.name not in self.config.allowed_fill_labels:
                raise PolicyViolation("Input field is not permitted.")

        elif isinstance(action, ClickAction):
            if action.target not in self.config.allowed_clicks:
                raise PolicyViolation("Clickable control is not permitted.")

        elif isinstance(action, ReadAction):
            if action.target.row_label not in self.config.allowed_read_labels:
                raise PolicyViolation("Output field is not permitted.")

        else:
            raise PolicyViolation("Unsupported action.")
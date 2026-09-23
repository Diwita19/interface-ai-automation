from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class StrictModel(BaseModel):
    """Shared validation rules for our action contracts."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )


class LabelTarget(StrictModel):
    """Identify an input through its associated label."""

    kind: Literal["label"] = "label"
    name: str = Field(min_length=1)


class RoleTarget(StrictModel):
    """Identify a clickable control through its role and accessible name."""

    kind: Literal["role"] = "role"
    role: Literal["button", "link"]
    name: str = Field(min_length=1)


class TableValueTarget(StrictModel):
    """Identify a value through the heading of its table row."""

    kind: Literal["table_value"] = "table_value"
    row_label: str = Field(min_length=1)


class FillAction(StrictModel):
    """Fill a labeled field using a named runtime input."""

    kind: Literal["fill"] = "fill"
    target: LabelTarget
    input_name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")


class ClickAction(StrictModel):
    """Click a button or link."""

    kind: Literal["click"] = "click"
    target: RoleTarget


class ReadAction(StrictModel):
    """Read a table value into a named output."""

    kind: Literal["read"] = "read"
    target: TableValueTarget
    output_name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")


Action = Annotated[
    FillAction | ClickAction | ReadAction,
    Field(discriminator="kind"),
]


ACTION_ADAPTER = TypeAdapter(Action)

class Observation(StrictModel):
    """A bounded description of the current browser page."""

    page_path: str
    title: str
    aria_snapshot: str = Field(
        min_length=1,
        max_length=20_000,
    )
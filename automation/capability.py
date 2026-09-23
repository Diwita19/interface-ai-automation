from typing import Literal, Self

from pydantic import Field, model_validator

from automation.contracts import (
    Action,
    FillAction,
    ReadAction,
    StrictModel,
    TableValueTarget,
)


class StringInput(StrictModel):
    """A runtime string input and its required format."""

    value_type: Literal["string"] = "string"
    pattern: str = Field(min_length=1)


class StringOutput(StrictModel):
    """Where an output comes from and how to check its value."""

    value_type: Literal["string"] = "string"
    source: TableValueTarget

    equals_input: str | None = None
    equals_literal: str | None = None
    pattern: str | None = None


class PageCheckpoint(StrictModel):
    """UI conditions that must hold at a recorded boundary."""

    path_template: str = Field(min_length=1)
    heading: str = Field(min_length=1)

    # Map an input name to the table value that must match it.
    input_checks: dict[str, TableValueTarget] = Field(
        default_factory=dict
    )


class CapabilityStep(StrictModel):
    """An action surrounded by explicit UI checkpoints."""

    before: PageCheckpoint
    action: Action
    after: PageCheckpoint


class Capability(StrictModel):
    """A versioned workflow that can be executed without a model."""

    schema_version: Literal[1] = 1

    capability_id: str = Field(
        pattern=r"^[a-z][a-z0-9_]*$"
    )
    capability_version: int = Field(ge=1)

    source_run_id: str = Field(
        pattern=r"^[0-9a-f]{32}$"
    )
    source_record_sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$"
    )

    inputs: dict[str, StringInput]
    outputs: dict[str, StringOutput]

    steps: list[CapabilityStep] = Field(
        min_length=1,
        max_length=12,
    )
    success: PageCheckpoint

    @model_validator(mode="after")
    def check_references(self) -> Self:
        """Reject inconsistent input and output references."""

        written: set[str] = set()

        for step in self.steps:
            action = step.action

            if isinstance(action, FillAction):
                if action.input_name not in self.inputs:
                    raise ValueError(
                        "An action references an undeclared input."
                    )

            if isinstance(action, ReadAction):
                if action.output_name not in self.outputs:
                    raise ValueError(
                        "An action references an undeclared output."
                    )

                if action.output_name in written:
                    raise ValueError(
                        "An output is written more than once."
                    )

                if (
                    action.target
                    != self.outputs[action.output_name].source
                ):
                    raise ValueError(
                        "An output source differs from its read action."
                    )

                written.add(action.output_name)

        if written != set(self.outputs):
            raise ValueError(
                "Every declared output must have one read action."
            )

        for output in self.outputs.values():
            if (
                output.equals_input is not None
                and output.equals_input not in self.inputs
            ):
                raise ValueError(
                    "An output check references an undeclared input."
                )

            if (
                output.equals_input is not None
                and output.equals_literal is not None
            ):
                raise ValueError(
                    "An output cannot have two equality rules."
                )

        checkpoints = [self.success]

        for step in self.steps:
            checkpoints.extend([step.before, step.after])

        for checkpoint in checkpoints:
            if not set(checkpoint.input_checks).issubset(self.inputs):
                raise ValueError(
                    "A checkpoint references an undeclared input."
                )

        return self
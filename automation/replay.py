import re
from contextlib import contextmanager
from datetime import datetime, timezone
from string import Formatter
from time import perf_counter
from typing import Iterator
from urllib.parse import quote

from playwright.sync_api import Page, expect

from automation.business_outcomes import (
    MemberNotFound,
    member_not_found_on_search,
)
from automation.capability import Capability, PageCheckpoint
from automation.contracts import ClickAction, FillAction, ReadAction
from automation.executor import BrowserExecutor
from automation.handoff import wait_for_human_review
from automation.network_guard import NetworkGuard
from automation.policy import Policy
from automation.session_control import SessionControl
from automation.verification import (
    VerificationError,
    verification_check,
)


def render_path(
    template: str,
    inputs: dict[str, str],
) -> str:
    """Substitute simple input names into a path template."""

    parts = []

    for literal, name, format_spec, conversion in Formatter().parse(
        template
    ):
        parts.append(literal)

        if name is None:
            continue

        # Attribute access and formatting expressions are unsupported.
        if name not in inputs or format_spec or conversion:
            raise ValueError(
                "Unsupported path-template placeholder."
            )

        parts.append(quote(inputs[name], safe=""))

    path = "".join(parts)

    if (
        not path.startswith("/")
        or path.startswith("//")
        or "?" in path
        or "#" in path
    ):
        raise ValueError(
            "A checkpoint must contain an absolute URL path."
        )

    return path


def check_network(guard: NetworkGuard) -> None:
    """Stop if the browser guard recorded a problem."""

    if guard.blocked_requests:
        raise RuntimeError(
            "The network guard blocked a browser request."
        )

    if guard.transport_failures:
        raise RuntimeError(
            "A guarded browser request failed."
        )


def validate_replay(
    capability: Capability,
    inputs: dict[str, str],
    policy: Policy,
) -> None:
    """Check inputs, permissions, and templates before navigation."""

    if set(inputs) != set(capability.inputs):
        raise ValueError(
            "Runtime inputs do not match capability inputs."
        )

    for name, definition in capability.inputs.items():
        value = inputs[name]

        if not isinstance(value, str):
            raise ValueError(f"Input {name} must be a string.")

        if re.fullmatch(definition.pattern, value) is None:
            raise ValueError(
                f"Input {name} has an invalid format."
            )

    origin = policy.config.allowed_origin.rstrip("/")
    checkpoints = [capability.success]

    for index, step in enumerate(capability.steps):
        policy.check_action(step.action)

        if index > 0:
            previous = capability.steps[index - 1]

            if previous.after != step.before:
                raise ValueError(
                    "Adjacent step checkpoints do not match."
                )

        checkpoints.extend([step.before, step.after])

    for checkpoint in checkpoints:
        path = render_path(checkpoint.path_template, inputs)
        policy.check_url(origin + path)

        # Checkpoint reads obey the same permissions as action reads.
        for target in checkpoint.input_checks.values():
            policy.check_action(
                ReadAction(
                    target=target,
                    output_name="checkpoint",
                )
            )

    for name, definition in capability.outputs.items():
        policy.check_action(
            ReadAction(
                target=definition.source,
                output_name=name,
            )
        )

        if definition.pattern is not None:
            re.compile(definition.pattern)


def verify_checkpoint(
    *,
    page: Page,
    executor: BrowserExecutor,
    checkpoint: PageCheckpoint,
    inputs: dict[str, str],
    policy: Policy,
    phase: str = "final_checkpoint",
    step_number: int | None = None,
) -> None:
    """Verify the expected URL, heading, and displayed identity."""

    origin = policy.config.allowed_origin.rstrip("/")
    path = render_path(checkpoint.path_template, inputs)
    expected_url = origin + path

    # Query strings are checked separately by policy.
    url_pattern = re.compile(
        r"^" + re.escape(expected_url) + r"(?:\?[^#]*)?$"
    )

    with verification_check(
        check="checkpoint_url",
        phase=phase,
        step_number=step_number,
    ):
        expect(page).to_have_url(url_pattern)

    policy.check_url(page.url)

    with verification_check(
        check="checkpoint_heading",
        phase=phase,
        step_number=step_number,
    ):
        expect(
            page.get_by_role(
                "heading",
                name=checkpoint.heading,
                exact=True,
            )
        ).to_be_visible()

    for input_name, target in checkpoint.input_checks.items():
        cell = executor.resolve_target(target)

        with verification_check(
            check="checkpoint_identity",
            phase=phase,
            step_number=step_number,
            field=input_name,
        ):
            expect(cell).to_have_text(inputs[input_name])


def verify_outputs(
    *,
    capability: Capability,
    executor: BrowserExecutor,
    inputs: dict[str, str],
    outputs: dict[str, str],
) -> None:
    """Check extracted outputs against the artifact and final UI."""

    if set(outputs) != set(capability.outputs):
        raise VerificationError(
            check="output_fields",
            phase="final_outputs",
        )

    for name, definition in capability.outputs.items():
        value = outputs[name]

        if definition.equals_input is not None:
            if value != inputs[definition.equals_input]:
                raise VerificationError(
                    check="output_input",
                    phase="final_outputs",
                    field=name,
                )

        if definition.equals_literal is not None:
            if value != definition.equals_literal:
                raise VerificationError(
                    check="output_literal",
                    phase="final_outputs",
                    field=name,
                )

        if definition.pattern is not None:
            if re.fullmatch(definition.pattern, value) is None:
                raise VerificationError(
                    check="output_format",
                    phase="final_outputs",
                    field=name,
                )

        cell = executor.resolve_target(definition.source)

        with verification_check(
            check="output_page",
            phase="final_outputs",
            field=name,
        ):
            expect(cell).to_have_text(value)


@contextmanager
def record_replay_operation(
    *,
    control: SessionControl,
    operation: str,
    step_number: int | None = None,
    action_kind: str | None = None,
) -> Iterator[None]:
    """Record execution context without inputs or extracted values."""

    descriptions = {
        "validation": (
            "Validate artifact inputs and policy before navigation."
        ),
        "navigation": "Open the capability's initial page.",
        "step": (
            "Execute the saved action and verify its checkpoints."
        ),
        "final_verification": (
            "Verify the final checkpoint and output rules."
        ),
    }

    action_descriptions = {
        "fill": (
            "Fill the permitted field using a validated runtime input."
        ),
        "click": (
            "Activate the saved target and verify the resulting state."
        ),
        "read": (
            "Read the permitted field into the declared output."
        ),
    }

    context = {
        "operation": operation,
        "reason": descriptions[operation],
    }

    if step_number is not None:
        context["step"] = str(step_number)

    if action_kind is not None:
        context["action"] = (
            action_kind
            if action_kind in action_descriptions
            else "unsupported"
        )

        context["reason"] = action_descriptions.get(
            action_kind,
            descriptions[operation],
        )

    def emit(event: str, *, elapsed: bool = False) -> None:
        entry = {
            **context,
            "event": event,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }

        if elapsed:
            entry["elapsed_seconds"] = (
                f"{perf_counter() - started:.3f}"
            )

        control.events.append(entry)

    started = perf_counter()
    emit("operation_started")

    try:
        yield

    except MemberNotFound:
        emit("operation_business_outcome", elapsed=True)
        control.events[-1]["outcome"] = "member_not_found"
        raise

    except VerificationError as error:
        emit("operation_failed", elapsed=True)

        control.events[-1]["verification_check"] = str(
            error.details["check"]
        )
        control.events[-1]["verification_phase"] = str(
            error.details["phase"]
        )

        raise

    except Exception:
        # Preserve the exception's existing classification.
        emit("operation_failed", elapsed=True)
        raise

    else:
        emit("operation_completed", elapsed=True)


def replay(
    *,
    page: Page,
    capability: Capability,
    inputs: dict[str, str],
    policy: Policy,
    guard: NetworkGuard,
    handoff_timeout_seconds: int = 180,
) -> dict[str, str]:
    """Execute a saved capability without making model requests."""

    with record_replay_operation(
        control=guard.control,
        operation="validation",
    ):
        validate_replay(capability, inputs, policy)

    executor = BrowserExecutor(page, policy, guard.control)
    outputs: dict[str, str] = {}

    origin = policy.config.allowed_origin.rstrip("/")
    start_path = render_path(
        capability.steps[0].before.path_template,
        inputs,
    )

    with record_replay_operation(
        control=guard.control,
        operation="navigation",
    ):
        page.goto(origin + start_path)
        check_network(guard)

    for step_number, step in enumerate(capability.steps, start=1):
        with record_replay_operation(
            control=guard.control,
            operation="step",
            step_number=step_number,
            action_kind=step.action.kind,
        ):
            print(
                f"Replay step {step_number}: {step.action.kind}"
            )

            verify_checkpoint(
                page=page,
                executor=executor,
                checkpoint=step.before,
                inputs=inputs,
                policy=policy,
                phase="before_action",
                step_number=step_number,
            )

            executor.execute(
                action=step.action,
                inputs=inputs,
                outputs=outputs,
                step_number=step_number,
            )

            check_network(guard)

            # The saved navigation may encounter the known review gate.
            if (
                capability.capability_id == "get_savings_balance"
                and isinstance(step.action, ClickAction)
                and step.action.target.role == "link"
                and step.action.target.name == "View savings"
                and step.after.path_template
                == "/members/{member_id}/accounts/savings"
            ):
                outcome_heading = page.get_by_role(
                    "heading",
                    name=re.compile(
                        r"^(Savings account|Manual review required)$"
                    ),
                )

                with verification_check(
                    check="review_outcome_count",
                    phase="review_detection",
                    step_number=step_number,
                ):
                    expect(outcome_heading).to_have_count(1)

                with verification_check(
                    check="review_outcome_visibility",
                    phase="review_detection",
                    step_number=step_number,
                ):
                    expect(outcome_heading).to_be_visible()

                review_heading = page.get_by_role(
                    "heading",
                    name="Manual review required",
                    exact=True,
                )

                if review_heading.is_visible():

                    def verify_resume() -> None:
                        verify_checkpoint(
                            page=page,
                            executor=executor,
                            checkpoint=step.after,
                            inputs=inputs,
                            policy=policy,
                            phase="resume_verification",
                            step_number=step_number,
                        )

                    wait_for_human_review(
                        page=page,
                        guard=guard,
                        member_id=inputs["member_id"],
                        step_number=step_number,
                        verify_resume=verify_resume,
                        timeout_seconds=handoff_timeout_seconds,
                    )

                    check_network(guard)

            # Recognize the application's alternative search outcome.
            if (
                capability.capability_id == "get_savings_balance"
                and isinstance(step.action, ClickAction)
                and step.action.target.role == "button"
                and step.action.target.name == "Search"
                and step.before.path_template == "/"
                and step.after.path_template == "/search"
            ):
                not_found = member_not_found_on_search(
                    page=page,
                    member_id=inputs["member_id"],
                    policy=policy,
                )

                check_network(guard)

                if not_found:
                    raise MemberNotFound(
                        steps_executed=step_number,
                    )

            # A page checkpoint alone cannot verify a filled field.
            if isinstance(step.action, FillAction):
                field = executor.resolve_target(step.action.target)

                with verification_check(
                    check="filled_value",
                    phase="action_verification",
                    step_number=step_number,
                    field=step.action.input_name,
                ):
                    expect(field).to_have_value(
                        inputs[step.action.input_name]
                    )

            verify_checkpoint(
                page=page,
                executor=executor,
                checkpoint=step.after,
                inputs=inputs,
                policy=policy,
                phase="after_action",
                step_number=step_number,
            )

            check_network(guard)

    with record_replay_operation(
        control=guard.control,
        operation="final_verification",
    ):
        verify_checkpoint(
            page=page,
            executor=executor,
            checkpoint=capability.success,
            inputs=inputs,
            policy=policy,
        )

        verify_outputs(
            capability=capability,
            executor=executor,
            inputs=inputs,
            outputs=outputs,
        )

        check_network(guard)

    return outputs
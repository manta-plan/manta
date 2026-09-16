# SPDX-FileCopyrightText: 2026 Manta Blocks contributors
#
# SPDX-License-Identifier: MIT

"""Everything that can be checked about a playbook before running it.

Some checks need no settings at all - a step cannot reference one that comes after it,
whatever the settings say. The rest depend on the settings, because which steps run
does. Both are reported the same way: a list of problems, each pointing at the step
and, where it applies, the exact setting it is about, so a user interface can mark the
right box and the right field.

Most of this works even for a block that cannot be imported here, since a block's
description says enough. The one thing that cannot travel is a rule a block expresses
in code, such as "exactly one of these two settings" - that can only be checked where
the block itself can be imported.
"""

from typing import Literal

from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, ValidationError

from manta_blocks import EnvironmentConflictError, EnvironmentSpec
from manta_playbooks.playbook import (
    BlockStep,
    NestedPlaybookStep,
    Playbook,
    child_config,
    step_label,
)

IssueKind = Literal["structure", "ref", "dims", "config", "when", "environment"]


class PlaybookIssue(BaseModel):
    """One problem with a playbook."""

    model_config = ConfigDict(frozen=True)

    kind: IssueKind
    message: str

    path: tuple[str, ...] = ()
    """Which step, named from the outermost playbook inwards. Empty means the playbook itself."""

    field: tuple[str | int, ...] | None = None
    """Which setting of that step, for problems about a particular one."""

    input: str | None = None
    """Which wired-in setting, for problems about how a step is fed."""

    @property
    def step(self) -> str | None:
        """The step this is about, as a readable path."""
        return "/".join(self.path) if self.path else None

    def __str__(self) -> str:
        where = f"step {self.step!r}" if self.path else "playbook"
        if self.field:
            where += f" setting {'.'.join(str(part) for part in self.field)!r}"
        return f"[{self.kind}] {where}: {self.message}"


class PlaybookValidationError(Exception):
    """Raised when a playbook cannot be used as written."""

    def __init__(self, issues: list[PlaybookIssue]) -> None:
        self.issues = issues
        header = f"{len(issues)} issue(s) found"
        body = "\n".join(f"  {issue}" for issue in issues)
        super().__init__(f"{header}:\n{body}")


def validate_report(
    playbook: Playbook, config: dict | None = None
) -> list[PlaybookIssue]:
    """Every problem with `playbook`, without raising.

    Without `config`, only the checks that do not depend on settings are run. With it,
    everything is checked against the steps that would actually run.
    """
    issues: list[PlaybookIssue] = []
    issues.extend(_structure_issues(playbook))
    issues.extend(_ref_issues(playbook))
    issues.extend(_cycle_issues(playbook, frozenset()))

    if config is not None:
        issues.extend(_when_issues(playbook, config))
        active = playbook.active(config)
        issues.extend(_skipped_ref_issues(active))
        issues.extend(_dims_issues(playbook, active, config))
        issues.extend(_config_issues(playbook, active, config))
        issues.extend(_environment_issues(playbook, config))
        issues.extend(_nested_issues(active, config))

    return issues


def _structure_issues(playbook: Playbook) -> list[PlaybookIssue]:
    """Step names have to be unique, and usable as identifiers."""
    issues = []
    seen: set[str] = set()
    for step in playbook.steps:
        if not step.name.isidentifier():
            issues.append(
                PlaybookIssue(
                    kind="structure",
                    path=(step.name,),
                    message="step name is not a valid identifier",
                )
            )
        if step.name in seen:
            issues.append(
                PlaybookIssue(
                    kind="structure", path=(step.name,), message="duplicate step name"
                )
            )
        seen.add(step.name)
    return issues


def _cycle_issues(playbook: Playbook, visited: frozenset[int]) -> list[PlaybookIssue]:
    """A playbook cannot contain itself, however deeply nested."""
    issues = []
    seen = visited | {id(playbook)}
    for step in playbook.steps:
        if not isinstance(step, NestedPlaybookStep):
            continue
        if id(step.playbook) in seen:
            issues.append(
                PlaybookIssue(
                    kind="structure",
                    path=(step.name,),
                    message=(
                        f"circular nested playbook reference: "
                        f"{step.playbook.name!r} already appears further out"
                    ),
                )
            )
            continue
        issues.extend(_cycle_issues(step.playbook, seen))
    return issues


def _ref_issues(playbook: Playbook) -> list[PlaybookIssue]:
    """Every wire has to name a setting that exists and a step that comes earlier."""
    issues = []
    index = {step.name: i for i, step in enumerate(playbook.steps)}
    for i, step in enumerate(playbook.steps):
        for input_name, ref in step.inputs.items():
            if input_name not in step.declared_inputs():
                issues.append(
                    PlaybookIssue(
                        kind="ref",
                        path=(step.name,),
                        input=input_name,
                        message=(
                            f"{step_label(step)} has no input called {input_name!r} "
                            f"(it accepts: {sorted(step.declared_inputs())})"
                        ),
                    )
                )
            if ref.step not in index:
                issues.append(
                    PlaybookIssue(
                        kind="ref",
                        path=(step.name,),
                        input=input_name,
                        message=(
                            f"references step {ref.step!r}, which does not exist "
                            f"(earlier steps: {[s.name for s in playbook.steps[:i]]})"
                        ),
                    )
                )
                continue
            if index[ref.step] >= i:
                issues.append(
                    PlaybookIssue(
                        kind="ref",
                        path=(step.name,),
                        input=input_name,
                        message=(
                            f"references step {ref.step!r}, which does not come "
                            "before it"
                        ),
                    )
                )
                continue
            target = playbook.steps[index[ref.step]]
            if ref.output not in target.declared_outputs():
                issues.append(
                    PlaybookIssue(
                        kind="ref",
                        path=(step.name,),
                        input=input_name,
                        message=(
                            f"references result {ref.output!r} of step "
                            f"{ref.step!r}, which offers "
                            f"{sorted(target.declared_outputs())}"
                        ),
                    )
                )
    return issues


def _when_issues(playbook: Playbook, config: dict) -> list[PlaybookIssue]:
    """A condition that looks at a setting nobody set is almost certainly a mistake."""
    issues = []
    for step in playbook.steps:
        if step.when is not None and step.when.check(config) is None:
            issues.append(
                PlaybookIssue(
                    kind="when",
                    path=(step.name,),
                    field=tuple(step.when.config.split(".")),
                    message=(
                        f"condition looks at setting {step.when.config!r}, which is "
                        "not set anywhere"
                    ),
                )
            )
    return issues


def _skipped_ref_issues(active: Playbook) -> list[PlaybookIssue]:
    """A step that runs cannot be fed by one that does not."""
    issues = []
    running = {step.name for step in active.steps}
    for step in active.steps:
        for input_name, ref in step.inputs.items():
            if ref.step not in running:
                issues.append(
                    PlaybookIssue(
                        kind="ref",
                        path=(step.name,),
                        input=input_name,
                        message=(
                            f"input {input_name!r} comes from step {ref.step!r}, "
                            "which does not run with these settings"
                        ),
                    )
                )
    return issues


def _dims_issues(
    playbook: Playbook, active: Playbook, config: dict
) -> list[PlaybookIssue]:
    """Every step has to find the dimensions it needs still present when it runs."""
    issues = []
    dims = frozenset(playbook.initial_dims)
    removed_by: dict[str, str] = {}
    for step in active.steps:
        step_dims = step.dims(config)
        for dim in sorted(step_dims.requires - dims):
            message = (
                f"needs the {dim!r} dimension, which is not there at this point "
                f"(present: {sorted(dims)})"
            )
            if dim in removed_by:
                message += f"; {removed_by[dim]}"
            issues.append(
                PlaybookIssue(kind="dims", path=(step.name,), message=message)
            )
        for dim in step_dims.removes & dims:
            removed_by[dim] = f"step {step.name!r} removed it"
        dims = step_dims.apply(dims)
    return issues


def _config_issues(
    playbook: Playbook, active: Playbook, config: dict
) -> list[PlaybookIssue]:
    """Settings have to belong to a step, and match what that step accepts."""
    issues = []
    # Unknown keys are checked against every step, not only the ones that run: one
    # settings file legitimately carries settings for each branch of a condition,
    # including the branches this particular run does not take.
    known_keys = {step.name for step in playbook.steps} | {"globals"}
    for key in config:
        if key not in known_keys:
            issues.append(
                PlaybookIssue(
                    kind="config",
                    field=(key,),
                    message=(
                        f"there is no step called {key!r}, and it is not 'globals'"
                    ),
                )
            )

    for step in active.steps:
        if not isinstance(step, BlockStep):
            continue  # a nested playbook's own settings are checked further down
        issues.extend(_step_config_issues(step, config.get(step.name, {})))
    return issues


def _step_config_issues(step: BlockStep, values: dict) -> list[PlaybookIssue]:
    """Check one step's settings against what its block accepts.

    Where the block can be imported, its own settings model does the checking and
    catches everything. Where it cannot - because it belongs to another environment -
    the description of its settings is used instead, which catches wrong types and
    missing values but not rules the block expresses in code.
    """
    model = step.block.config_model()
    if model is not None:
        return _pydantic_issues(step, values, model)
    return _schema_issues(step, values)


def _pydantic_issues(step: BlockStep, values: dict, model) -> list[PlaybookIssue]:
    try:
        model.model_validate(values)
    except ValidationError as exc:
        return [
            PlaybookIssue(
                kind="config",
                path=(step.name,),
                field=tuple(error["loc"]),
                message=error["msg"],
            )
            for error in exc.errors()
        ]
    return []


def _schema_issues(step: BlockStep, values: dict) -> list[PlaybookIssue]:
    schema = step.block.config_schema
    if not schema:
        return []
    validator = Draft202012Validator(schema)
    return [
        PlaybookIssue(
            kind="config",
            path=(step.name,),
            field=tuple(error.absolute_path),
            message=error.message,
        )
        for error in sorted(validator.iter_errors(values), key=str)
    ]


def _environment_issues(playbook: Playbook, config: dict) -> list[PlaybookIssue]:
    """Blocks sharing an environment name have to agree on where it lives."""
    issues = []
    seen: dict[str, EnvironmentSpec] = {}
    for path, spec in _environments(playbook, config, ()):
        existing = seen.get(spec.name)
        if existing is not None and existing != spec:
            issues.append(
                PlaybookIssue(
                    kind="environment",
                    path=path,
                    message=str(
                        EnvironmentConflictError(
                            f"environment {spec.name!r} is described as {existing!r} "
                            f"by one block and {spec!r} by another"
                        )
                    ),
                )
            )
            continue
        seen[spec.name] = spec
    return issues


def _environments(
    playbook: Playbook, config: dict, prefix: tuple[str, ...]
) -> "list[tuple[tuple[str, ...], EnvironmentSpec]]":
    """Every environment the steps that will run need, with the step that needs it."""
    found = []
    for step in playbook.active(config).steps:
        path = (*prefix, step.name)
        if isinstance(step, BlockStep):
            found.append((path, step.block.environment()))
        else:
            found.extend(
                _environments(step.playbook, child_config(config, step.name), path)
            )
    return found


def _nested_issues(active: Playbook, config: dict) -> list[PlaybookIssue]:
    """Check each nested playbook, and report its problems against its own step."""
    issues = []
    for step in active.steps:
        if not isinstance(step, NestedPlaybookStep):
            continue
        inner_config = child_config(config, step.name)
        for inner in validate_report(step.playbook, inner_config):
            if inner.kind == "environment":
                continue  # already covered across the whole playbook, in one pass
            issues.append(inner.model_copy(update={"path": (step.name, *inner.path)}))
    return issues

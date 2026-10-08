# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Everything that can be checked about a playbook before running it.

Some checks need no settings at all - a step cannot be fed by one that comes after
it, whatever the settings say. The rest depend on the settings, because which steps
run does. Both are reported the same way: a list of issues, each saying which step it
is about and, where it applies, exactly where in the settings the problem is, so a
user interface can mark the right step and the right field.

Most of this works for a block that cannot be imported here, since its description
in a catalogue says enough. What cannot travel is a rule a block expresses in code,
such as "exactly one of these two settings": where the block cannot be imported, that
is only enforced once the block runs.
"""

from typing import Literal

from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match
from pydantic import BaseModel, ConfigDict, ValidationError

from playbook.blocks import ConfigSchema, EnvironmentSpec
from playbook.playbooks.playbook import (
    BlockStep,
    NestedPlaybookStep,
    Playbook,
    Step,
    child_config,
)

PlaybookIssueKind = Literal["structure", "wiring", "dims", "config", "when", "environment"]
"""What sort of problem an issue is:

- `structure`: step names that clash or cannot be used, or a playbook containing itself
- `wiring`: a step fed from a result that does not exist, comes later, or does not run
- `dims`: a step needing a dimension the data does not have by the time it runs
- `config`: settings that do not fit what a step accepts, or belong to no step at all
- `when`: a condition looking at a setting nobody set
- `environment`: two blocks describing the same environment differently
"""

ConfigPath = tuple[str | int, ...]
"""Where a value sits in a settings document: keys, and indexes into lists."""


class PlaybookIssue(BaseModel):
    """One problem with a playbook, or with running it with particular settings."""

    model_config = ConfigDict(frozen=True)

    kind: PlaybookIssueKind
    message: str

    step_path: tuple[str, ...] = ()
    """Which step this is about, named from the outermost playbook inwards, e.g.
    `("regional", "dispatch")` for a step of the playbook nested as `regional`. Empty
    for a problem with the playbook as a whole."""

    config_path: ConfigPath | None = None
    """Where in the settings the problem is, always counted from the top of the
    settings document, e.g. `("dispatch", "optimize_config", "horizon")`. None for a
    problem that is not about any one setting."""

    input: str | None = None
    """Which wired-in setting, for a problem with how a step is fed."""

    def __str__(self) -> str:
        where = f"step {'/'.join(self.step_path)!r}" if self.step_path else "playbook"
        if self.config_path is not None:
            where += f", setting {'.'.join(str(part) for part in self.config_path)!r}"
        if self.input is not None:
            where += f", input {self.input!r}"
        return f"[{self.kind}] {where}: {self.message}"


class PlaybookHasIssuesError(Exception):
    """Raised when a playbook cannot run as written, carrying every issue found."""

    def __init__(self, issues: list[PlaybookIssue]) -> None:
        self.issues = issues
        listed = "\n".join(f"  {issue}" for issue in issues)
        super().__init__(f"{len(issues)} issue(s) found:\n{listed}")


def find_playbook_issues(playbook: Playbook, config: dict | None = None) -> list[PlaybookIssue]:
    """Every problem with `playbook`, returned rather than raised.

    Without `config`, only the checks that do not depend on settings are run. With it,
    everything is checked, against the steps that would actually run with it.
    """
    circular = _circular_nesting_issues(playbook, frozenset())
    if circular:
        # Every other check walks into nested playbooks, which a playbook containing
        # itself would turn into a walk that never ends.
        return circular

    issues = _settings_independent_issues(playbook)
    if config is not None:
        issues.extend(_settings_dependent_issues(playbook, config))
        issues.extend(_environment_issues(playbook, config))
    return issues


def raise_for_playbook_issues(playbook: Playbook, config: dict | None = None) -> None:
    """Raise `PlaybookHasIssuesError` if `find_playbook_issues` finds anything."""
    issues = find_playbook_issues(playbook, config)
    if issues:
        raise PlaybookHasIssuesError(issues)


def _settings_independent_issues(playbook: Playbook) -> list[PlaybookIssue]:
    """What is wrong with a playbook whatever the settings, nested playbooks included."""
    issues = [*_structure_issues(playbook), *_wiring_issues(playbook)]
    for step in playbook.steps:
        if isinstance(step, NestedPlaybookStep):
            issues.extend(_from_nested_step(step.name, _settings_independent_issues(step.playbook)))
    return issues


def _settings_dependent_issues(playbook: Playbook, config: dict) -> list[PlaybookIssue]:
    """What is wrong with running a playbook with `config`, nested playbooks included."""
    active = playbook.active(config)
    issues = [
        *_when_issues(playbook, config),
        *_skipped_step_wiring_issues(playbook, active),
        *_dims_issues(playbook, active, config),
        *_config_issues(playbook, active, config),
    ]
    for step in active.steps:
        if isinstance(step, NestedPlaybookStep):
            inner = _settings_dependent_issues(step.playbook, child_config(config, step.name))
            issues.extend(_from_nested_step(step.name, inner))
    return issues


def _from_nested_step(step_name: str, issues: list[PlaybookIssue]) -> list[PlaybookIssue]:
    """Issues found inside a nested playbook, addressed from the playbook nesting it.

    The nested playbook's settings are filed under its step's name, so the setting an
    issue points at moves down a level along with the step.
    """
    return [
        issue.model_copy(
            update={
                "step_path": (step_name, *issue.step_path),
                "config_path": (
                    None if issue.config_path is None else (step_name, *issue.config_path)
                ),
            }
        )
        for issue in issues
    ]


def _structure_issues(playbook: Playbook) -> list[PlaybookIssue]:
    """Step names have to be unique, and usable wherever a step is named."""
    issues = []
    seen: set[str] = set()
    for step in playbook.steps:
        if not step.name.isidentifier():
            issues.append(
                PlaybookIssue(
                    kind="structure",
                    step_path=(step.name,),
                    message=(
                        "step name has to be letters, digits and underscores, not "
                        "starting with a digit, so that other steps can refer to it"
                    ),
                )
            )
        if step.name == "globals":
            issues.append(
                PlaybookIssue(
                    kind="structure",
                    step_path=(step.name,),
                    message="step name 'globals' is taken by the settings every step can see",
                )
            )
        if step.name in seen:
            issues.append(
                PlaybookIssue(
                    kind="structure", step_path=(step.name,), message="duplicate step name"
                )
            )
        seen.add(step.name)
    return issues


def _circular_nesting_issues(
    playbook: Playbook, further_out: frozenset[int]
) -> list[PlaybookIssue]:
    """A playbook cannot contain itself, however deeply nested."""
    issues = []
    chain = further_out | {id(playbook)}
    for step in playbook.steps:
        if not isinstance(step, NestedPlaybookStep):
            continue
        if id(step.playbook) in chain:
            issues.append(
                PlaybookIssue(
                    kind="structure",
                    step_path=(step.name,),
                    message=(
                        f"nests playbook {step.playbook.name!r}, which this step is "
                        "already inside, so running it would never finish"
                    ),
                )
            )
            continue
        issues.extend(_from_nested_step(step.name, _circular_nesting_issues(step.playbook, chain)))
    return issues


def _wiring_issues(playbook: Playbook) -> list[PlaybookIssue]:
    """Every wire has to fill a setting that exists, from an earlier step's result."""
    issues = []
    position = {step.name: i for i, step in enumerate(playbook.steps)}
    for i, step in enumerate(playbook.steps):
        for input_name, ref in step.inputs.items():
            if input_name not in step.declared_inputs():
                issues.append(
                    _wiring_issue(
                        step,
                        input_name,
                        f"{_what_step_runs(step)} has no input called {input_name!r} "
                        f"(it accepts: {sorted(step.declared_inputs())})",
                    )
                )
            if ref.step not in position:
                issues.append(
                    _wiring_issue(
                        step,
                        input_name,
                        f"is fed from step {ref.step!r}, which does not exist "
                        f"(earlier steps: {[s.name for s in playbook.steps[:i]]})",
                    )
                )
                continue
            if position[ref.step] >= i:
                issues.append(
                    _wiring_issue(
                        step,
                        input_name,
                        f"is fed from step {ref.step!r}, which does not come before it",
                    )
                )
                continue
            source = playbook.steps[position[ref.step]]
            if ref.output not in source.declared_outputs():
                issues.append(
                    _wiring_issue(
                        step,
                        input_name,
                        f"is fed from result {ref.output!r} of step {ref.step!r}, which "
                        f"offers {sorted(source.declared_outputs())}",
                    )
                )
    return issues


def _wiring_issue(step: Step, input_name: str, message: str) -> PlaybookIssue:
    return PlaybookIssue(kind="wiring", step_path=(step.name,), input=input_name, message=message)


def _what_step_runs(step: Step) -> str:
    """A step's block or nested playbook, named for a message."""
    if isinstance(step, BlockStep):
        return f"block {step.block.name!r}"
    return f"playbook {step.playbook.name!r}"


def _when_issues(playbook: Playbook, config: dict) -> list[PlaybookIssue]:
    """A condition looking at a setting nobody set is almost certainly a mistake."""
    return [
        PlaybookIssue(
            kind="when",
            step_path=(step.name,),
            config_path=tuple(step.when.config.split(".")),
            message=(
                f"only runs depending on setting {step.when.config!r}, which is not set anywhere"
            ),
        )
        for step in playbook.steps
        if step.when is not None and step.when.check(config) is None
    ]


def _skipped_step_wiring_issues(playbook: Playbook, active: Playbook) -> list[PlaybookIssue]:
    """A step that runs cannot be fed by one that does not.

    A wire from a step that does not exist at all is already reported by
    `_wiring_issues`, whatever the settings.
    """
    all_steps = {step.name for step in playbook.steps}
    running = {step.name for step in active.steps}
    return [
        _wiring_issue(
            step,
            input_name,
            f"is fed from step {ref.step!r}, which does not run with these settings",
        )
        for step in active.steps
        for input_name, ref in step.inputs.items()
        if ref.step in all_steps and ref.step not in running
    ]


def _dims_issues(playbook: Playbook, active: Playbook, config: dict) -> list[PlaybookIssue]:
    """Every step has to find the dimensions it needs still there when it runs."""
    issues = []
    dims = playbook.initial_dims
    removed_by: dict[str, str] = {}
    for step in active.steps:
        effect = step.dims_effect(config)
        for dim in sorted(effect.requires - dims):
            message = (
                f"needs the {dim!r} dimension, which the data does not have at this "
                f"point (it has: {sorted(dims)})"
            )
            if dim in removed_by:
                message += f"; step {removed_by[dim]!r} removed it"
            issues.append(PlaybookIssue(kind="dims", step_path=(step.name,), message=message))
        for dim in effect.removes & dims:
            removed_by[dim] = step.name
        dims = effect.apply(dims)
    return issues


def _config_issues(playbook: Playbook, active: Playbook, config: dict) -> list[PlaybookIssue]:
    """Settings have to belong to a step, and fit what that step accepts."""
    issues = []
    # Checked against every step, not only the ones that run: one settings document
    # legitimately carries settings for each branch of a condition, including the
    # branches a particular run does not take.
    known = {step.name for step in playbook.steps} | {"globals"}
    for key in config:
        if key not in known:
            issues.append(
                PlaybookIssue(
                    kind="config",
                    config_path=(key,),
                    message=f"there is no step called {key!r}, and it is not 'globals'",
                )
            )

    for step in active.steps:
        if isinstance(step, BlockStep):  # a nested playbook's are checked inside it
            issues.extend(
                PlaybookIssue(
                    kind="config",
                    step_path=(step.name,),
                    config_path=(step.name, *where),
                    message=message,
                )
                for where, message in _block_settings_problems(step, config.get(step.name, {}))
            )
    return issues


def _block_settings_problems(step: BlockStep, values: object) -> list[tuple[ConfigPath, str]]:
    """Where `values` do not fit what the step's block accepts, and why.

    Where the block can be imported, its own settings model does the checking and
    catches everything. Where it cannot - because it belongs to another environment -
    the description of its settings is used instead, which catches wrong types,
    missing and unknown settings, but not rules the block expresses in code.
    """
    model = step.block.config_model()
    if model is not None:
        return _settings_model_problems(model, values)
    return _settings_schema_problems(step.block.config_schema, values)


def _settings_model_problems(
    model: type[ConfigSchema], values: object
) -> list[tuple[ConfigPath, str]]:
    try:
        model.model_validate(values)
    except ValidationError as exc:
        problems = []
        for error in exc.errors():
            where = tuple(error["loc"])
            # Worded as the schema check words them, so the same mistake reads the
            # same whether or not the block could be imported.
            if error["type"] == "missing":
                problems.append((where, "this setting is required"))
            elif error["type"] == "extra_forbidden":
                problems.append((where, f"there is no setting called {where[-1]!r}"))
            else:
                problems.append((where, error["msg"]))
        return problems
    return []


def _settings_schema_problems(schema: dict, values: object) -> list[tuple[ConfigPath, str]]:
    if not schema:
        return []
    problems: list[tuple[ConfigPath, str]] = []
    for error in Draft202012Validator(schema).iter_errors(values):
        # An optional group of settings is described as `anyOf` it or null, and the
        # error that helps is the one from inside it, down at the setting itself.
        error = best_match([error])
        where = tuple(error.absolute_path)
        # Both of these are reported on the object holding the setting; pointing at
        # the setting itself is what lets a form mark the right field.
        if error.validator == "required":
            problems.extend(
                ((*where, name), "this setting is required")
                for name in error.validator_value
                if name not in error.instance
            )
        elif error.validator == "additionalProperties" and error.validator_value is False:
            accepted = error.schema.get("properties", {})
            problems.extend(
                ((*where, name), f"there is no setting called {name!r}")
                for name in error.instance
                if name not in accepted
            )
        else:
            problems.append((where, error.message))
    # A `required` error is raised once per missing setting, but each one names them all.
    return list(dict.fromkeys(problems))


def _environment_issues(playbook: Playbook, config: dict) -> list[PlaybookIssue]:
    """Blocks naming the same environment have to agree on what it is.

    Checked once across the whole playbook, nested ones included, since two blocks
    can disagree from anywhere in it.
    """
    issues = []
    first_described: dict[str, EnvironmentSpec] = {}
    for step_path, environment in _environments_needed(playbook, config, ()):
        described = first_described.setdefault(environment.name, environment)
        if described != environment:
            issues.append(
                PlaybookIssue(
                    kind="environment",
                    step_path=step_path,
                    message=(
                        f"describes environment {environment.name!r} as {environment!r}, "
                        f"but an earlier step describes it as {described!r}"
                    ),
                )
            )
    return issues


def _environments_needed(
    playbook: Playbook, config: dict, further_out: tuple[str, ...]
) -> list[tuple[tuple[str, ...], EnvironmentSpec]]:
    """The environment each step that will run needs, with that step's path."""
    needed = []
    for step in playbook.active(config).steps:
        step_path = (*further_out, step.name)
        if isinstance(step, BlockStep):
            needed.append((step_path, step.block.environment()))
        else:
            needed.extend(
                _environments_needed(step.playbook, child_config(config, step.name), step_path)
            )
    return needed

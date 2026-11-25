# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Everything that can be checked about a playbook before running it.

Some checks need no input values at all: step ids that clash, an expression reading an
input that does not exist. The rest depend on the inputs, because which steps run and
what their settings are does. Both are reported the same way: a list of issues, each
saying which step it is about and, where it applies, which input or which setting, so a
user interface can mark the right field.

Most of this works for a block that cannot be imported here, since its description in
a catalogue says enough. What cannot travel is a rule a block expresses in code, such
as "exactly one of these two settings": where the block cannot be imported, that is
only enforced once the block runs.
"""

from collections.abc import Mapping

from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match
from pydantic import ValidationError

from playbook.blocks import BlockDims, BlockSpec, ConfigSchema, EnvironmentSpec
from playbook.playbooks.expressions import Node, Ref, map_expressions, parse, refs
from playbook.playbooks.inputs import collect_inputs
from playbook.playbooks.issues import PlaybookHasIssuesError, PlaybookIssue, SettingPath
from playbook.playbooks.planner import PlannedBlock, PlannedGroup, plan, walk_planned
from playbook.playbooks.playbook import Playbook, PlaybookStep
from playbook.playbooks.syntax import InputSpec

_BLOCKING = frozenset({"structure", "reference"})


def find_playbook_issues(playbook: Playbook, inputs: dict | None = None) -> list[PlaybookIssue]:
    """Every problem with `playbook`, returned rather than raised.

    Without `inputs`, only the checks that do not depend on input values are run. With
    them, the input values are checked, and then every block that would run with them.
    """
    circular = _circular_nesting_issues(playbook, frozenset())
    if circular:
        return circular
    issues = _static_issues(playbook, ())
    if inputs is None or any(issue.kind in _BLOCKING for issue in issues):
        return issues
    try:
        planned = plan(playbook, inputs)
    except PlaybookHasIssuesError as exc:
        return [*issues, *exc.issues]
    blocks = [step for step in walk_planned(planned) if isinstance(step, PlannedBlock)]
    return [
        *issues,
        *_dims_issues(planned)[1],
        *_config_issues(blocks),
        *_environment_issues(blocks),
    ]


def raise_for_playbook_issues(playbook: Playbook, inputs: dict | None = None) -> None:
    """Raise `PlaybookHasIssuesError` if `find_playbook_issues` finds anything."""
    issues = find_playbook_issues(playbook, inputs)
    if issues:
        raise PlaybookHasIssuesError(issues)


def _static_issues(playbook: Playbook, prefix: tuple[str, ...]) -> list[PlaybookIssue]:
    """What is wrong with a playbook whatever its inputs, nested playbooks included."""
    specs, issues = collect_inputs(playbook)
    issues = [
        issue.model_copy(update={"step_path": (*prefix, *issue.step_path)}) for issue in issues
    ]
    issues.extend(_id_issues(playbook, prefix))
    issues.extend(_reference_issues(playbook, specs, prefix))
    for step in playbook.steps:
        if isinstance(step, PlaybookStep):
            issues.extend(_static_issues(step.playbook, (*prefix, step.id)))
    return issues


def _id_issues(playbook: Playbook, prefix: tuple[str, ...]) -> list[PlaybookIssue]:
    """Step ids are unique across a playbook."""
    seen: set[str] = set()
    issues = []
    for step in playbook.steps:
        if step.id in seen:
            issues.append(
                PlaybookIssue(
                    kind="structure", message="duplicate step id", step_path=(*prefix, step.id)
                )
            )
        seen.add(step.id)
    return issues


def _circular_nesting_issues(
    playbook: Playbook, further_out: frozenset[int]
) -> list[PlaybookIssue]:
    """A playbook cannot contain itself, however deeply nested."""
    issues = []
    chain = further_out | {id(playbook)}
    for step in playbook.steps:
        if not isinstance(step, PlaybookStep):
            continue
        if id(step.playbook) in chain:
            message = (
                f"nests playbook {step.playbook.name!r}, which this step is already inside, "
                f"so running it would never finish"
            )
            issues.append(PlaybookIssue(kind="structure", message=message, step_path=(step.id,)))
            continue
        inner = _circular_nesting_issues(step.playbook, chain)
        issues.extend(
            issue.model_copy(update={"step_path": (step.id, *issue.step_path)}) for issue in inner
        )
    return issues


def _expressions(value: object) -> list[Node]:
    nodes: list[Node] = []
    map_expressions(value, nodes.append)
    return nodes


def _reference_problem(ref: Ref, specs: Mapping[str, InputSpec]) -> str | None:
    if not ref.path:
        return f"reads {ref} as a whole, rather than one input"
    name, *rest = ref.path
    if name not in specs:
        return f"reads {ref}, but there is no input {name!r} (inputs: {sorted(specs)})"
    if rest:
        return f"reads {ref}, which input {name!r} does not have"
    return None


def _reference_issues(
    playbook: Playbook, specs: Mapping[str, InputSpec], prefix: tuple[str, ...]
) -> list[PlaybookIssue]:
    """Every expression reads an input that exists."""
    issues = []
    for step in playbook.steps:
        path = (*prefix, step.id)
        nodes = [] if step.if_ is None else [parse(step.if_)]
        nodes.extend(_expressions(step.with_))
        for ref in sorted({ref for node in nodes for ref in refs(node)}, key=str):
            problem = _reference_problem(ref, specs)
            if problem is not None:
                issues.append(PlaybookIssue(kind="reference", message=problem, step_path=path))
        if isinstance(step, PlaybookStep):
            accepted = collect_inputs(step.playbook)[0]
            issues.extend(
                PlaybookIssue(
                    kind="reference",
                    message=f"playbook {step.playbook.name!r} has no input {name!r}",
                    step_path=path,
                    input_path=(name,),
                )
                for name in step.with_
                if name not in accepted
            )
    return issues


def _dims_issues(group: PlannedGroup) -> tuple[frozenset[str], list[PlaybookIssue]]:
    """The dimensions the data has after `group`, and every step needing one it lacks.

    A nested playbook is one step to the playbook nesting it: it needs the dimensions its
    `initial_data` states, and its own steps are checked against those.
    """
    dims = group.initial_dims
    removed_by: dict[str, tuple[str, ...]] = {}
    issues = []
    for step in group.steps:
        if isinstance(step, PlannedBlock):
            effect = step.block.dims
        else:
            final, inner = _dims_issues(step)
            issues.extend(inner)
            initial = step.initial_dims
            effect = BlockDims(requires=initial, adds=final - initial, removes=initial - final)
        for dim in sorted(effect.requires - dims):
            message = (
                f"needs the {dim!r} dimension, which the data does not have at this "
                f"point (it has: {sorted(dims)})"
            )
            if dim in removed_by:
                message += f"; step {'/'.join(removed_by[dim])!r} removed it"
            issues.append(PlaybookIssue(kind="dims", message=message, step_path=step.path))
        for dim in effect.removes & dims:
            removed_by[dim] = step.path
        dims = effect.apply(dims)
    return dims, issues


def _config_issues(blocks: list[PlannedBlock]) -> list[PlaybookIssue]:
    """Each block's settings fit what it accepts."""
    return [
        PlaybookIssue(kind="config", message=message, step_path=step.path, setting_path=where)
        for step in blocks
        for where, message in _block_settings_problems(step.block, step.settings)
    ]


def _block_settings_problems(block: BlockSpec, values: dict) -> list[tuple[SettingPath, str]]:
    """Where `values` do not fit what `block` accepts, and why.

    Where the block can be imported, its own settings model does the checking and
    catches everything. Where it cannot - because it belongs to another environment -
    the description of its settings is used instead, which catches wrong types,
    missing and unknown settings, but not rules the block expresses in code.
    """
    model = block.config_model()
    if model is not None:
        return _settings_model_problems(model, values)
    return _settings_schema_problems(block.config_schema, values)


def _settings_model_problems(
    model: type[ConfigSchema], values: dict
) -> list[tuple[SettingPath, str]]:
    try:
        model.model_validate(values)
    except ValidationError as exc:
        problems = []
        for error in exc.errors():
            where = tuple(error["loc"])
            if error["type"] == "missing":
                problems.append((where, "this setting is required"))
            elif error["type"] == "extra_forbidden":
                problems.append((where, f"there is no setting called {where[-1]!r}"))
            else:
                problems.append((where, error["msg"]))
        return problems
    return []


def _settings_schema_problems(schema: dict, values: dict) -> list[tuple[SettingPath, str]]:
    if not schema:
        return []
    problems: list[tuple[SettingPath, str]] = []
    for error in Draft202012Validator(schema).iter_errors(values):
        error = best_match([error])
        where = tuple(error.absolute_path)
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
    return list(dict.fromkeys(problems))


def _environment_issues(blocks: list[PlannedBlock]) -> list[PlaybookIssue]:
    """Blocks naming the same environment agree on what it is."""
    issues = []
    first_described: dict[str, EnvironmentSpec] = {}
    for step in blocks:
        environment = step.block.environment()
        described = first_described.setdefault(environment.name, environment)
        if described != environment:
            message = (
                f"describes environment {environment.name!r} as {environment!r}, "
                f"but an earlier step describes it as {described!r}"
            )
            issues.append(PlaybookIssue(kind="environment", message=message, step_path=step.path))
    return issues

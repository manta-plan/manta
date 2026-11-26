# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Plan the steps a playbook runs with given input values, without reading any data.

`plan` resolves the inputs, removes each step whose `if` is false, evaluates every
expression in `with`, and expands each nested playbook into a group of its own steps.

`find_playbook_issues`, `execute_playbook`, and any caller that lists the steps of a
run all call `plan`. The steps that are checked are therefore the steps that run.
"""

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from playbook.blocks import BlockSpec
from playbook.playbooks.expressions import ExpressionError, evaluate, parse, substitute
from playbook.playbooks.inputs import effective_inputs, resolve_inputs
from playbook.playbooks.issues import PlaybookHasIssuesError, PlaybookIssue
from playbook.playbooks.playbook import BlockStep, Playbook, PlaybookStep, Step

Scope = Mapping[str, Any]


@dataclass(frozen=True)
class PlannedBlock:
    """A block that runs, with its settings evaluated."""

    path: tuple[str, ...]
    block: BlockSpec
    settings: dict


@dataclass(frozen=True)
class PlannedGroup:
    """The steps of a nested playbook, or of the whole playbook, in the order they run."""

    path: tuple[str, ...]
    steps: tuple["Planned", ...]
    initial_dims: frozenset[str] = frozenset()
    """The dimensions that `initial_data` states for the playbook of these steps."""


Planned = PlannedBlock | PlannedGroup


def walk_planned(planned: Planned) -> Iterator[Planned]:
    """Yield `planned` and every step inside it, in the order they run."""
    yield planned
    if isinstance(planned, PlannedGroup):
        for step in planned.steps:
            yield from walk_planned(step)


def plan(playbook: Playbook, inputs: Mapping[str, object]) -> PlannedGroup:
    """Return the steps that `playbook` runs with `inputs`.

    Raises:
        PlaybookHasIssuesError: If an input value does not fit, for `playbook` or for a
            nested playbook whose inputs a step sets, or if the `if` or `with` of a step
            cannot be evaluated with the input values.
    """
    steps = _plan_playbook(playbook, inputs, ())
    return PlannedGroup(path=(), steps=steps, initial_dims=playbook.initial_dims)


def _plan_playbook(
    playbook: Playbook, given: Mapping[str, object], path: tuple[str, ...]
) -> tuple[Planned, ...]:
    try:
        resolved = resolve_inputs(effective_inputs(playbook), given)
    except PlaybookHasIssuesError as exc:
        moved = [
            issue.model_copy(update={"step_path": (*path, *issue.step_path)})
            for issue in exc.issues
        ]
        raise PlaybookHasIssuesError(moved) from exc
    scope = {"inputs": resolved}
    planned = []
    issues = []
    for step in playbook.steps:
        step_path = (*path, step.id)
        try:
            if _runs(step, scope):
                planned.append(_plan_step(step, scope, step_path))
        except ExpressionError as exc:
            issues.append(PlaybookIssue(kind="inputs", message=str(exc), step_path=step_path))
        except PlaybookHasIssuesError as exc:
            issues.extend(exc.issues)
    if issues:
        raise PlaybookHasIssuesError(issues)
    return tuple(planned)


def _runs(step: Step, scope: Scope) -> bool:
    return step.if_ is None or bool(evaluate(parse(step.if_), scope))


def _plan_step(step: Step, scope: Scope, path: tuple[str, ...]) -> Planned:
    match step:
        case BlockStep():
            return PlannedBlock(path, step.block, substitute(step.with_, scope))
        case PlaybookStep():
            given = substitute(step.with_, scope)
            unset = effective_inputs(step.playbook).keys() - step.with_.keys()
            inherited = {name: scope["inputs"][name] for name in unset} if step.inherit else {}
            steps = _plan_playbook(step.playbook, {**inherited, **given}, path)
            return PlannedGroup(path, steps, step.playbook.initial_dims)

# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""What a playbook will run, given values for its inputs, worked out without reading any data.

Planning resolves the inputs, removes each step whose `if` is false, evaluates every
expression in `with`, and expands each nested playbook into a group of its own steps.

The validator, the executor and anything listing a run's steps all plan the same way,
so what a playbook is understood to do and what it does cannot drift apart.
"""

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from playbook.blocks import BlockSpec
from playbook.playbooks.expressions import evaluate, parse, substitute
from playbook.playbooks.inputs import effective_inputs, resolve_inputs
from playbook.playbooks.issues import PlaybookHasIssuesError
from playbook.playbooks.playbook import BlockStep, Playbook, PlaybookStep, Step

Scope = Mapping[str, Any]


@dataclass(frozen=True)
class PlannedBlock:
    """A block that will run, with its settings worked out."""

    path: tuple[str, ...]
    block: BlockSpec
    settings: dict


@dataclass(frozen=True)
class PlannedGroup:
    """Steps that will run in order: a nested playbook, or the whole playbook."""

    path: tuple[str, ...]
    steps: tuple["Planned", ...]
    initial_dims: frozenset[str] = frozenset()
    """The dimensions the playbook these steps belong to states its data starts with."""


Planned = PlannedBlock | PlannedGroup


def walk_planned(planned: Planned) -> Iterator[Planned]:
    """`planned` and every step inside it, in the order they run."""
    yield planned
    if isinstance(planned, PlannedGroup):
        for step in planned.steps:
            yield from walk_planned(step)


def plan(playbook: Playbook, inputs: Mapping[str, object]) -> PlannedGroup:
    """The steps `playbook` will run with `inputs`.

    Raises `PlaybookHasIssuesError` for input values that do not fit, here or where a
    step gives a nested playbook its inputs.
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
    return tuple(
        _plan_step(step, scope, (*path, step.id)) for step in playbook.steps if _runs(step, scope)
    )


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

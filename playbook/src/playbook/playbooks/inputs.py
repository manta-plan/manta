# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""The inputs a playbook declares, and a run's values for them, checked and filled with defaults."""

from collections.abc import Mapping

from playbook.playbooks.issues import PlaybookHasIssuesError, PlaybookIssue
from playbook.playbooks.playbook import Playbook, PlaybookStep
from playbook.playbooks.syntax import ChoiceInput, InputSpec

_TYPES: dict[str, type | tuple[type, ...]] = {
    "string": str,
    "number": (int, float),
    "boolean": bool,
}


def _issue(path: tuple[str, ...], message: str) -> PlaybookIssue:
    return PlaybookIssue(kind="inputs", message=message, input_path=path)


def _type_problem(spec: InputSpec, value: object) -> str | None:
    if value is None:
        return None
    if isinstance(spec, ChoiceInput):
        listed = value in spec.options and not isinstance(value, bool)
        return None if listed else f"{value!r} is not one of {spec.options}"
    wrong_bool = isinstance(value, bool) and spec.type == "number"
    if wrong_bool or not isinstance(value, _TYPES[spec.type]):
        return f"{value!r} is not a {spec.type}"
    return None


def resolve_inputs(specs: Mapping[str, InputSpec], given: Mapping[str, object]) -> dict:
    """Every declared input's value: the given one, or its default.

    Raises `PlaybookHasIssuesError` (kind `inputs`) listing every value that does not fit.
    """
    issues = [_issue((name,), "is not an input") for name in given if name not in specs]
    resolved = {}
    for name, spec in specs.items():
        if name not in given and spec.required:
            issues.append(_issue((name,), "is required and has no default"))
            continue
        resolved[name] = given.get(name, spec.default)
        problem = _type_problem(spec, resolved[name])
        if problem is not None:
            issues.append(_issue((name,), problem))
    if issues:
        raise PlaybookHasIssuesError(issues)
    return resolved


def collect_inputs(playbook: Playbook) -> tuple[dict[str, InputSpec], list[PlaybookIssue]]:
    """The inputs `playbook` takes, and an issue for each inherited one whose name is taken.

    Only clashes in `playbook` itself are reported; a nested playbook's own are its issues.
    """
    collected = dict(playbook.inputs)
    issues = []
    for step in playbook.steps:
        if not (isinstance(step, PlaybookStep) and step.inherit):
            continue
        for name, spec in collect_inputs(step.playbook)[0].items():
            if name in step.with_:
                continue
            if name in collected:
                message = f"inherits input {name!r}, which the playbook already has"
                issue = PlaybookIssue(
                    kind="structure", message=message, step_path=(step.id,), input_path=(name,)
                )
                issues.append(issue)
                continue
            collected[name] = spec
    return collected, issues


def effective_inputs(playbook: Playbook) -> dict[str, InputSpec]:
    """The inputs `playbook` takes: its own, and those its `inputs: inherit` steps leave unset.

    Raises `PlaybookHasIssuesError` (kind `structure`) for an inherited input whose name is
    taken.
    """
    collected, issues = collect_inputs(playbook)
    if issues:
        raise PlaybookHasIssuesError(issues)
    return collected

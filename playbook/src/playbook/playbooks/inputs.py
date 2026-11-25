# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Check the values a run gives for the inputs of a playbook, and fill in the defaults."""

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
    if isinstance(spec, ChoiceInput):
        listed = value in spec.options and not isinstance(value, bool)
        return None if listed else f"{value!r} is not one of {spec.options}"
    wrong_bool = isinstance(value, bool) and spec.type == "number"
    if wrong_bool or not isinstance(value, _TYPES[spec.type]):
        return f"{value!r} is not a {spec.type}"
    return None


def _null_problem(spec: InputSpec) -> str | None:
    if spec.required:
        return "is required and has no value. Give it a value that is not null"
    if spec.default is not None:
        return (
            f"cannot be null. Give it a value, or leave it out to use the default {spec.default!r}"
        )
    return None


def resolve_inputs(specs: Mapping[str, InputSpec], given: Mapping[str, object]) -> dict:
    """Return the value of each declared input: the given value, or the default.

    A required input needs a value that is not null. An optional input with a default
    takes the default when the run leaves it out, and cannot be null. An optional input
    without a default is null when the run leaves it out.

    Raises:
        PlaybookHasIssuesError: With one `inputs` issue for each value that does not fit.
    """
    issues = [_issue((name,), "is not an input") for name in given if name not in specs]
    resolved = {}
    for name, spec in specs.items():
        resolved[name] = given.get(name, spec.default)
        if resolved[name] is None:
            problem = _null_problem(spec)
        else:
            problem = _type_problem(spec, resolved[name])
        if problem is not None:
            issues.append(_issue((name,), problem))
    if issues:
        raise PlaybookHasIssuesError(issues)
    return resolved


def collect_inputs(playbook: Playbook) -> tuple[dict[str, InputSpec], list[PlaybookIssue]]:
    """Return the inputs of `playbook`, and an issue for each inherited input whose name is taken.

    The issues cover `playbook` alone. A clash inside a nested playbook is an issue of
    that nested playbook.
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
    """Return the inputs of `playbook`: its own, and those its `inputs: inherit` steps leave unset.

    Raises:
        PlaybookHasIssuesError: With one `structure` issue for each inherited input whose
            name is taken.
    """
    collected, issues = collect_inputs(playbook)
    if issues:
        raise PlaybookHasIssuesError(issues)
    return collected

# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Apply the settings a run gives to the steps of a playbook.

A setting written in the `with` of a step is fixed by the author of the playbook. Every
other setting of a block can be given by a run. A run gives these settings by step id,
and they are merged into the `with` of each step before the playbook is checked and run.
"""

from collections.abc import Iterator, Mapping
from copy import deepcopy

from playbook.playbooks.expressions import is_expression
from playbook.playbooks.issues import PlaybookHasIssuesError, PlaybookIssue, SettingPath
from playbook.playbooks.playbook import BlockStep, Playbook, PlaybookStep, Step

Problems = list[tuple[SettingPath, str]]


def apply_settings(playbook: Playbook, settings: Mapping[str, object]) -> Playbook:
    """Return a copy of `playbook` with `settings` merged into the `with` of its steps.

    `settings` maps a step id to the settings of that step. For a block step, these are
    merged into its `with`, nested mappings key by key. For a nested playbook step,
    these are the settings of the nested playbook, by its own step ids.

    Raises:
        PlaybookHasIssuesError: With one `config` issue for each entry that names no
            step, is not a mapping, sets a setting that the playbook sets, or contains
            an expression.
    """
    applied, issues = _apply(playbook, settings, ())
    if issues:
        raise PlaybookHasIssuesError(issues)
    return applied


def _issue(step_path: tuple[str, ...], setting_path: SettingPath, message: str) -> PlaybookIssue:
    return PlaybookIssue(
        kind="config", message=message, step_path=step_path, setting_path=setting_path
    )


def _apply(
    playbook: Playbook, settings: Mapping[str, object], path: tuple[str, ...]
) -> tuple[Playbook, list[PlaybookIssue]]:
    ids = [step.id for step in playbook.steps]
    issues = [
        _issue(path, (key,), f"there is no step called {key!r}. Use one of {ids}")
        for key in settings
        if key not in ids
    ]
    steps = []
    for step in playbook.steps:
        if step.id not in settings:
            steps.append(step)
            continue
        applied, found = _apply_to_step(step, settings[step.id], (*path, step.id))
        steps.append(applied)
        issues.extend(found)
    return playbook.model_copy(update={"steps": steps}), issues


def _apply_to_step(
    step: Step, entry: object, path: tuple[str, ...]
) -> tuple[Step, list[PlaybookIssue]]:
    if not isinstance(entry, Mapping):
        message = (
            f"the settings of a step are a mapping of setting name to value, not {entry!r}. "
            f"Write them as a mapping"
        )
        return step, [_issue(path, (), message)]
    match step:
        case BlockStep():
            merged, problems = _merge(step.with_, entry, ())
            issues = [_issue(path, where, message) for where, message in problems]
            return step.model_copy(update={"with_": merged}), issues
        case PlaybookStep():
            nested, issues = _apply(step.playbook, entry, path)
            return step.model_copy(update={"playbook": nested}), issues


def _merge(
    written: Mapping[str, object], given: Mapping[str, object], where: SettingPath
) -> tuple[dict[str, object], Problems]:
    merged = dict(written)
    problems: Problems = []
    for key, value in given.items():
        path = (*where, key)
        if key not in written:
            merged[key] = deepcopy(value)
            problems.extend(_expression_problems(value, path))
            continue
        fixed = written[key]
        if isinstance(fixed, Mapping) and isinstance(value, Mapping):
            merged[key], inner = _merge(fixed, value, path)
            problems.extend(inner)
            continue
        message = (
            f"the playbook sets this to {fixed!r}, so a run cannot set it. "
            f"Leave it out of the settings"
        )
        problems.append((path, message))
    return merged, problems


def _leaves(value: object, where: SettingPath) -> Iterator[tuple[SettingPath, object]]:
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield from _leaves(item, (*where, key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _leaves(item, (*where, index))
    else:
        yield where, value


def _expression_problems(value: object, where: SettingPath) -> Problems:
    return [
        (path, f"{leaf!r} contains an expression, but a run gives literal values. Write the value")
        for path, leaf in _leaves(value, where)
        if is_expression(leaf)
    ]

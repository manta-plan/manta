# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Playbooks: blocks chained together into a piece of work that can be run."""

from playbook.playbooks.execution import BlockRunner, LocalBlockRunner, execute_playbook
from playbook.playbooks.expressions import ExpressionError
from playbook.playbooks.inputs import effective_inputs, resolve_inputs
from playbook.playbooks.issues import PlaybookHasIssuesError, PlaybookIssue, PlaybookIssueKind
from playbook.playbooks.planner import Planned, PlannedBlock, PlannedGroup, plan
from playbook.playbooks.playbook import BlockStep, Playbook, PlaybookStep, Step
from playbook.playbooks.syntax import BlockStepDoc, InputSpec, PlaybookDoc, PlaybookStepDoc, StepDoc
from playbook.playbooks.validation import find_playbook_issues, raise_for_playbook_issues
from playbook.playbooks.yaml_io import (
    FilePlaybookLoader,
    LoadedPlaybook,
    PlaybookLoader,
    PlaybookLoadError,
    load_playbook,
    parse_doc,
    playbook_from_doc,
    playbook_to_doc,
)

__all__ = [
    "BlockRunner",
    "BlockStep",
    "BlockStepDoc",
    "ExpressionError",
    "FilePlaybookLoader",
    "InputSpec",
    "LoadedPlaybook",
    "LocalBlockRunner",
    "Planned",
    "PlannedBlock",
    "PlannedGroup",
    "Playbook",
    "PlaybookDoc",
    "PlaybookHasIssuesError",
    "PlaybookIssue",
    "PlaybookIssueKind",
    "PlaybookLoadError",
    "PlaybookLoader",
    "PlaybookStep",
    "PlaybookStepDoc",
    "Step",
    "StepDoc",
    "effective_inputs",
    "execute_playbook",
    "find_playbook_issues",
    "load_playbook",
    "parse_doc",
    "plan",
    "playbook_from_doc",
    "playbook_to_doc",
    "raise_for_playbook_issues",
    "resolve_inputs",
]

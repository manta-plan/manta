# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""What a playbook is once read: its inputs, and its steps with their blocks looked up.

A step runs a block or a nested playbook. Each step receives the revision of the step
above it that ran. Expressions are kept as written, and are only evaluated by the
planner (see `planner`), once the input values are known.

This module holds only the description. Reading and writing it lives in `yaml_io`,
checking it in `validation`, planning it in `planner` and running it in `execution`.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import ConfigDict, Field

from playbook.blocks import BlockSpec, RevisionRef
from playbook.playbooks.syntax import InputSpec, Strict

if TYPE_CHECKING:
    from playbook.blocks import Catalogue
    from playbook.playbooks.execution import BlockRunner
    from playbook.playbooks.issues import PlaybookIssue
    from playbook.playbooks.syntax import PlaybookDoc


class _StepBase(Strict):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: str
    if_: str | None = Field(None, alias="if")


class BlockStep(_StepBase):
    """One block, used once, in a playbook."""

    block: BlockSpec
    with_: dict[str, Any] = Field(default_factory=dict, alias="with")


class PlaybookStep(_StepBase):
    """A whole playbook used as a single step in a longer one."""

    playbook: "Playbook"
    with_: dict[str, Any] = Field(default_factory=dict, alias="with")
    inherit: bool = False
    """Whether the inputs this step leaves unset become inputs of the playbook nesting it."""


Step = BlockStep | PlaybookStep


class Playbook(Strict):
    """Steps that run as one piece of work, given values for its inputs."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    initial_dims: frozenset[str] = frozenset()
    """The dimensions the data already has before the first step runs."""
    inputs: dict[str, InputSpec] = Field(default_factory=dict)
    steps: list[Step]

    @classmethod
    def from_yaml(cls, path: str | Path, catalogue: "Catalogue | None" = None) -> "Playbook":
        """Read a playbook from a YAML file."""
        from playbook.playbooks.yaml_io import load_playbook

        return load_playbook(path, catalogue=catalogue)

    def find_issues(self, inputs: dict | None = None) -> "list[PlaybookIssue]":
        """Everything wrong with this playbook, as a list (see `validation`)."""
        from playbook.playbooks.validation import find_playbook_issues

        return find_playbook_issues(self, inputs)

    def raise_for_issues(self, inputs: dict | None = None) -> None:
        """Raise `PlaybookHasIssuesError` if anything is wrong with this playbook."""
        from playbook.playbooks.validation import raise_for_playbook_issues

        raise_for_playbook_issues(self, inputs)

    def to_doc(self) -> "PlaybookDoc":
        """This playbook as a document, ready to save as YAML or send to a browser."""
        from playbook.playbooks.yaml_io import playbook_to_doc

        return playbook_to_doc(self)

    def run(
        self,
        revision: RevisionRef,
        inputs: dict,
        runner: "BlockRunner | None" = None,
    ) -> RevisionRef:
        """Check this playbook against `inputs`, then run it.

        Without a `runner`, every block runs in this process.
        """
        from playbook.playbooks.execution import execute_playbook

        return execute_playbook(self, revision, inputs, runner=runner)


PlaybookStep.model_rebuild()

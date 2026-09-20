# SPDX-FileCopyrightText: 2026 Manta Blocks contributors
#
# SPDX-License-Identifier: MIT

"""What a playbook is: an ordered list of steps, and how they are wired together.

A playbook hands one record along from each step to the next. On top of that, a step
can pull a specific earlier step's result into one of its settings, which is how a
block gets a second data source without it having to be the step immediately before.

Steps can be switched on and off by a condition, and a playbook can be used as a
single step inside a longer one.

This module holds only the description. Checking it, drawing it, and running it live
in `validation`, `graph`, and `execution`.
"""

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from blocks import BlockSpec, DataRecord, MantaBlock, describe_block, resolve_block

if TYPE_CHECKING:
    from blocks import BlockDims, Catalogue
    from playbooks.execution import StepRunner
    from playbooks.graph import PlaybookGraph
    from playbooks.validation import PlaybookIssue

_REF_RE = re.compile(r"^\$\{steps\.([A-Za-z_]\w*)\.([A-Za-z_]\w*)\}$")

REF_TEMPLATE = "${{steps.{step}.{output}}}"
"""How a reference to another step's result is written down."""


class OutputRef(BaseModel):
    """A reference to a named result of an earlier step: `${steps.<step>.<output>}`."""

    model_config = ConfigDict(frozen=True)

    step: str
    output: str = "output"

    @classmethod
    def parse(cls, value: str) -> "OutputRef | None":
        """Read a `${steps.<step>.<output>}` reference, or return None if it isn't one."""
        match = _REF_RE.match(value)
        if match is None:
            return None
        return cls(step=match.group(1), output=match.group(2))

    def as_text(self) -> str:
        """This reference written the way it appears in a playbook file."""
        return REF_TEMPLATE.format(step=self.step, output=self.output)


class When(BaseModel):
    """A condition that decides whether a step runs."""

    model_config = ConfigDict(frozen=True)

    config: str
    """Which setting to look at, e.g. `globals.expansion_mode`."""

    equals: Any
    """The value that setting has to have."""

    def check(self, config: dict) -> bool | None:
        """Whether this condition holds, or None if the setting isn't there at all."""
        node: Any = config
        for part in self.config.split("."):
            if not isinstance(node, dict) or part not in node:
                return None
            node = node[part]
        return node == self.equals


def child_config(parent_config: dict, step_name: str) -> dict:
    """The settings a nested playbook sees.

    A nested playbook gets the settings filed under its step's name. It also inherits
    the outer `globals` unless it has its own, so shared settings do not have to be
    repeated at every level.
    """
    child = dict(parent_config.get(step_name) or {})
    if "globals" not in child and "globals" in parent_config:
        child["globals"] = parent_config["globals"]
    return child


class BlockStep(BaseModel):
    """One block, used once, in a playbook."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    """This step's name: where its settings live, and what it is called in diagrams."""

    block: BlockSpec

    inputs: dict[str, OutputRef] = Field(default_factory=dict)
    """Which earlier step's result feeds each of the block's wired-in settings."""

    when: "When | None" = None
    """If set, the step only runs when this condition holds."""

    def declared_inputs(self) -> frozenset[str]:
        return self.block.inputs

    def declared_outputs(self) -> frozenset[str]:
        return self.block.outputs

    def dims(self, config: dict) -> "BlockDims":
        return self.block.dims


class NestedPlaybookStep(BaseModel):
    """A whole playbook used as a single step in a longer one.

    Anything the inner playbook does not wire up itself is offered to the outer one as
    `<inner step>.<setting>`, so the outer playbook can feed it exactly as it would
    feed a block. The inner playbook's settings live under this step's name.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    playbook: "Playbook"

    inputs: dict[str, OutputRef] = Field(default_factory=dict)
    when: "When | None" = None

    def declared_inputs(self) -> frozenset[str]:
        return self.playbook.unbound_inputs()

    def declared_outputs(self) -> frozenset[str]:
        return frozenset({"output"})

    def dims(self, config: dict) -> "BlockDims":
        """The net effect of everything the inner playbook does, as one step's worth."""
        from blocks import BlockDims

        inner_config = child_config(config, self.name)
        final = fold_dims(
            self.playbook.active(inner_config).steps,
            self.playbook.initial_dims,
            inner_config,
        )
        initial = self.playbook.initial_dims
        return BlockDims(
            requires=initial, adds=final - initial, removes=initial - final
        )


Step = BlockStep | NestedPlaybookStep


def fold_dims(
    steps: "list[Step]", initial: frozenset[str], config: dict
) -> frozenset[str]:
    """The dimensions left after every step in `steps` has run."""
    dims = initial
    for step in steps:
        dims = step.dims(config).apply(dims)
    return dims


def step_label(step: Step) -> str:
    """A short name for a step, for use in messages."""
    if isinstance(step, BlockStep):
        return step.block.label
    return f"playbook {step.playbook.name!r}"


class StepHandle:
    """What `Playbook.add` gives back, so a later step can use this step's result."""

    def __init__(self, name: str) -> None:
        self.name = name

    def out(self, output: str = "output") -> OutputRef:
        return OutputRef(step=self.name, output=output)

    @property
    def output(self) -> OutputRef:
        return self.out()


class Playbook(BaseModel):
    """An ordered list of steps that runs as one piece of work."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    initial_dims: frozenset[str] = frozenset()
    """The dimensions the data already has before the first step runs."""
    steps: list[Step] = Field(default_factory=list)

    def add(
        self,
        name: str,
        block: "type[MantaBlock] | BlockSpec | str",
        inputs: dict[str, OutputRef] | None = None,
        when: When | None = None,
        catalogue: "Catalogue | None" = None,
    ) -> StepHandle:
        """Add a block as the next step, and return a handle to its result.

        The block can be a registered name, a block class, or a description of one
        from a catalogue.
        """
        self.steps.append(
            BlockStep(
                name=name,
                block=as_block_spec(block, catalogue),
                inputs=inputs or {},
                when=when,
            )
        )
        return StepHandle(name=name)

    def add_playbook(
        self,
        name: str,
        playbook: "Playbook",
        inputs: dict[str, OutputRef] | None = None,
        when: When | None = None,
    ) -> StepHandle:
        """Add another playbook as the next step, and return a handle to its result."""
        self.steps.append(
            NestedPlaybookStep(
                name=name, playbook=playbook, inputs=inputs or {}, when=when
            )
        )
        return StepHandle(name=name)

    def active(self, config: dict) -> "Playbook":
        """This playbook as it will actually run: steps whose condition fails are gone.

        Every part of the system asks this one question, so what gets checked, drawn,
        and run can never drift apart.
        """
        return self.model_copy(
            update={
                "steps": [
                    step
                    for step in self.steps
                    if step.when is None or bool(step.when.check(config))
                ]
            }
        )

    def unbound_inputs(self) -> frozenset[str]:
        """Everything this playbook needs fed in from outside.

        These are the settings its steps expect from another block but that nothing
        inside the playbook provides, named `<step>.<setting>`. A step that nests this
        playbook can wire them just like a block's own inputs.
        """
        return frozenset(
            f"{step.name}.{input_name}"
            for step in self.steps
            for input_name in step.declared_inputs()
            if input_name not in step.inputs
        )

    # --- Convenience methods. Each one is the matching module's entry point. ---

    @classmethod
    def from_yaml(
        cls, path: str | Path, catalogue: "Catalogue | None" = None
    ) -> "Playbook":
        """Read a playbook from a YAML file."""
        from playbooks.yaml_io import load_playbook

        return load_playbook(path, catalogue=catalogue)

    def issues(self, config: dict | None = None) -> "list[PlaybookIssue]":
        """Everything wrong with this playbook, as a list to show the user."""
        from playbooks.validation import validate_report

        return validate_report(self, config)

    def validate_playbook(self, config: dict | None = None) -> None:
        """Raise if anything is wrong with this playbook."""
        from playbooks.validation import PlaybookValidationError

        issues = self.issues(config)
        if issues:
            raise PlaybookValidationError(issues)

    def to_doc(self):
        """This playbook as a document, ready to save as YAML or send to a browser."""
        from playbooks.yaml_io import playbook_to_doc

        return playbook_to_doc(self)

    def to_graph(self, config: dict | None = None) -> "PlaybookGraph":
        """This playbook as boxes and arrows, worked out without running anything."""
        from playbooks.graph import playbook_graph

        return playbook_graph(self, config)

    def to_mermaid(self, config: dict | None = None) -> str:
        """A Mermaid diagram of this playbook."""
        from playbooks.graph import graph_to_mermaid

        return graph_to_mermaid(self.to_graph(config))

    def run(
        self,
        record: DataRecord,
        config: dict,
        output_prefix: str,
        runner: "StepRunner | None" = None,
    ) -> DataRecord:
        """Check this playbook and run it.

        Step outputs land under `output_prefix` (see `execution.execute_playbook`).
        Without a `runner`, every block runs in this process.
        """
        from playbooks.execution import execute_playbook

        return execute_playbook(
            self, record, config, output_prefix=output_prefix, runner=runner
        )


def as_block_spec(
    block: "type[MantaBlock] | BlockSpec | str", catalogue: "Catalogue | None" = None
) -> BlockSpec:
    """Turn whatever a caller gave us into a block description a step can hold."""
    if isinstance(block, BlockSpec):
        return block
    if isinstance(block, str):
        return resolve_block(block, catalogue)
    return describe_block(block)


NestedPlaybookStep.model_rebuild()

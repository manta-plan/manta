# SPDX-FileCopyrightText: 2026 Manta Blocks contributors
#
# SPDX-License-Identifier: MIT

"""Playbooks as documents: reading them, writing them, and sending them about.

A playbook document is the written-down form of a playbook. It is the same shape
whether it arrives as a YAML file or as JSON from a browser, so there is only one
thing to keep in step, and `PlaybookDoc.model_json_schema()` tells an editor what a
valid document looks like.

Settings are kept in a separate document, filed by step name plus a `globals` section
that everything can see.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import yaml
from pydantic import BaseModel, Field, model_validator

from blocks import Catalogue
from playbooks.playbook import (
    BlockStep,
    NestedPlaybookStep,
    OutputRef,
    Playbook,
    Step,
    When,
    as_block_spec,
)


class PlaybookLoadError(Exception):
    """Raised when a playbook document cannot be read or makes no sense."""


class WhenDoc(BaseModel):
    """A written-down condition on a step."""

    config: str
    equals: Any


class StepDoc(BaseModel):
    """One step, as written down.

    A step is either a block, named so it can be looked up, or another playbook. That
    playbook can be given as a locator to fetch, or written out in place - which is
    what a browser sends, having nowhere to put a file.
    """

    name: str
    block: str | None = None
    playbook: "str | PlaybookDoc | None" = None
    when: WhenDoc | None = None
    inputs: dict[str, str] = Field(default_factory=dict)
    """Each wired-in setting, and the `${steps.<step>.<output>}` reference feeding it."""

    @model_validator(mode="after")
    def _exactly_one_of_block_or_playbook(self) -> "StepDoc":
        if (self.block is None) == (self.playbook is None):
            raise ValueError("Exactly one of `block` or `playbook` must be set")
        return self


class InitialDataDoc(BaseModel):
    """What the data already looks like before the playbook starts."""

    dims: list[str] = Field(default_factory=list)


class PlaybookDoc(BaseModel):
    """A whole playbook, as written down."""

    name: str
    initial_data: InitialDataDoc = Field(default_factory=InitialDataDoc)
    steps: list[StepDoc] = Field(default_factory=list)


StepDoc.model_rebuild()


@dataclass(frozen=True)
class LoadedPlaybook:
    """A fetched playbook document, and what is needed to follow its own references."""

    key: str
    """A name for this playbook that is the same however it was reached.

    Used to notice a playbook that ends up including itself.
    """

    doc: PlaybookDoc
    loader: "PlaybookLoader"
    """The loader to use for references found inside this document."""


class PlaybookLoader(Protocol):
    """Fetches the playbook a `playbook:` reference points at.

    A reference is not necessarily a file path. The loader that ships here reads files
    relative to the playbook doing the referring, which is all a folder of YAML needs,
    but a system keeping playbooks in a database would look them up there instead.
    """

    def load(self, locator: str) -> LoadedPlaybook: ...


class FilePlaybookLoader:
    """Reads playbooks from files, relative to the one that referred to them."""

    def __init__(self, base: Path | None = None) -> None:
        self._base = base

    def load(self, locator: str) -> LoadedPlaybook:
        path = Path(locator)
        if self._base is not None and not path.is_absolute():
            path = self._base.parent / path
        try:
            raw = yaml.safe_load(path.read_text())
        except OSError as exc:
            raise PlaybookLoadError(
                f"could not read playbook file {path}: {exc}"
            ) from exc
        return LoadedPlaybook(
            key=str(path.resolve()),
            doc=parse_doc(raw, source=str(path)),
            loader=FilePlaybookLoader(base=path),
        )


def parse_doc(raw: object, source: str = "") -> PlaybookDoc:
    """Check a loaded YAML or JSON document really is a playbook."""
    try:
        return PlaybookDoc.model_validate(raw)
    except Exception as exc:
        where = f" {source}" if source else ""
        raise PlaybookLoadError(f"invalid playbook{where}: {exc}") from exc


def playbook_from_doc(
    doc: PlaybookDoc,
    loader: PlaybookLoader | None = None,
    catalogue: Catalogue | None = None,
    _chain: tuple[str, ...] = (),
) -> Playbook:
    """Turn a playbook document into a playbook.

    `loader` fetches any playbooks this one refers to, and defaults to reading files.
    `catalogue` lets blocks that cannot be imported here still be used, described
    rather than loaded.
    """
    loader = loader or FilePlaybookLoader()
    steps: list[Step] = []

    for step_doc in doc.steps:
        inputs = _parse_inputs(step_doc)
        when = (
            When(config=step_doc.when.config, equals=step_doc.when.equals)
            if step_doc.when
            else None
        )

        if step_doc.block is not None:
            try:
                block = as_block_spec(step_doc.block, catalogue)
            except Exception as exc:
                raise PlaybookLoadError(f"step {step_doc.name!r}: {exc}") from exc
            steps.append(
                BlockStep(name=step_doc.name, block=block, inputs=inputs, when=when)
            )
        else:
            child = _nested_playbook(step_doc, loader, catalogue, _chain)
            steps.append(
                NestedPlaybookStep(
                    name=step_doc.name, playbook=child, inputs=inputs, when=when
                )
            )

    return Playbook(
        name=doc.name, initial_dims=frozenset(doc.initial_data.dims), steps=steps
    )


def _parse_inputs(step_doc: StepDoc) -> dict[str, OutputRef]:
    inputs = {}
    for input_name, value in step_doc.inputs.items():
        ref = OutputRef.parse(value)
        if ref is None:
            raise PlaybookLoadError(
                f"step {step_doc.name!r}: input {input_name!r} is set to {value!r}, "
                "which is not a '${steps.<step>.<output>}' reference"
            )
        inputs[input_name] = ref
    return inputs


def _nested_playbook(
    step_doc: StepDoc,
    loader: PlaybookLoader,
    catalogue: Catalogue | None,
    chain: tuple[str, ...],
) -> Playbook:
    """The playbook a nested step refers to, whether fetched or written out in place."""
    if isinstance(step_doc.playbook, PlaybookDoc):
        # Written out in place, so there is nothing to fetch and no way to loop.
        return playbook_from_doc(step_doc.playbook, loader, catalogue, chain)

    locator = str(step_doc.playbook)
    try:
        loaded = loader.load(locator)
    except PlaybookLoadError:
        raise
    except Exception as exc:
        raise PlaybookLoadError(
            f"step {step_doc.name!r}: could not load nested playbook {locator!r}: {exc}"
        ) from exc

    # Checked before following the reference, so a playbook that ends up including
    # itself is reported rather than followed until the process runs out of stack.
    if loaded.key in chain:
        loop = " -> ".join([*chain, loaded.key])
        raise PlaybookLoadError(
            f"step {step_doc.name!r}: circular playbook reference: {loop}"
        )

    return playbook_from_doc(loaded.doc, loaded.loader, catalogue, (*chain, loaded.key))


def playbook_to_doc(playbook: Playbook) -> PlaybookDoc:
    """Write a playbook back out as a document.

    Nested playbooks are written out in place rather than as references, since a
    playbook in memory no longer knows where it was fetched from.
    """
    steps = []
    for step in playbook.steps:
        step_doc = StepDoc(
            name=step.name,
            block=step.block.name if isinstance(step, BlockStep) else None,
            playbook=(
                playbook_to_doc(step.playbook)
                if isinstance(step, NestedPlaybookStep)
                else None
            ),
            when=(
                WhenDoc(config=step.when.config, equals=step.when.equals)
                if step.when
                else None
            ),
            inputs={name: ref.as_text() for name, ref in step.inputs.items()},
        )
        steps.append(step_doc)
    return PlaybookDoc(
        name=playbook.name,
        initial_data=InitialDataDoc(dims=sorted(playbook.initial_dims)),
        steps=steps,
    )


def load_playbook(
    path: str | Path,
    loader: PlaybookLoader | None = None,
    catalogue: Catalogue | None = None,
) -> Playbook:
    """Read a playbook from a YAML file.

    `loader` resolves any nested `playbook:` references, and defaults to reading files
    relative to `path`.
    """
    if loader is None:
        loaded = FilePlaybookLoader().load(str(path))
        return playbook_from_doc(loaded.doc, loaded.loader, catalogue, (loaded.key,))

    loaded = loader.load(str(path))
    return playbook_from_doc(loaded.doc, loaded.loader, catalogue, (loaded.key,))


def load_config(path: str | Path) -> dict:
    """Read a settings file: values filed by step name, plus `globals`."""
    raw = yaml.safe_load(Path(path).read_text())
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise PlaybookLoadError(
            f"settings file {path} has to be a mapping at the top level"
        )
    return raw

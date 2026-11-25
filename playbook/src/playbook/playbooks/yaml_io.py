# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Playbooks as documents: reading them, writing them, and sending them about.

A playbook document has the same shape as a YAML file and as JSON from a browser (see
`syntax`). `playbook_from_doc` resolves each block and fetches each nested playbook, so
a playbook in memory has everything that checking and running it need.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import yaml
from pydantic import ValidationError

from playbook.blocks import BlockNotRegisteredError, BlockUnavailableError, Catalogue, resolve_block
from playbook.playbooks.playbook import BlockStep, Playbook, PlaybookStep, Step
from playbook.playbooks.syntax import (
    BlockStepDoc,
    InitialDataDoc,
    PlaybookDoc,
    PlaybookStepDoc,
    StepDoc,
)


class PlaybookLoadError(Exception):
    """Raised when a playbook document cannot be read or makes no sense."""


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

    def __init__(self, base: Path | None = None, root: Path | None = None) -> None:
        self._base = base
        self._root = root

    def load(self, locator: str) -> LoadedPlaybook:
        path = Path(locator)
        if self._base is not None and not path.is_absolute():
            path = self._base.parent / path

        path = path.resolve()
        root = self._root if self._root is not None else path.parent
        if not path.is_relative_to(root):
            raise PlaybookLoadError(
                f"playbook reference {locator!r} points outside {root}, which is the "
                "directory the first playbook was read from"
            )

        try:
            raw = yaml.safe_load(path.read_text())
        except OSError as exc:
            raise PlaybookLoadError(f"could not read playbook file {path}: {exc}") from exc
        return LoadedPlaybook(
            key=str(path),
            doc=parse_doc(raw, source=str(path)),
            loader=FilePlaybookLoader(base=path, root=root),
        )


def parse_doc(raw: object, source: str = "") -> PlaybookDoc:
    """Check a loaded YAML or JSON document really is a playbook."""
    try:
        return PlaybookDoc.model_validate(raw)
    except ValidationError as exc:
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
    steps = [_step_from_doc(step, loader, catalogue, _chain) for step in doc.steps]
    initial_dims = frozenset(doc.initial_data.dims)
    return Playbook(name=doc.name, initial_dims=initial_dims, inputs=doc.inputs, steps=steps)


def _step_from_doc(
    doc: StepDoc, loader: PlaybookLoader, catalogue: Catalogue | None, chain: tuple[str, ...]
) -> Step:
    match doc:
        case BlockStepDoc():
            shared = doc.model_dump(exclude_unset=True, exclude={"block"})
            try:
                block = resolve_block(doc.block, catalogue)
            except (BlockNotRegisteredError, BlockUnavailableError) as exc:
                raise PlaybookLoadError(f"step {doc.id!r}: {exc}") from exc
            return BlockStep(**shared, block=block)
        case PlaybookStepDoc():
            shared = doc.model_dump(exclude_unset=True, exclude={"playbook", "inputs"})
            child = _nested_playbook(doc, loader, catalogue, chain)
            return PlaybookStep(**shared, playbook=child, inherit=doc.inputs == "inherit")


def _nested_playbook(
    doc: PlaybookStepDoc,
    loader: PlaybookLoader,
    catalogue: Catalogue | None,
    chain: tuple[str, ...],
) -> Playbook:
    """Return the playbook of a nested step, fetched or written out in place."""
    if isinstance(doc.playbook, PlaybookDoc):
        return playbook_from_doc(doc.playbook, loader, catalogue, chain)

    loaded = loader.load(doc.playbook)
    if loaded.key in chain:
        loop = " -> ".join([*chain, loaded.key])
        raise PlaybookLoadError(f"step {doc.id!r}: circular playbook reference: {loop}")
    return playbook_from_doc(loaded.doc, loaded.loader, catalogue, (*chain, loaded.key))


def playbook_to_doc(playbook: Playbook) -> PlaybookDoc:
    """Write a playbook back out as a document.

    Nested playbooks are written out in place rather than as references, since a
    playbook in memory no longer knows where it was fetched from.
    """
    steps = [_step_to_doc(step) for step in playbook.steps]
    initial = {"initial_data": InitialDataDoc(dims=sorted(playbook.initial_dims))}
    return PlaybookDoc(
        name=playbook.name,
        **(initial if playbook.initial_dims else {}),
        inputs=playbook.inputs,
        steps=steps,
    )


def _step_to_doc(step: Step) -> StepDoc:
    match step:
        case BlockStep():
            shared = step.model_dump(exclude_unset=True, exclude={"block"})
            return BlockStepDoc(**shared, block=step.block.name)
        case PlaybookStep():
            shared = step.model_dump(exclude_unset=True, exclude={"playbook", "inherit"})
            inherit = {"inputs": "inherit"} if step.inherit else {}
            return PlaybookStepDoc(**shared, **inherit, playbook=playbook_to_doc(step.playbook))


def load_playbook(
    path: str | Path,
    loader: PlaybookLoader | None = None,
    catalogue: Catalogue | None = None,
) -> Playbook:
    """Read a playbook from a YAML file, or from the place where `loader` finds `path`.

    `loader` resolves any nested `playbook:` references, and defaults to reading files
    relative to `path`.
    """
    loaded = (loader or FilePlaybookLoader()).load(str(path))
    return playbook_from_doc(loaded.doc, loaded.loader, catalogue, (loaded.key,))

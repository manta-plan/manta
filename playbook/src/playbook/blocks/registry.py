# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Which blocks exist, and how to describe them without running them.

Blocks are looked up by name so that a playbook can name a block it cannot import:
each block only works inside its own environment, and no single environment has all
of them. That is also why the catalogue exists. Run

    python -m playbook.blocks <block library module>

once per environment and merge the results, and you get a description of every block
in the system - enough to describe it, offer its settings, and check how it is wired -
without needing an environment that can import them all.

Block libraries (such as `playbook_library`) announce their blocks by calling
`register_lazy` when they are imported, naming the module each block lives in without
importing it. Which libraries a process should know about is either said explicitly or
read from the `MANTA_BLOCK_SOURCES` environment variable; see `load_block_sources`.
"""

import importlib
import os
import re
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from playbook.blocks.core import BlockDims, ConfigSchema, MantaBlock
from playbook.blocks.environments import EnvironmentSpec, current_env

if TYPE_CHECKING:
    from collections.abc import Iterable

_SNAKE_CASE_RE = re.compile(r"(?<!^)(?=[A-Z])")

CATALOGUE_VERSION = 1
"""Bumped when the catalogue's shape changes, so a reader can tell what it has."""

INPUT_MARKER = "x-manta-input"
"""Marks a setting that another block fills in, so no form asks the user for it."""


def _snake_case(name: str) -> str:
    return _SNAKE_CASE_RE.sub("_", name).lower()


class BlockRegistrationError(Exception):
    """Raised when registering a block under a name that is already taken."""


class BlockNotFoundError(Exception):
    """Raised when asking for a block name that nothing has registered."""


class BlockUnavailableError(Exception):
    """Raised when a known block cannot be imported here.

    Usually this means the block's dependencies belong to a different environment
    than the one this process runs in.
    """


class BlockDescription(BaseModel):
    """Everything about a block that can be known without importing it.

    This is what a playbook needs in order to name a block, offer its settings, and
    work out how it is wired, in a process that cannot import it.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    env: str
    manifest: str | None = None
    module: str
    """Where the block's class lives, as `module:Class`."""
    doc: str = ""
    """The first line of the block's docstring, as a one-line summary."""
    dims: BlockDims = BlockDims()
    inputs: frozenset[str] = frozenset()
    outputs: frozenset[str] = frozenset({"output"})
    config_schema: dict = Field(default_factory=dict)
    """The block's settings, as a JSON schema."""

    @field_serializer("dims")
    def _serialise_dims(self, dims: BlockDims) -> dict[str, list[str]]:
        # Sorted, so that two runs of the same environment produce the same file.
        return {
            "requires": sorted(dims.requires),
            "adds": sorted(dims.adds),
            "removes": sorted(dims.removes),
        }

    @field_serializer("inputs", "outputs")
    def _serialise_names(self, names: frozenset[str]) -> list[str]:
        return sorted(names)

    @classmethod
    def for_block(cls, block: type[MantaBlock], name: str) -> "BlockDescription":
        return cls(
            name=name,
            env=block.ENV,
            manifest=block.MANIFEST,
            module=f"{block.__module__}:{block.__qualname__}",
            doc=(block.__doc__ or "").strip().split("\n")[0],
            dims=block.DIMS,
            inputs=block.INPUTS,
            outputs=block.OUTPUTS,
            config_schema=_tag_wired_settings(block.CONFIG.model_json_schema(), block.INPUTS),
        )


def _tag_wired_settings(schema: dict, inputs: frozenset[str]) -> dict:
    """Mark the settings that another block fills in.

    A form built from this schema should skip them: they are connection points in the
    playbook, not something a user types.
    """
    properties = schema.get("properties", {})
    for input_name in inputs:
        if input_name in properties:
            properties[input_name] = {**properties[input_name], INPUT_MARKER: True}
    return schema


class Catalogue(BaseModel):
    """A description of the blocks that could be imported where it was made.

    One environment can rarely import every block, so a full picture is built by
    making a catalogue in each environment and merging them.
    """

    model_config = ConfigDict(frozen=True)

    catalogue_version: int = CATALOGUE_VERSION
    generated_in_env: str | None = None
    blocks: dict[str, BlockDescription] = Field(default_factory=dict)
    environments: dict[str, EnvironmentSpec] = Field(default_factory=dict)


class BlockSpec:
    """A block a playbook can use, whether or not it can be imported here.

    Every step in a playbook holds one of these instead of a block class, so that a
    playbook can be built, read, and dispatched from a process that cannot import the
    blocks it names. Actually running a block needs the real class, and asking for one
    that is not available says so plainly.
    """

    def __init__(
        self, description: BlockDescription, block_cls: type[MantaBlock] | None = None
    ) -> None:
        self.description = description
        self._block_cls = block_cls

    @property
    def name(self) -> str:
        return self.description.name

    @property
    def env(self) -> str:
        return self.description.env

    @property
    def manifest(self) -> str | None:
        return self.description.manifest

    @property
    def dims(self) -> BlockDims:
        return self.description.dims

    @property
    def inputs(self) -> frozenset[str]:
        return self.description.inputs

    @property
    def outputs(self) -> frozenset[str]:
        return self.description.outputs

    @property
    def config_schema(self) -> dict:
        return self.description.config_schema

    @property
    def label(self) -> str:
        """A short name for this block, for use in messages."""
        return self.description.module.rpartition(":")[2] or self.name

    @property
    def available(self) -> bool:
        """Whether this block can actually be run here."""
        return self._block_cls is not None

    def environment(self) -> EnvironmentSpec:
        return EnvironmentSpec(name=self.env, manifest=self.manifest)

    def config_model(self) -> type[ConfigSchema] | None:
        """The block's settings class, if the block can be imported here."""
        return self._block_cls.CONFIG if self._block_cls is not None else None

    def block_class(self) -> type[MantaBlock]:
        """The real block class, for running it."""
        if self._block_cls is None:
            raise BlockUnavailableError(
                f"Block {self.name!r} is described in the catalogue but cannot be "
                f"imported here. It needs the {self.env!r} environment."
            )
        return self._block_cls

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, BlockSpec):
            return NotImplemented
        return self.description == other.description

    def __hash__(self) -> int:
        return hash(self.description)

    def __repr__(self) -> str:
        return f"BlockSpec({self.name!r})"


_REGISTRY: dict[str, type[MantaBlock]] = {}
_LAZY: dict[str, str] = {}

BLOCK_SOURCES_ENV_VAR = "MANTA_BLOCK_SOURCES"
"""Comma-separated modules whose import registers blocks, e.g. `playbook_library`."""


def register_lazy(name: str, locator: str) -> None:
    """Register a block as `module:Class` without importing it.

    This is how a block library announces its blocks: the name becomes known in every
    environment, while the import - and with it the library's heavy dependencies -
    happens only where the block actually runs. Registering the same name with the
    same locator twice is harmless, so a library module can be imported freely.
    """
    if _LAZY.get(name) == locator:
        return
    if name in _REGISTRY or name in _LAZY:
        raise BlockRegistrationError(f"A block is already registered under the name {name!r}")
    _LAZY[name] = locator


def load_block_sources(sources: "Iterable[str] | None" = None) -> list[str]:
    """Import the modules that register blocks, and return their names.

    Without an argument, module names are read from the `MANTA_BLOCK_SOURCES`
    environment variable (comma-separated); unset means there is nothing to load.
    Importing a source module runs its `register_lazy` calls, which is all it takes
    for its blocks to become known here.
    """
    # TODO: replace with packaging entry points once block libraries are published
    # packages, so installing a library is enough for its blocks to be found.
    if sources is None:
        raw = os.environ.get(BLOCK_SOURCES_ENV_VAR, "")
        sources = (part.strip() for part in raw.split(",") if part.strip())
    loaded = []
    for module_name in sources:
        importlib.import_module(module_name)
        loaded.append(module_name)
    return loaded


def register(name: str | None = None):
    """Class decorator that registers a block under `name`.

    Without a name, the class name is used in snake_case, so `MyBlock` becomes
    `my_block`.
    """

    def _decorate(cls: type[MantaBlock]) -> type[MantaBlock]:
        registered_name = name or _snake_case(cls.__name__)
        if registered_name in _REGISTRY or registered_name in _LAZY:
            raise BlockRegistrationError(
                f"A block is already registered under the name {registered_name!r}"
            )
        _REGISTRY[registered_name] = cls
        return cls

    return _decorate


def get_block(name: str) -> type[MantaBlock]:
    """The block class registered under `name`, imported now if not already."""
    if name in _REGISTRY:
        return _REGISTRY[name]

    if name in _LAZY:
        module_name, _, class_name = _LAZY[name].partition(":")
        try:
            module = importlib.import_module(module_name)
        except ImportError as exc:
            raise BlockUnavailableError(
                f"Block {name!r} could not be imported ({exc}). Is the "
                "environment providing its ENV active?"
            ) from exc
        block = getattr(module, class_name)
        _REGISTRY[name] = block
        return block

    raise BlockNotFoundError(
        f"No block registered under {name!r}. Available blocks: {sorted(available_blocks())}"
    )


def block_name(cls: type[MantaBlock]) -> str:
    """The registered name of a block class.

    A block that was never registered has no name to deploy or dispatch it under, so
    this says so rather than guessing one that nothing could look up.
    """
    for name, registered in _REGISTRY.items():
        if registered is cls:
            return name
    for name, locator in _LAZY.items():
        module_name, _, class_name = locator.partition(":")
        if cls.__module__ == module_name and cls.__qualname__ == class_name:
            return name
    raise BlockNotFoundError(
        f"{cls.__name__} is not registered, so it has no name that a playbook could "
        f"refer to it by. Add the `@register(...)` decorator to the class."
    )


def available_blocks() -> dict[str, str]:
    """Every known block name, and where its class lives."""
    known = dict(_LAZY)
    known.update({name: f"{cls.__module__}:{cls.__qualname__}" for name, cls in _REGISTRY.items()})
    return known


def describe_block(cls: type[MantaBlock], name: str | None = None) -> BlockSpec:
    """Describe an imported block class, for use as a playbook step."""
    resolved = name or block_name(cls)
    return BlockSpec(BlockDescription.for_block(cls, resolved), cls)


def resolve_block(name: str, catalogue: Catalogue | None = None) -> BlockSpec:
    """The block registered under `name`, imported if possible.

    If the block cannot be imported here but `catalogue` describes it, the description
    is used instead. That is enough to build, check, draw, and deploy a playbook; only
    running the block itself needs the real class.
    """
    try:
        return describe_block(get_block(name), name)
    except BlockUnavailableError:
        if catalogue is not None and name in catalogue.blocks:
            return BlockSpec(catalogue.blocks[name])
        raise


def catalogue() -> Catalogue:
    """Describe every block that can be imported in this environment.

    Blocks belonging to other environments are left out, since nothing here can read
    their settings; make a catalogue in each environment and merge the results.
    """
    blocks: dict[str, BlockDescription] = {}
    environments: dict[str, EnvironmentSpec] = {}
    for name in sorted(available_blocks()):
        try:
            block = get_block(name)
        except BlockUnavailableError:
            continue
        blocks[name] = BlockDescription.for_block(block, name)
        spec = EnvironmentSpec.for_block(block)
        environments[spec.name] = spec
    return Catalogue(generated_in_env=current_env(), blocks=blocks, environments=environments)


def merge_catalogues(parts: "list[Catalogue] | tuple[Catalogue, ...]") -> Catalogue:
    """Combine catalogues made in different environments into one.

    The same block may appear in more than one part, but only if it is described
    identically; two different blocks under one name would leave a playbook unable to
    say which it meant.
    """
    blocks: dict[str, BlockDescription] = {}
    environments: dict[str, EnvironmentSpec] = {}
    for part in parts:
        for name, description in part.blocks.items():
            existing = blocks.get(name)
            if existing is not None and existing != description:
                raise BlockRegistrationError(
                    f"Block {name!r} is described differently in two catalogues: "
                    f"{existing.module} and {description.module}"
                )
            blocks[name] = description
        for name, spec in part.environments.items():
            existing_env = environments.get(name)
            if existing_env is not None and existing_env != spec:
                raise BlockRegistrationError(
                    f"Environment {name!r} is described differently in two "
                    f"catalogues: {existing_env!r} and {spec!r}"
                )
            environments[name] = spec
    return Catalogue(blocks=blocks, environments=environments)

# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""What a block is: its data handle, its dimension bookkeeping, and its base class.

A block is one unit of work on a model. It reads a datarecord `Revision`, does
something with it, and returns the new `Revision` holding the result. Between
processes a revision travels as a `RevisionRef`, a pointer that needs no datarecord
installed to pass along. Everything a block declares about itself - the environment
it needs, the settings it accepts, the dimensions it works on - lives on the class, so
that other tools can read it without running the block.

Blocks are deliberately unaware of whatever runs them. Running one is a plain method
call; the thing that schedules that call - a workflow engine, a container, a test -
lives outside this package and can be swapped without touching a single block.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.dataclasses import dataclass

if TYPE_CHECKING:
    from datarecord import Revision


class BlockDefinitionError(Exception):
    """Raised when a block class is written in a way that cannot work.

    These are mistakes in the block's own definition, caught as soon as the class is
    created rather than when someone tries to run it.
    """


class BlockRunError(Exception):
    """Raised by a block when a run fails for a reason its user can act on.

    Anything else a block raises is a fault in the block itself. Subclasses name the
    reason, so whoever started the run can report it without reading the message.
    """


class SolveError(BlockRunError):
    """Raised when a model a block built could not be solved to optimality."""


class DataRecordError(BlockRunError):
    """Raised when a block could not read a model from, or write one to, a revision."""


@dataclass(frozen=True)
class RevisionRef:
    """Where a block's data lives, as it travels between processes.

    Only ever a pointer - never the data itself - because it is passed between
    processes and machines, which a loaded model could not survive. `store` names a
    datarecord store, either a local directory or an `s3://` address, and `id` names
    one revision in that store: the fields a datarecord `Revision` serialises to.
    """

    store: str
    id: UUID

    def to_dict(self) -> dict:
        """Turn this pointer into plain data, for sending to another process."""
        return {"store": self.store, "id": str(self.id)}

    @classmethod
    def from_dict(cls, data: dict) -> "RevisionRef":
        """Rebuild a pointer from the plain data `to_dict` produced."""
        return cls(**data)

    @classmethod
    def from_revision(cls, revision: "Revision") -> "RevisionRef":
        """The pointer that carries `revision` to another process."""
        return cls(store=revision.store.uri, id=revision.id)


class BlockDims(BaseModel):
    """Dimensions a block requires on, adds to, and removes from the model data."""

    model_config = ConfigDict(frozen=True)

    requires: frozenset[str] = frozenset()
    adds: frozenset[str] = frozenset()
    removes: frozenset[str] = frozenset()

    def apply(self, dims: frozenset[str]) -> frozenset[str]:
        """The dimensions left after this block has run on `dims`."""
        return (dims - self.removes) | self.adds


class ConfigSchema(BaseModel):
    """Base class for a block's settings.

    Settings can always be given by field name, even where a field also has a
    friendlier display name for the user interface to show.

    A setting the block does not have is refused rather than ignored, so a misspelt
    name is reported instead of silently leaving the default in place. The block's
    JSON schema says the same (`additionalProperties: false`), so this is caught even
    where the block cannot be imported.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class MantaBlock[CONFIG_T: ConfigSchema](ABC):
    """Base class for every block.

    To write a block, subclass this, point `CONFIG` at your settings class, and put
    the work in `run`.

    Give your settings class as the type parameter too, e.g.
    `class MyBlock(MantaBlock[MyBlockConfig]): CONFIG = MyBlockConfig`, so that
    `self.config` is known to be `MyBlockConfig` throughout the subclass.
    """

    ENV: ClassVar[str]
    """The named environment this block needs in order to run."""

    MANIFEST: ClassVar[str | None] = None
    """Third-party blocks only: where to find the environment named by `ENV`.

    Blocks shipped with Manta leave this as `None`, meaning the environment is one of
    the ones Manta itself provides.
    """

    CONFIG: ClassVar[type[ConfigSchema]]
    """The settings class for this block."""

    DIMS: ClassVar[BlockDims] = BlockDims()
    """The dimensions this block requires on, adds to, and removes from the model data."""

    def __init_subclass__(cls, **kwargs: object) -> None:
        """Check a new block class makes sense, as soon as it is written.

        Only classes that actually implement `run` are checked; a subclass that
        leaves `run` abstract is a shared base for other blocks, not a block itself.
        """
        super().__init_subclass__(**kwargs)

        if getattr(cls.run, "__isabstractmethod__", False):
            return

        if not hasattr(cls, "ENV"):
            raise BlockDefinitionError(
                f"{cls.__name__} does not say which environment it needs. Set "
                "`ENV` to the name of an environment."
            )
        if not hasattr(cls, "CONFIG"):
            raise BlockDefinitionError(
                f"{cls.__name__} does not say what settings it accepts. Set "
                "`CONFIG` to a `ConfigSchema` subclass."
            )

    def __init__(self, config: CONFIG_T | dict) -> None:
        self.config: CONFIG_T = cast(
            CONFIG_T,
            config if isinstance(config, self.CONFIG) else self.CONFIG.model_validate(config),
        )

    @abstractmethod
    def run(self, base: "Revision") -> "Revision":
        """Do this block's work on `base`, returning the revision holding the result.

        The result is committed through `base.store`, as a new revision in the input's
        own store, so the caller never has to say where it should go.
        """

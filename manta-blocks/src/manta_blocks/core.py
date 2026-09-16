# SPDX-FileCopyrightText: 2026 Manta Blocks contributors
#
# SPDX-License-Identifier: MIT

"""What a block is: its data handle, its dimension bookkeeping, and its base class.

A block is one unit of work on a model. It reads a `DataRecord` (a pointer to where
the data lives), does something with it, and returns a new `DataRecord` pointing at
the result. Everything a block declares about itself - the environment it needs, the
settings it accepts, the dimensions it works on - lives on the class, so that other
tools can read it without running the block.
"""

import inspect
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar, cast, get_args

from prefect import Flow, flow
from pydantic import BaseModel, ConfigDict
from pydantic.dataclasses import dataclass

if TYPE_CHECKING:
    from collections.abc import Iterable


class BlockDefinitionError(Exception):
    """Raised when a block class is written in a way that cannot work.

    These are mistakes in the block's own definition, caught as soon as the class is
    created rather than when someone tries to run it.
    """


@dataclass
class DataRecord:
    """Where a block's data lives.

    Only ever a pointer - never the data itself - because a record is passed between
    processes and machines, which a loaded model could not survive.
    """

    url: str

    def to_dict(self) -> dict:
        """Turn this record into plain data, for sending to another process."""
        return {"url": self.url}

    @classmethod
    def from_dict(cls, data: dict) -> "DataRecord":
        """Rebuild a record from the plain data `to_dict` produced."""
        return cls(**data)


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
    """

    model_config = ConfigDict(populate_by_name=True)


def _accepts_record(annotation: object) -> bool:
    """Whether a settings field can hold a `DataRecord`."""
    if annotation is DataRecord:
        return True
    return any(arg is DataRecord for arg in get_args(annotation))


class MantaBlock[CONFIG_T: ConfigSchema](ABC):
    """Base class for every block.

    To write a block, subclass this, point `CONFIG` at your settings class, and put
    the work in `flow`. You can split that work into as many Prefect `task` methods
    as you like and call them from `flow`.

    Give your settings class as the type parameter too, e.g.
    `class MyBlock(MantaBlock[MyBlockConfig]): CONFIG = MyBlockConfig`, so that
    `self.config` is known to be `MyBlockConfig` throughout the subclass.
    """

    ENV: ClassVar[str]
    """The pixi environment this block needs in order to run."""

    MANIFEST: ClassVar[str | None] = None
    """Third-party blocks only: where to find the environment named by `ENV`.

    Today that is a path to a pixi manifest, used as
    `pixi run --manifest-path <MANIFEST> -e <ENV>`. Blocks shipped with Manta leave
    this as `None`, meaning this project's own pixi.toml.
    """

    CONFIG: ClassVar[type[ConfigSchema]]
    """The settings class for this block."""

    DIMS: ClassVar[BlockDims] = BlockDims()
    """The dimensions this block requires on, adds to, and removes from the model data."""

    INPUTS: ClassVar[frozenset[str]] = frozenset()
    """Settings that are filled in by another block's output rather than by the user.

    Each name here must be a field of `CONFIG` that can hold a `DataRecord` and has a
    default, since the block also has to be usable with nothing wired to it. These are
    extra data sources, on top of the record handed along from the previous step.
    """

    OUTPUTS: ClassVar[frozenset[str]] = frozenset({"output"})
    """The names of the results this block offers to later blocks in a playbook."""

    def __init_subclass__(cls, **kwargs: object) -> None:
        """Check a new block class makes sense, as soon as it is written.

        Only classes that actually implement `flow` are checked; a subclass that
        leaves `flow` abstract is a shared base for other blocks, not a block itself.
        """
        super().__init_subclass__(**kwargs)

        if getattr(cls.flow, "__isabstractmethod__", False):
            return

        if not hasattr(cls, "ENV"):
            raise BlockDefinitionError(
                f"{cls.__name__} does not say which environment it needs. Set "
                "`ENV` to the name of a pixi environment."
            )
        if not hasattr(cls, "CONFIG"):
            raise BlockDefinitionError(
                f"{cls.__name__} does not say what settings it accepts. Set "
                "`CONFIG` to a `ConfigSchema` subclass."
            )

        fields = cls.CONFIG.model_fields
        for input_name in sorted(cls.INPUTS):
            field = fields.get(input_name)
            if field is None:
                raise BlockDefinitionError(
                    f"{cls.__name__} lists {input_name!r} in INPUTS, but "
                    f"{cls.CONFIG.__name__} has no such setting. Every input is "
                    f"filled into a setting of the same name (settings: "
                    f"{sorted(fields)})."
                )
            if not _accepts_record(field.annotation):
                raise BlockDefinitionError(
                    f"{cls.__name__} lists {input_name!r} in INPUTS, so that setting "
                    f"has to be able to hold a DataRecord, but "
                    f"{cls.CONFIG.__name__}.{input_name} is typed as "
                    f"{field.annotation}."
                )
            if field.is_required():
                raise BlockDefinitionError(
                    f"{cls.__name__} lists {input_name!r} in INPUTS, so that setting "
                    f"needs a default: the block must still be usable when nothing "
                    f"is wired to it."
                )

    def __init__(self, config: CONFIG_T | dict) -> None:
        self.config: CONFIG_T = cast(
            CONFIG_T,
            config
            if isinstance(config, self.CONFIG)
            else self.CONFIG.model_validate(config),
        )

    @classmethod
    def merge_config(
        cls, config: "ConfigSchema | dict", inputs: "dict[str, DataRecord]"
    ) -> ConfigSchema:
        """The block's settings with any wired-in records filled into place.

        The result is checked in full, so a record wired to the wrong kind of setting
        is reported here rather than surfacing much later inside the block.
        """
        base = config.model_dump() if isinstance(config, BaseModel) else dict(config)
        return cls.CONFIG.model_validate({**base, **inputs})

    @classmethod
    def as_flow(
        cls,
        config: "ConfigSchema | dict",
        name: str | None = None,
        input_names: "Iterable[str]" = (),
    ) -> Flow:
        """Wrap this block as a named Prefect flow, ready to run with `config`.

        The name is per-use rather than per-class, so one block can appear several
        times in a playbook without every appearance sharing a single flow name.

        `input_names` lists the settings this particular call will have wired to it.
        Prefect rebuilds a flow's arguments from the function signature, so passing
        wired inputs through a `**inputs` catch-all would collapse them into one
        dict-shaped argument, and Prefect would no longer see them individually.
        Giving each of this call's inputs its own keyword argument keeps them visible,
        without inventing placeholders for inputs this call never passes.
        """
        input_names = sorted(input_names)

        def _run(record: DataRecord, **inputs: DataRecord) -> DataRecord:
            # A fresh instance per run: a block never carries state between runs, and
            # the same flow object can safely be called more than once.
            return cls(cls.merge_config(config, inputs)).flow(record)

        if input_names:
            _run.__signature__ = inspect.Signature(
                [inspect.Parameter("record", inspect.Parameter.POSITIONAL_OR_KEYWORD)]
                + [
                    inspect.Parameter(input_name, inspect.Parameter.KEYWORD_ONLY)
                    for input_name in input_names
                ]
            )

        return flow(name=name or cls.__name__)(_run)

    @abstractmethod
    def flow(self, record: DataRecord) -> DataRecord:
        """Do this block's work, returning a record pointing at the result."""

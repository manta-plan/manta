# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""The environments blocks run in.

An environment is a name plus, optionally, where to find it: a dependency manifest
for a third-party block, or a container image. Nothing here resolves those pointers;
that is the job of whatever provides the environments and runs the blocks, which
lives outside this package.

Environments are not configured up front. Each block says which one it needs, so the
set of environments a playbook uses is worked out from the blocks in it.
"""

import os
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, model_validator

if TYPE_CHECKING:
    from playbook.blocks.core import MantaBlock


class EnvironmentConflictError(Exception):
    """Raised when two blocks want the same environment name but describe it differently."""


def current_env() -> str:
    """The environment this process is running in.

    `MANTA_ENV` wins if set, as an explicit override. Otherwise pixi-style
    environments announce themselves via `PIXI_ENVIRONMENT_NAME`, and outside any
    managed environment this is `"default"`.
    """
    return os.environ.get("MANTA_ENV") or os.environ.get("PIXI_ENVIRONMENT_NAME", "default")


class EnvironmentSpec(BaseModel):
    """One environment a block can run in.

    At most one of `manifest` or `image` may be set. `manifest` says where a
    third-party block's own dependency manifest lives; `image` names a container
    image that already provides the environment. With neither set, the environment
    is one of the ones Manta itself provides, known by name alone.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    manifest: str | None = None
    image: str | None = None

    @model_validator(mode="after")
    def _not_both_manifest_and_image(self) -> "EnvironmentSpec":
        if self.manifest is not None and self.image is not None:
            raise ValueError("At most one of `manifest` or `image` may be set")
        return self

    @classmethod
    def for_block(cls, block: "type[MantaBlock]") -> "EnvironmentSpec":
        """The environment the given block says it needs."""
        return cls(name=block.ENV, manifest=block.MANIFEST)

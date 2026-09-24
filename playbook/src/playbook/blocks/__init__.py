# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Blocks: single units of work on a model, and everything needed to describe them."""

from playbook.blocks.core import (
    BlockDefinitionError,
    BlockDims,
    ConfigSchema,
    DataRecord,
    MantaBlock,
)
from playbook.blocks.environments import EnvironmentConflictError, EnvironmentSpec, current_env
from playbook.blocks.registry import (
    BlockDescription,
    BlockNotRegisteredError,
    BlockRegistrationError,
    BlockSpec,
    BlockUnavailableError,
    Catalogue,
    available_blocks,
    catalogue,
    describe_block,
    get_block,
    load_block_sources,
    merge_catalogues,
    register,
    register_lazy,
    resolve_block,
)

__all__ = [
    "BlockDefinitionError",
    "BlockDescription",
    "BlockDims",
    "BlockNotRegisteredError",
    "BlockRegistrationError",
    "BlockSpec",
    "BlockUnavailableError",
    "Catalogue",
    "ConfigSchema",
    "DataRecord",
    "EnvironmentConflictError",
    "EnvironmentSpec",
    "MantaBlock",
    "available_blocks",
    "catalogue",
    "current_env",
    "describe_block",
    "get_block",
    "load_block_sources",
    "merge_catalogues",
    "register",
    "register_lazy",
    "resolve_block",
]

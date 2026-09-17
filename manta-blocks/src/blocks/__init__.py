# SPDX-FileCopyrightText: 2026 Manta Blocks contributors
#
# SPDX-License-Identifier: MIT

"""Blocks: single units of work on a model, and everything needed to describe them."""

from blocks.core import (
    BlockDefinitionError,
    BlockDims,
    ConfigSchema,
    DataRecord,
    MantaBlock,
)
from blocks.environments import EnvironmentConflictError, EnvironmentSpec, current_env
from blocks.registry import (
    BlockDescription,
    BlockNotFoundError,
    BlockRegistrationError,
    BlockSpec,
    BlockUnavailableError,
    Catalogue,
    available_blocks,
    catalogue,
    describe_block,
    get_block,
    merge_catalogues,
    register,
    resolve_block,
)

__all__ = [
    "BlockDefinitionError",
    "BlockDescription",
    "BlockDims",
    "BlockNotFoundError",
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
    "merge_catalogues",
    "register",
    "resolve_block",
]

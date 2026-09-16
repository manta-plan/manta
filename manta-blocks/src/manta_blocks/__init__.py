# SPDX-FileCopyrightText: 2026 Manta Blocks contributors
#
# SPDX-License-Identifier: MIT

"""Blocks: single units of work on a model, and everything needed to describe them."""

from manta_blocks.core import (
    BlockDefinitionError,
    BlockDims,
    ConfigSchema,
    DataRecord,
    MantaBlock,
)
from manta_blocks.deployment import (
    Deployment,
    DeploymentPlan,
    deployment_path,
    deployment_slug,
)
from manta_blocks.environments import (
    EnvironmentConflictError,
    EnvironmentSpec,
    current_env,
)
from manta_blocks.records import (
    RecordStorageError,
    is_s3_url,
    sibling_url,
    stage,
    stage_output,
)
from manta_blocks.registry import (
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
    "BlockNotFoundError",
    "BlockRegistrationError",
    "BlockSpec",
    "BlockUnavailableError",
    "Catalogue",
    "ConfigSchema",
    "DataRecord",
    "Deployment",
    "DeploymentPlan",
    "EnvironmentConflictError",
    "EnvironmentSpec",
    "MantaBlock",
    "RecordStorageError",
    "available_blocks",
    "catalogue",
    "current_env",
    "deployment_path",
    "deployment_slug",
    "describe_block",
    "get_block",
    "is_s3_url",
    "load_block_sources",
    "merge_catalogues",
    "register",
    "register_lazy",
    "resolve_block",
    "sibling_url",
    "stage",
    "stage_output",
]

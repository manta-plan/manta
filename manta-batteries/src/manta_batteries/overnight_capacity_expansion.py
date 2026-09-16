# SPDX-FileCopyrightText: 2026 Manta Blocks contributors
#
# SPDX-License-Identifier: MIT

import pypsa
from manta_blocks.core import BlockDims, ConfigSchema, DataRecord, MantaBlock
from prefect import task
from pydantic import Field

from manta_batteries.pypsa_configs import PyPSAOptimizeSchema
from manta_batteries.pypsa_helpers import optimize_network, patch_record, to_network


class OvernightCapacityExpansionConfig(ConfigSchema):
    optimize_config: PyPSAOptimizeSchema = Field(default_factory=PyPSAOptimizeSchema)


class OvernightCapacityExpansion(MantaBlock[OvernightCapacityExpansionConfig]):
    """Decide what to build, treating the whole model as one moment in time."""

    ENV = "pypsa"
    CONFIG = OvernightCapacityExpansionConfig
    DIMS = BlockDims(requires=frozenset({"snapshot"}))

    @task
    def optimize(self, n: pypsa.Network) -> pypsa.Network:
        return optimize_network(n, self.config.optimize_config)

    def flow(self, record: DataRecord) -> DataRecord:
        n_new = self.optimize.submit(to_network(record)).result()
        return patch_record(record, n_new, "overnight_capacity_expansion")

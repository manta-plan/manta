# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

import pypsa
from playbook.blocks.core import BlockDims, ConfigSchema, DataRecord, MantaBlock
from pydantic import Field

from playbook_library.pypsa_configs import PyPSAOptimizeSchema
from playbook_library.pypsa_helpers import optimize_network, to_network, write_network


class OvernightCapacityExpansionConfig(ConfigSchema):
    optimize_config: PyPSAOptimizeSchema = Field(default_factory=PyPSAOptimizeSchema)


class OvernightCapacityExpansion(MantaBlock[OvernightCapacityExpansionConfig]):
    """Decide what to build, treating the whole model as one moment in time."""

    ENV = "pypsa"
    CONFIG = OvernightCapacityExpansionConfig
    DIMS = BlockDims(requires=frozenset({"snapshot"}))

    def optimize(self, n: pypsa.Network) -> pypsa.Network:
        return optimize_network(n, self.config.optimize_config)

    def run(self, record: DataRecord, output_base: str) -> DataRecord:
        n_new = self.optimize(to_network(record))
        return write_network(n_new, output_base)

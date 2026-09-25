# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

import pypsa
from playbook.blocks.core import BlockDims, ConfigSchema, DataRecord, MantaBlock
from pydantic import Field

from playbook_library.pypsa_configs import PyPSAOptimizeSchema
from playbook_library.pypsa_helpers import (
    freeze_period,
    optimize_network,
    to_network,
    write_network,
)


class MyopicCapacityExpansionConfig(ConfigSchema):
    optimize_config: PyPSAOptimizeSchema = Field(default_factory=PyPSAOptimizeSchema)


class MyopicCapacityExpansion(MantaBlock[MyopicCapacityExpansionConfig]):
    """Decide what to build one investment period at a time, in order.

    Each period sees only what came before it, so decisions are made without
    knowledge of later periods - closer to how investment actually happens.
    """

    ENV = "pypsa"
    CONFIG = MyopicCapacityExpansionConfig
    DIMS = BlockDims(requires=frozenset({"snapshot", "investment_period"}))

    def optimize_period(self, n: pypsa.Network, snapshots) -> pypsa.Network:
        # One period at a time, so each solve is a single-period problem even though
        # the network as a whole covers several. What earlier periods built has
        # already been fixed in place by the time this runs.
        return optimize_network(
            n,
            self.config.optimize_config,
            snapshots=snapshots,
            multi_investment_periods=False,
        )

    def run(self, record: DataRecord, output_base: str) -> DataRecord:
        n_new = to_network(record)
        for period in n_new.periods:
            period_snapshots = n_new.snapshots[n_new.snapshots.get_level_values("period") == period]
            n_new = self.optimize_period(n_new, period_snapshots)
            freeze_period(n_new, period)

        return write_network(n_new, output_base)

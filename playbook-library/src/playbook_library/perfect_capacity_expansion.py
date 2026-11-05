# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

import pypsa
from playbook.blocks.core import BlockDims, DataRecord, MantaBlock
from pydantic import Field

from playbook_library.pypsa_configs import PyPSAOptimizeSchema, TimeAggregatedConfig
from playbook_library.pypsa_helpers import optimize_network, solve_and_write, to_network


class PerfectCapacityExpansionConfig(TimeAggregatedConfig):
    optimize_config: PyPSAOptimizeSchema = Field(default_factory=PyPSAOptimizeSchema)


class PerfectCapacityExpansion(MantaBlock[PerfectCapacityExpansionConfig]):
    """Decide what to build in every investment period at once, with perfect foresight.

    All periods are solved as one problem, so each decision knows about every later
    period.
    """

    ENV = "pypsa"
    CONFIG = PerfectCapacityExpansionConfig
    DIMS = BlockDims(requires=frozenset({"snapshot", "period"}))

    def optimize(self, n: pypsa.Network) -> pypsa.Network:
        return optimize_network(n, self.config.optimize_config, multi_investment_periods=True)

    def run(self, record: DataRecord) -> DataRecord:
        n = to_network(record)
        return solve_and_write(n, record, self.optimize, self.config.time_aggregation, True)[1]

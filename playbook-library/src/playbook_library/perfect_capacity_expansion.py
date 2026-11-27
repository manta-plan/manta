# SPDX-FileCopyrightText: Manta contributors
#
# SPDX-License-Identifier: Apache-2.0

import pypsa
from datarecord import Revision
from playbook.blocks.core import BlockDims, ConfigSchema, MantaBlock
from pydantic import Field

from playbook_library.pypsa_configs import PyPSAOptimizeSchema
from playbook_library.pypsa_helpers import optimize_network, to_network, write_network


class PerfectCapacityExpansionConfig(ConfigSchema):
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

    def run(self, base: Revision) -> Revision:
        n_new = self.optimize(to_network(base))
        return write_network(n_new, base, results_only=True)

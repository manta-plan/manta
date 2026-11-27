# SPDX-FileCopyrightText: Manta contributors
#
# SPDX-License-Identifier: Apache-2.0

import pypsa
from datarecord import Revision
from playbook.blocks.core import BlockDims, MantaBlock

from playbook_library.pypsa_configs import PyPSAOptimizeBlockConfig
from playbook_library.pypsa_helpers import optimize_network, solve_and_write, to_network


class PerfectCapacityExpansionConfig(PyPSAOptimizeBlockConfig):
    pass


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
        n = to_network(base)
        return solve_and_write(n, base, self.optimize, self.config.time_aggregation, True)[1]

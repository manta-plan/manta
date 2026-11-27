# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

from typing import Annotated

import pypsa
from datarecord import Revision
from playbook.blocks import RecordDimCoord
from playbook.blocks.core import BlockDims, MantaBlock
from pydantic import Field

from playbook_library.pypsa_configs import PyPSAOptimizeBlockConfig
from playbook_library.pypsa_helpers import (
    investment_periods,
    optimize_network,
    remove_unbuilt_cohorts,
    solve_and_write,
    to_network,
)


class OvernightCapacityExpansionConfig(PyPSAOptimizeBlockConfig):
    period: Annotated[int, RecordDimCoord("period")] | None = Field(default=None)
    """The investment period to build for, in a model with investment periods.

    None takes the last one. A model without investment periods is solved whole."""


class OvernightCapacityExpansion(MantaBlock[OvernightCapacityExpansionConfig]):
    """Decide what to build, treating the whole model as one moment in time.

    In a model with investment periods, that moment is one period, built from what
    exists alone: the cohorts that only an earlier period could have built are left out.
    """

    ENV = "pypsa"
    CONFIG = OvernightCapacityExpansionConfig
    DIMS = BlockDims(requires=frozenset({"snapshot"}))

    def optimize(self, n: pypsa.Network) -> pypsa.Network:
        return optimize_network(
            n, self.config.optimize_config, multi_investment_periods=n.has_periods
        )

    def run(self, base: Revision) -> Revision:
        periods = investment_periods(base)
        if periods:
            period = periods[-1] if self.config.period is None else self.config.period
            if period not in periods:
                raise ValueError(f"The model has no investment period {period}: {periods}.")
            n = to_network(base, select={"period": [period]})
            remove_unbuilt_cohorts(n)
        else:
            n = to_network(base)
        return solve_and_write(n, base, self.optimize, self.config.aggregation, n.has_periods)[1]

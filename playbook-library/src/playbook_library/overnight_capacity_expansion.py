# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

import pypsa
from playbook.blocks.core import BlockDims, ConfigSchema, DataRecord, MantaBlock
from pydantic import Field

from playbook_library.pypsa_configs import PyPSAOptimizeSchema
from playbook_library.pypsa_helpers import (
    investment_periods,
    optimize_network,
    remove_unbuilt_cohorts,
    to_network,
    write_network,
)


class OvernightCapacityExpansionConfig(ConfigSchema):
    optimize_config: PyPSAOptimizeSchema = Field(default_factory=PyPSAOptimizeSchema)
    period: int | None = None
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
        multi_investment_periods = not n.investment_periods.empty
        return optimize_network(
            n, self.config.optimize_config, multi_investment_periods=multi_investment_periods
        )

    def run(self, record: DataRecord) -> DataRecord:
        periods = investment_periods(record)
        if periods:
            period = periods[-1] if self.config.period is None else self.config.period
            if period not in periods:
                raise ValueError(f"The model has no investment period {period}: {periods}.")
            n = to_network(record, select={"period": [period]})
            remove_unbuilt_cohorts(n)
        else:
            n = to_network(record)
        return write_network(self.optimize(n), record, results_only=True)

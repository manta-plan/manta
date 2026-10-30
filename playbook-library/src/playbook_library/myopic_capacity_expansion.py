# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

import pypsa
from playbook.blocks.core import BlockDims, ConfigSchema, DataRecord, MantaBlock
from pydantic import Field

from playbook_library.pypsa_configs import PyPSAOptimizeSchema
from playbook_library.pypsa_helpers import (
    BUILT_COMPONENTS,
    investment_periods,
    nominal_attr,
    optimize_network,
    remove_unbuilt_cohorts,
    to_network,
    write_network,
)


class MyopicCapacityExpansionConfig(ConfigSchema):
    optimize_config: PyPSAOptimizeSchema = Field(default_factory=PyPSAOptimizeSchema)


class MyopicCapacityExpansion(MantaBlock[MyopicCapacityExpansionConfig]):
    """Decide what to build one investment period at a time, in order.

    Each period sees only what came before it, so decisions are made without
    knowledge of later periods - closer to how investment actually happens. No period
    keeps a cohort of an earlier build year that an earlier period solved did not build,
    so the first period starts from what exists alone.

    Each solved period is written as a revision of its own, a child of the previous
    period's, adding that period's results to those before it. The record returned points
    at the last period's revision, which holds the results of every period.
    """

    ENV = "pypsa"
    CONFIG = MyopicCapacityExpansionConfig
    DIMS = BlockDims(requires=frozenset({"snapshot", "period"}))

    @staticmethod
    def add_brownfield(n: pypsa.Network, previous: pypsa.Network) -> None:
        """Carry what `previous` built into `n`, the network of the next investment period.

        Every extendable asset of an earlier build year that was active in the investment
        period of `previous` keeps the capacity built there and can no longer be extended,
        whatever its lifetime.
        """
        (period,) = n.investment_periods
        for c in n.components[BUILT_COMPONENTS]:
            attr = nominal_attr(c.name)
            static = c.static
            active = previous.c[c.name].get_active_assets(previous.investment_periods)
            before = previous.c[c.name].static[active]
            earlier = static.index[static[attr + "_extendable"] & (static.build_year < period)]
            fixed = earlier.intersection(before.index)
            static.loc[fixed, attr] = before.loc[fixed, attr + "_opt"]
            static.loc[fixed, attr + "_extendable"] = False

    def optimize(self, n: pypsa.Network) -> pypsa.Network:
        return optimize_network(n, self.config.optimize_config, multi_investment_periods=True)

    def run(self, record: DataRecord) -> DataRecord:
        written = record
        previous = None
        for period in investment_periods(record):
            n_period = to_network(record, select={"period": [period]})
            if previous is not None:
                self.add_brownfield(n_period, previous)
            remove_unbuilt_cohorts(n_period)
            previous = self.optimize(n_period)
            written = write_network(previous, written, results_only=True)
        return written

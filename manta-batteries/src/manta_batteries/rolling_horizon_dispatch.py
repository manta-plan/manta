# SPDX-FileCopyrightText: 2026 Manta Blocks contributors
#
# SPDX-License-Identifier: MIT

import pypsa
from manta_blocks.core import BlockDims, ConfigSchema, DataRecord, MantaBlock
from prefect import task
from pydantic import Field

from manta_batteries.pypsa_configs import PyPSAOptimizeRollingHorizonConfig
from manta_batteries.pypsa_helpers import (
    apply_optimised_capacities,
    patch_record,
    to_network,
)


class RollingHorizonDispatchConfig(ConfigSchema):
    optimize_config: PyPSAOptimizeRollingHorizonConfig = Field(
        default_factory=PyPSAOptimizeRollingHorizonConfig
    )
    capacity_source: DataRecord | None = Field(
        default=None, title="Capacity data source"
    )
    """Where the capacities to dispatch against come from.

    Normally wired to a capacity-expansion block earlier in the playbook. Left unset,
    the block dispatches against whatever capacities the model already has.
    """


class RollingHorizonDispatch(MantaBlock[RollingHorizonDispatchConfig]):
    """Decide how to run a system, a stretch of time at a time."""

    ENV = "pypsa"
    CONFIG = RollingHorizonDispatchConfig
    DIMS = BlockDims(requires=frozenset({"snapshot"}))
    INPUTS = frozenset({"capacity_source"})

    @task
    def optimize(self, n: pypsa.Network) -> pypsa.Network:
        n.optimize.optimize_with_rolling_horizon(
            **self.config.optimize_config.model_dump()
        )
        return n

    def flow(self, record: DataRecord) -> DataRecord:
        n_new = to_network(record)
        if self.config.capacity_source is not None:
            apply_optimised_capacities(n_new, to_network(self.config.capacity_source))

        n_new = self.optimize.submit(n_new).result()
        return patch_record(record, n_new, "rolling_horizon_dispatch")

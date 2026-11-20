# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

from typing import Annotated, Self

import pandas as pd
import pypsa
from datarecord import Revision
from playbook.blocks import RecordDimCoord
from playbook.blocks.core import BlockDims, MantaBlock
from pydantic import Field, model_validator

from playbook_library.pypsa_configs import PyPSAFixedCapacityBlockConfig
from playbook_library.pypsa_helpers import (
    fixed_capacity_model,
    optimize_network,
    restarting_storage,
    selected_periods,
    to_network,
    write_series,
)
from playbook_library.pypsa_spatial_aggregation import aggregate_network, expand_network
from playbook_library.pypsa_time_aggregation import snapshot_map


class WaterValueCalculationConfig(PyPSAFixedCapacityBlockConfig):
    carriers: list[Annotated[str, RecordDimCoord("carrier")]] = Field(min_length=1)
    """Carriers of the stores to value, such as `H2`."""

    @model_validator(mode="after")
    def solves_one_period_at_a_time(self) -> Self:
        if self.optimize_config.multi_investment_periods:
            raise ValueError("A water value solves one investment period at a time.")
        return self


class WaterValueCalculation(MantaBlock[WaterValueCalculationConfig]):
    """Price the energy in long-duration stores, so a rolling horizon dispatch keeps it for later.

    Each investment period of `periods` is solved whole, with the capacities a solve of the
    record decided, and gives the marginal price at each store's bus: the value of energy
    kept in the store, its water value. Solved by a coarse time aggregation, such as one
    snapshot a month, it stands for an owner who knows only a rough forecast of the year.
    Each store of `carriers` then takes its water value as its `marginal_cost` at every
    snapshot, the one input this block writes. A rolling horizon dispatch of the result
    sees what energy in the store is worth
    beyond each of its own windows. Each store keeps its own `marginal_cost` at the
    snapshots of the other periods. Solved by an aggregation, the prices of a merged bus
    apply to each of its buses, and those of a time cluster to each of its snapshots. With
    `load_shedding`, the solve sheds load as a dispatch of the same setting does, and the
    written revision holds the water values alone, without the load-shedding generators.
    """

    ENV = "pypsa"
    CONFIG = WaterValueCalculationConfig
    DIMS = BlockDims(requires=frozenset({"snapshot"}))

    def valued_stores(self, n: pypsa.Network) -> pd.Series:
        """Return the bus of each store of `n` of `carriers`, by store name.

        Raises `ValueError` if a carrier has no store, or a store of them is cyclic. Each
        window of the rolling horizon dispatch that uses the values would restart it by
        itself, so its water value would not carry its energy beyond a window.
        """
        stores = n.stores[n.stores.carrier.isin(self.config.carriers)]
        missing = sorted(set(self.config.carriers) - set(stores.carrier))
        if missing:
            raise ValueError(f"The model has no stores of the carriers {missing}.")
        restarting = stores.index[restarting_storage(stores, "e", False)]
        if not restarting.empty:
            raise ValueError(
                f"The stores {restarting.tolist()} restart: a rolling horizon dispatch restarts "
                "them within each window, so a water value gives them no seasonal behaviour."
            )
        return stores.bus

    def marginal_prices(self, n: pypsa.Network, rev: Revision) -> pd.DataFrame:
        """Solve `n`, built from `rev`, by `aggregation` in one go; return bus prices.

        The prices cover every bus and snapshot of `n`, per unit of energy.
        """
        aggregation = self.config.aggregation
        n_c = aggregate_network(n, rev, aggregation)
        solved = optimize_network(n_c, self.config.optimize_config)
        prices = expand_network(solved, n, rev, aggregation).buses_t.marginal_price
        if aggregation.snapshot is None:
            return prices
        representatives = snapshot_map(n, rev, aggregation.snapshot)
        return prices.loc[representatives.to_numpy()].set_axis(representatives.index)

    def period_values(self, base: Revision, period: int | None) -> pd.DataFrame:
        """Return the water value of each store of `carriers` over `period`, or all if None."""
        config = self.config.model_copy(update={"periods": None if period is None else [period]})
        model, n = fixed_capacity_model(base, config, windowed=False)
        buses = self.valued_stores(n)
        return self.marginal_prices(n, model)[buses].set_axis(buses.index, axis=1)

    def run(self, base: Revision) -> Revision:
        periods = selected_periods(base, self.config.periods) or [None]
        values = pd.concat([self.period_values(base, period) for period in periods])
        held = to_network(base).get_switchable_as_dense("Store", "marginal_cost")[values.columns]
        return write_series(base, "marginal_cost", values.reindex(held.index).fillna(held))

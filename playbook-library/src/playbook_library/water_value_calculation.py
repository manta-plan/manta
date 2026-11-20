# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

from typing import Annotated

import pandas as pd
import pypsa
from datarecord import Revision
from playbook.blocks import RecordDimCoord
from playbook.blocks.core import BlockDims, MantaBlock
from pydantic import Field

from playbook_library.pypsa_helpers import (
    fixed_capacity_model,
    restarting_storage,
    to_network,
    write_series,
)
from playbook_library.pypsa_spatial_aggregation import aggregate_network, expand_network
from playbook_library.pypsa_time_aggregation import snapshot_map
from playbook_library.rolling_horizon_dispatch import (
    RollingHorizonDispatchConfig,
    optimize_rolling_horizon,
)


class WaterValueCalculationConfig(RollingHorizonDispatchConfig):
    carriers: list[Annotated[str, RecordDimCoord("carrier")]] = Field(min_length=1)
    """Carriers of the stores to value, such as `H2`."""


class WaterValueCalculation(MantaBlock[WaterValueCalculationConfig]):
    """Price the energy in long-duration stores, so a rolling horizon dispatch keeps it for later.

    A rolling horizon dispatch, set up as `rolling_horizon_dispatch` is, gives the marginal
    price at each store's bus: the value of energy kept in the store, its water value. Its
    windows are longer than those of the dispatch that uses the values, and its snapshots
    coarser, such as one-day snapshots in four-week windows that move on one week at a time.
    Each store of `carriers` then takes its water value as its `marginal_cost` at every
    snapshot, the one input this block writes. A rolling horizon dispatch of the result sees
    what energy in the store is worth beyond each of its own windows. The values cover the
    snapshots of `periods`, and each store keeps its own `marginal_cost` at the other
    snapshots. Solved by an aggregation,
    the prices of a merged bus apply to each of its buses, and those of a time cluster to
    each of its snapshots. With `load_shedding`, the solve sheds load as a dispatch of the
    same setting does, and the written revision holds the water values alone, without the
    load-shedding generators.
    """

    ENV = "pypsa"
    CONFIG = WaterValueCalculationConfig
    DIMS = BlockDims(requires=frozenset({"snapshot"}))

    def valued_stores(self, n: pypsa.Network) -> pd.Series:
        """Return the bus of each store of `n` of `carriers`, by store name.

        Raises `ValueError` if a carrier has no store, or a store of them restarts, as
        `restarting_storage` sets out. Each window of a rolling horizon restarts it by itself,
        so its water value would not carry its energy beyond a window.
        """
        stores = n.stores[n.stores.carrier.isin(self.config.carriers)]
        missing = sorted(set(self.config.carriers) - set(stores.carrier))
        if missing:
            raise ValueError(f"The model has no stores of the carriers {missing}.")
        multi = self.config.optimize_config.multi_investment_periods
        restarting = stores.index[restarting_storage(stores, "e", multi)]
        if not restarting.empty:
            raise ValueError(
                f"The stores {restarting.tolist()} restart: a rolling horizon restarts them "
                "within each window, so a water value gives them no seasonal behaviour."
            )
        return stores.bus

    def marginal_prices(self, n: pypsa.Network, rev: Revision) -> pd.DataFrame:
        """Solve `n`, built from `rev`, by `aggregation` one window at a time; return bus prices.

        The prices cover every bus and snapshot of `n`, per unit of energy.
        """
        aggregation = self.config.aggregation
        n_c = aggregate_network(n, rev, aggregation)
        solved = optimize_rolling_horizon(n_c, self.config.optimize_config)
        prices = expand_network(solved, n, rev, aggregation).buses_t.marginal_price
        if aggregation.snapshot is None:
            return prices
        representatives = snapshot_map(n, rev, aggregation.snapshot)
        return prices.loc[representatives.to_numpy()].set_axis(representatives.index)

    def run(self, base: Revision) -> Revision:
        model, n = fixed_capacity_model(base, self.config, windowed=True)
        buses = self.valued_stores(n)
        values = self.marginal_prices(n, model)[buses].set_axis(buses.index, axis=1)
        held = to_network(base).get_switchable_as_dense("Store", "marginal_cost")[buses.index]
        return write_series(base, "marginal_cost", values.reindex(held.index).fillna(held))

# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

import logging
import threading

import pandas as pd
import pypsa
from playbook.blocks.core import BlockDims, DataRecord, MantaBlock, SolveError
from pydantic import Field

from playbook_library.datarecord_helpers import revision
from playbook_library.pypsa_configs import (
    LoadSheddingConfig,
    PyPSAOptimizeBlockConfig,
    PyPSAOptimizeRollingHorizonConfig,
)
from playbook_library.pypsa_helpers import (
    BUILT_COMPONENTS,
    investment_periods,
    nominal_attr,
    remove_unbuilt_cohorts,
    solve_and_write,
    to_network,
    write_network,
)
from playbook_library.pypsa_time_aggregation import STATES


class FailedWindows(logging.Handler):
    """A log handler that raises `SolveError` at the first window PyPSA could not solve.

    A rolling horizon solves the snapshots one window at a time. PyPSA logs a message for
    a window that does not solve, and moves on to the next. Only messages logged by the
    thread that created the handler count.
    """

    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self.thread = threading.get_ident()

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage()
        if record.thread == self.thread and message.startswith("Optimization failed"):
            raise SolveError(f"PyPSA could not solve a window: {message}")


class RollingHorizonDispatchConfig(PyPSAOptimizeBlockConfig):
    optimize_config: PyPSAOptimizeRollingHorizonConfig = Field(
        default_factory=PyPSAOptimizeRollingHorizonConfig
    )
    capacity_source: DataRecord | None = Field(default=None, title="Capacity data source")
    """Where the capacities to dispatch against come from.

    It is normally wired to a capacity-expansion block earlier in the playbook. Left
    unset, the block dispatches against whatever capacities the model already has. Set,
    it must have results for every period dispatched, and a capacity for every asset that
    can be built in them. A cohort is an extendable asset of finite lifetime. When a
    single period is dispatched, a cohort that only an earlier period could have built
    may lack a capacity, and is left out.
    """

    periods: list[int] | None = Field(default=None, min_length=1)
    """The investment periods to dispatch, in a model with investment periods.

    An investment period is one of the years in which the model builds capacity. None
    dispatches every one, and an empty list is refused.
    """

    load_shedding: LoadSheddingConfig | None = None
    """Load each bus may shed at a cost, so demand the capacities cannot meet is shed.

    None adds no load shedding, which leaves any to the model. Set, the block adds a
    load-shedding generator at every bus before it dispatches.
    """

    time_aggregation: str | None = None
    """The time aggregation to solve by: the `name` given to an earlier `time_partition` block.

    A time aggregation groups the snapshots into clusters. With one, `horizon` and
    `overlap` count clusters, not snapshots, and the results are spread over every
    snapshot. A model without that time aggregation is refused. So is a model with
    storage that each window cycles or starts afresh. None solves at full resolution.
    """


class RollingHorizonDispatch(MantaBlock[RollingHorizonDispatchConfig]):
    """Decide how to run a system, one window of time at a time.

    Only the results are written, whichever periods are dispatched. So the capacities
    dispatched against appear as `p_nom_opt` and the like, not as inputs.
    """

    ENV = "pypsa"
    CONFIG = RollingHorizonDispatchConfig
    DIMS = BlockDims(requires=frozenset({"snapshot"}))
    INPUTS = frozenset({"capacity_source"})

    @staticmethod
    def solved_periods(record: DataRecord) -> list[int]:
        """Return the investment periods that `record` has results for, without building a network.

        A record without the result `p` or without investment periods has none.
        """
        _, rev = revision(record)
        if "p" not in rev.record.attributes or "period" not in rev.record.dims:
            return []
        solved = rev.record.attributes["p"].filter("snapshot IS NOT NULL")
        held = solved.project("snapshot.period").distinct()
        return sorted(period for (period,) in held.fetchall())

    @staticmethod
    def decided_capacities(record: DataRecord) -> pd.Series:
        """Return the optimised capacity of each asset that `record` has one for, by asset name.

        It reads the record, not a network built from it, because a network fills an
        undecided capacity with 0.
        """
        _, rev = revision(record)
        names = {nominal_attr(c) + "_opt" for c in BUILT_COMPONENTS} & set(rev.record.attributes)
        frames = [rev.record.attributes[name].df().set_index("entity")["value"] for name in names]
        return pd.concat(frames) if frames else pd.Series(dtype=float)

    @staticmethod
    def apply_decided_capacities(n: pypsa.Network, decided: pd.Series) -> None:
        """Fix in `n` the capacity of each asset that `decided` has one for, matched by name.

        This is how the dispatch runs against the capacities an expansion block chose.
        Each such asset takes its capacity as given and stops being extendable, so the
        dispatch cannot change it. Assets that `decided` lacks keep their settings.
        """
        for c in n.components[BUILT_COMPONENTS]:
            attr = nominal_attr(c.name)
            static = c.static
            fixed = static.index.intersection(decided.index)
            static.loc[fixed, attr] = decided[fixed]
            static.loc[fixed, attr + "_extendable"] = False

    @staticmethod
    def refuse_undecided_capacities(n: pypsa.Network) -> None:
        """Raise `ValueError` if an asset of `n` is still extendable, its capacity undecided."""
        undecided = {}
        for c in n.components[BUILT_COMPONENTS]:
            static = c.static
            extendable = static.index[static[nominal_attr(c.name) + "_extendable"]]
            if not extendable.empty:
                undecided[c.name] = extendable.tolist()
        if undecided:
            raise ValueError(f"The capacity source decided no capacity of {undecided}")

    def selected_periods(self, record: DataRecord) -> list[int]:
        """Return the investment periods of `record` to dispatch, in model order.

        Raises `ValueError` if `periods` is set and the model has no investment periods,
        or lacks one of those set.
        """
        periods = investment_periods(record)
        if self.config.periods is None:
            return periods
        if not periods:
            raise ValueError("The model has no investment periods to dispatch some of.")
        missing = sorted(set(self.config.periods) - set(periods))
        if missing:
            raise ValueError(f"The model has no investment periods {missing}: {periods}.")
        return [period for period in periods if period in self.config.periods]

    def fix_capacities(self, n: pypsa.Network, source: DataRecord, periods: list[int]) -> None:
        """Fix in `n` the capacities that `source` decided for `periods`, the periods `n` has.

        Over a single period, overnight expansion removes the cohorts only an earlier period
        could have built. So this removes them too, where `source` has no capacity for them. Raises
        `ValueError` if `source` has no results for one of `periods`, or if an asset of `n`
        is left without a decided capacity.
        """
        unsolved = sorted(set(periods).difference(self.solved_periods(source))) if periods else []
        if unsolved:
            raise ValueError(f"The capacity source holds no results of the periods {unsolved}.")
        self.apply_decided_capacities(n, self.decided_capacities(source))
        if len(periods) == 1:
            remove_unbuilt_cohorts(n)
        self.refuse_undecided_capacities(n)

    def with_load_shedding(self, record: DataRecord) -> DataRecord:
        """Add load shedding to the network of `record`, and store it as a child revision of it.

        The load-shedding generators are then part of the stored model, so a later
        results-only write includes their results.
        """
        n = to_network(record)
        n.optimize.add_load_shedding(**self.config.load_shedding.model_dump())
        return write_network(n, record)

    def refuse_restarting_storage(self, n: pypsa.Network) -> None:
        """Raise `NotImplementedError` for storage of `n` that a window starts afresh.

        The results of each window solved by a time aggregation are expanded as if the
        whole horizon were solved at once. That holds only while each window carries over
        the state the last window ended at. Cyclic storage cycles within each window. Over
        investment periods, storage that cycles or starts afresh per period does so within
        each window too.
        """
        multi_investment_periods = self.config.optimize_config.multi_investment_periods
        for ctype, cyclic, cycles_per_period, starts_per_period, _ in STATES.values():
            static = n.components[ctype].static
            per_period = static[cycles_per_period] | static[starts_per_period]
            restarting = static[cyclic] | (multi_investment_periods & per_period)
            if restarting.any():
                raise NotImplementedError(
                    f"Rolling horizon dispatch by a time aggregation of {ctype} "
                    f"{restarting[restarting].index.tolist()}, which each window restarts"
                )

    def optimize(self, n: pypsa.Network) -> pypsa.Network:
        """Solve `n` one window at a time, and return it.

        Each result series then spans every snapshot. PyPSA keeps a series it writes whole
        on each window, such as `Bus.v_ang`, at the last window alone, so the windows before
        it are missing values. Raises `SolveError` at the first window that does not solve,
        which PyPSA itself only logs.
        """
        logger = logging.getLogger("pypsa.optimization.abstract")
        failed = FailedWindows()
        level = logger.level
        logger.setLevel(min(logger.getEffectiveLevel(), logging.WARNING))
        logger.addHandler(failed)
        try:
            n.optimize.optimize_with_rolling_horizon(**self.config.optimize_config.model_dump())
        finally:
            logger.removeHandler(failed)
            logger.setLevel(level)
        for c in n.components:
            for attr, series in c.dynamic.items():
                c.dynamic[attr] = series.reindex(n.snapshots)
        return n

    def run(self, record: DataRecord) -> DataRecord:
        periods = self.selected_periods(record)
        if self.config.load_shedding is not None:
            record = self.with_load_shedding(record)
        n_new = to_network(record, select={"period": periods}) if periods else to_network(record)
        if self.config.capacity_source is not None:
            self.fix_capacities(n_new, self.config.capacity_source, periods)
        if self.config.time_aggregation is not None:
            self.refuse_restarting_storage(n_new)

        return solve_and_write(
            n_new,
            record,
            self.optimize,
            self.config.time_aggregation,
            multi_investment_periods=self.config.optimize_config.multi_investment_periods,
        )[1]

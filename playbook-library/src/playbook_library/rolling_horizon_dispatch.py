# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

import logging
import threading
from functools import partial

import pypsa
from datarecord import Revision
from playbook.blocks.core import BlockDims, MantaBlock, SolveError
from pydantic import Field

from playbook_library.pypsa_configs import (
    Aggregation,
    PyPSAFixedCapacityBlockConfig,
    PyPSAOptimizeRollingHorizonConfig,
)
from playbook_library.pypsa_helpers import (
    fixed_capacity_model,
    restarting_storage,
    solve_and_write,
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


def optimize_rolling_horizon(
    n: pypsa.Network, config: PyPSAOptimizeRollingHorizonConfig
) -> pypsa.Network:
    """Solve `n` one window at a time by `config`, and return it.

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
        n.optimize.optimize_with_rolling_horizon(**config.model_dump())
    finally:
        logger.removeHandler(failed)
        logger.setLevel(level)
    for c in n.components:
        for attr, series in c.dynamic.items():
            c.dynamic[attr] = series.reindex(n.snapshots)
    return n


class RollingHorizonDispatchConfig(PyPSAFixedCapacityBlockConfig):
    optimize_config: PyPSAOptimizeRollingHorizonConfig = Field(
        default_factory=PyPSAOptimizeRollingHorizonConfig
    )
    aggregation: Aggregation = Field(default_factory=Aggregation)
    """Merge buses, assets and snapshots before dispatch. Results cover the full model."""


class RollingHorizonDispatch(MantaBlock[RollingHorizonDispatchConfig]):
    """Decide how to run a system, one window of time at a time.

    Only the results are written, whichever periods are dispatched. So the capacities
    dispatched against appear as `p_nom_opt` and the like, not as inputs.
    """

    ENV = "pypsa"
    CONFIG = RollingHorizonDispatchConfig
    DIMS = BlockDims(requires=frozenset({"snapshot"}))

    def refuse_restarting_storage(self, n: pypsa.Network) -> None:
        """Raise `NotImplementedError` for storage of `n` that a window starts afresh.

        The results of each window solved by a time aggregation are expanded as if the
        whole horizon were solved at once. That holds only while each window carries over
        the state the last window ended at, which `restarting_storage` sets out.
        """
        multi_investment_periods = self.config.optimize_config.multi_investment_periods
        for state, (ctype, *_) in STATES.items():
            static = n.components[ctype].static
            restarting = restarting_storage(static, state, multi_investment_periods)
            if restarting.any():
                raise NotImplementedError(
                    f"Rolling horizon dispatch by a time aggregation of {ctype} "
                    f"{restarting[restarting].index.tolist()}, which each window restarts"
                )

    def run(self, base: Revision) -> Revision:
        optimize_config = self.config.optimize_config
        base, n_new = fixed_capacity_model(base, self.config, windowed=True)
        if self.config.aggregation.snapshot is not None:
            self.refuse_restarting_storage(n_new)

        return solve_and_write(
            n_new,
            base,
            partial(optimize_rolling_horizon, config=optimize_config),
            self.config.aggregation,
            multi_investment_periods=optimize_config.multi_investment_periods,
        )[1]

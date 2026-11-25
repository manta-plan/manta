# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

import pandas as pd
import pypsa
from datarecord import Revision
from playbook.blocks.core import BlockDims, ConfigSchema, MantaBlock
from pydantic import Field

from playbook_library.pypsa_configs import PyPSAOptimizeRollingHorizonConfig
from playbook_library.pypsa_helpers import (
    BUILT_COMPONENTS,
    nominal_attr,
    to_network,
    write_network,
)


class RollingHorizonDispatchConfig(ConfigSchema):
    optimize_config: PyPSAOptimizeRollingHorizonConfig = Field(
        default_factory=PyPSAOptimizeRollingHorizonConfig
    )


class RollingHorizonDispatch(MantaBlock[RollingHorizonDispatchConfig]):
    """Decide how to run a system, a stretch of time at a time."""

    ENV = "pypsa"
    CONFIG = RollingHorizonDispatchConfig
    DIMS = BlockDims(requires=frozenset({"snapshot"}))

    @staticmethod
    def decided_capacities(rev: Revision) -> pd.Series:
        """Return the optimised capacity of each asset that `rev` has one for, by asset name.

        It reads the revision, not a network built from it, because a network fills an
        undecided capacity with 0.
        """
        names = {nominal_attr(c) + "_opt" for c in BUILT_COMPONENTS} & set(rev.record.attributes)
        frames = [rev.record.attributes[name].df().set_index("entity")["value"] for name in names]
        return pd.concat(frames) if frames else pd.Series(dtype=float)

    @staticmethod
    def apply_decided_capacities(n: pypsa.Network, decided: pd.Series) -> None:
        """Fix in `n` the capacity of each asset that `decided` has one for, matched by name.

        This is how the dispatch runs against the capacities an expansion block before it
        chose. Each such asset takes its capacity as given and stops being extendable, so
        the dispatch cannot change it. Assets that `decided` lacks keep their settings.
        """
        for c in n.components[BUILT_COMPONENTS]:
            attr = nominal_attr(c.name)
            static = c.static
            fixed = static.index.intersection(decided.index)
            static.loc[fixed, attr] = decided[fixed]
            static.loc[fixed, attr + "_extendable"] = False

    def optimize(self, n: pypsa.Network) -> pypsa.Network:
        """Dispatch `n` window by window, each result series then spanning every snapshot.

        PyPSA keeps a series it writes whole on each window, such as `Bus.v_ang`, at
        the last window alone; the windows before it are missing values.
        """
        n.optimize.optimize_with_rolling_horizon(**self.config.optimize_config.model_dump())
        for c in n.components:
            for attr, series in c.dynamic.items():
                c.dynamic[attr] = series.reindex(n.snapshots)
        return n

    def run(self, base: Revision) -> Revision:
        n_new = to_network(base)
        self.apply_decided_capacities(n_new, self.decided_capacities(base))
        n_new = self.optimize(n_new)
        return write_network(n_new, base)

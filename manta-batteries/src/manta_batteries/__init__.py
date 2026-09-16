# SPDX-FileCopyrightText: 2026 Manta Blocks contributors
#
# SPDX-License-Identifier: MIT

"""The standard library of blocks that ships with Manta (PyPSA blocks, for now).

Importing this package is all it takes for its blocks to become known: they are
registered by name and location without being imported, so this package works in
environments that could never import PyPSA. The blocks themselves are only imported
where one actually runs - inside the `pypsa` environment's worker.
"""

from manta_blocks import register_lazy

register_lazy("cluster_time", "manta_batteries.time_cluster:ClusterTime")
register_lazy(
    "overnight_capacity_expansion",
    "manta_batteries.overnight_capacity_expansion:OvernightCapacityExpansion",
)
register_lazy(
    "myopic_capacity_expansion",
    "manta_batteries.myopic_capacity_expansion:MyopicCapacityExpansion",
)
register_lazy(
    "rolling_horizon_dispatch",
    "manta_batteries.rolling_horizon_dispatch:RollingHorizonDispatch",
)

# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""The blocks and playbooks that ship with Manta (PyPSA-based, for now).

Importing this package is all it takes for its blocks to become known: they are
registered by name and location without being imported, so this package works in
environments that could never import PyPSA. The blocks themselves are only imported
where one actually runs.

`catalogue.json` is the **generated** description of these blocks, committed so that
environments which cannot import them can still list them and check how a playbook
wires them up. Regenerate it after changing anything a block declares (settings, dims,
inputs, docstring first line):

    pixi run -e pypsa catalogue

The pypsa-marked test suite checks the committed file still matches the blocks, so a
stale catalogue fails there.
"""

import json
from importlib import resources

from playbook.blocks import Catalogue, register_lazy

register_lazy("cluster_time", "playbook_library.time_cluster:ClusterTime")
register_lazy(
    "overnight_capacity_expansion",
    "playbook_library.overnight_capacity_expansion:OvernightCapacityExpansion",
)
register_lazy(
    "myopic_capacity_expansion",
    "playbook_library.myopic_capacity_expansion:MyopicCapacityExpansion",
)
register_lazy(
    "rolling_horizon_dispatch",
    "playbook_library.rolling_horizon_dispatch:RollingHorizonDispatch",
)


def library_catalogue() -> Catalogue:
    """The committed description of this library's blocks, importable anywhere."""
    raw = (resources.files(__package__) / "catalogue.json").read_text()
    return Catalogue.model_validate(json.loads(raw))

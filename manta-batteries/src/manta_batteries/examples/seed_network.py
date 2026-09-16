# SPDX-FileCopyrightText: 2026 Manta Blocks contributors
#
# SPDX-License-Identifier: MIT

"""Build a tiny example network and publish it, as input data for a playbook run.

    pixi run -e pypsa python -m manta_batteries.examples.seed_network s3://manta/examples/network-tiny.nc

The network is one bus, one extendable generator, and one load over 24 hours - small
enough that the whole example playbook solves in seconds, but real enough that every
block has something to do. The url can also be a local path.

This stands in for real input data until Manta grows upload endpoints and a data
record catalogue; it exists so a playbook run can be tried end to end.
"""

import sys

import pandas as pd
import pypsa
from manta_blocks.records import stage_output

DEFAULT_URL = "s3://manta/examples/network-tiny.nc"


def build_network() -> pypsa.Network:
    n = pypsa.Network()
    n.set_snapshots(pd.date_range("2030-01-01", periods=24, freq="h"))
    n.add("Bus", "bus")
    n.add(
        "Generator",
        "gen",
        bus="bus",
        p_nom_extendable=True,
        capital_cost=100.0,
        marginal_cost=10.0,
    )
    n.add("Load", "load", bus="bus", p_set=50.0)
    return n


def main(argv: list[str]) -> int:
    url = argv[0] if argv else DEFAULT_URL
    with stage_output(url) as path:
        build_network().export_to_netcdf(str(path))
    print(f"Wrote example network to {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

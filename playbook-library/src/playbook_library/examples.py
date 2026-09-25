# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""A tiny example network, and the shipped playbook run against it.

    pixi run -e full python -m playbook_library.examples [output prefix]

The network is one bus, one generator that can be built, and a day of demand - small
enough that the whole playbook solves in seconds, but real enough that every block has
something to do. The output prefix can be a local directory or an `s3://` URL; every
step writes its result under it, so a finished run reads as a folder of outputs.

This stands in for real input data until Manta can be given some, and it is the
quickest way to see a change to a block or to the playbook actually run. The test
suite builds the same network, so what this demonstrates is what is tested.
"""

import sys
import tempfile

import pandas as pd
import pypsa
from playbook.blocks import DataRecord, storage
from playbook.playbooks.yaml_io import playbook_from_doc

from playbook_library.playbooks import library_playbooks

EXAMPLE_PLAYBOOK = "cluster-expand-dispatch"


def build_example_network() -> pypsa.Network:
    """One bus, one generator that can be built, and a day of demand."""
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


def seed_network(url: str) -> DataRecord:
    """Write the example network at `url` and point a record at it."""
    with storage.local_target(url) as path:
        build_example_network().export_to_netcdf(str(path))
    return DataRecord(url=url)


def main(argv: list[str]) -> int:
    output_prefix = argv[0] if argv else tempfile.mkdtemp(prefix="playbook-example-")

    entry = library_playbooks()[EXAMPLE_PLAYBOOK]
    playbook = playbook_from_doc(entry.doc)
    record = seed_network(f"{output_prefix}/input.nc")

    print(f"Running {EXAMPLE_PLAYBOOK!r} on {record.url}")
    result = playbook.run(record, entry.default_config, output_prefix=output_prefix)
    print(f"Done. Final result: {result.url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

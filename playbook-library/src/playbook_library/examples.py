# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""A tiny example network, and the example playbook run against it.

    pixi run -e full python -m playbook_library.examples [store url]

The network is one bus, one generator that can be built, and a day of demand - small
enough that the whole playbook solves in seconds, but real enough that there is
something to decide. The network is stored as the root revision of a datarecord store at
the given URL, a local directory or an `s3://` URL; every step adds its result as a
new revision to that store, so a finished run reads as a lineage of revisions.

This stands in for real input data until Manta can be given some, and it is the
quickest way to see a change to a block or to the playbook actually run. The test
suite builds the same network, so what this demonstrates is what is tested.
"""

import sys
import tempfile
from contextlib import closing

import pandas as pd
import pypsa
from datarecord import Workspace
from playbook.blocks.core import RevisionRef
from playbook.playbooks.yaml_io import playbook_from_doc

from playbook_library.playbooks import library_playbooks
from playbook_library.pypsa_helpers import store_network

EXAMPLE_PLAYBOOK = "expand"


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


def main(argv: list[str]) -> int:
    url = argv[0] if argv else tempfile.mkdtemp(prefix="playbook-example-")

    playbook = playbook_from_doc(library_playbooks()[EXAMPLE_PLAYBOOK])
    with closing(Workspace()) as workspace:
        ref = RevisionRef.from_revision(
            store_network(build_example_network(), workspace.store(url))
        )

    print(f"Running {EXAMPLE_PLAYBOOK!r} on revision {ref.id} of {ref.store}")
    result = playbook.run(ref, {})
    print(f"Done. Final result: revision {result.id} of {result.store}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

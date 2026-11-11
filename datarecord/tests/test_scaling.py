# SPDX-FileCopyrightText: datarecord contributors
#
# SPDX-License-Identifier: MIT

"""Memory-bounded per-type build on a large network.

Marked slow: `carbon_management` is ~2164 buses / 6830 links / 168 snapshots,
so the record write alone dominates the suite runtime.

Notes
-----
- [consuming a record](https://energy-models.github.io/datarecord/design/tools/)
"""

import tracemalloc

import pytest

from datarecord.tools.pypsa import PyPSA
from tests.fixtures import export_network

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def carbon():
    """`carbon_management`, with every type that shares a `Bus` name renamed off it.

    Same reconciliation `ac_dc` needs (see `conftest.ac_dc`): the network names
    its `Load`s, `Store`s, `Link`s and `Generator`s after the `Bus` they sit on,
    which a record cannot represent (design doc §4.3).
    """
    import pypsa

    from tests.fixtures import example, rename_components

    n = example(pypsa.examples.carbon_management)
    for ctype in ("Load", "Store", "Link", "Generator"):
        rename_components(n, ctype, f" {ctype}")
    return n


def test_to_model_peaks_near_one_component_type(store, carbon):
    """Peak memory stays near the largest single type, not the whole network."""
    revision = export_network(carbon, store)

    tracemalloc.start()
    n = PyPSA.build(revision.record)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert len(n.c["Link"].static) == len(carbon.c["Link"].static)
    assert len(n.snapshots) == len(carbon.snapshots)

    # The widest single frame is Link's dynamic p_max_pu-shaped block; allow a
    # generous multiple of it, but far below materialising every type at once.
    cell = len(carbon.snapshots) * len(carbon.c["Link"].static) * 8
    assert peak < 20 * cell, f"peak {peak / 1e6:.0f} MB vs one-type {cell / 1e6:.0f} MB"

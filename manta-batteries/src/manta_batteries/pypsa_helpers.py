# SPDX-FileCopyrightText: 2026 Manta Blocks contributors
#
# SPDX-License-Identifier: MIT

"""Shared PyPSA work for the blocks in this library.

This is also where the blocks meet their data. A record points at a PyPSA netCDF
file - on the local filesystem or in S3 - and `manta_blocks.records` stages it either
way: `to_network` reads one, and `patch_record` writes a new one beside it. Proper
record storage (structured, diff-aware) will replace both, and confining that to this
one module is what keeps the change small when it arrives.
"""

from collections.abc import Iterator

import pypsa
from manta_blocks.core import DataRecord
from manta_blocks.records import sibling_url, stage, stage_output

CAPACITY_COMPONENTS = ["Generator", "Link", "StorageUnit", "Store"]
"""The components whose capacity a capacity-expansion block can change."""


def nominal_attr(component_name: str) -> str:
    """The name of a component's nominal capacity: stores hold energy, the rest power."""
    return "e_nom" if component_name == "Store" else "p_nom"


def capacity_components(n: pypsa.Network) -> Iterator:
    """Each component of `n` that has a nominal capacity."""
    yield from n.components[CAPACITY_COMPONENTS]


def to_network(record: DataRecord) -> pypsa.Network:
    """Read the network a record points at.

    Every call reads the file again, so a block gets a network of its own and never
    has to copy one. That is worth knowing: copying a network with several investment
    periods is not currently safe in PyPSA.
    """
    with stage(record.url) as path:
        return pypsa.Network(str(path))


def patch_record(source: DataRecord, n: pypsa.Network, label: str) -> DataRecord:
    """Write `n` beside the record it came from, and point a new record at it.

    A block is meant to record only what it changed, but PyPSA cannot yet compare two
    networks or store a difference, so the whole network is written out instead. The
    result is correct, just larger than it needs to be. The file is named after the
    one it came from plus `label`, so a chain of blocks leaves a readable trail - and
    everything a run touched stays under the run's own prefix.
    """
    # TODO: write only the difference from `source` once PyPSA can compare networks
    # and store the result. Only this function changes when it can.
    target_url = sibling_url(source.url, label)
    with stage_output(target_url) as path:
        n.export_to_netcdf(str(path))
    return DataRecord(url=target_url)


def optimize_network(n: pypsa.Network, config, **overrides: object) -> pypsa.Network:
    """Optimise `n` with the given settings, overriding individual ones if asked.

    Overrides are passed straight through rather than folded into `config`, so values
    that only make sense to PyPSA - a slice of snapshots, say - never have to survive
    a round trip through the settings model.
    """
    n.optimize(**{**config.model_dump(), **overrides})
    return n


def freeze_period(n: pypsa.Network, period: int) -> None:
    """Keep what was built in `period` from being changed by a later period.

    The optimised capacities become the fixed ones, and anything built in this period
    is no longer extendable.
    """
    for c in capacity_components(n):
        attr = nominal_attr(c.name)
        c.static[attr] = c.static[attr + "_opt"]
        c.static.loc[c.static.build_year == period, attr + "_extendable"] = False


def apply_optimised_capacities(n: pypsa.Network, source: pypsa.Network) -> None:
    """Take the capacities decided in `source` and fix them in `n`.

    This is how a dispatch block runs against capacities an expansion block chose:
    the capacities come across as given, and dispatch cannot change them.
    """
    for c in capacity_components(n):
        attr = nominal_attr(c.name)
        c.static[attr] = source.c[c.name].static[attr + "_opt"]
        c.static[attr + "_extendable"] = False

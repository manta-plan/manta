# SPDX-FileCopyrightText: datarecord contributors
#
# SPDX-License-Identifier: MIT

"""Piecewise-linear values as breakpoint rows.

Notes
-----
- [wide and long rows](https://energy-models.github.io/datarecord/design/record/#wide-and-long-rows)
"""

import pytest

from datarecord.layered.revision import Revision
from datarecord.record import Flags
from tests.fixtures import (
    empty_child,
    empty_root,
    relation,
    schema,
    write_connections,
    write_entity_type,
    write_input,
    write_schema,
)

PROCESS = "Process"


def _curve(revision, attribute: str) -> list[tuple[float, float]]:
    """`(breakpoint, value)` pairs, in curve order - a sort on `breakpoint`."""
    df = relation(revision, attribute).order("breakpoint").df()
    return list(zip(df["breakpoint"], df["value"], strict=True))


def _flags(revision, attribute: str) -> Flags:
    flags = revision.record.flags()
    if attribute not in flags:
        raise AssertionError(f"{attribute} not in the owner map")
    return flags[attribute]


def _root_with_curve(store, *, scalar: float | None = None) -> Revision:
    """A root whose `steel_dri` has a three-point `marginal_cost`, or `scalar` instead."""
    revision = empty_root(store)
    layer = store.layer_dir(revision.id)
    write_schema(schema(), store)
    write_entity_type(layer, PROCESS, [{"entity": "steel_dri"}])
    rows = (
        [{"entity_type": PROCESS, "entity": "steel_dri", "value": scalar}]
        if scalar is not None
        else [
            {
                "entity_type": PROCESS,
                "entity": "steel_dri",
                "breakpoint": x,
                "value": v,
            }
            for x, v in ((0.0, 20.0), (50.0, 35.0), (80.0, 60.0))
        ]
    )
    write_input(layer, "marginal_cost", rows)
    return revision


@pytest.mark.parametrize("scalar", [None, 20.0], ids=["over-a-curve", "over-a-scalar"])
def test_a_child_curve_replaces_the_parents_value_whole(store, scalar):
    """`breakpoint` is not in `input_key`: one layer owns every breakpoint of a key.

    So a child's curve replaces a parent's curve entirely - never a mix of the
    two - and may turn a scalar into a curve, it being one key either way.
    """
    root = _root_with_curve(store, scalar=scalar)
    root.materialise()

    child = empty_child(root)
    write_input(
        store.layer_dir(child.id),
        "marginal_cost",
        [
            {
                "entity_type": PROCESS,
                "entity": "steel_dri",
                "breakpoint": x,
                "value": v,
            }
            for x, v in ((0.0, 25.0), (90.0, 70.0))
        ],
    )

    assert _curve(child, "marginal_cost") == [(0.0, 25.0), (90.0, 70.0)], (
        "the child's breakpoints only"
    )
    assert _flags(child, "marginal_cost").breakpoints


def test_breakpoints_distinguishes_curve_from_scalar(store):
    """The owner map says which keys are curves, without opening the file.

    Notes
    -----
    - [the owner map](https://energy-models.github.io/datarecord/design/read-path/#owner-map)
    """
    revision = _root_with_curve(store)
    write_input(
        store.layer_dir(revision.id),
        "p_nom",
        [{"entity_type": PROCESS, "entity": "steel_dri", "value": 100.0}],
    )

    curve = _flags(revision, "marginal_cost")
    scalar = _flags(revision, "p_nom")
    # A curve and a scalar are shaped alike - both rows name the entity and
    # leave every other dim NULL - and `breakpoints` is what separates them,
    # without opening the file.
    assert curve.broadcast == scalar.broadcast
    assert curve.varies == scalar.varies
    assert "snapshot" in curve.broadcast
    assert curve.varies == {"entity"}, "only the entity is named"
    assert curve.breakpoints
    assert not scalar.breakpoints
    assert _curve(revision, "marginal_cost") == [
        (0.0, 20.0),
        (50.0, 35.0),
        (80.0, 60.0),
    ], "a curve is N rows of one key, ordered by sorting on `breakpoint`"


def test_curve_on_a_connection(store):
    """`bus` and `breakpoint` compose: one keys, the other does not.

    Notes
    -----
    - [wide and long rows](https://energy-models.github.io/datarecord/design/record/#wide-and-long-rows)
    """
    revision = empty_root(store)
    layer = store.layer_dir(revision.id)
    write_schema(schema(), store)
    write_entity_type(layer, PROCESS, [{"entity": "steel_dri"}])
    write_connections(
        layer,
        [
            {"entity": "steel_dri", "bus": "h2_north", "role": "input"},
            {"entity": "steel_dri", "bus": "dri", "role": "output"},
        ],
    )
    write_input(
        layer,
        "efficiency",
        [
            {
                "entity_type": PROCESS,
                "entity": "steel_dri",
                "bus": bus,
                "breakpoint": x,
                "value": v,
            }
            for bus, x, v in (
                ("h2_north", 0.0, 2.0),
                ("h2_north", 50.0, 2.4),
                ("dri", 0.0, 1.0),
            )
        ],
    )
    revision.materialise()

    # Each connection owns its own curve, so a patch to one leaves the other.
    child = empty_child(revision)
    write_input(
        store.layer_dir(child.id),
        "efficiency",
        [
            {
                "entity_type": PROCESS,
                "entity": "steel_dri",
                "bus": "h2_north",
                "breakpoint": x,
                "value": v,
            }
            for x, v in ((0.0, 3.0), (50.0, 3.5), (99.0, 4.0))
        ],
    )

    df = (
        relation(child, "efficiency")
        .project("connection.bus AS bus, breakpoint, value")
        .order("bus, breakpoint")
        .df()
    )
    rows = list(zip(df["bus"], df["breakpoint"], df["value"], strict=True))
    assert rows == [
        ("dri", 0.0, 1.0),
        ("h2_north", 0.0, 3.0),
        ("h2_north", 50.0, 3.5),
        ("h2_north", 99.0, 4.0),
    ]


def test_curve_varying_by_snapshot(store):
    """A curve per snapshot: `breakpoint` multiplies by the dims like anything else."""
    revision = empty_root(store)
    layer = store.layer_dir(revision.id)
    write_schema(schema(), store)
    write_entity_type(layer, PROCESS, [{"entity": "steel_dri"}])
    write_input(
        layer,
        "marginal_cost",
        [
            {
                "entity_type": PROCESS,
                "entity": "steel_dri",
                "snapshot": snap,
                "breakpoint": x,
                "value": v,
            }
            for snap, x, v in (
                ("2030-01-01", 0.0, 20.0),
                ("2030-01-01", 50.0, 30.0),
                ("2030-01-02", 0.0, 22.0),
                ("2030-01-02", 50.0, 33.0),
            )
        ],
    )

    flags = _flags(revision, "marginal_cost")
    # A curve that varies over snapshots: on the snapshot axis and a curve too.
    assert "snapshot" in flags.varies
    assert "snapshot" not in flags.broadcast
    assert flags.breakpoints
    assert len(relation(revision, "marginal_cost").df()) == 4

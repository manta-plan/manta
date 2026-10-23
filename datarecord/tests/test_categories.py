# SPDX-FileCopyrightText: datarecord contributors
#
# SPDX-License-Identifier: MIT

"""A NULL on a categorized dim reaches only the labels carrying the attribute.

Notes
-----
- [owner map](https://energy-models.github.io/datarecord/design/read-path/#owner-map)
"""

import narwhals as nw
import pytest

from datarecord.layered.resolve import write_schema
from datarecord.mutable import WorkingRecord
from datarecord.schema import (
    AttributeSpec,
    Dimension,
    Group,
    PropertySpec,
    Schema,
    Trait,
)
from tests.fixtures import empty_root


@pytest.fixture
def categorized():
    """`p_max_pu` narrowed to generators and to wind entities."""
    return Schema(
        dimensions={
            "entity": Dimension(dtype=nw.String()),
            "bus": Dimension(dtype=nw.String()),
            "snapshot": Dimension(dtype=nw.Int64()),
        },
        properties={
            "entity": {
                "entity_type": PropertySpec(
                    dtype=nw.Enum(["Bus", "Generator", "Link", "Load"])
                ),
                "carrier": PropertySpec(dtype=nw.Enum(["gas", "wind"])),
            }
        },
        attributes={
            "p_max_pu": AttributeSpec(dtype=nw.Float64(), dims={"entity", "snapshot"}),
            "efficiency": AttributeSpec(
                dtype=nw.Float64(), dims={"connection", "snapshot"}
            ),
        },
        groups={"connection": Group(over={"entity": "entity", "bus": "bus"})},
        traits={
            "generator": Trait(
                attributes=frozenset({"p_max_pu"}),
                on={"entity_type": frozenset({"Generator"})},
            ),
            "wind": Trait(
                attributes=frozenset({"p_max_pu"}),
                on={"carrier": frozenset({"wind"})},
            ),
            "link": Trait(
                attributes=frozenset({"efficiency"}),
                on={"entity_type": frozenset({"Link"})},
            ),
        },
        partial=frozenset({"entity", "bus", "connection"}),
    )


@pytest.fixture
def root(store, categorized):
    """A root with a gas generator, a wind load, a gas load and a bus-category label."""
    write_schema(categorized, store)
    revision = empty_root(store)
    staged = WorkingRecord(revision.record)
    staged.add("entity", ["g1"], entity_type="Generator", carrier="gas")
    staged.add("entity", ["w1"], entity_type="Load", carrier="wind")
    staged.add("entity", ["l1"], entity_type="Load", carrier="gas")
    staged.add("entity", ["b1"], entity_type="Bus")
    return revision.child(staged.edits)


def _values(record, attribute: str) -> dict:
    """`record.attributes[attribute]` as `entity -> value`."""
    frame = record.attributes[attribute].collect().to_native().to_pandas()
    assert frame["entity"].is_unique, f"one row per entity, got {frame}"
    return dict(zip(frame["entity"], frame["value"], strict=True))


def test_a_null_reaches_a_label_added_in_the_same_staged_record(root):
    staged = WorkingRecord(root.record)
    staged.set("p_max_pu", 0.9)
    staged.add("entity", ["g2"], entity_type="Generator")
    assert _values(staged, "p_max_pu") == {"g1": 0.9, "w1": 0.9, "g2": 0.9}, (
        "every generator and every wind entity, never the bus or the gas load"
    )


def test_a_null_reaches_a_label_added_in_an_unmaterialised_child(root):
    staged = WorkingRecord(root.record)
    staged.set("p_max_pu", 0.9)
    layer = root.child(staged.edits)
    later = WorkingRecord(layer.record)
    later.add("entity", ["g2"], entity_type="Generator", carrier="gas")
    child = layer.child(later.edits)
    assert _values(child.record, "p_max_pu") == {"g1": 0.9, "w1": 0.9, "g2": 0.9}, (
        "a generator added below the broadcast is reached by it"
    )


def test_a_null_no_label_carries_reaches_nothing(store, categorized):
    write_schema(categorized, store)
    staged = WorkingRecord(empty_root(store).record)
    staged.add("entity", ["l1"], entity_type="Load", carrier="gas")
    staged.set("p_max_pu", 0.9)
    assert "p_max_pu" not in staged.attributes, "no generator and no wind entity"


def test_a_re_categorized_label_drops_out_of_the_broadcast(root):
    staged = WorkingRecord(root.record)
    staged.set("p_max_pu", 0.5, entity="g1")
    explicit = root.child(staged.edits)
    staged = WorkingRecord(explicit.record)
    staged.add("entity", ["g2"], entity_type="Generator", carrier="gas")
    staged.set("p_max_pu", 0.9)
    broadcast = explicit.child(staged.edits)
    assert _values(broadcast.record, "p_max_pu") == {"g1": 0.9, "g2": 0.9, "w1": 0.9}

    staged = WorkingRecord(broadcast.record)
    staged.add("entity", ["g1", "g2"], entity_type="Load", carrier="gas")
    re_categorized = broadcast.child(staged.edits)
    assert _values(re_categorized.record, "p_max_pu") == {"g1": 0.5, "w1": 0.9}, (
        "g2 is out of the broadcast's reach, g1's explicit row stays"
    )


def test_a_null_over_a_group_reaches_the_tuples_carrying_it(store, categorized):
    write_schema(categorized, store)
    staged = WorkingRecord(empty_root(store).record)
    staged.add("entity", ["k1"], entity_type="Link")
    staged.add("entity", ["g1"], entity_type="Generator")
    staged.add("bus", ["b0", "b1"])
    staged.add_group(
        "connection",
        nw.from_dict(
            {
                "connection": [
                    {"entity": "k1", "bus": "b0"},
                    {"entity": "k1", "bus": "b1"},
                    {"entity": "g1", "bus": "b0"},
                ]
            },
            backend="pandas",
        ),
    )
    staged.set("efficiency", 0.7)
    frame = staged.attributes["efficiency"].collect().to_native().to_pandas()
    assert sorted(c["entity"] + c["bus"] for c in frame["connection"]) == [
        "k1b0",
        "k1b1",
    ], "the link's connections, not the generator's"


@pytest.fixture
def buses(store):
    """Two AC buses and a DC one; `frequency` is an AC bus's only, defaulting by type."""
    write_schema(
        Schema(
            dimensions={"bus": Dimension(dtype=nw.String())},
            properties={"bus": {"bus_type": PropertySpec(dtype=nw.Enum(["AC", "DC"]))}},
            attributes={
                "v_nom": AttributeSpec(dtype=nw.Float64(), dims={"bus"}),
                "frequency": AttributeSpec(
                    dtype=nw.Float64(),
                    dims={"bus"},
                    default=0.0,
                    default_by={"bus_type": {"AC": 50.0}},
                ),
            },
            traits={
                "alternating": Trait(
                    attributes=frozenset({"frequency"}),
                    on={"bus_type": frozenset({"AC"})},
                )
            },
            partial=frozenset({"bus"}),
        ),
        store,
    )
    revision = empty_root(store)
    staged = WorkingRecord(revision.record)
    staged.add("bus", ["ac1", "ac2"], bus_type="AC")
    staged.add("bus", ["dc1"], bus_type="DC")
    return revision.child(staged.edits)


def _by_bus(record, attribute: str) -> dict:
    """`record.attributes[attribute]` as `bus -> value`."""
    frame = record.attributes[attribute].collect().to_native().to_pandas()
    return dict(zip(frame["bus"], frame["value"], strict=True))


def test_a_category_on_another_dim_than_entity_narrows_the_record(buses):
    staged = WorkingRecord(buses.record)
    staged.set("frequency", 60.0)
    staged.set("v_nom", 380.0)
    record = buses.child(staged.edits).record

    assert _by_bus(record, "frequency") == {"ac1": 60.0, "ac2": 60.0}, (
        "the NULL reaches the AC buses alone"
    )
    assert set(_by_bus(record, "v_nom")) == {"ac1", "ac2", "dc1"}, "untraited"
    dc = record.properties["bus"].filter(nw.col("bus_type") == "DC").select("bus")
    assert dc.collect().to_native().to_pylist() == [{"bus": "dc1"}]
    assert set(record.flags(bus_type="AC")) == {"frequency", "v_nom"}
    assert set(record.flags(bus_type="DC")) == {"v_nom"}, "frequency is an AC bus's"


def test_attributes_leave_a_default_by_unapplied(buses):
    staged = WorkingRecord(buses.record)
    staged.set("frequency", 60.0, bus="ac1")
    record = buses.child(staged.edits).record
    assert _by_bus(record, "frequency") == {"ac1": 60.0}, (
        "ac2 has no row, so it is absent rather than its default_by 50.0"
    )

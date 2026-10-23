# SPDX-FileCopyrightText: datarecord contributors
#
# SPDX-License-Identifier: MIT

"""Connections as bus-keyed rows, and `bus` in the inputs key.

Notes
-----
- [connections](https://energy-models.github.io/datarecord/design/record/#connections)
"""

from pathlib import Path
from typing import Any

import duckdb
import narwhals as nw
import pytest

from datarecord.layered.revision import Revision
from datarecord.mutable import WorkingRecord
from datarecord.schema import AttributeSpec
from tests.fixtures import (
    empty_child,
    empty_root,
    relation,
    schema,
    tombstone,
    tombstone_connection,
    unpacked,
    write_axis,
    write_connections,
    write_entity_type,
    write_group,
    write_input,
    write_schema,
)

PROCESS = "Process"


def _connections(revision):
    """`group_frame`, asserted non-`None` for tests where a row must exist.

    No type: one `groups/connection.parquet` holds every type's rows, and these
    tests declare a single one.
    """
    frame = revision.resolver.group_frame("connection")
    assert frame is not None
    return frame


def _root(store) -> Revision:
    """A record whose layer has one Process with three connections."""
    revision = empty_root(store)
    layer = store.layer_dir(revision.id)
    write_schema(schema(), store)
    write_entity_type(layer, PROCESS, [{"entity": "steel_dri"}])
    write_connections(
        layer,
        [
            {"entity": "steel_dri", "bus": "h2_north", "role": "input"},
            {"entity": "steel_dri", "bus": "iron_ore", "role": "input"},
            {"entity": "steel_dri", "bus": "dri", "role": "output"},
        ],
    )
    write_input(
        layer,
        "efficiency",
        [
            {"entity_type": PROCESS, "entity": "steel_dri", "bus": b, "value": v}
            for b, v in (("h2_north", 2.1), ("iron_ore", 1.6), ("dri", 1.0))
        ],
    )
    return revision


def _efficiencies(revision) -> dict[str, float]:
    df = relation(revision, "efficiency").project("connection.bus AS bus, value").df()
    return dict(zip(df["bus"], df["value"], strict=True))


def test_connections_resolve_in_order(store):
    """A component's connections come back in first-introduced order."""
    revision = _root(store)
    frame = unpacked(_connections(revision))
    assert list(frame["bus"]) == ["h2_north", "iron_ore", "dri"]
    # `role` describes the connection rather than keying it, so it rides along
    # from the owning layer's file (https://energy-models.github.io/datarecord/design/record/#connections).
    assert list(frame["role"]) == ["input", "input", "output"]


def test_patch_overrides_one_connection_only(store):
    """The sibling-clobbering case: `bus` in `input_key` scopes ownership per connection."""
    root = _root(store)
    root.materialise()

    child = empty_child(root)
    write_input(
        store.layer_dir(child.id),
        "efficiency",
        [
            {
                "entity_type": PROCESS,
                "entity": "steel_dri",
                "bus": "h2_north",
                "value": 9.9,
            }
        ],
    )

    # The patched connection takes the child's value; its siblings keep the
    # root's rather than vanishing.
    assert _efficiencies(child) == {"h2_north": 9.9, "iron_ore": 1.6, "dri": 1.0}


def test_patch_hits_the_bus_it_named_not_a_position(store):
    """An intermediate layer inserting a connection does not redirect a later patch."""
    root = _root(store)
    root.materialise()

    # A middle layer prepends a connection, which under a positional encoding
    # would shift every later index by one.
    middle = empty_child(root)
    write_connections(
        store.layer_dir(middle.id),
        [{"entity": "steel_dri", "bus": "elec_north", "role": "input"}],
    )
    write_input(
        store.layer_dir(middle.id),
        "efficiency",
        [
            {
                "entity_type": PROCESS,
                "entity": "steel_dri",
                "bus": "elec_north",
                "value": 0.4,
            }
        ],
    )
    middle.materialise()

    leaf = empty_child(middle)
    write_input(
        store.layer_dir(leaf.id),
        "efficiency",
        [
            {
                "entity_type": PROCESS,
                "entity": "steel_dri",
                "bus": "dri",
                "value": 7.7,
            }
        ],
    )

    assert _efficiencies(leaf) == {
        "h2_north": 2.1,
        "iron_ore": 1.6,
        "dri": 7.7,  # the bus the patch named
        "elec_north": 0.4,
    }


def test_component_level_attribute_is_unaffected(store):
    """A component attribute carries no `bus` column at all, and resolves as ever.

    `bus` is the `connection` group's coordinate, so it is on the files of the
    attributes addressed by that group and on no others - where before every
    long file carried it, all-NULL, whether or not the attribute could use it.

    Notes
    -----
    - [the long schema](https://energy-models.github.io/datarecord/design/format/#the-long-schema)
    """
    root = _root(store)
    write_input(
        store.layer_dir(root.id),
        "p_nom",
        [{"entity_type": PROCESS, "entity": "steel_dri", "value": 100.0}],
    )
    root.materialise()

    child = empty_child(root)
    write_input(
        store.layer_dir(child.id),
        "p_nom",
        [{"entity_type": PROCESS, "entity": "steel_dri", "value": 250.0}],
    )

    df = relation(child, "p_nom").df()
    assert list(df["value"]) == [250.0]
    assert "bus" not in df.columns, "`p_nom` is not addressed by the connection group"


def test_per_connection_attribute_varies_by_snapshot(store):
    """`bus` extends the key; it does not displace the dims.

    Notes
    -----
    - [connections](https://energy-models.github.io/datarecord/design/record/#connections)
    """
    revision = empty_root(store)
    layer = store.layer_dir(revision.id)
    write_schema(schema(), store)
    write_entity_type(layer, PROCESS, [{"entity": "steel_dri"}])
    write_connections(
        layer, [{"entity": "steel_dri", "bus": "h2_north", "role": "input"}]
    )
    write_input(
        layer,
        "efficiency",
        [
            # one static row, and a two-snapshot series for the same connection
            {
                "entity_type": PROCESS,
                "entity": "steel_dri",
                "bus": "h2_north",
                "value": 2.0,
            },
            {
                "entity_type": PROCESS,
                "entity": "steel_dri",
                "bus": "h2_north",
                "snapshot": "2030-01-01",
                "value": 2.5,
            },
            {
                "entity_type": PROCESS,
                "entity": "steel_dri",
                "bus": "h2_north",
                "snapshot": "2030-01-02",
                "value": 2.7,
            },
        ],
    )

    flags = revision.record.flags()["efficiency"]
    # Both sets hold `snapshot`: one connection's efficiency is per-snapshot,
    # another's is a single broadcast row, and the union over the rows
    # reports both - which is what tells a consumer one container will not do
    # (https://energy-models.github.io/datarecord/design/record/#flags). A per-connection attribute needs no special case for this.
    assert "snapshot" in flags.varies
    assert "snapshot" in flags.broadcast
    assert not flags.breakpoints
    assert len(relation(revision, "efficiency").df()) == 3


def test_connection_tombstone_removes_one_connection(store):
    """A connection tombstone drops its connection row and its `inputs/` rows."""
    root = _root(store)
    root.materialise()

    child = empty_child(root)
    tombstone_connection(store.layer_dir(child.id), [("steel_dri", "iron_ore")])

    frame = unpacked(_connections(child))
    assert set(frame["bus"]) == {"h2_north", "dri"}
    # ... and the attribute rows go with it, which the map can scope per
    # connection only because `bus` is in `input_key`.
    assert _efficiencies(child) == {"h2_north": 2.1, "dri": 1.0}


def test_a_component_tombstone_reaches_its_connections_through_theirs(store):
    """The fold infers nothing from the entity: the tuples' own tombstones clear them.

    Notes
    -----
    - [deletion](https://energy-models.github.io/datarecord/design/layers/#deletion)
    """
    root = _root(store)
    root.materialise()

    both = empty_child(root)
    tombstone(store.layer_dir(both.id), PROCESS, ["steel_dri"])
    tombstone_connection(
        store.layer_dir(both.id),
        [("steel_dri", "h2_north"), ("steel_dri", "iron_ore"), ("steel_dri", "dri")],
    )
    frame = both.resolver.group_frame("connection")
    assert frame is not None, "the group was written, so it is present"
    assert frame.count("*").fetchone() == (0,), "every connection row is tombstoned"
    assert _efficiencies(both) == {}, "and their values go with them"


def test_a_dim_a_group_draws_on_still_broadcasts(store):
    """A NULL `bus` on a per-bus attribute is every bus, beside a `connection` group.

    The group carries its `bus` inside its own struct column, so the dim keeps
    its axis to expand against.

    Notes
    -----
    - [the broadcast rule](https://energy-models.github.io/datarecord/design/record/#the-broadcast-rule)
    - [groups](https://energy-models.github.io/datarecord/design/schema/#groups)
    """
    price = AttributeSpec(dtype=nw.Float64(), dims={"bus", "snapshot"})
    write_schema(
        schema(attributes={"Bus": {"marginal_price": price}}, partial={"bus"}), store
    )
    root = empty_root(store)
    layer = store.layer_dir(root.id)
    write_axis(layer, "bus", [{"bus": "north"}, {"bus": "south"}])
    write_input(layer, "marginal_price", [{"value": 5.0}], connection=False)
    root.materialise()

    child = empty_child(root)
    write_input(
        store.layer_dir(child.id),
        "marginal_price",
        [{"bus": "south", "value": 7.0}],
        connection=False,
    )

    def prices(revision):
        df = relation(revision, "marginal_price").df()
        return dict(zip(df["bus"], df["value"], strict=True))

    assert prices(root) == {"north": 5.0, "south": 5.0}, "one row, every bus"
    assert prices(child) == {"north": 5.0, "south": 7.0}, "a patch hits its bus"
    assert "bus" in root.resolver.fold.flags()["marginal_price"].broadcast


def test_a_null_connection_broadcasts_to_every_connection(store):
    """A NULL struct is every tuple of the group, as a NULL dim is every label.

    Notes
    -----
    - [the broadcast rule](https://energy-models.github.io/datarecord/design/record/#the-broadcast-rule)
    """
    root = _root(store)
    child = empty_child(root)
    target = Path(store.layer_dir(child.id), "inputs")
    target.mkdir(parents=True, exist_ok=True)
    duckdb.sql(
        """
        SELECT NULL::STRUCT(entity VARCHAR, bus VARCHAR) AS connection,
               'efficiency' AS attribute, NULL::DOUBLE AS breakpoint, 0.5 AS value
        """
    ).to_parquet(str(target / "efficiency.parquet"))
    assert _efficiencies(child) == {"h2_north": 0.5, "iron_ore": 0.5, "dri": 0.5}


def test_a_group_outside_partial_is_owned_whole(store):
    """Not `partial`, a layer touching one connection owns them all.

    A removed tuple's values still go, though no owner key names it.

    Notes
    -----
    - [partial](https://energy-models.github.io/datarecord/design/schema/#partial-the-granularity-of-an-override)
    """
    root = _root(store)
    write_schema(schema(partial={"scenario"}), store)
    child = empty_child(root)
    write_input(
        store.layer_dir(child.id),
        "efficiency",
        [{"entity": "steel_dri", "bus": "h2_north", "value": 9.9}],
    )
    assert _efficiencies(child) == {"h2_north": 9.9}, "the child restates the attribute"

    gone = empty_child(root)
    tombstone_connection(store.layer_dir(gone.id), [("steel_dri", "iron_ore")])
    assert _efficiencies(gone) == {"h2_north": 2.1, "dri": 1.0}


def _connection_frame(staged, entity, bus):
    """A one-tuple `connection` frame for `add_group`."""
    return staged.con.sql(
        f"SELECT {{'entity': '{entity}', 'bus': '{bus}'}}"
        "::STRUCT(entity VARCHAR, bus VARCHAR) AS connection"
    )


def _efficiency_rows(record) -> dict[tuple[str, str], float]:
    df = unpacked(record.attributes["efficiency"])
    return {
        (e, b): v for e, b, v in zip(df["entity"], df["bus"], df["value"], strict=True)
    }


def test_remove_tombstones_the_tuples_naming_the_entity(store):
    """`remove` writes the cascade: the connections go, and their values with them.

    Notes
    -----
    - [deletion](https://energy-models.github.io/datarecord/design/layers/#deletion)
    """
    base = _root(store)
    other = WorkingRecord(base.record)
    other.add("entity", ["blast_furnace"], entity_type=PROCESS)
    other.add_group("connection", _connection_frame(other, "blast_furnace", "iron_ore"))
    other.set("efficiency", 3.0, entity=["blast_furnace"], bus="iron_ore")
    root = base.child(other.edits)

    staged = WorkingRecord(root.record)
    staged.set("efficiency", 0.5, entity=["steel_dri"], bus="dri")
    staged.remove("entity", ["steel_dri"])
    assert set(unpacked(staged.groups["connection"])["entity"]) == {"blast_furnace"}, (
        "every tuple naming it goes, and no other"
    )
    assert _efficiency_rows(staged) == {("blast_furnace", "iron_ore"): 3.0}, (
        "neither the base's nor the staged values, and another entity keeps its own"
    )

    child = root.child(staged.edits)
    assert set(unpacked(child.record.groups["connection"])["entity"]) == {
        "blast_furnace"
    }
    assert _efficiency_rows(child.record) == {("blast_furnace", "iron_ore"): 3.0}


def test_the_writer_refuses_a_tuple_naming_a_removed_entity(store):
    """Below a materialised node too: the dead labels survive in its cache.

    Notes
    -----
    - [deletion](https://energy-models.github.io/datarecord/design/layers/#deletion)
    """
    root = _root(store)
    staged = WorkingRecord(root.record)
    staged.remove("entity", ["steel_dri"])
    removed = root.child(staged.edits)
    removed.materialise()

    revived = WorkingRecord(removed.record)
    revived.add_group("connection", _connection_frame(revived, "steel_dri", "dri"))
    with pytest.raises(ValueError, match=r"a removed entity in 'entity'"):
        removed.child(revived.edits)


def test_a_tuple_an_ancestor_left_dangling_fails_no_later_write(store):
    """The writer checks what a layer does, not what it inherits.

    Notes
    -----
    - [deletion](https://energy-models.github.io/datarecord/design/layers/#deletion)
    """
    root = _root(store)
    dangling = empty_child(root)
    tombstone(store.layer_dir(dangling.id), PROCESS, ["steel_dri"])

    staged = WorkingRecord(dangling.record)
    staged.add("entity", ["blast_furnace"], entity_type=PROCESS)
    child = dangling.child(staged.edits)
    entities = child.record.dims["entity"].collect()["entity"].to_list()
    assert "blast_furnace" in entities


def test_set_requires_every_party_to_exist(store):
    """The buyer need not carry `price`, but it must be an entity.

    Notes
    -----
    - [validation](https://energy-models.github.io/datarecord/design/working-record/#validation)
    """
    staged = WorkingRecord(_contract_root(store).record)
    contract: dict[str, Any] = {"from": "plant", "to": "nobody"}
    with pytest.raises(KeyError, match="nobody"):
        staged.set("price", 3.0, **contract)


def test_a_removed_tuple_outside_partial_stays_removed_past_a_cache(store):
    """Its values are owned per attribute, so only the cached dead tuples drop them.

    Notes
    -----
    - [materialised node caches](https://energy-models.github.io/datarecord/design/layers/#materialised-node-caches)
    """
    root = _root(store)
    write_schema(schema(partial={"scenario"}), store)
    dead = Path(store.resolved_dir(root.id), "dead")
    root.materialise()
    assert not dead.exists() or not any(dead.iterdir()), "nothing dead, no file"

    staged = WorkingRecord(root.record)
    staged.remove("entity", ["steel_dri"])
    removed = root.child(staged.edits)
    removed.materialise()
    assert Path(store.resolved_dir(removed.id), "dead", "connection.parquet").exists()

    leaf = empty_child(removed)
    assert _efficiencies(leaf) == {}


def test_readding_a_tuple_outside_partial_revives_its_values(store):
    """Owned per attribute, not per tuple: the root's value is the owner again.

    Notes
    -----
    - [deletion](https://energy-models.github.io/datarecord/design/layers/#deletion)
    """
    root = _root(store)
    write_schema(schema(partial={"scenario"}), store)
    staged = WorkingRecord(root.record)
    staged.remove("entity", ["steel_dri"])
    removed = root.child(staged.edits)
    removed.materialise()

    revived = WorkingRecord(removed.record)
    revived.add("entity", ["steel_dri"], entity_type=PROCESS)
    revived.add_group("connection", _connection_frame(revived, "steel_dri", "dri"))
    assert _efficiencies(removed.child(revived.edits)) == {"dri": 1.0}


# -- a group drawing twice on `entity` --------------------------------------

SELLER, BUYER = "Generator", "Load"


def _contract_root(store) -> Revision:
    """Two contracts `(from, to)`, from one seller to two buyers.

    `price` is over `{contract, snapshot}`, so no top-level `entity` names
    either party: both ride inside the `contract` struct.
    """
    price = AttributeSpec(dtype=nw.Float64(), dims={"contract", "snapshot"})
    write_schema(
        schema(
            attributes={SELLER: {"price": price}},
            partial={"scenario", "contract"},
            groups={
                "connection": {"entity": "entity", "bus": "bus"},
                "contract": {"from": "entity", "to": "entity"},
            },
        ),
        store,
    )
    revision = empty_root(store)
    layer = store.layer_dir(revision.id)
    write_entity_type(layer, SELLER, [{"entity": "plant"}])
    write_entity_type(layer, BUYER, [{"entity": "mill"}, {"entity": "smelter"}])
    write_group(
        layer,
        "contract",
        [
            {"contract": {"from": "plant", "to": "mill"}},
            {"contract": {"from": "plant", "to": "smelter"}},
        ],
    )
    Path(layer, "inputs").mkdir(parents=True, exist_ok=True)
    duckdb.sql(
        """
        SELECT {'from': 'plant', 'to': c}::STRUCT("from" VARCHAR, "to" VARCHAR)
                   AS contract,
               NULL::TIMESTAMP AS snapshot, 'price' AS attribute, v AS value
        FROM (VALUES ('mill', 10.0), ('smelter', 20.0)) t(c, v)
        """
    ).to_parquet(str(Path(layer, "inputs", "price.parquet")))
    return revision


def _prices(record) -> dict[str, float]:
    df = record.attributes["price"].collect().to_native().to_pandas()
    return {c["to"]: v for c, v in zip(df["contract"], df["value"], strict=True)}


def test_remove_reaches_a_groups_second_entity_before_and_after_commit(store):
    """Removing the buyer removes its contract, as removing the seller would.

    Staging drops the parent's and its own rows for the `to` entity, as the fold.

    Notes
    -----
    - [add / remove](https://energy-models.github.io/datarecord/design/working-record/#add-remove)
    - [deletion](https://energy-models.github.io/datarecord/design/layers/#deletion)
    """
    root = _contract_root(store)
    assert _prices(root.record) == {"mill": 10.0, "smelter": 20.0}
    staged = WorkingRecord(root.record)
    contract: dict[str, Any] = {"from": "plant", "to": "mill"}
    staged.set("price", 30.0, **contract)
    assert _prices(staged)["mill"] == 30.0, "the staged value reads before removal"
    staged.remove("entity", ["mill"])
    assert _prices(staged) == {"smelter": 20.0}, "neither the base's nor the staged"

    child = root.child(staged.edits)
    assert _prices(child.record) == {"smelter": 20.0}, "the `to` entity's row is gone"
    contracts = child.record.groups["contract"].collect().to_native()
    assert len(contracts) == 1, "its tuple went with it"


def test_set_addresses_a_groups_fields_by_keyword(store):
    """Each party is its own keyword, one label or a list; `entity=` is neither.

    Notes
    -----
    - [set](https://energy-models.github.io/datarecord/design/working-record/#set)
    """
    staged = WorkingRecord(_contract_root(store).record)
    contract: dict[str, Any] = {"from": "plant", "to": "mill"}
    staged.set("price", 30.0, **contract)
    assert len(staged.attributes["price"].collect()) == 2, "one row per contract"
    assert _prices(staged) == {"mill": 30.0, "smelter": 20.0}

    plant: dict[str, Any] = {"from": "plant"}
    staged.set("price", 40.0, to=["smelter"], **plant)
    assert _prices(staged) == {"mill": 30.0, "smelter": 40.0}, "a list fills `to`"

    with pytest.raises(ValueError, match=r"\['from', 'to'"):
        staged.set("price", {"mill": 50.0})
    with pytest.raises(ValueError, match=r"\['to'\] was not given"):
        staged.set("price", 50.0, **plant)
    with pytest.raises(ValueError, match=r"does not vary over \['entity'\]"):
        staged.set("price", 50.0, entity=["mill"])

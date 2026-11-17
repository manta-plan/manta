# SPDX-FileCopyrightText: datarecord contributors
#
# SPDX-License-Identifier: MIT

"""`Record`, and the `RecordLike` protocol it is one implementation of.

Notes
-----
- [the Record protocol](https://energy-models.github.io/datarecord/design/record/)
"""

from dataclasses import dataclass

import narwhals as nw
import pytest

from datarecord.layered.record import Record
from datarecord.mutable import WorkingRecord
from datarecord.record import EMPTY, Flags, Frames, RecordLike
from datarecord.schema import AttributeSpec, Schema
from datarecord.tools.pypsa import PyPSA
from tests.fixtures import (
    empty_child,
    empty_root,
    schema,
    write_entity_type,
    write_group,
    write_input,
    write_schema,
)

MEMBERS = ("dims", "groups", "attributes")


@pytest.fixture
def written(store):
    """A record of one layer, so every construction below reads the same files.

    One generator with a `p_max_pu` series and an `efficiency` on its
    connection, so attributes, the entity axis and a group are all present.
    """
    revision = empty_root(store)
    layer = store.layer_dir(revision.id)
    write_schema(schema(), store)
    write_entity_type(layer, "Generator", [{"entity": "wind"}])
    write_group(
        layer, "connection", [{"connection": {"entity": "wind", "bus": "north"}}]
    )
    write_input(
        layer,
        "p_max_pu",
        [
            {"entity": "wind", "snapshot": s, "value": v}
            for s, v in (("2030-01-01", 0.4), ("2030-01-02", 0.6))
        ],
    )
    write_input(layer, "efficiency", [{"entity": "wind", "bus": "north", "value": 0.9}])
    return revision


@pytest.fixture
def both(written, store):
    """One record, every way of constructing a `Record` over it.

    The same files reached by two source constructions: as the layer of a
    revision, and as a plain directory at a URI. They must agree on everything,
    which is what says reading a directory needs no implementation of its own -
    a fold over one source is a scan of it.

    A `WorkingRecord` with nothing staged is here for the mirrored reason: it is
    a `Record` one layer deeper, and an empty staging area must add nothing.

    Notes
    -----
    - [reading with pending edits](https://energy-models.github.io/datarecord/design/working-record/#reading-with-pending-edits)
    """
    node = Record(written.resolver)
    directory = store.layer(written.id)
    return (
        node,
        directory,
        WorkingRecord(node),
        WorkingRecord(directory),
    )


# -- the protocol ------------------------------------------------------------


def test_every_construction_satisfies_the_protocol(both):
    """Structural conformance, so a consumer cannot tell which it holds.

    Notes
    -----
    - [one record over one fold](https://energy-models.github.io/datarecord/design/read-path/#one-record-over-one-fold)
    """
    for record in both:
        assert isinstance(record, RecordLike)


def test_a_network_source_is_a_record(store, ac_dc):
    """`to_datarecord` returns one too, which is what puts read and write on one seam."""
    assert isinstance(PyPSA.to_datarecord(ac_dc, store.workspace.con), RecordLike)


def test_a_plain_dict_backed_record_satisfies_the_protocol(store):
    """`Frames` is the `Mapping` ABC, so eager `dict` values are a valid backing.

    The protocol asks for named lazy frames, not for a mapping that defers
    building them - so whether an implementation is lazy like `LazyFrames` or
    eager like this stays its own business.

    Notes
    -----
    - [Frames](https://energy-models.github.io/datarecord/design/record/#frames)
    """
    entity_axis = nw.from_native(
        store.workspace.con.sql(
            "SELECT 'wind' AS entity, 'Generator' AS entity_type, FALSE AS deleted"
        )
    )
    # `p_nom`'s own coordinates and no others: no `entity_type` in a long
    # row, and no `bus`, which is the connection group's coordinate rather than
    # a column every attribute carries.
    long = nw.from_native(
        store.workspace.con.sql(
            "SELECT 'wind' AS entity, 'p_nom' AS attribute,"
            " NULL::DOUBLE AS breakpoint, 100.0 AS value,"
            " NULL::VARCHAR AS snapshot, NULL::VARCHAR AS scenario,"
            " NULL::BIGINT AS period"
        )
    )

    @dataclass(frozen=True)
    class DictRecord:
        schema: Schema
        dims: Frames
        properties: Frames
        groups: dict[str, Frames]
        attributes: Frames
        outputs: Frames

        def flags(self, **categories: object) -> dict[str, Flags]:
            return {}

    record = DictRecord(
        schema(),
        {"entity": entity_axis.select("entity")},
        {"entity": entity_axis},
        {},
        {"p_nom": long},
        EMPTY,
    )
    assert isinstance(record, RecordLike)
    # Results absent, spelled as an empty mapping rather than a protocol a
    # consumer has to test for (https://energy-models.github.io/datarecord/design/record/#frames).
    assert list(record.outputs) == []
    assert record.attributes["p_nom"].implementation == nw.Implementation.DUCKDB

    # And the writer consumes it, which is the point of widening the type:
    # it iterates and looks up, both of which a `dict` answers.
    revision = store.root(record)
    assert "p_nom" in store.layer(revision.id).attributes


def test_constructions_agree_on_every_key_set(both):
    """One record, several ways of reading it: the keys must not depend on which."""
    node, *rest = both
    for other in rest:
        for member in MEMBERS:
            assert list(getattr(node, member)) == list(getattr(other, member)), member


def test_constructions_agree_on_flags(both):
    """One aggregate, whichever source list it folds over.

    Notes
    -----
    - [one record over one fold](https://energy-models.github.io/datarecord/design/read-path/#one-record-over-one-fold)
    """
    node, *rest = both
    for other in rest:
        assert node.flags() == other.flags()


def test_constructions_agree_on_rows(both):
    """A single-layer record resolves to the same rows every way.

    The rows themselves, not their count: this fixture is the whole evidence
    that reading a directory needs no implementation of its own, and two
    constructions returning the same number of different rows would satisfy a
    count.
    """
    node, *rest = both
    for other in rest:
        for attribute in node.attributes:
            left = node.attributes[attribute].collect().to_native().to_pandas()
            right = other.attributes[attribute].collect().to_native().to_pandas()
            columns = sorted(set(left.columns) & set(right.columns))
            assert set(left.columns) == set(right.columns), attribute
            # A group's struct column arrives as dicts, which pandas cannot sort.
            order = {"by": columns, "key": lambda s: s.astype(str)}
            left = left[columns].sort_values(**order).reset_index(drop=True)
            right = right[columns].sort_values(**order).reset_index(drop=True)
            assert left.equals(right), attribute


# -- laziness (https://energy-models.github.io/datarecord/design/record/#frames, https://energy-models.github.io/datarecord/design/read-path/#one-record-over-one-fold) ---------------------------------------------------


def test_frames_stay_unmaterialised(both):
    """An overlay-backed frame is a DuckDB plan, not a materialised table."""
    node, *_ = both
    frame = node.attributes["p_max_pu"]
    assert isinstance(frame, nw.LazyFrame)
    assert frame.implementation == nw.Implementation.DUCKDB
    # A narwhals operation pushes into the plan rather than executing it.
    filtered = frame.filter(~nw.col("snapshot").is_null())
    assert "FILTER" in filtered.to_native().explain().upper()


# -- flags, the one non-frame member (https://energy-models.github.io/datarecord/design/read-path/#one-record-over-one-fold) ----------------------------------


def test_flags_report_both_sets_where_components_disagree(store):
    """A mixed type puts `snapshot` in both sets, which is the split.

    Two generators, one with a series and one with a single value. Both
    containers are needed, and both sets holding `snapshot` is what says so -
    the constant pass takes the NULL-snapshot rows, the series pass the rest.

    Notes
    -----
    - [Flags](https://energy-models.github.io/datarecord/design/record/#flags)
    """
    revision = empty_root(store)
    layer = store.layer_dir(revision.id)
    write_schema(schema(), store)
    write_entity_type(layer, "Generator", [{"entity": "wind"}, {"entity": "gas"}])
    write_input(
        layer,
        "p_max_pu",
        [
            {"entity": "wind", "snapshot": s, "value": v}
            for s, v in (("2030-01-01", 0.4), ("2030-01-02", 0.6))
        ]
        + [{"entity": "gas", "value": 1.0}],
    )

    record = revision.record
    combined = record.flags()["p_max_pu"]
    assert "snapshot" in combined.varies
    assert "snapshot" in combined.broadcast


def test_flags_are_scoped_to_what_an_attribute_is_addressed_by(store):
    """A dim an attribute has no column for is in neither set, not in `broadcast`.

    `varies | broadcast` is the test for whether an attribute touches a dim at
    all, so a dim it is not addressed by has to be absent from both - otherwise
    a consumer builds a container along an axis the attribute has no values on.

    The two are easy to conflate because one relation holds every attribute's
    rows: `p_nom` is stored beside `p_max_pu`, whose `snapshot` column is NULL
    for `p_nom`'s rows. That NULL is "no such axis", not "every snapshot".

    Notes
    -----
    - [Flags](https://energy-models.github.io/datarecord/design/record/#flags)
    - [the long schema](https://energy-models.github.io/datarecord/design/format/#the-long-schema)
    """
    revision = empty_root(store)
    layer = store.layer_dir(revision.id)
    write_schema(
        schema(
            attributes={
                "Generator": {
                    # Addressed by the entity axis and nothing else.
                    "p_nom": AttributeSpec(dtype=nw.Float64(), dims={"entity"}),
                    "p_max_pu": AttributeSpec(
                        dtype=nw.Float64(), dims={"entity", "snapshot"}
                    ),
                }
            }
        ),
        store,
    )
    write_entity_type(layer, "Generator", [{"entity": "wind"}])
    write_input(layer, "p_nom", [{"entity": "wind", "value": 100.0}])
    write_input(layer, "p_max_pu", [{"entity": "wind", "value": 0.9}])

    record = revision.record
    flags = record.flags()
    # Addressed by `entity` alone, so no other axis is reportable either way.
    assert flags["p_nom"].varies == {"entity"}
    assert flags["p_nom"].broadcast == frozenset(), (
        "a dim `p_nom` has no column for is not one it broadcasts over"
    )
    # Addressed by `snapshot`, with a row leaving it NULL - that *is* a
    # broadcast, and the two cases must not read the same.
    assert "snapshot" in flags["p_max_pu"].broadcast


# -- more than one layer, which is where the fold stops being a scan ---------


def test_node_record_orders_members(store):
    """A `Record` promises member order; for an overlay that means `order_key`.

    The order follows the true owning layer through a closed intermediate node
    that changes nothing about membership.

    Notes
    -----
    - [one record over one fold](https://energy-models.github.io/datarecord/design/read-path/#one-record-over-one-fold)
    - [materialised node caches](https://energy-models.github.io/datarecord/design/layers/#materialised-node-caches)
    """
    root = empty_root(store)
    write_schema(schema(), store)
    write_entity_type(
        store.layer_dir(root.id),
        "Generator",
        [{"entity": "wind"}, {"entity": "gas"}, {"entity": "coal"}],
    )
    root.materialise()
    middle = empty_child(root)
    middle.materialise()

    child = empty_child(middle)
    write_entity_type(store.layer_dir(child.id), "Generator", [{"entity": "New Solar"}])

    axis = Record(child.resolver).properties["entity"].collect().to_native().to_pandas()
    names = list(axis[axis["entity_type"] == "Generator"]["entity"])
    assert names == ["wind", "gas", "coal", "New Solar"], (
        "first-introduced order: the root's members, then the child's addition"
    )


# -- one layer read at its URI, with no tree around it -----------------------


def test_a_directory_has_no_connections_when_none_were_written(store, tmp_path):
    """A record with no `groups/connection.parquet` has no such key, not an error.

    Notes
    -----
    - [connections](https://energy-models.github.io/datarecord/design/record/#connections)
    """
    revision = empty_root(store)
    layer = store.layer_dir(revision.id)
    write_schema(schema(), store)
    write_entity_type(layer, "Generator", [{"entity": "wind"}])

    assert "connection" not in store.layer(revision.id).groups


def test_missing_key_raises(both):
    """A key the record does not hold is a `KeyError`, not an empty frame.

    Listing the keys is cheap and answers membership without a lookup.

    Notes
    -----
    - [Frames](https://energy-models.github.io/datarecord/design/record/#frames)
    """
    for record in both:
        assert "p_max_pu" in record.attributes
        assert "nope" not in record.attributes
        assert len(list(record.attributes)) == len(record.attributes)
        with pytest.raises(KeyError):
            record.attributes["not_an_attribute"]


def test_outputs_are_empty_until_solved(both):
    """An unsolved network's results are absent rather than defaults.

    Notes
    -----
    - [outputs](https://energy-models.github.io/datarecord/design/read-path/#outputs)
    """
    for record in both:
        assert list(record.outputs) == []


def test_write_record_omits_outputs_for_an_unsolved_source(store, written):
    """A source with no results produces a layer with no `outputs/`.

    Notes
    -----
    - [writing a whole record](https://energy-models.github.io/datarecord/design/writing/)
    """
    from datarecord.duck import try_read_parquet

    base = written.record

    class Unsolved:
        """The same record, with no results: `outputs` answers empty."""

        schema = base.schema
        dims = base.dims
        properties = base.properties
        groups = base.groups
        attributes = base.attributes
        outputs = EMPTY
        flags = base.flags

    source = Unsolved()
    assert isinstance(source, RecordLike)

    # An empty `outputs` writes no `outputs/` at all, rather than an empty
    # directory (https://energy-models.github.io/datarecord/design/writing/).
    revision = store.root(source)
    layer = store.layer_dir(revision.id)
    assert try_read_parquet(layer + "outputs/*.parquet", store.workspace.con) is None
    assert "p_max_pu" in store.layer(revision.id).attributes


# -- one schema per record root (https://energy-models.github.io/datarecord/design/schema/#one-schema-per-record) ----------------------------------------


def test_two_stores_on_one_workspace_read_their_own_schema(workspace, tmp_path):
    """A store's schema comes from *its* location, and so do its layers.

    Two records on two locations disagree about their dims without either
    being wrong, while sharing one workspace.
    """
    stores = {}
    cases: list[tuple[str, dict[str, nw.dtypes.DType]]] = [
        ("a", {"scenario": nw.String()}),
        ("b", {"vintage": nw.Int64()}),
    ]
    for name, dims in cases:
        store = workspace.store(str(tmp_path / name))
        write_schema(schema(dims=dims, partial=set(dims)), store)
        revision = empty_root(store)
        write_input(
            store.layer_dir(revision.id), "p_nom", [{"entity": "g", "value": 1.0}]
        )
        stores[name] = (store, revision)

    (_, revision_a), (store_b, revision_b) = stores["a"], stores["b"]
    # Beyond `entity` and `bus`, which every schema here declares, the group.
    a, b = revision_a.record.schema, revision_b.record.schema
    assert a.broadcast_dims == ("entity", "bus", "scenario", "connection")
    assert b.broadcast_dims == ("entity", "bus", "vintage", "connection")

    # A layer read directly needs no schema supplied either: its own directory
    # carries none (https://energy-models.github.io/datarecord/design/schema/#one-schema-per-record), so its store's answers.
    assert store_b.layer(revision_b.id).schema.broadcast_dims == (
        "entity",
        "bus",
        "vintage",
        "connection",
    )

    for name, (store, revision) in stores.items():
        location = tmp_path / name
        assert (location / "layers" / str(revision.id)).is_dir(), (
            "each location's layers land under it"
        )
        assert (location / "revisions" / f"{revision.id}.json").is_file()

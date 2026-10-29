# SPDX-FileCopyrightText: datarecord contributors
#
# SPDX-License-Identifier: MIT

"""Writing a layer from long-format frames.

Notes
-----
- [writing a whole record](https://energy-models.github.io/datarecord/design/writing/)
"""

import shutil
from pathlib import Path

import narwhals as nw
import pandas as pd
import pytest

from datarecord import Workspace
from datarecord.layered.resolve import read_schema
from datarecord.mutable import WorkingRecord
from datarecord.record import EMPTY, LazyFrames
from datarecord.schema import AttributeSpec, Dimension, PropertySpec, Schema
from datarecord.tools.pypsa import PyPSA
from tests.fixtures import (
    empty_root,
    export_network,
    relation,
    schema,
    unpacked,
    write_schema,
)


class _Source:
    """A minimal `Record` over ready-made frames, counting each build."""

    def __init__(
        self,
        schema,
        attributes=None,
        connections=None,
        outputs=None,
        dims=None,
        properties=None,
    ):
        self._schema = schema
        self.built: list[str] = []
        self._attributes = attributes or {}
        self._connections = connections or {}
        self._outputs = outputs or {}
        self._dims = dims or {}
        self._properties = properties or {}

    @property
    def schema(self):
        return self._schema

    def _frames(self, mapping, tag):
        def build(key):
            self.built.append(f"{tag}:{key}")
            return nw.from_native(mapping[key]).lazy()

        return LazyFrames(tuple(mapping), build)

    @property
    def dims(self):
        return self._frames(self._dims, "dims") if self._dims else EMPTY

    @property
    def properties(self):
        return self._frames(self._properties, "properties")

    @property
    def groups(self):
        """Keyed by group, one frame each."""
        return self._frames(self._connections, "groups")

    @property
    def attributes(self):
        return self._frames(self._attributes, "attributes")

    @property
    def outputs(self):
        return self._frames(self._outputs, "outputs")

    def flags(self, **categories):
        return {}


_SCHEMA = schema()


def _long(**overrides) -> pd.DataFrame:
    """One long row carrying its attribute's own coordinates, and no others.

    Shaped from the spec rather than spelled: a source handing over a column
    the attribute is not addressed by is what the writer now rejects, so a
    helper that spelled every declared dim would be testing against a record no
    reader would accept.

    Notes
    -----
    - [the long schema](https://energy-models.github.io/datarecord/design/format/#the-long-schema)
    """
    row = {
        "connection": None,
        "entity": "steel_dri",
        "bus": None,
        "snapshot": None,
        "scenario": None,
        "period": None,
        "attribute": "p_nom",
        "breakpoint": None,
        "value": 1.0,
    }
    row.update(overrides)
    columns = _SCHEMA.long_columns_for(str(row["attribute"]))
    return pd.DataFrame([{c: row[c] for c in columns}])


# -- the lazy mapping (https://energy-models.github.io/datarecord/design/format/) -------------------------------------------------


def test_a_write_builds_each_key_once(store):
    """The writer looks up every key exactly once, and only what it writes."""
    source = _Source(
        _SCHEMA,
        attributes={"p_nom": _long(), "e_nom": _long(attribute="e_nom")},
        dims={"entity": pd.DataFrame({"entity": ["steel_dri"]})},
        properties={
            "entity": pd.DataFrame(
                {"entity": ["steel_dri"], "entity_type": ["Process"]}
            )
        },
    )
    store.root(source)

    assert sorted(source.built) == [
        "attributes:e_nom",
        "attributes:p_nom",
        "dims:entity",
        "properties:entity",
    ]


# -- creating a layer -------------------------------------------------------


def test_a_write_creates_a_new_layer(store):
    """Files land where `layer_dir` says - data only, no schema.

    The record's one schema goes beside `layers/`, so a layer directory holds
    nothing but data. That is what keeps it a plain parquet directory a reader
    knowing nothing about layering can open.

    Notes
    -----
    - [one schema per record](https://energy-models.github.io/datarecord/design/schema/#one-schema-per-record)
    """
    revision = store.root(_Source(_SCHEMA, attributes={"p_nom": _long()}))

    base = Path(store.layer_dir(revision.id))
    assert (base / "inputs" / "p_nom.parquet").exists()
    assert not (base / "manifest.json").exists()
    # Written once for the whole tree, and it is what the layer is read under.
    assert read_schema(store) == _SCHEMA
    assert store.revisions() == [revision], "the revision file makes it real"


def test_no_layer_file_carries_order_key(store, tmp_path):
    """`order_key` is the fold's answer about a frame, never a column of one.

    A source handing over *resolved* frames carries it - which is what writing
    a `WorkingRecord` as a standalone directory does, the record itself being
    what is written. Writing it would put a struct column in files the
    format promises a foreign reader can open, and would look like stored order
    where the fold always re-derives it from file order.

    Notes
    -----
    - [the owner map](https://energy-models.github.io/datarecord/design/read-path/#owner-map)
    - [writing a whole record](https://energy-models.github.io/datarecord/design/writing/)
    """
    entities = ["steel_dri", "h2_north"]
    connection = {"entity": "steel_dri", "bus": "h2_north"}
    revision = store.root(
        _Source(
            _SCHEMA,
            attributes={"p_nom": _long()},
            dims={"entity": pd.DataFrame({"entity": entities})},
            properties={
                "entity": pd.DataFrame(
                    {"entity": entities, "entity_type": ["Process", "Bus"]}
                )
            },
            connections={"connection": pd.DataFrame({"connection": [connection]})},
        )
    )

    staged = WorkingRecord(revision.record)
    staged.set("p_nom", 150.0, entity=["steel_dri"])
    out = str(tmp_path / "flat")
    store.workspace.write(staged, out)

    written = sorted(Path(out).rglob("*.parquet"))
    assert {"dims/entity.parquet", "groups/connection.parquet"} <= {
        path.relative_to(out).as_posix() for path in written
    }, "the frames the fold orders must be among those written"
    for path in written:
        columns = store.workspace.con.sql(
            f"SELECT * FROM read_parquet('{path}')"
        ).columns
        assert "order_key" not in columns, f"{path.relative_to(out)} carries order_key"


def test_a_write_rejects_a_category_the_enum_does_not_declare(store):
    entities = pd.DataFrame({"entity": ["a"], "entity_type": ["Nope"]})
    with pytest.raises(Exception, match="Nope"):
        store.root(
            _Source(
                _SCHEMA,
                dims={"entity": entities[["entity"]]},
                properties={"entity": entities},
            )
        )
    _nothing_reachable(store)


def test_a_directory_target_carries_its_own_schema(workspace, tmp_path):
    """A standalone record *is* one record, so its schema goes in the directory.

    Notes
    -----
    - [one schema per record](https://energy-models.github.io/datarecord/design/schema/#one-schema-per-record)
    """
    out = str(tmp_path / "standalone")
    source = _Source(_SCHEMA, attributes={"p_nom": _long()})
    record = workspace.write(source, out)

    assert (Path(out) / "manifest.json").exists()
    assert record.schema == _SCHEMA
    assert workspace.at(out).schema == _SCHEMA

    # And it is that file answering: a standalone record is one whole record,
    # so it reads the same through a workspace that knows nothing about it.
    elsewhere = Workspace()
    try:
        again = elsewhere.at(out)
        assert again.schema == _SCHEMA
        assert again.resolver.revision_id == record.resolver.revision_id, (
            "the manifest's id names one layer to every reader"
        )
    finally:
        elsewhere.close()


def test_a_directory_without_a_manifest_is_no_standalone_record(store, tmp_path):
    """`Workspace.at` refuses a layer directory: that is read through its store.

    Notes
    -----
    - [one schema per record](https://energy-models.github.io/datarecord/design/schema/#one-schema-per-record)
    """
    revision = store.root(_Source(_SCHEMA, attributes={"p_nom": _long()}))
    with pytest.raises(FileNotFoundError, match="no manifest"):
        store.workspace.at(store.layer_dir(revision.id))
    assert store.layer(revision.id).schema == _SCHEMA


def test_a_standalone_write_refuses_an_existing_directory(workspace, tmp_path):
    """Refused up front, empty or holding a record, so nothing is half-replaced.

    Notes
    -----
    - [a standalone directory](https://energy-models.github.io/datarecord/design/writing/#a-standalone-directory)
    """
    source = _Source(_SCHEMA, attributes={"p_nom": _long()})
    with pytest.raises(FileExistsError, match="does not exist yet"):
        workspace.write(source, str(tmp_path))
    assert source.built == [], "refused before any frame was built"
    assert list(tmp_path.iterdir()) == [], "refused before anything was written"

    out = str(tmp_path / "new")
    assert workspace.write(source, out).schema == _SCHEMA
    with pytest.raises(FileExistsError, match="does not exist yet"):
        workspace.write(source, out)


def test_a_failed_standalone_write_leaves_no_record(workspace, tmp_path):
    """The manifest is written last, so a directory whose write failed is none.

    Notes
    -----
    - [a standalone directory](https://energy-models.github.io/datarecord/design/writing/#a-standalone-directory)
    """
    out = tmp_path / "standalone"
    short = _long().drop(columns=["breakpoint"])
    with pytest.raises(ValueError, match="missing long-schema columns"):
        workspace.write(_Source(_SCHEMA, attributes={"p_nom": short}), str(out))
    assert not out.exists()
    with pytest.raises(FileNotFoundError):
        workspace.at(str(out))


def _p_nom(value: float) -> _Source:
    return _Source(_SCHEMA, attributes={"p_nom": _long(value=value)})


def _read_p_nom(record) -> list[float]:
    return record.attributes["p_nom"].collect()["value"].to_list()


def test_a_record_written_again_at_one_uri_reads_as_itself(workspace, tmp_path):
    """The workspace shares fold tables by layer id, so each write mints its own.

    An id derived from the URI would key the second record's folds as the
    first's, and serve the deleted record's values.

    Notes
    -----
    - [a standalone directory](https://energy-models.github.io/datarecord/design/writing/#a-standalone-directory)
    """
    out = tmp_path / "standalone"
    assert _read_p_nom(workspace.write(_p_nom(1.0), str(out))) == [1.0]
    shutil.rmtree(out)
    assert _read_p_nom(workspace.write(_p_nom(2.0), str(out))) == [2.0], (
        "the new record, not the fold of the one deleted"
    )


def test_a_relative_uri_is_read_where_it_was_resolved(workspace, tmp_path, monkeypatch):
    """One relative path names two records from two working directories.

    Notes
    -----
    - [a standalone directory](https://energy-models.github.io/datarecord/design/writing/#a-standalone-directory)
    """
    for name, value in [("a", 1.0), ("b", 2.0)]:
        (tmp_path / name).mkdir()
        monkeypatch.chdir(tmp_path / name)
        assert _read_p_nom(workspace.write(_p_nom(value), "out")) == [value], (
            f"the record written under {name}/"
        )
    assert _read_p_nom(workspace.at("out")) == [2.0], "read from the cwd, b/"
    monkeypatch.chdir(tmp_path / "a")
    assert _read_p_nom(workspace.at("out")) == [1.0], "read from the cwd, a/"


def test_a_manifest_without_an_id_is_refused(workspace, tmp_path):
    """Read without one, the record's folds would have nothing to be keyed by.

    Notes
    -----
    - [one schema per record](https://energy-models.github.io/datarecord/design/schema/#one-schema-per-record)
    """
    out = tmp_path / "standalone"
    workspace.write(_p_nom(1.0), str(out))
    (out / "manifest.json").write_text(_SCHEMA.model_dump_json())
    with pytest.raises(ValueError, match="no record id"):
        workspace.at(str(out))


def _nothing_reachable(store) -> None:
    """A failed tree write leaves no revision, no layer and no manifest."""
    assert store.revisions() == [], "no revision file, so nothing reaches a layer"
    layers = Path(store.uri, "layers")
    assert not (layers.exists() and any(layers.iterdir())), "staged and removed"
    assert not Path(store.manifest_uri).exists(), "never widened for no layer"


def test_a_file_carries_only_its_own_attributes_coordinates(store):
    """One attribute is one file, so one column set - not every declared dim.

    A component attribute has no `bus` column, a connection attribute does, and
    neither carries a dim it is not addressed by. The uniform prefix this
    replaces put an all-NULL `bus` on every file and a `period` column on
    attributes that never vary over one.

    Notes
    -----
    - [the long schema](https://energy-models.github.io/datarecord/design/format/#the-long-schema)
    - [where a value lives](https://energy-models.github.io/datarecord/design/format/#where-a-value-lives)
    """
    connection = {"entity": "steel_dri", "bus": "h2_north"}
    revision = store.root(
        _Source(
            _SCHEMA,
            attributes={
                "p_max_pu": _long(
                    attribute="p_max_pu", snapshot=pd.Timestamp("2030-01-01")
                ),
                "efficiency": _long(attribute="efficiency", connection=connection),
                "weight": _long(attribute="weight", scenario="s1"),
            },
        )
    )
    inputs = Path(store.layer_dir(revision.id), "inputs")

    def columns(attribute: str) -> set[str]:
        return set(
            store.workspace.con.read_parquet(
                str(inputs / f"{attribute}.parquet")
            ).columns
        )

    assert columns("p_max_pu") == {
        "entity",
        "snapshot",
        "scenario",
        "period",
        "attribute",
        "breakpoint",
        "value",
    }, "a component attribute carries `entity`, not the connection group's `bus`"

    efficiency = columns("efficiency")
    assert "connection" in efficiency, "a connection attribute carries the group"
    assert "bus" not in efficiency, "as one struct column, not its coordinates"
    assert columns("weight") & {"entity", "period"} == set(), (
        "and no dim it is not addressed by"
    )


# -- validation -------------------------------------------------------------


def test_a_write_rejects_an_undeclared_attribute(store):
    """An attribute with no spec has no shape, so there is nothing to write it as.

    Its `dims` are what say which columns the file carries, so writing one the
    schema does not declare would put a file in `inputs/` whose column set no
    reader could derive. A *result* is exempt - a tool derives those from its
    own registry, never from the schema.

    Notes
    -----
    - [AttributeSpec](https://energy-models.github.io/datarecord/design/schema/#attributespec)
    """
    source = _Source(_SCHEMA, attributes={"not_declared": _long(attribute="nope")})

    with pytest.raises(ValueError, match="not a declared attribute"):
        store.root(source)


def test_a_write_rejects_a_coordinate_the_attribute_lacks(store):
    """A column the attribute is not addressed by is a disagreement, not a spare.

    The read path projects an attribute's own coordinates, so a `bus` on a
    component attribute would be written and never read - and a source emitting
    one means something different by the attribute than the schema does.
    Reported rather than dropped, since silently narrowing would hide that.

    Notes
    -----
    - [the long schema](https://energy-models.github.io/datarecord/design/format/#the-long-schema)
    """
    wide = _long().assign(bus=None)
    source = _Source(_SCHEMA, attributes={"p_nom": wide})

    with pytest.raises(
        ValueError, match=r"carries columns \['bus'\].*not addressed by"
    ):
        store.root(source)


def test_a_write_rejects_a_group_column_that_is_not_its_key(store):
    """A group's column is a struct of exactly its key coordinates.

    DuckDB casts a struct by field name, so a missing field would be written as
    NULL rather than refused, re-keying every row.

    Notes
    -----
    - [groups](https://energy-models.github.io/datarecord/design/schema/#groups)
    """
    row = {"attribute": "efficiency", "breakpoint": None, "value": 1.0}
    row |= {"snapshot": None, "scenario": None, "period": None}
    short = pd.DataFrame([{"connection": {"entity": "steel_dri"}, **row}])
    source = _Source(_SCHEMA, attributes={"efficiency": short})

    with pytest.raises(ValueError, match=r"'connection' as .*\['entity', 'bus'\]"):
        store.root(source)


def test_a_group_column_round_trips_as_a_struct(store):
    """What a source hands over as the group's struct reads back as one."""
    row = {"attribute": "efficiency", "breakpoint": None, "value": 1.0}
    row |= {"snapshot": None, "scenario": None, "period": None}
    connection = {"entity": "steel_dri", "bus": "h2_north"}
    frame = pd.DataFrame([{"connection": connection, **row}])
    revision = store.root(_Source(_SCHEMA, attributes={"efficiency": frame}))

    rows = relation(revision, "efficiency").project("connection, value").fetchall()
    assert rows == [(connection, 1.0)]


def test_a_write_rejects_a_missing_long_column(store):
    """A frame the fold could not resolve is refused before anything is written."""
    short = _long().drop(columns=["breakpoint"])
    source = _Source(_SCHEMA, attributes={"p_nom": short})

    with pytest.raises(ValueError, match="missing long-schema columns.*breakpoint"):
        store.root(source)
    _nothing_reachable(store)


def test_a_write_rejects_a_flat_group_frame(store):
    """A group file is keyed by the struct column named for it, not its coordinates.

    Notes
    -----
    - [groups](https://energy-models.github.io/datarecord/design/schema/#groups)
    """
    flat = pd.DataFrame({"entity": ["steel_dri"], "bus": ["h2"]})
    source = _Source(_SCHEMA, connections={"connection": flat})

    with pytest.raises(ValueError, match=r"missing \['connection'\]"):
        store.root(source)


def test_a_write_rejects_a_group_struct_not_of_its_key(store):
    """A struct missing a key field would re-key every row once cast.

    Notes
    -----
    - [groups](https://energy-models.github.io/datarecord/design/schema/#groups)
    """
    partial = pd.DataFrame({"connection": [{"entity": "steel_dri"}]})
    source = _Source(_SCHEMA, connections={"connection": partial})

    with pytest.raises(ValueError, match="one struct column"):
        store.root(source)


def test_a_write_rejects_a_nested_axis_without_its_parent(store):
    """A `within` dim's file needs a column per parent, or the fold miskeys it.

    `snapshot within period` makes the axis key `(period, snapshot)`, so a
    `snapshot.parquet` carrying only timestamps would fold two periods'
    identically labelled hours into one row.

    Notes
    -----
    - [within](https://energy-models.github.io/datarecord/design/schema/#within-an-axis-inside-an-axis)
    """
    nested = schema(within={"snapshot": {"period"}})
    source = _Source(
        nested,
        dims={"snapshot": pd.DataFrame({"snapshot": pd.to_datetime(["2020-01-01"])})},
    )

    with pytest.raises(ValueError, match="axis key columns.*period"):
        store.root(source)
    _nothing_reachable(store)


def test_a_write_rejects_an_undeclared_axis_column(store):
    """An axis file's payload is the schema's to state, like a long frame's.

    A column no declaration accounts for would be read back with no dtype and
    no meaning, so it is refused rather than carried along.

    Notes
    -----
    - [where a value lives](https://energy-models.github.io/datarecord/design/format/#where-a-value-lives)
    """
    source = _Source(
        schema(),
        dims={"scenario": pd.DataFrame({"scenario": ["high"], "nonsense": [1.0]})},
    )

    with pytest.raises(
        ValueError, match="does not declare as properties of 'scenario'"
    ):
        store.root(source)
    _nothing_reachable(store)


def test_an_attribute_column_in_a_dims_frame_is_refused(store):
    """`weight` over `scenario` alone is an attribute, so long rows, never an axis column.

    Notes
    -----
    - [where a value lives](https://energy-models.github.io/datarecord/design/format/#where-a-value-lives)
    """
    source = _Source(
        schema(),
        dims={"scenario": pd.DataFrame({"scenario": ["high"], "weight": [0.4]})},
    )

    with pytest.raises(ValueError, match="they are attributes, whose values are long"):
        store.root(source)
    _nothing_reachable(store)


def _plant(p_nom: frozenset[str], *, categorized: bool = False) -> Schema:
    """Entities and scenarios, `p_nom` over `p_nom`, `entity_type` if `categorized`."""
    return Schema(
        dimensions={
            "entity": Dimension(dtype=nw.String()),
            "scenario": Dimension(dtype=nw.String()),
        },
        properties=(
            {"entity": {"entity_type": PropertySpec(dtype=nw.Enum(["Gen", "Load"]))}}
            if categorized
            else {}
        ),
        attributes={"p_nom": AttributeSpec(dtype=nw.Float64(), dims=p_nom)},
        partial=frozenset({"entity", "scenario"}),
    )


def _plant_layer(store, schema: Schema, **columns):
    """A root holding entities `g1` and `g2` with their `p_nom`, under `schema`."""
    write_schema(schema, store)
    root = empty_root(store)
    staged = WorkingRecord(root.record)
    staged.add("entity", ["g1", "g2"], **columns)
    staged.set("p_nom", {"g1": 1.0, "g2": 2.0})
    return root.child(staged.edits)


def test_a_single_dim_attribute_is_long_rows_of_inputs(store):
    """`p_nom` over `entity` alone is one `inputs/` row per label, not an axis column.

    Notes
    -----
    - [where a value lives](https://energy-models.github.io/datarecord/design/format/#where-a-value-lives)
    """
    layer = _plant_layer(store, _plant(frozenset({"entity"})))

    assert "p_nom" in layer.record.attributes
    on_disk = pd.read_parquet(
        Path(store.layer_dir(layer.id), "inputs", "p_nom.parquet")
    )
    assert list(on_disk.columns) == ["entity", "attribute", "breakpoint", "value"]
    assert dict(zip(on_disk["entity"], on_disk["value"])) == {"g1": 1.0, "g2": 2.0}, (
        "one row per label"
    )
    axis = pd.read_parquet(Path(store.layer_dir(layer.id), "dims", "entity.parquet"))
    assert "p_nom" not in axis.columns


def test_widening_a_single_dim_attribute_reads_old_rows_in_every_scenario(store):
    """An old row has no `scenario` column, read NULL, so it broadcasts.

    Notes
    -----
    - [versioning](https://energy-models.github.io/datarecord/design/schema/#versioning)
    """
    narrow = _plant(frozenset({"entity"}))
    layer = _plant_layer(store, narrow)

    wide = _plant(frozenset({"entity", "scenario"}))
    assert wide.compatible_with(narrow) == []
    write_schema(wide, store)
    staged = WorkingRecord(store.revision(layer.id).record)
    staged.add("scenario", ["low", "high"])
    child = store.revision(layer.id).child(staged.edits)

    rows = child.record.attributes["p_nom"].collect().to_pandas()
    got = dict(zip(zip(rows["entity"], rows["scenario"]), rows["value"]))
    assert got == {
        ("g1", "low"): 1.0,
        ("g1", "high"): 1.0,
        ("g2", "low"): 2.0,
        ("g2", "high"): 2.0,
    }, "the old layer's value in every scenario"


def test_categories_add_one_column_to_the_entity_axis_and_nothing_else(tmp_path):
    """Same files with and without a categorizing property; `dims/entity.parquet` differs by it.

    Notes
    -----
    - [the entity axis](https://energy-models.github.io/datarecord/design/format/#the-entity-axis)
    """
    layouts = {}
    for categorized in (False, True):
        ws = Workspace()
        try:
            store = ws.store(str(tmp_path / str(categorized)))
            columns = {"entity_type": "Gen"} if categorized else {}
            layer = _plant_layer(
                store, _plant(frozenset({"entity"}), categorized=categorized), **columns
            )
        finally:
            ws.close()
        base = Path(store.layer_dir(layer.id))
        files = sorted(str(f.relative_to(base)) for f in base.rglob("*.parquet"))
        layouts[categorized] = (
            files,
            pd.read_parquet(base / "dims" / "entity.parquet"),
        )

    (plain_files, plain_axis), (typed_files, typed_axis) = layouts[False], layouts[True]
    assert plain_files == typed_files, "the same files"
    assert not any(f.startswith("dims/entity_type") for f in typed_files), (
        "no per-label file"
    )
    assert set(typed_axis.columns) - set(plain_axis.columns) == {"entity_type"}
    assert set(plain_axis.columns) <= set(typed_axis.columns), (
        "differing by exactly one column"
    )
    assert dict(zip(typed_axis["entity"], typed_axis["entity_type"].astype(str))) == {
        "g1": "Gen",
        "g2": "Gen",
    }, "the category is read back from the axis file"


_AWKWARD = Schema(
    dimensions={
        "entity": Dimension(dtype=nw.String()),
        "select": Dimension(dtype=nw.String()),
        "Horizon": Dimension(dtype=nw.String()),
    },
    attributes={
        "Order Size": AttributeSpec(
            dtype=nw.Float64(), dims={"entity", "select", "Horizon"}
        ),
    },
    properties={"select": {"Group": PropertySpec(dtype=nw.Float64())}},
    partial={"select", "Horizon"},
)


def _awkward(values: dict[tuple[str, str], float]) -> _Source:
    long = pd.DataFrame(
        [
            {
                "entity": "plant",
                "select": s,
                "Horizon": h,
                "attribute": "Order Size",
                "breakpoint": None,
                "value": v,
            }
            for (s, h), v in values.items()
        ]
    )
    return _Source(
        _AWKWARD,
        attributes={"Order Size": long},
        dims={
            "entity": pd.DataFrame({"entity": ["plant"]}),
            "select": pd.DataFrame({"select": ["a", "b"]}),
            "Horizon": pd.DataFrame({"Horizon": ["near", "far"]}),
        },
        properties={
            "select": pd.DataFrame({"select": ["a", "b"], "Group": [1.0, 2.0]})
        },
    )


def test_names_needing_quotes_round_trip_through_layers(store, workspace, tmp_path):
    """A space, mixed case and an SQL keyword are all a declared name may hold.

    The child patches one value along both `partial` dims, so the owner map's
    flag structs, keyed by those names, are built and folded.

    Notes
    -----
    - [names](https://energy-models.github.io/datarecord/design/schema/#names)
    """
    root = store.root(_awkward({("a", "near"): 1.0, ("b", "far"): 2.0}))
    child = root.child(_awkward({("b", "far"): 5.0}))

    assert child.record.schema == _AWKWARD, "the manifest reads back unchanged"
    rows = relation(child, "Order Size").df()
    got = dict(zip(zip(rows["select"], rows["Horizon"]), rows["value"]))
    assert got == {("a", "near"): 1.0, ("b", "far"): 5.0}, (
        "the child's value wins at its coordinate and the root's elsewhere"
    )
    axis = child.resolver.dims.axes["select"].df()
    assert dict(zip(axis["select"], axis["Group"])) == {"a": 1.0, "b": 2.0}

    out = str(tmp_path / "standalone")
    workspace.write(child.record, out)
    again = workspace.at(out)
    assert again.schema == _AWKWARD
    flat = again.attributes["Order Size"].collect().to_pandas()
    assert dict(zip(zip(flat["select"], flat["Horizon"]), flat["value"])) == got, (
        "a flattened standalone copy reads the same"
    )


# -- the PyPSA source (https://energy-models.github.io/datarecord/design/format/) ------------------------------------------------


def test_to_datarecord_lists_without_unpivoting(store, ac_dc):
    """Key sets come off the network and its registry, so listing is cheap."""
    source = PyPSA.to_datarecord(ac_dc, store.workspace.con)
    assert "entity" in source.dims
    assert "connection" in source.groups
    assert "p_max_pu" in source.attributes
    assert "v_nom" in source.attributes, "a static attribute is long rows too"
    assert "carrier" not in source.attributes, "a property is no attribute"
    # A port attribute is one bus-keyed attribute, not one per port (https://energy-models.github.io/datarecord/design/record/#connections).
    assert "efficiency" in source.attributes
    assert "efficiency2" not in source.attributes


def test_ports_round_trip_through_connections_with_a_role_per_type(store, ac_dc):
    """Each port is a connection row with a role, and comes back as its own column.

    Notes
    -----
    - [connections](https://energy-models.github.io/datarecord/design/record/#connections)
    - [consuming a record](https://energy-models.github.io/datarecord/design/tools/)
    """
    revision = export_network(ac_dc, store)
    rows = unpacked(
        store.workspace.con.read_parquet(
            store.layer_dir(revision.id) + "groups/connection.parquet"
        )
    )
    back = PyPSA.build(revision.record)

    for ctype, roles, ports in (
        ("Link", {"input", "output"}, ("bus0", "bus1")),
        ("Generator", {"attached"}, ("bus",)),
    ):
        original = ac_dc.c[ctype].static
        mine = rows[rows["entity"].isin(original.index)]
        assert set(mine["role"]) == roles, f"{ctype} roles follow PyPSA's sign"
        for port in ports:
            assert set(mine["bus"]) >= set(original[port]), f"{ctype}.{port} stored"
            assert list(back.c[ctype].static[port]) == list(original[port]), (
                f"{ctype}.{port} comes back under its own name"
            )

# SPDX-FileCopyrightText: datarecord contributors
#
# SPDX-License-Identifier: MIT

"""`WorkingRecord`: staging, the edit operations, writing the edits.

Notes
-----
- [WorkingRecord](https://energy-models.github.io/datarecord/design/working-record/)
"""

import narwhals as nw
import pandas as pd
import pytest

from datarecord import Workspace
from datarecord.layered.record import Record
from datarecord.layered.resolve import read_schema, write_schema
from datarecord.layered.sources import ParquetLayer
from datarecord.mutable import WorkingRecord, normalise_value
from datarecord.schema import (
    AttributeSpec,
    Dimension,
    Group,
    PropertySpec,
    Schema,
    Trait,
)
from tests.fixtures import empty_root, export_network, schema, unpacked

GEN = "Generator"


@pytest.fixture(scope="module")
def root(tmp_path_factory, ac_dc):
    """`ac_dc` exported and materialised once for the module, to branch edits from.

    Shared, so a test only ever branches a child of it and never declares
    into its store.
    """
    workspace = Workspace()
    revision = export_network(
        ac_dc, workspace.store(str(tmp_path_factory.mktemp("ac_dc")))
    )
    revision.materialise()
    yield revision
    workspace.close()


@pytest.fixture
def staged(root):
    return WorkingRecord(root.record)


@pytest.fixture(scope="module")
def written_directory(root, tmp_path_factory):
    """`root` written standalone, as a URI a caller could pass to `Workspace.at`."""
    out = str(tmp_path_factory.mktemp("written") / "standalone")
    root.store.workspace.write(root.record, out)
    return out


def _small(store, **declared):
    """A root of two generators with a `p_nom`, under `schema(**declared)`.

    `Norway` is both a `Bus` entity and a `bus` label, as in `ac_dc`.
    """
    write_schema(schema(**declared), store)
    revision = empty_root(store)
    staged = WorkingRecord(revision.record)
    staged.add("entity", ["Manchester Wind", "Norway Wind"], entity_type=GEN)
    staged.add("entity", ["Norway"], entity_type="Bus")
    staged.add("bus", ["Norway"])
    staged.set("p_nom", [80.0, 100.0], entity=["Manchester Wind", "Norway Wind"])
    return revision.child(staged.edits)


def _layer_rows(revision, attribute, kind="inputs"):
    """One committed layer's own `<kind>/<attribute>.parquet`, as pandas.

    The single-layer view, read through the `LayerSource` for that layer rather
    than the folding resolver: "what did this patch write" is a question about
    one layer's file, not the resolved record, so `Store.layer` - which folds a
    source through the whole-tree machinery - is the wrong lens for it.
    """
    rel = ParquetLayer(
        revision.id, read_schema(revision.store), revision.store
    ).attribute(attribute, kind)
    return rel.to_df() if rel is not None else pd.DataFrame()


def _layer_axis(revision, dim):
    """One committed layer's own `dims/<dim>.parquet`, as pandas - `_layer_rows` for an axis."""
    rel = ParquetLayer(revision.id, read_schema(revision.store), revision.store).axis(
        dim
    )
    return rel.to_df() if rel is not None else pd.DataFrame()


def _unpacked(frame, group="connection"):
    """A group attribute's rows with the group's struct spread flat, as pandas."""
    native = frame.collect().to_native().to_pandas()
    fields = pd.DataFrame(native.pop(group).tolist(), index=native.index)
    return pd.concat([fields, native], axis=1)


# -- the protocol (https://energy-models.github.io/datarecord/design/working-record/#the-shape-of-an-edit) ----------------------------------------------------


def test_a_working_record_overrides_no_read_member():
    """Every member it defines beyond `Record`'s is an edit, `edits`, or private.

    The property the whole design rests on: a staged edit is read by the same
    fold that reads a committed layer, so a *read* member `WorkingRecord`
    redefines is a place where staging stopped being just another layer. No
    behavioural test would name that, because both paths would still answer -
    they would just be two paths again.

    `outputs` is the one allowed exception, results not overlaying, and it is
    listed so that adding a second one requires editing this line.
    """
    edits = {
        "set",
        "add",
        "remove",
        "add_group",
        "remove_group",
        "rollback",
        "edits",
    }
    allowed_read_override = {"outputs"}

    inherited = {n for n in vars(Record) if not n.startswith("_")}
    defined = {n for n in vars(WorkingRecord) if not n.startswith("_")}
    assert inherited & defined <= allowed_read_override, (
        "a read member redefined here means staging is no longer just a layer"
    )
    assert defined - inherited == edits, (
        "a public member that is neither an edit nor an inherited read"
    )


# -- value forms (https://energy-models.github.io/datarecord/design/working-record/#set) -----------------------------------------------------


@pytest.mark.parametrize(
    ("value", "labels", "keys", "values"),
    [
        (150.0, ["wind1", "wind2"], None, [150.0]),
        ([150.0, 80.0], ["wind1", "wind2"], ["wind1", "wind2"], [150.0, 80.0]),
        ({"wind1": 150.0, "wind2": 80.0}, None, ["wind1", "wind2"], [150.0, 80.0]),
        (
            pd.Series({"2030-01-01": 0.4, "2030-01-02": 0.6}),
            None,
            ["2030-01-01", "2030-01-02"],
            [0.4, 0.6],
        ),
    ],
    ids=["scalar-has-no-keys", "sequence-is-positional", "mapping", "series-index"],
)
def test_a_value_form_supplies_its_keys(value, labels, keys, values):
    got_keys, got_values = normalise_value(value, labels)
    assert (got_keys, got_values) == (keys, values), "keys align with values"


@pytest.mark.parametrize(
    ("value", "labels", "match"),
    [
        ([1.0, 2.0, 3.0], ["wind1", "wind2"], "2 labels"),
        ([1.0, 2.0], None, "list keyword"),
    ],
    ids=["wrong-length", "needs-labels"],
)
def test_a_sequence_must_align_to_labels(value, labels, match):
    with pytest.raises(ValueError, match=match):
        normalise_value(value, labels)


def test_an_unnamed_series_index_over_several_open_coordinates_is_refused(staged):
    """Not inferred from the labels, so an index saying nothing must be told.

    `entity=` fixes one coordinate, but `p_max_pu` has more than one left open,
    so nothing says which the index holds.
    """
    series = pd.Series({"2030-01-01": 0.4})
    with pytest.raises(ValueError, match="naming the series' index"):
        staged.set("p_max_pu", series, entity=["Manchester Wind"])


def test_the_series_index_name_says_what_it_holds(staged):
    """A caller who named the index has said which coordinate it holds."""
    index = pd.Index([pd.Timestamp("2015-01-01")], name="snapshot")
    staged.set("p_max_pu", pd.Series([0.4], index=index), entity=["Manchester Wind"])
    assert "p_max_pu" in staged.attributes


# -- set (https://energy-models.github.io/datarecord/design/working-record/#set) -------------------------------------------------------------


def test_a_staged_edit_is_visible_through_the_record(staged):
    """A set of pending edits is a layer, so the read resolves over it.

    Notes
    -----
    - [reading with pending edits](https://energy-models.github.io/datarecord/design/working-record/#reading-with-pending-edits)
    - [the broadcast rule](https://energy-models.github.io/datarecord/design/record/#the-broadcast-rule)
    """
    staged.set("p_max_pu", 0.42, entity=["Manchester Wind"])

    rows = staged.attributes["p_max_pu"].collect().to_native().to_pandas()
    mine = rows[rows["entity"] == "Manchester Wind"]
    assert set(mine["value"]) == {0.42}
    assert mine["snapshot"].isna().all(), (
        "a broadcast edit displaces the whole series: rows never overlap"
    )
    assert set(rows["entity"]) > {"Manchester Wind"}, (
        "every other name still reads the base record's rows"
    )


def test_two_lazy_reads_stay_bound_to_their_own_relations(staged, root):
    """A `Record` hands over unmaterialised frames, so two must not alias.

    The read path composes relations by replacement scan, which binds each one
    at build time. Registering them under a fixed catalog name instead would
    rebind on the second read and both frames would collapse onto the last
    one - the frames are lazy, so nothing forces the first before that happens.

    Notes
    -----
    - [Frames](https://energy-models.github.io/datarecord/design/record/#frames)
    """
    staged.set("p_max_pu", 0.42, entity=["Manchester Wind"])
    first = staged.attributes["p_max_pu"]

    staged.set("p_min_pu", 0.11, entity=["Manchester Wind"])
    second = staged.attributes["p_min_pu"]

    # Collected only now, after the second frame was built.
    got_first = first.collect().to_native().to_pandas()
    got_second = second.collect().to_native().to_pandas()
    assert set(got_first["attribute"]) == {"p_max_pu"}
    assert 0.42 in set(got_first["value"])
    assert set(got_second["attribute"]) == {"p_min_pu"}

    # And nothing was left behind in the catalog to leak into the next read.
    views = {
        v
        for (v,) in root.store.workspace.con.sql(
            "SELECT view_name FROM duckdb_views()"
        ).fetchall()
    }
    assert not {v for v in views if v.startswith("_")}


def test_set_over_several_names(staged, root):
    staged.set("p_nom", 150.0, entity=["Manchester Wind", "Norway Wind"])
    child = root.child(staged.edits)

    got = _entity_values(child.record, "p_nom")
    assert got["Manchester Wind"] == got["Norway Wind"] == 150.0


@pytest.mark.parametrize(
    ("value", "kwargs"),
    [
        (1.0, {"entity": ["Nope"]}),
        (pd.DataFrame([{"entity": "Nope", "value": 1.0}]), {}),
    ],
    ids=["keyword", "long-frame"],
)
def test_set_rejects_an_unknown_name(staged, value, kwargs):
    """A value for a name no layer declares would resolve to nothing.

    Validation applies to the frame form too: a typo is caught where it is typed.

    Notes
    -----
    - [add / remove](https://energy-models.github.io/datarecord/design/working-record/#add-remove)
    - [validation](https://energy-models.github.io/datarecord/design/working-record/#validation)
    """
    with pytest.raises(KeyError, match="Nope"):
        staged.set("p_max_pu", value, **kwargs)


def test_set_accepts_a_name_staged_by_add(staged, root):
    """`add` makes the name exist, so a value for it is no longer unknown.

    Notes
    -----
    - [validation](https://energy-models.github.io/datarecord/design/working-record/#validation)
    """
    staged.add("entity", ["NewSolar"], entity_type=GEN)
    staged.set("p_nom", 7.0, entity=["NewSolar"])

    child = root.child(staged.edits)
    assert _entity_values(child.record, "p_nom")["NewSolar"] == 7.0


# -- the overlay does not overlap (https://energy-models.github.io/datarecord/design/record/#the-broadcast-rule, https://energy-models.github.io/datarecord/design/working-record/#reading-with-pending-edits) -----------------------------


def test_a_pointwise_edit_keeps_the_rest_of_the_series(staged):
    """An edit naming a coordinate displaces that one only.

    Keying the overlay on the input key alone would drop the whole series here,
    since it excludes the dims an attribute is not owned per.

    Notes
    -----
    - [the broadcast rule](https://energy-models.github.io/datarecord/design/record/#the-broadcast-rule)
    - [partial](https://energy-models.github.io/datarecord/design/schema/#partial-the-granularity-of-an-override)
    - [reading with pending edits](https://energy-models.github.io/datarecord/design/working-record/#reading-with-pending-edits)
    """
    base = staged.attributes["p_max_pu"].collect().to_native().to_pandas()
    mine = base[base["entity"] == "Manchester Wind"].sort_values("snapshot")
    one = mine.iloc[[0]][["entity", "snapshot"]].assign(value=0.123)

    staged.set("p_max_pu", one)

    rows = staged.attributes["p_max_pu"].collect().to_native().to_pandas()
    got = rows[rows["entity"] == "Manchester Wind"].sort_values("snapshot")
    assert len(got) == len(mine)
    assert got.iloc[0]["value"] == 0.123
    assert got.iloc[1:]["value"].tolist() == mine.iloc[1:]["value"].tolist()


def test_set_with_no_names_over_a_non_partial_dim_stays_one_row(store):
    """A scalar with no `entity=` leaves `entity` NULL, and a non-partial dim keeps it so.

    The read does not expand the broadcast per label when `entity` is not
    `partial`.
    """
    write_schema(
        Schema(
            dimensions={"entity": Dimension(dtype=nw.String())},
            attributes={"p_nom": AttributeSpec(dtype=nw.Float64(), dims={"entity"})},
            partial=frozenset(),
        ),
        store,
    )
    revision = empty_root(store)
    added = WorkingRecord(revision.record)
    added.add("entity", ["a", "b"])
    added.set("p_nom", {"a": 1.0, "b": 2.0})
    root = revision.child(added.edits)

    staged = WorkingRecord(root.record)
    staged.set("p_nom", 9.0)
    rows = root.child(staged.edits).record.attributes["p_nom"].collect()
    rows = rows.to_native().to_pandas()
    assert rows["entity"].isna().all(), "one broadcast row, not one per label"
    assert rows["value"].tolist() == [9.0]


def test_an_expression_value_stages_the_whole_series(staged, root):
    """A derived edit covers every coordinate it read, not just one.

    Notes
    -----
    - [a derived value](https://energy-models.github.io/datarecord/design/working-record/#an-nwexpr-value-derived-from-the-current-one)
    """
    base = staged.attributes["p_max_pu"].collect().to_native().to_pandas()
    mine = base[base["entity"] == "Manchester Wind"].sort_values("snapshot")

    staged.set("p_max_pu", nw.col("value") * 2, entity=["Manchester Wind"])
    read = staged.attributes["p_max_pu"].collect().to_native().to_pandas()
    read = read[read["entity"] == "Manchester Wind"].sort_values("snapshot")
    assert read["value"].tolist() == (mine["value"] * 2).tolist(), (
        "every coordinate the expression read, not just one"
    )

    child = root.child(staged.edits)
    got = child.record.attributes["p_max_pu"].collect().to_native().to_pandas()
    got = got[got["entity"] == "Manchester Wind"].sort_values("snapshot")
    assert got["value"].tolist() == (mine["value"] * 2).tolist()


def test_flags_report_a_dim_a_staged_edit_introduces(staged, ac_dc):
    """A staged row's dims join the flags, unioned with the base answer.

    `flags` is the one non-`Frames` member of `Record`, so the promise that a
    read reflects pending edits has to hold for it too - and it decides which
    container a consumer puts a value in (`PyPSA.build` splits static from
    series on exactly this). `marginal_cost` starts broadcast over `snapshot`
    and varying over nothing; a per-snapshot edit must add `snapshot` to
    `varies` while leaving `broadcast` alone, since the base's NULL-snapshot
    rows are still there.

    Notes
    -----
    - [reading with pending edits](https://energy-models.github.io/datarecord/design/working-record/#reading-with-pending-edits)
    - [the owner map](https://energy-models.github.io/datarecord/design/read-path/#owner-map)
    """
    before = staged.flags()["marginal_cost"]
    assert "snapshot" not in before.varies
    assert "snapshot" in before.broadcast

    staged.set(
        "marginal_cost",
        pd.DataFrame(
            [
                {
                    "entity": "Manchester Wind",
                    "snapshot": ac_dc.snapshots[0],
                    "value": 7.5,
                }
            ]
        ),
    )

    after = staged.flags()["marginal_cost"]
    assert "snapshot" in after.varies
    assert after.broadcast == before.broadcast

    staged.set("marginal_cost", 3.0, entity=["Norway Wind"])
    mixed = staged.flags()["marginal_cost"]
    assert {"snapshot"} <= mixed.varies & mixed.broadcast, (
        "members staged at different grains report both, whatever the map's grain"
    )


def test_a_staged_edit_is_read_back_and_then_re_read(staged, root):
    """Set, read, set again, read again: the second read must see the second edit.

    That is the whole content of "the staged step is not cached", and it fails
    loudly if anyone later materialises past the frozen prefix - a
    `cached_property` over the tail, or a `.create()` that does not stop where
    `frozen` does. The first read is what arms it: it builds the fold, so a
    cache introduced anywhere in it would be populated before the second `set`.

    Notes
    -----
    - [reading with pending edits](https://energy-models.github.io/datarecord/design/working-record/#reading-with-pending-edits)
    - [a layer's data is write-once](https://energy-models.github.io/datarecord/design/layers/#a-layers-data-is-write-once)
    """

    def p_nom(name):
        return _entity_values(staged, "p_nom").loc[[name]].tolist()

    staged.set("p_nom", 11.0, entity=["Manchester Wind"])
    assert p_nom("Manchester Wind") == [11.0]

    staged.set("p_nom", 22.0, entity=["Manchester Wind"])
    assert p_nom("Manchester Wind") == [22.0], "the read re-folds the staged layer"

    # A key the second edit never named, to pin that re-folding is not
    # re-resolving from scratch and dropping what the first edit staged.
    staged.set("p_nom", 33.0, entity=["Norway Wind"])
    assert p_nom("Manchester Wind") == [22.0]
    assert p_nom("Norway Wind") == [33.0]

    committed = _entity_values(root.child(staged.edits).record, "p_nom")
    assert committed["Manchester Wind"] == 22.0, "the later edit to a key commits"


# -- value dtypes (https://energy-models.github.io/datarecord/design/record/#flags, https://energy-models.github.io/datarecord/design/schema/#attributespec) -----------------------------------------------


def test_a_non_float_attribute_stages_and_commits(store):
    """`value` carries the attribute's declared dtype, not always `DOUBLE`.

    One staging table holds every attribute's values, so it stages `value` as
    text and casts to the declared dtype where the attribute is known - which
    is the point at which `inputs/<attr>.parquet` is per-attribute.

    The schema is amended before the `WorkingRecord` is built: a record carries
    the schema its base was resolved under, so a widening has to be in force
    when the record is constructed, not slipped in before a later commit.

    Notes
    -----
    - [Flags](https://energy-models.github.io/datarecord/design/record/#flags)
    """
    root = _small(store)
    amended = read_schema(store)
    amended.attributes["fuel"] = AttributeSpec(
        dtype=nw.String(), dims={"entity", "scenario"}
    )
    write_schema(amended, store)

    staged = WorkingRecord(root.record)
    staged.set("fuel", "solar", entity=["Manchester Wind"])
    rows = staged.attributes["fuel"].collect().to_native().to_pandas()
    assert rows[rows["entity"] == "Manchester Wind"]["value"].tolist() == ["solar"]

    staged.set("p_nom", 150.0, entity=["Manchester Wind"])
    assert _entity_values(staged, "p_nom").dtype.kind == "f", (
        "the cast is per attribute, so a DOUBLE one is not turned into text"
    )

    child = root.child(staged.edits)
    got = child.record.attributes["fuel"].collect().to_native().to_pandas()
    assert got[got["entity"] == "Manchester Wind"]["value"].tolist() == ["solar"]


# -- ownership granularity (https://energy-models.github.io/datarecord/design/schema/#partial-the-granularity-of-an-override, https://energy-models.github.io/datarecord/design/working-record/#edits) -------------------------------------


def test_two_edits_on_one_whole_owned_series_both_land(staged, root):
    """A second `set` replaces its own fill without disturbing the first edit's.

    The case `staging-without-seq` leans on hardest: a `set` on a whole-owned
    axis stages the touched value plus the untouched coordinates as fills, and a
    second `set` at another coordinate must replace only the fill on *its* key -
    the first edit's value and its fills have to survive. Idempotence of
    `_complete_owned_whole` and replace-by-coordinate are what make it hold with
    no ordering column to rank a fill below an edit.

    Notes
    -----
    - [edits](https://energy-models.github.io/datarecord/design/working-record/#edits)
    - [partial](https://energy-models.github.io/datarecord/design/schema/#partial-the-granularity-of-an-override)
    """
    base = staged.attributes["p_max_pu"].collect().to_native().to_pandas()
    mine = base[base["entity"] == "Manchester Wind"].sort_values("snapshot")
    assert len(mine) > 2, "the series needs an untouched middle to keep"

    first = mine.iloc[[0]][["entity", "snapshot"]].assign(value=0.111)
    second = mine.iloc[[1]][["entity", "snapshot"]].assign(value=0.222)
    staged.set("p_max_pu", first)
    staged.set("p_max_pu", second)

    child = root.child(staged.edits)
    rows = _layer_rows(child, "p_max_pu")
    got = rows[rows["entity"] == "Manchester Wind"].sort_values("snapshot")

    assert len(got) == len(mine), "the whole extent is carried, once per snapshot"
    assert got.iloc[0]["value"] == 0.111, "the first edit survives the second"
    assert got.iloc[1]["value"] == 0.222, "the second edit replaced its own fill"
    assert got.iloc[2:]["value"].tolist() == mine.iloc[2:]["value"].tolist(), (
        "every untouched snapshot keeps the base value"
    )
    assert set(rows["entity"]) == {"Manchester Wind"}, (
        "an axis owned whole restates the touched key's extent, not every key's"
    )


# -- add and remove (https://energy-models.github.io/datarecord/design/working-record/#add-remove) --------------------------------------------------


def _entity_axis(record):
    """The record's resolved `properties["entity"]`, indexed by label, as pandas."""
    frame = record.properties["entity"].collect().to_native().to_pandas()
    return frame.set_index("entity")


def _entity_values(record, attribute):
    """`attribute`'s rows naming an entity alone - every other coordinate NULL - by label."""
    rows = record.attributes[attribute].collect().to_native().to_pandas()
    others = [c for c in rows.columns if c not in ("entity", "attribute", "value")]
    return rows[rows[others].isna().all(axis=1)].set_index("entity")["value"]


def test_add_then_commit_makes_a_label_exist(staged, root):
    staged.add("entity", ["NewSolar"], entity_type=GEN)
    assert "NewSolar" in _entity_axis(staged).index, "it reads back before commit"

    child = root.child(staged.edits)
    assert _entity_axis(child.record).loc["NewSolar", "entity_type"] == GEN


@pytest.fixture
def units(store):
    """An empty record over `unit` and `hour`, `unit` carrying a category and a site.

    Only a `plant` carries `capacity`, through a trait on `tech`.
    """
    write_schema(
        Schema(
            dimensions={
                "unit": Dimension(dtype=nw.String()),
                "hour": Dimension(dtype=nw.Int64()),
            },
            properties={
                "unit": {
                    "tech": PropertySpec(dtype=nw.Enum(["plant", "node"])),
                    "site": PropertySpec(dtype=nw.String()),
                }
            },
            attributes={
                "output": AttributeSpec(dtype=nw.Float64(), dims={"unit", "hour"}),
                "demand": AttributeSpec(dtype=nw.Float64(), dims={"hour"}),
                "capacity": AttributeSpec(dtype=nw.Float64(), dims={"unit"}),
            },
            traits={
                "plant": Trait(
                    attributes=frozenset({"capacity"}),
                    on={"tech": frozenset({"plant"})},
                )
            },
            partial=frozenset({"unit"}),
        ),
        store,
    )
    staged = WorkingRecord(empty_root(store).record)
    staged.add(
        "unit",
        ["p1", "p2", "n1"],
        tech=["plant", "plant", "node"],
        site=["north", "south", "north"],
    )
    return staged


def _unit_axis(record):
    return record.properties["unit"].collect().to_native().to_pandas().set_index("unit")


def test_set_may_change_a_category(units):
    """A category is a patch of one column of the axis row, like any property.

    Notes
    -----
    - [set](https://energy-models.github.io/datarecord/design/working-record/#set)
    """
    units.set("tech", "node", unit=["p2"])

    axis = _unit_axis(units)
    assert axis.loc["p2", "tech"] == "node", "a category may change"
    assert axis.loc["p2", "site"] == "south", "a sibling column stays put"


@pytest.mark.parametrize(
    ("op", "args", "kwargs", "error", "match"),
    [
        ("set", ("site", "east"), {"unit": "x"}, KeyError, "no 'unit' label \\['x'\\]"),
        (
            "set",
            ("tech", "mill"),
            {"unit": "p1"},
            ValueError,
            "'tech' values \\['mill'\\]",
        ),
        (
            "add",
            ("unit", ["m"]),
            {"tech": "mill"},
            ValueError,
            "'tech' values \\['mill'\\]",
        ),
        (
            "set",
            ("capacity", pd.Series({"p1": 1.0, "n1": 1.0}).rename_axis("unit")),
            {},
            KeyError,
            "'n1' is tech 'node'",
        ),
        (
            "set",
            ("output", 1.0),
            {"tech": "mill", "hour": [0]},
            ValueError,
            "'tech' values \\['mill'\\]",
        ),
        (
            "set",
            ("output", 1.0),
            {"tech": "plant", "unit": ["p1"], "hour": [0]},
            ValueError,
            "one way",
        ),
        (
            "set",
            ("demand", 1.0),
            {"tech": "plant", "hour": [0]},
            ValueError,
            "through no coordinate",
        ),
    ],
    ids=[
        "unknown-label",
        "unknown-category",
        "add-unknown-category",
        "label-of-wrong-kind",
        "keyword-unknown-category",
        "keyword-and-label",
        "keyword-reaching-no-coordinate",
    ],
)
def test_an_edit_refuses_an_unknown_label_category_or_keyword(
    units, op, args, kwargs, error, match
):
    """A category is checked against its `Enum`, a label against its kind's traits.

    The error names the label that caused it, not a kind the caller never said.

    Notes
    -----
    - [validation](https://energy-models.github.io/datarecord/design/working-record/#validation)
    - [traits](https://energy-models.github.io/datarecord/design/schema/#traits)
    """
    with pytest.raises(error, match=match):
        getattr(units, op)(*args, **kwargs)


def _output_units(record):
    rows = record.edits.attribute("output").df()
    return dict(zip(rows["unit"], rows["value"], strict=True))


def test_a_property_keyword_selects_the_labels_there_are_now(units):
    """`tech="plant"` writes one row per plant, and nothing of the filter.

    Notes
    -----
    - [set](https://energy-models.github.io/datarecord/design/working-record/#set)
    """
    units.set("output", 1.0, tech="plant", hour=[0])
    assert _output_units(units) == {"p1": 1.0, "p2": 1.0}, "one row per plant"

    units.set("output", 2.0, tech=["plant", "node"], site="north", hour=[0])
    assert _output_units(units) == {"p1": 2.0, "p2": 1.0, "n1": 2.0}, (
        "keywords intersect, a list matching any of its values"
    )

    units.add("unit", ["p3"], tech="plant")
    assert "p3" not in _output_units(units), "a label added later is not reached"


def test_set_of_a_category_survives_a_commit(staged, root):
    staged.set("entity_type", "Load", entity="Manchester Wind")

    child = root.child(staged.edits)
    axis = _entity_axis(child.record)
    assert axis.loc["Manchester Wind", "entity_type"] == "Load"
    assert (
        _entity_values(child.record, "p_nom")["Manchester Wind"]
        == _entity_values(root.record, "p_nom")["Manchester Wind"]
    ), "a re-categorized label keeps the values it holds"


def test_re_adding_a_label_replaces_its_row(staged, root):
    """One axis row per label: a later `add` is the row, whatever kind it names.

    Uniqueness needs no check of its own - the axis is keyed by the label, so
    a `remove` then an `add` under another kind is one row, the later.

    Notes
    -----
    - [edits](https://energy-models.github.io/datarecord/design/working-record/#edits)
    """
    staged.remove("entity", ["Manchester Wind"])
    staged.add("entity", ["Manchester Wind"], entity_type="Bus")

    rows = staged.edits.axis("entity").df()
    rows = rows[rows["entity"] == "Manchester Wind"]
    assert len(rows) == 1, "one label, one row"
    assert list(rows["entity_type"]) == ["Bus"], "the later op wins"

    child = root.child(staged.edits)
    assert _entity_axis(child.record).loc["Manchester Wind", "entity_type"] == "Bus"


def test_add_rejects_a_column_the_schema_does_not_declare(staged):
    """An axis column no declaration accounts for is an error, not a new column.

    A staging table is shaped like the file it becomes, from the schema, so an
    undeclared column has no dtype to be given it. A tool that grows a column
    declares it first.

    Notes
    -----
    - [add / remove](https://energy-models.github.io/datarecord/design/working-record/#add-remove)
    - [versioning](https://energy-models.github.io/datarecord/design/schema/#versioning)
    """
    assert "capex" not in staged.schema.attributes, "undeclared, which is the case here"
    with pytest.raises(ValueError, match="capex"):
        staged.add("entity", ["NewSolar"], capex=1234.5)


def test_add_fills_a_declared_column_another_add_omitted(staged):
    """An `add` omitting a declared column stages it as NULL rather than failing.

    Notes
    -----
    - [add / remove](https://energy-models.github.io/datarecord/design/working-record/#add-remove)
    """
    staged.add("entity", ["NewSolar"], entity_type=GEN)
    staged.add("entity", ["NewWind"])

    rows = staged.edits.axis("entity").df().set_index("entity")
    assert pd.isna(rows.loc["NewWind", "entity_type"]), "not carried, so NULL"
    assert rows.loc["NewSolar", "entity_type"] == GEN, "unaffected by the later add"


def test_remove_tombstones_without_enumerating_attributes(staged, root):
    staged.remove("entity", ["Norway Gas"])
    assert "Norway Gas" not in _entity_axis(staged).index, "it reads back at once"

    child = root.child(staged.edits)
    assert "Norway Gas" not in set(child.resolver.axis("entity").df()["entity"])


def test_a_tombstone_drops_that_labels_staged_attributes(staged, root):
    """Removing a label discards values staged for it, via the anti-join.

    Notes
    -----
    - [edits](https://energy-models.github.io/datarecord/design/working-record/#edits)
    """
    staged.set("p_nom", 99.0, entity=["Norway Gas"])
    staged.remove("entity", ["Norway Gas"])

    child = root.child(staged.edits)
    assert "Norway Gas" not in _entity_values(child.record, "p_nom")


# -- connect and disconnect (https://energy-models.github.io/datarecord/design/working-record/#add-remove, https://energy-models.github.io/datarecord/design/record/#connections) --------------------------------------


def test_remove_group_stages_a_tombstone(staged, root):
    """One `deleted` row per `(entity, bus)`, the group's own key.

    Notes
    -----
    - [connections](https://energy-models.github.io/datarecord/design/record/#connections)
    """
    staged.remove_group("connection", [("Norwich Converter", "Norwich")])
    before = unpacked(staged.groups["connection"])
    ports = set(before[before["entity"] == "Norwich Converter"]["bus"])
    assert "Norwich" not in ports, "the removal reads back before commit"
    assert "Norwich DC" in ports, "deletion is per connection, not per component"

    child = root.child(staged.edits)
    rows = unpacked(child.resolver.group_frame("connection"))
    left = set(rows[rows["entity"] == "Norwich Converter"]["bus"])
    assert "Norwich" not in left
    # The component's other port survives: deletion is per connection, not per
    # component (https://energy-models.github.io/datarecord/design/record/#connections).
    assert "Norwich DC" in left


def _efficiency(record, entity="Manchester Wind"):
    """`efficiency` per bus for one entity, as the record resolves it."""
    rows = _unpacked(record.attributes["efficiency"])
    return rows[rows["entity"] == entity].groupby("bus")["value"].unique().to_dict()


def test_a_bus_keyword_addresses_one_connection(staged, root):
    """`bus=` names one connection, which the stage packs into its struct.

    Notes
    -----
    - [set](https://energy-models.github.io/datarecord/design/working-record/#set)
    - [groups](https://energy-models.github.io/datarecord/design/schema/#groups)
    """
    staged.set("efficiency", 0.5, entity=["Manchester Wind"], bus="Manchester")

    own = staged.edits.attribute("efficiency")
    assert "bus" not in own.columns, "the row carries the connection, not its bus"
    assert own.project("connection").distinct().fetchall() == [
        ({"entity": "Manchester Wind", "bus": "Manchester"},)
    ]
    assert list(_efficiency(staged)["Manchester"]) == [0.5]

    child = root.child(staged.edits)
    assert list(_efficiency(child.record)["Manchester"]) == [0.5]


def test_no_group_field_given_broadcasts_over_every_tuple(staged):
    """A wholly NULL struct is every tuple, by the broadcast rule.

    Notes
    -----
    - [the broadcast rule](https://energy-models.github.io/datarecord/design/record/#the-broadcast-rule)
    - [groups](https://energy-models.github.io/datarecord/design/schema/#groups)
    """
    staged.set("efficiency", 0.7)

    own = staged.edits.attribute("efficiency")
    assert own.project("connection").fetchall() == [(None,)], "one broadcast row"
    assert _efficiency(staged) and all(
        list(v) == [0.7] for v in _efficiency(staged).values()
    ), "every connection reads the broadcast"


def test_a_frame_carries_a_group_as_its_struct(staged):
    """A packed struct passes through, one key replacing the last.

    Notes
    -----
    - [set](https://energy-models.github.io/datarecord/design/working-record/#set)
    """
    for value in (0.5, 0.25):
        staged.set(
            "efficiency",
            staged.con.sql(
                "SELECT {'entity': 'Manchester Wind', 'bus': 'Manchester'} "
                f"AS connection, {value} AS value"
            ),
        )
    assert list(_efficiency(staged)["Manchester"]) == [0.25], "one key, replaced"


@pytest.mark.parametrize(
    "select",
    [
        "'Manchester Wind' AS entity, 'Manchester' AS bus, 0.5 AS value",
        "{'entity': 'Manchester Wind', 'bus': 'Manchester'} AS connection, "
        "'Manchester' AS bus, 0.5 AS value",
        "{'entity': 'Manchester Wind'} AS connection, 0.5 AS value",
        "'Manchester' AS connection, 0.5 AS value",
        "{'entity': 'Manchester Wind', 'bus': NULL::VARCHAR} AS connection, "
        "0.5 AS value",
    ],
    ids=["flat", "both", "partial-struct", "not-a-struct", "partly-null"],
)
def test_a_frame_carrying_a_group_but_as_its_struct_is_rejected(staged, select):
    """Flat coordinates, beside the struct or not, or a wrong struct, are refused.

    Notes
    -----
    - [groups](https://energy-models.github.io/datarecord/design/schema/#groups)
    """
    with pytest.raises(ValueError, match="'connection'"):
        staged.set("efficiency", staged.con.sql(f"SELECT {select}"))


def test_an_expression_scoped_by_bus_derives_one_connection(staged):
    """`bus=` scopes a derived value through the struct field.

    Notes
    -----
    - [a derived value](https://energy-models.github.io/datarecord/design/working-record/#an-nwexpr-value-derived-from-the-current-one)
    """
    staged.set("efficiency", 0.5, entity=["Manchester Gas"], bus="Manchester")
    staged.set(
        "efficiency", nw.col("value") * 2, entity=["Manchester Gas"], bus="Manchester"
    )
    assert list(_efficiency(staged, "Manchester Gas")["Manchester"]) == [1.0]


def test_a_layer_touching_no_tuple_resolves_no_ancestry_to_check(
    staged, root, monkeypatch
):
    """The living-tuple check resolves the ancestry only for a layer it concerns.

    Notes
    -----
    - [deletion](https://energy-models.github.io/datarecord/design/layers/#deletion)
    """
    import datarecord.layered.write as write

    def unwanted(*_):
        pytest.fail("resolved the ancestry for a layer with nothing to check")

    monkeypatch.setattr(write, "resolve_coords", unwanted)
    staged.set("p_nom", 150.0, entity=["Manchester Wind"])
    root.child(staged.edits)


def test_remove_of_no_labels_stages_nothing(staged):
    staged.remove("entity", [])
    assert not staged.edits.axes(), "no tombstone, and no cascade to look up"


def test_remove_then_add_starts_without_the_parents_connections(staged, root):
    """`add` replaces the entity's tombstone, not its connections'.

    Notes
    -----
    - [edits](https://energy-models.github.io/datarecord/design/working-record/#edits)
    - [deletion](https://energy-models.github.io/datarecord/design/layers/#deletion)
    """
    assert _efficiency(staged), "the base carries a value to lose"
    staged.remove("entity", ["Manchester Wind"])
    staged.add("entity", ["Manchester Wind"], entity_type=GEN)

    child = root.child(staged.edits)
    assert _entity_axis(child.record).loc["Manchester Wind", "entity_type"] == GEN
    assert _efficiency(child.record) == {}, "its connections are re-added by hand"


def _connections(record):
    return unpacked(record.groups["connection"])


@pytest.mark.parametrize(
    ("frame", "match"),
    [
        (
            pd.DataFrame([{"entity": "Manchester Wind", "bus": "Norway"}]),
            "pass 'connection' as one struct column",
        ),
        (pd.DataFrame([{"role": "attached"}]), "needs a 'connection' column"),
    ],
    ids=["flat-coordinates", "no-struct-column"],
)
def test_add_group_needs_the_struct_column(staged, frame, match):
    with pytest.raises(ValueError, match=match):
        staged.add_group("connection", frame)


def test_every_declared_group_reads_its_staged_rows(store):
    """A second group is not silently dropped: the reads are keyed by group.

    `connection` is the group every fixture has, so a read path naming it rather
    than iterating the declared ones would pass everywhere except here - a
    record declaring a `corridor` would read nothing while holding rows to
    commit.

    Notes
    -----
    - [groups](https://energy-models.github.io/datarecord/design/schema/#groups)
    """
    revision = _small(
        store,
        groups={
            "connection": {"entity": "entity", "bus": "bus"},
            "corridor": {"from": "entity", "to": "entity"},
        },
    )
    staged = WorkingRecord(revision.record)

    staged.add_group(
        "connection",
        pd.DataFrame([{"connection": {"entity": "Manchester Wind", "bus": "Norway"}}]),
    )
    staged.add_group(
        "corridor",
        pd.DataFrame([{"corridor": {"from": "Manchester Wind", "to": "Norway"}}]),
    )

    connections = unpacked(staged.groups["connection"])
    assert "Norway" in set(
        connections[connections["entity"] == "Manchester Wind"]["bus"]
    )

    corridors = unpacked(staged.groups["corridor"], "corridor")
    assert list(zip(corridors["from"], corridors["to"], strict=True)) == [
        ("Manchester Wind", "Norway")
    ], "the second group reads its own rows, not the first's"


def _with_roles(store):
    """A root whose `l1` attaches to `b0` and `b1`, `role` a property of `connection`."""
    write_schema(
        Schema(
            dimensions={
                "entity": Dimension(dtype=nw.String()),
                "bus": Dimension(dtype=nw.String()),
            },
            groups={"connection": Group(over={"entity": "entity", "bus": "bus"})},
            properties={"connection": {"role": PropertySpec(dtype=nw.String())}},
            attributes={
                "efficiency": AttributeSpec(dtype=nw.Float64(), dims={"connection"})
            },
            partial=frozenset({"entity", "connection"}),
        ),
        store,
    )
    root = empty_root(store)
    staged = WorkingRecord(root.record)
    staged.add("entity", ["l1"])
    staged.add("bus", ["b0", "b1"])
    staged.add_group(
        "connection",
        pd.DataFrame(
            [
                {"connection": {"entity": "l1", "bus": "b0"}, "role": "in"},
                {"connection": {"entity": "l1", "bus": "b1"}, "role": "out"},
            ]
        ),
    )
    return root.child(staged.edits)


def _roles(record):
    """`(entity, bus) -> role` off the record's resolved `connection` group."""
    rows = unpacked(record.groups["connection"])
    return dict(zip(zip(rows["entity"], rows["bus"]), rows["role"]))


def test_a_group_property_is_a_column_of_the_group_file(store):
    """And `set` with the group's fields as keywords patches the tuples they select.

    Notes
    -----
    - [where a value lives](https://energy-models.github.io/datarecord/design/format/#where-a-value-lives)
    """
    root = _with_roles(store)
    on_disk = pd.read_parquet(f"{store.layer_dir(root.id)}groups/connection.parquet")
    assert "role" in on_disk.columns

    staged = WorkingRecord(root.record)
    staged.set("role", "both", entity="l1", bus="b1")
    assert _roles(staged) == {("l1", "b0"): "in", ("l1", "b1"): "both"}

    child = root.child(staged.edits)
    assert _roles(child.record) == {("l1", "b0"): "in", ("l1", "b1"): "both"}
    patch = pd.read_parquet(f"{store.layer_dir(child.id)}groups/connection.parquet")
    assert len(patch) == 1, "the patch is the one tuple it selected"


def test_a_group_property_with_no_field_reaches_every_tuple(store):
    staged = WorkingRecord(_with_roles(store).record)
    staged.set("role", "any")
    assert set(_roles(staged).values()) == {"any"}


def test_a_group_property_refuses_what_is_no_field(store):
    staged = WorkingRecord(_with_roles(store).record)
    with pytest.raises(ValueError, match="whose tuples its fields"):
        staged.set("role", "x", snapshot="2020")
    with pytest.raises(KeyError, match="selects no tuple"):
        staged.set("role", "x", entity="l1", bus="nowhere")


def test_add_and_add_group_refuse_an_attribute(store):
    """An axis or group row carries properties and keys; an attribute is long rows of `inputs/`."""
    staged = WorkingRecord(_with_roles(store).record)
    with pytest.raises(ValueError, match=r"attributes \['efficiency'\].*`set"):
        staged.add("entity", ["l2"], efficiency=0.5)
    frame = pd.DataFrame(
        [{"connection": {"entity": "l1", "bus": "b0"}, "efficiency": 0.9}]
    )
    with pytest.raises(ValueError, match="stage them with `set"):
        staged.add_group("connection", frame)


# -- rollback (https://energy-models.github.io/datarecord/design/working-record/#edits) --------------------------------------------------------


def test_rollback_discards_everything_staged(staged, root):
    staged.set("p_max_pu", 0.42, entity=["Manchester Wind"])
    staged.remove("entity", ["Norway Gas"])
    staged.rollback()

    # The record reads the base rows again, edit and tombstone alike.
    rows = staged.attributes["p_max_pu"].collect().to_native().to_pandas()
    assert 0.42 not in set(rows["value"])
    assert "Norway Gas" in _entity_axis(staged).index, (
        "the tombstone went with the rest"
    )


def test_writing_the_edits_clears_nothing(staged, root):
    """A `WorkingRecord` still holding its edits after a write reads the same.

    Clearing is `rollback()`, called or not, so a second write of the edits
    writes them again and one after `rollback()` writes nothing.

    Notes
    -----
    - [edits](https://energy-models.github.io/datarecord/design/working-record/#edits)
    """
    staged.set("p_nom", 150.0, entity=["Manchester Wind"])
    first = root.child(staged.edits)
    still = _entity_values(staged, "p_nom")["Manchester Wind"]
    assert still == 150.0, "still staged"

    again = root.child(staged.edits)
    assert list(_layer_rows(again, "p_nom")["entity"]) == ["Manchester Wind"]
    assert list(_layer_rows(first, "p_nom")["entity"]) == ["Manchester Wind"]

    staged.rollback()
    emptied = root.child(staged.edits)
    assert _layer_rows(emptied, "p_nom").empty


# -- commit targets (https://energy-models.github.io/datarecord/design/working-record/#edits) --------------------------------------------------


def test_a_completed_axis_carries_the_touched_key_and_no_other(staged, root):
    """Owning `snapshot` whole completes the edited series, not every series.

    `p_max_pu` varies over a non-partial `snapshot`, so touching one of
    Manchester Wind's snapshots makes the layer the owner of that generator's
    whole series and it must carry the untouched snapshots too. The scope is the
    key the edit named: a second generator the edit never mentioned stays in the
    parent, and a layer carrying it would claim an extent it was never given.

    Notes
    -----
    - [partial](https://energy-models.github.io/datarecord/design/schema/#partial-the-granularity-of-an-override)
    - [edits](https://energy-models.github.io/datarecord/design/working-record/#edits)
    """
    assert "snapshot" not in (staged.schema.partial or frozenset())
    assert "snapshot" not in staged.schema.owned_per("p_max_pu"), (
        "owned per entity, but not per snapshot, the axis this test is about"
    )
    base = staged.attributes["p_max_pu"].collect().to_native().to_pandas()
    mine = base[base["entity"] == "Manchester Wind"].sort_values("snapshot")
    one = mine.iloc[[0]][["entity", "snapshot"]].assign(value=0.123)
    assert len(mine) > 1, "a one-snapshot series would not distinguish the two scopes"

    staged.set("p_max_pu", one)
    child = root.child(staged.edits)

    rows = _layer_rows(child, "p_max_pu")
    assert set(rows["entity"]) == {"Manchester Wind"}, (
        "only the touched key's extent is carried"
    )
    written = rows.sort_values("snapshot")
    assert written["value"].tolist() == [0.123, *mine.iloc[1:]["value"].tolist()], (
        "the edit, then the rest of the series it now owns"
    )


def test_edits_are_written_only_under_their_base(store):
    """A delta against one revision would read back wrong under another.

    An axis edit carries its base's sibling columns, so the edits staged over
    `root` describe a layer over `root` and nothing else.

    Notes
    -----
    - [edits](https://energy-models.github.io/datarecord/design/working-record/#edits)
    """
    root = _small(store)
    other = empty_root(store)
    staged = WorkingRecord(root.record)
    staged.set("p_nom", 150.0, entity=["Manchester Wind"])

    with pytest.raises(ValueError, match="delta against"):
        other.child(staged.edits)
    assert root.child(staged.edits).parent == root.id
    # The record itself is the flattened whole, which any revision may take.
    assert other.child(staged).parent == other.id


def test_the_edits_land_in_the_child_not_the_node_branched_from(staged, root):
    """Layers are write-once, so the parent still reads its own values.

    Notes
    -----
    - [a layer's data is write-once](https://energy-models.github.io/datarecord/design/layers/#a-layers-data-is-write-once)
    - [edits](https://energy-models.github.io/datarecord/design/working-record/#edits)
    """
    before = _entity_values(root.record, "p_nom")["Manchester Wind"]
    staged.set("p_nom", 150.0, entity=["Manchester Wind"])
    child = root.child(staged.edits)

    assert _entity_values(child.record, "p_nom")["Manchester Wind"] == 150.0
    assert _entity_values(root.record, "p_nom")["Manchester Wind"] == before
    assert list(_layer_rows(child, "p_nom")["entity"]) == ["Manchester Wind"], (
        "a patch layer is the edits alone"
    )
    assert len(_entity_values(child.record, "p_nom")) > 1, "the fold resolves the rest"


def test_an_edit_over_a_directory_base_reads_back(root):
    """A staged edit must win over a directory base, as it does over a layered one.

    The two are separate sources of one fold, and `source_for` tells them apart
    by `layer_uuid` alone - so a base and a staging area sharing an id would
    send every staged win to the base and read the edit back as the base's
    value, with a correct-looking owner map above it. The unstaged fixtures
    cannot see that: it takes an edit that is supposed to displace something.

    Notes
    -----
    - [reading with pending edits](https://energy-models.github.io/datarecord/design/working-record/#reading-with-pending-edits)
    - [the owner map](https://energy-models.github.io/datarecord/design/read-path/#owner-map)
    """
    staged = WorkingRecord(root.store.layer(root.id))

    def marginal_cost() -> list[float]:
        frame = staged.attributes["marginal_cost"].collect().to_native().to_pandas()
        return frame[frame["entity"] == "Manchester Wind"]["value"].tolist()

    before = marginal_cost()
    staged.set("marginal_cost", 4242.0, entity=["Manchester Wind"])
    assert marginal_cost() == [4242.0], (
        "the staged layer owns the key, so the read takes its value"
    )
    assert before != [4242.0], "otherwise the assertion above proves nothing"

    # The base's id is derived from its revision's rather than allocated, so
    # two readers of one layer agree on which layer they are reading.
    other = WorkingRecord(root.store.layer(root.id))
    assert other._base.revision_id == staged._base.revision_id
    assert other._layer_id != staged._layer_id, "each staging area is its own layer"


def test_edits_over_a_directory_are_no_revisions_delta(store, written_directory):
    """A directory is no node in a tree, so its edits are a child of none.

    Its `revision_id` is the id its manifest carries, so it names no
    revision; the flattened record writes as a standalone directory instead.

    Notes
    -----
    - [edits](https://energy-models.github.io/datarecord/design/working-record/#edits)
    """
    revision = empty_root(store)
    over_a_directory = WorkingRecord(store.workspace.at(written_directory))

    with pytest.raises(ValueError, match="delta against"):
        revision.child(over_a_directory.edits)


def test_a_directory_uri_reads_the_same_with_or_without_a_trailing_slash(
    written_directory, workspace
):
    """Every member path is appended to the URI, so the slash cannot be optional.

    And `layer_id` is the id the manifest under that URI carries, so both
    spellings must reach the one file - otherwise one directory reads as two
    layers and a `WorkingRecord` over each disagrees about which it edits.
    """
    bare = written_directory.rstrip("/")
    assert not bare.endswith("/"), "otherwise this asserts nothing"

    with_slash = workspace.at(bare + "/")
    without = workspace.at(bare)
    assert list(without.attributes) == list(with_slash.attributes)
    assert list(without.attributes), "the fixture must have written attributes"
    assert without.resolver.revision_id == with_slash.resolver.revision_id, (
        "one directory is one layer, however its URI was spelled"
    )


def test_edits_read_under_the_base_records_schema(store, workspace, tmp_path):
    """A staging area declares nothing; it edits under the base's declaration.

    Which matters for a standalone base, whose schema is its own directory's
    rather than any store's: the staged layer is one more source over that
    base, so `with_source` has to carry the schema along. A store on the same
    workspace declaring something else must not reach the edit.

    Notes
    -----
    - [one schema per record](https://energy-models.github.io/datarecord/design/schema/#one-schema-per-record)
    """
    out = str(tmp_path / "standalone")
    workspace.write(WorkingRecord(_small(store).record), out)
    unrelated = workspace.store(str(tmp_path / "unrelated"))
    write_schema(Schema(), unrelated)

    base = workspace.at(out)
    assert base.schema.dims, "the standalone record carries its own schema"
    editing = WorkingRecord(base)
    assert editing.schema == base.schema, "an edit declares nothing of its own"
    editing.set("p_nom", 999.0, entity=["Manchester Wind"])
    assert _entity_values(editing, "p_nom")["Manchester Wind"] == 999.0


def test_a_standalone_write_of_the_record_is_flattened(staged, root, tmp_path):
    """No parent to resolve against, so the whole record is written.

    Notes
    -----
    - [edits](https://energy-models.github.io/datarecord/design/working-record/#edits)
    """
    staged.set("p_nom", 150.0, entity=["Manchester Wind"])
    out = str(tmp_path / "flat")
    record = root.store.workspace.write(staged, out)
    assert record.schema == staged.schema
    members = _entity_axis(record)
    assert _entity_values(record, "p_nom")["Manchester Wind"] == 150.0
    # Flattened: every component is present, not left to a parent to supply.
    assert (members["entity_type"] == GEN).sum() == 6
    assert not root.store.workspace.con.sql(
        "FROM duckdb_tables() WHERE table_name LIKE '_pinned_%'"
    ).fetchall(), "the write drops the owner map it held for its fold"


# -- the `Expr` value form's raise rule (https://energy-models.github.io/datarecord/design/working-record/#an-nwexpr-value-derived-from-the-current-one) -------------------------------


def test_an_expression_over_a_named_target_with_no_rows_raises(staged):
    """A named target that resolves to nothing is a failed change, not a no-op.

    The caller asked for these rows to take a new value and there is nothing to
    derive one from, so it fails loudly rather than staging zero rows.

    Notes
    -----
    - [a derived value](https://energy-models.github.io/datarecord/design/working-record/#an-nwexpr-value-derived-from-the-current-one)
    """
    with pytest.raises(KeyError, match="no current value to derive from"):
        staged.set(
            "p_max_pu",
            nw.col("value") * 2,
            entity=["Manchester Wind"],
            snapshot="1999-01-01",
        )


def test_an_unscoped_expression_over_an_absent_attribute_stages_nothing(staged):
    """`entity=None` and no scope means "whatever resolves", so empty is an answer."""
    absent = next(
        a
        for a in sorted(staged.schema.attributes_for("entity", entity_type=GEN))
        if a not in staged.attributes
    )
    staged.set(absent, nw.col("value") * 2)
    assert absent not in staged.attributes, "nothing resolved, so nothing was staged"


# -- results through `kind="outputs"` (https://energy-models.github.io/datarecord/design/working-record/#set, https://energy-models.github.io/datarecord/design/read-path/#outputs) ---------------------------


def test_results_stage_and_read_back_without_committing(staged):
    """A tool can attach what it solved and the record reads it.

    Notes
    -----
    - [set](https://energy-models.github.io/datarecord/design/working-record/#set)
    """
    assert list(staged.outputs) == []
    staged.set("p", 42.0, entity=["Manchester Wind"], bus="Manchester", kind="outputs")

    rows = _unpacked(staged.outputs["p"])
    assert dict(
        zip(zip(rows["entity"], rows["bus"], strict=True), rows["value"], strict=True)
    ) == {("Manchester Wind", "Manchester"): 42.0}, (
        "a result over `connection` is addressed by `bus=` like an input"
    )
    assert "p" not in staged.attributes, "staged as a result, so it is not an input"


def test_results_accept_a_component_type_the_record_never_declared(staged):
    """A solve may derive a component the record has no member row for.

    PyPSA's `SubNetwork` is the real case: it exists only after a solve, so
    requiring a declared member row - which an *input* value must have -
    would refuse a legitimate result.

    Notes
    -----
    - [results through kind="outputs"](https://energy-models.github.io/datarecord/design/working-record/#results-through-kindoutputs)
    - [validation](https://energy-models.github.io/datarecord/design/working-record/#validation)
    """
    staged.set("sub_network", "AC", entity=["1"], kind="outputs")
    rows = staged.outputs["sub_network"].collect().to_native().to_pandas()
    assert rows["entity"].tolist() == ["1"]

    # The same name as an input is still rejected: membership governs inputs.
    with pytest.raises(KeyError, match="NoSuchGenerator"):
        staged.set("p_max_pu", 1.0, entity=["NoSuchGenerator"])


def test_an_undeclared_result_is_rejected(staged):
    """A result is declared like an input, so a typo is caught where it is typed.

    The membership rule stays relaxed either way - it is the *attribute* that
    must be declared, not the component it names.

    Notes
    -----
    - [results through kind="outputs"](https://energy-models.github.io/datarecord/design/working-record/#results-through-kindoutputs)
    - [validation](https://energy-models.github.io/datarecord/design/working-record/#validation)
    """
    with pytest.raises(KeyError, match="no result 'p_nom_optt'"):
        staged.set("p_nom_optt", 1.0, entity=["Manchester Wind"], kind="outputs")


def test_a_result_may_not_vary_over_a_dim_it_does_not_declare(staged):
    """`results` carries coordinates like `attributes`, so the scope is checked.

    Notes
    -----
    - [results through kind="outputs"](https://energy-models.github.io/datarecord/design/working-record/#results-through-kindoutputs)
    """
    assert "period" not in staged.schema.results["p_nom_opt"].dims
    with pytest.raises(ValueError, match="does not vary over"):
        staged.set(
            "p_nom_opt", 1.0, entity=["Manchester Wind"], kind="outputs", period=2030
        )


def test_a_results_value_keeps_its_declared_type(staged):
    """A result round-trips at the dtype `results` declares, not a guessed one.

    Staged values are held as text, since one staging table serves every
    attribute, and reading one back casts to the declared dtype. Both halves
    have to hold at once: PyPSA's `sub_network` is a string-valued output, and
    casting it as a number would `TRY_CAST` it to NULL and lose it with nothing
    raised, while `p` must come back a number rather than the text it was held
    as.

    Notes
    -----
    - [results through kind="outputs"](https://energy-models.github.io/datarecord/design/working-record/#results-through-kindoutputs)
    """
    assert "sub_network" in staged.schema.results, "declared as a result, not an input"
    assert "sub_network" not in staged.schema.attributes
    staged.set("sub_network", "0", entity=["Manchester Wind"], kind="outputs")

    rows = staged.outputs["sub_network"].collect().to_native().to_pandas()
    assert rows["value"].tolist() == ["0"], "a string result survives the round trip"

    # The other half: dropping the cast altogether would answer '42.0' here,
    # a number read back as the text the staging column holds it as.
    staged.set("p", 42.0, entity=["Manchester Wind"], bus="Manchester", kind="outputs")
    numeric = staged.outputs["p"].collect().to_native().to_pandas()
    assert numeric["value"].tolist() == [42.0], "a numeric result comes back a number"


def test_a_multi_type_results_frame_stages_by_name_alone(staged, root):
    """One frame spanning types is one call, keyed by name alone.

    `Tool.results` hands over one frame per attribute carrying every type's rows; with names unique there is no type to stamp, so the frame needs no
    `entity_type` and nothing can be silently relabelled.

    Notes
    -----
    - [entity is unique across types](https://energy-models.github.io/datarecord/design/format/#entity-is-unique-across-types)
    - [results through kind="outputs"](https://energy-models.github.io/datarecord/design/working-record/#results-through-kindoutputs)
    - [outputs](https://energy-models.github.io/datarecord/design/read-path/#outputs)
    - [consuming a record](https://energy-models.github.io/datarecord/design/tools/)
    """
    frame = staged.con.sql(
        "SELECT {'entity': entity, 'bus': bus} AS connection, value "
        "FROM (VALUES ('Manchester Wind', 'Manchester', 1.0), ('0', 'Norway', 2.0)) "
        "t(entity, bus, value)"
    )
    staged.set("p", frame, kind="outputs")
    staged.set("p_nom", 150.0, entity=["Manchester Wind"])

    rows = _unpacked(staged.outputs["p"])
    assert dict(zip(rows["entity"], rows["value"], strict=True)) == {
        "Manchester Wind": 1.0,
        "0": 2.0,
    }

    child = root.child(staged.edits)
    got = root.store.layer(child.id).outputs["p"]
    assert set(_unpacked(got)["entity"]) == {"Manchester Wind", "0"}, (
        "results survive the commit into the layer's own `outputs/`"
    )
    assert "entity_type" not in got.collect_schema().names()
    assert not _layer_rows(child, "p_nom").empty, "the inputs went where inputs go"


def test_one_call_spans_component_types(staged):
    """Names decide the type, so one edit may cross types.

    `p_nom` is declared for both `Generator` and `Link`, and each name is
    validated against its own type's spec - one call, two types, no keyword.

    Notes
    -----
    - [set](https://energy-models.github.io/datarecord/design/working-record/#set)
    """
    staged.set("p_nom", {"Manchester Wind": 150.0, "DC link": 80.0})
    got = _entity_values(staged, "p_nom")
    assert got["Manchester Wind"] == 150.0
    assert got["DC link"] == 80.0

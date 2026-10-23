# SPDX-FileCopyrightText: datarecord contributors
#
# SPDX-License-Identifier: MIT

"""The fold, the cache and persistence.

Notes
-----
- [materialised node caches](https://energy-models.github.io/datarecord/design/layers/#materialised-node-caches)
- [the owner map](https://energy-models.github.io/datarecord/design/read-path/#owner-map)
- [consuming a record](https://energy-models.github.io/datarecord/design/tools/)
"""

import json
import shutil
from pathlib import Path
from uuid import uuid4

import pandas as pd
import pytest

from datarecord import WorkingRecord
from datarecord.duck import union_all_by_name
from datarecord.layered.resolve import _fold_kind, write_schema
from datarecord.layered.sources import LayerSource, ParquetLayer
from datarecord.schema import Schema
from datarecord.tools.pypsa import PyPSA
from tests.fixtures import (
    empty_child,
    empty_root,
    export_network,
    schema,
    tombstone,
    write_entity_type,
    write_input,
)


@pytest.fixture
def parent(store):
    """A materialised root of three generators, each with two attributes."""
    revision = empty_root(store)
    layer = store.layer_dir(revision.id)
    write_schema(schema(), store)
    names = ["Manchester Wind", "Norway Wind", "Norway Gas"]
    write_entity_type(layer, "Generator", [{"entity": n} for n in names])
    for attribute, value in (("p_max_pu", 0.5), ("marginal_cost", 10.0)):
        write_input(layer, attribute, [{"entity": n, "value": value} for n in names])
    revision.materialise()
    return revision


def test_union_all_by_name_folds_every_relation(store):
    """Three arms, not two: the fold's union binds `u`/`rel` by name.

    Two relations pass whatever the loop body does, since the first pairing is
    the only one. Three is what catches the failure mode the helper's variables
    invite - a scan that re-reads `rels[0]` instead of advancing would give
    `[1, 1]` here, with no error to point at it.

    Notes
    -----
    - [resolving a relation](https://energy-models.github.io/datarecord/design/read-path/#resolving-a-relation)
    """
    rels = [store.workspace.con.sql(f"SELECT {i} AS x") for i in (1, 2, 3)]
    got = union_all_by_name(rels, store.workspace.con).fetchall()
    assert sorted(v for (v,) in got) == [1, 2, 3]


def test_union_all_by_name_fills_a_missing_column_with_null(store):
    """By *name*, so an arm lacking a column reads NULL there.

    What lets a layer written before `bus`/`breakpoint` existed still resolve,
    and a persisted owner map survive a newly declared dim.

    Notes
    -----
    - [Flags](https://energy-models.github.io/datarecord/design/record/#flags)
    - [versioning](https://energy-models.github.io/datarecord/design/schema/#versioning)
    """
    rels = [
        store.workspace.con.sql("SELECT 1 AS x, 'a' AS y"),
        store.workspace.con.sql("SELECT 2 AS x"),
    ]
    got = union_all_by_name(rels, store.workspace.con).fetchall()
    assert sorted(got, key=lambda r: r[0]) == [(1, "a"), (2, None)]


def keys(revision):
    """The inputs map's keys: `(name, attribute)`, no type.

    The map is tombstone-pruned in the fold (`fold_inputs` anti-joins each
    membership's deletions), so a key whose component or group tuple was deleted
    is already gone from it - the read needs no further gating.

    Notes
    -----
    - [the owner map](https://energy-models.github.io/datarecord/design/read-path/#owner-map)
    - [deletion](https://energy-models.github.io/datarecord/design/layers/#deletion)
    """
    df = revision.resolver.inputs.df()
    return {(r["entity"], str(r.attribute)) for _, r in df.iterrows()}


def entity_names(revision):
    return set(revision.resolver.axis("entity").df()["entity"])


def test_materialise_writes_the_map_under_resolved(store, parent):
    """`materialise` writes the maps under `resolved/`, not at the layer root.

    Notes
    -----
    - [materialised node caches](https://energy-models.github.io/datarecord/design/layers/#materialised-node-caches)
    """
    assert Path(store.resolved_dir(parent.id), "owner_map", "inputs.parquet").exists()
    # The entity axis folds like an axis now, materialised under `dims/`, not as
    # an owner map (https://energy-models.github.io/datarecord/design/read-path/#one-fold-for-every-axis).
    assert Path(store.resolved_dir(parent.id), "dims", "entity.parquet").exists()
    assert not Path(
        store.resolved_dir(parent.id), "owner_map", "entities.parquet"
    ).exists()
    # The cache shares the record's directory but stays out of the layer's own
    # namespace, so a reader that knows nothing about layering still sees a
    # plain parquet directory: every glob into a layer is single-level, so nothing
    # under `resolved/` is reachable by one (https://energy-models.github.io/datarecord/design/layers/#deletion).
    assert not Path(store.layer_dir(parent.id), "owner_map").exists()
    # The globs the fold and `Record.at` actually use must not reach a
    # cached file.
    layer = Path(store.layer_dir(parent.id))
    reachable = {
        p
        for pattern in (
            "*.parquet",
            "inputs/*.parquet",
            "outputs/*.parquet",
            "dims/*.parquet",
            "dims/*/*.parquet",
        )
        for p in layer.glob(pattern)
    }
    assert reachable
    assert not any("resolved" in p.parts for p in reachable)


def test_last_writer_wins_per_key(store, parent):
    """A child's key overrides the parent's, others stay with the parent.

    Every key of a root's map points at the root itself. The entity axis has no
    `layer_uuid`: it folds like an axis, its winning row the whole row in one
    file.

    Notes
    -----
    - [one fold for every axis](https://energy-models.github.io/datarecord/design/read-path/#one-fold-for-every-axis)
    """
    om = parent.resolver
    assert set(om.inputs.df()["layer_uuid"]) == {parent.id}
    assert "layer_uuid" not in om.axis("entity").columns
    assert ("Manchester Wind", "p_max_pu") in keys(parent)

    child = empty_child(parent)
    write_input(
        store.layer_dir(child.id),
        "p_max_pu",
        [{"entity": "Manchester Wind", "value": 0.42}],
    )
    df = child.resolver.inputs.df()

    def owner_of(name, attr):
        sel = df[(df["entity"] == name) & (df["attribute"].astype(str) == attr)]
        return sel["layer_uuid"].iloc[0]

    assert owner_of("Manchester Wind", "p_max_pu") == child.id
    assert owner_of("Manchester Wind", "marginal_cost") == parent.id
    assert owner_of("Norway Wind", "p_max_pu") == parent.id


def test_tombstone_removes_all_attributes(store, ac_dc):
    """A tombstone removes every attribute and the component row of the component.

    Only on the branch that carries it, and through to a built model.

    Notes
    -----
    - [deletion](https://energy-models.github.io/datarecord/design/layers/#deletion)
    """
    parent = export_network(ac_dc, store)
    parent.materialise()
    before = {k for k in keys(parent) if k[0] == "Norway Gas"}
    assert len(before) > 1
    assert "Norway Gas" in entity_names(parent)

    child = empty_child(parent)
    tombstone(store.layer_dir(child.id), "Generator", ["Norway Gas"])
    sibling = empty_child(parent)
    assert not {k for k in keys(child) if k[0] == "Norway Gas"}
    assert "Norway Gas" not in entity_names(child)
    assert "Norway Gas" in entity_names(sibling), (
        "a tombstone only affects the branch that carries it"
    )

    n = PyPSA.build(child.record)
    assert "Norway Gas" not in n.c["Generator"].static.index
    assert "Norway Wind" in n.c["Generator"].static.index


def test_a_removed_cache_falls_back_to_the_fold(store, parent):
    """A cache is an optimisation, so losing it costs work rather than answers.

    The old model had to raise here: a closed node's ancestry was truncated to
    itself, so re-folding would have silently dropped every ancestor. Gating on
    the cache's presence instead means the untruncated path is still available.

    Notes
    -----
    - [materialised node caches](https://energy-models.github.io/datarecord/design/layers/#materialised-node-caches)
    """
    child = empty_child(parent)
    write_input(
        store.layer_dir(child.id),
        "p_min_pu",
        [{"entity": "Norway Gas", "value": 0.1}],
    )
    child.materialise()
    expected = keys(child)

    shutil.rmtree(Path(store.resolved_dir(child.id), "owner_map"))
    fresh = store.revision(child.id)
    assert keys(fresh) == expected


def test_any_node_may_be_a_parent(store, parent):
    """A layer is write-once, so no node needs preparing to branch from.

    Notes
    -----
    - [a layer's data is write-once](https://energy-models.github.io/datarecord/design/layers/#a-layers-data-is-write-once)
    """
    child = empty_child(parent)
    write_input(
        store.layer_dir(child.id),
        "p_max_pu",
        [{"entity": "Manchester Wind", "value": 0.42}],
    )
    grandchild = empty_child(child)
    # The child was never materialised, yet its layer resolves for the
    # grandchild all the same.
    df = grandchild.resolver.inputs.df()
    row = df[(df["entity"] == "Manchester Wind") & (df["attribute"] == "p_max_pu")]
    assert set(row["layer_uuid"]) == {child.id}


def test_a_record_with_no_manifest_folds(store):
    """A record that declares no schema resolves to an empty map, not a crash.

    `Schema()` is "no manifest yet", which is what a record reads before
    anything has been written to it. The map's flag columns are structs with a
    field per declared dim and DuckDB has no empty struct, so this is
    the one path where there are none to declare.

    Notes
    -----
    - [one schema per record](https://energy-models.github.io/datarecord/design/schema/#one-schema-per-record)
    - [the owner map](https://energy-models.github.io/datarecord/design/read-path/#owner-map)
    """
    revision = empty_root(store)
    assert revision.record.schema.dims == ()

    inputs = revision.resolver.inputs
    assert "varies" in inputs.columns
    assert inputs.fetchall() == []


def test_a_parquet_layer_locates_a_layers_files(store):
    """The fold names files and the source says where they are.

    `Store.layer_dir` is what a `ParquetLayer` derives from, so this pins the
    seam rather than the layout: a reader asks for `inputs/p_nom.parquet` and
    never builds the path itself.

    Notes
    -----
    - [the record format](https://energy-models.github.io/datarecord/design/format/)
    """
    revision_id = uuid4()
    source = ParquetLayer(revision_id, Schema(), store)
    assert isinstance(source, LayerSource), (
        "structural, so no import is needed to be one"
    )

    assert source.uri() == store.layer_dir(revision_id), "empty is the layer root"
    assert source.uri("inputs/p_nom.parquet") == (
        store.layer_dir(revision_id) + "inputs/p_nom.parquet"
    )
    # A glob is a path like any other: the source neither parses nor validates.
    assert source.uri("inputs/*.parquet").endswith("inputs/*.parquet")


def _largest_intermediate(store, rel):
    """The most rows any operator produced while DuckDB executed `rel`."""
    profile = json.loads(
        store.workspace.con.sql("EXPLAIN (ANALYZE, FORMAT JSON) FROM rel").fetchall()[
            0
        ][1]
    )

    def largest(node):
        return max(
            [node.get("operator_cardinality") or 0]
            + [largest(child) for child in node.get("children", [])]
        )

    return largest(profile)


def test_a_read_joins_no_more_rows_than_the_layers_hold(store):
    """The owner-map join is keyed on a partial dim, not filtered on it afterwards.

    The join matched a partial dim with `raw IS NULL OR raw IS NOT DISTINCT FROM
    owned`, which DuckDB cannot hash. It joined on `entity` and `layer_uuid`
    only and filtered on `snapshot` after the join, so one layer of `T`
    snapshots per entity produced `T * T` rows per entity before the filter,
    and a read slowed with the square of the series length.

    Notes
    -----
    - [resolving a relation](https://energy-models.github.io/datarecord/design/read-path/#resolving-a-relation)
    """
    write_schema(
        Schema(
            dimensions={
                "entity": {"dtype": "String"},
                "snapshot": {"dtype": "Int64"},
            },
            properties={
                "entity": {
                    "entity_type": {
                        "dtype": {"Enum": ["Generator"]},
                    }
                }
            },
            attributes={
                "p_max_pu": {"dtype": "Float64", "dims": ["entity", "snapshot"]}
            },
            partial=frozenset({"entity", "snapshot"}),
        ),
        store,
    )
    names, snapshots = ["wind", "solar"], 200
    base = empty_root(store)
    staged = WorkingRecord(base.record)
    staged.add("entity", names, entity_type="Generator")
    staged.set(
        "p_max_pu",
        pd.DataFrame(
            {
                "entity": [n for n in names for _ in range(snapshots)],
                "snapshot": list(range(snapshots)) * len(names),
                "value": 0.5,
            }
        ),
    )
    revision = base.child(staged.edits)

    rel = revision.record.attributes["p_max_pu"].to_native()
    stored = len(names) * snapshots
    assert rel.count("*").fetchone() == (stored,), "one row per stored value"
    assert _largest_intermediate(store, rel) <= stored, (
        "no operator produces more rows than the layer holds"
    )


def test_the_fold_broadcasts_by_hash_join(store):
    """Expanding a broadcast NULL over its axis is a hash join, not a nested loop.

    The join matched on `dim IS NULL` alone, which DuckDB runs as a nested loop
    comparing every row with every label - even a row that sets the dim and so
    matches none. Row counts stay right, so only the plan shows it.

    Notes
    -----
    - [the owner map](https://energy-models.github.io/datarecord/design/read-path/#owner-map)
    """
    write_schema(
        Schema(
            dimensions={
                "entity": {"dtype": "String"},
                "snapshot": {"dtype": "Int64"},
            },
            properties={
                "entity": {
                    "entity_type": {
                        "dtype": {"Enum": ["Generator"]},
                    }
                }
            },
            attributes={
                "p_max_pu": {"dtype": "Float64", "dims": ["entity", "snapshot"]},
                "weight": {"dtype": "Float64", "dims": ["snapshot"]},
            },
            partial=frozenset({"entity", "snapshot"}),
        ),
        store,
    )
    base = empty_root(store)
    staged = WorkingRecord(base.record)
    staged.add("entity", ["wind"], entity_type="Generator")
    staged.add("snapshot", [0, 1])
    staged.set("weight", {0: 1.0, 1: 1.0})
    staged.set(
        "p_max_pu",
        pd.DataFrame({"entity": ["wind", "wind"], "snapshot": [0, 1], "value": 0.5}),
    )
    resolver = base.child(staged.edits).resolver

    plan = _fold_kind(
        "inputs", resolver.sources, resolver.con, resolver.schema
    ).explain()
    assert "HASH_JOIN" in plan, "the fold joins at all"
    assert "NL_JOIN" not in plan and "NESTED_LOOP" not in plan, plan

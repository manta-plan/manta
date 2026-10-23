# SPDX-FileCopyrightText: datarecord contributors
#
# SPDX-License-Identifier: MIT

"""The workspace, its stores, and the tree at the location.

Notes
-----
- [the store](https://energy-models.github.io/datarecord/design/layers/#the-store)
- [a cursor per thread](https://energy-models.github.io/datarecord/design/read-path/#a-cursor-per-thread)
"""

import pickle
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import duckdb
import narwhals as nw
import pytest

from datarecord import Revision, Workspace
from datarecord.files import Absent, PreconditionFailedError
from datarecord.layered import write
from datarecord.layered.resolve import read_schema
from datarecord.mutable import WorkingRecord
from tests.fixtures import (
    RivalWrite,
    empty_child,
    empty_root,
    schema,
    widened,
    write_entity_type,
    write_input,
    write_scenarios,
    write_schema,
)
from tests.test_write import _SCHEMA, _long, _Source


@pytest.fixture
def tree(store):
    """A root holding one generator with a `p_max_pu`, and a child of it."""
    write_schema(schema(), store)
    root = empty_root(store)
    layer = store.layer_dir(root.id)
    write_entity_type(layer, "Generator", [{"entity": "wind"}])
    write_input(layer, "p_max_pu", [{"entity": "wind", "value": 0.4}])
    return root, empty_child(root)


def _in_threads(n, fn):
    """Run `fn(i)` in `n` threads released together, and return the results."""
    barrier = threading.Barrier(n)

    def run(i):
        barrier.wait()
        return fn(i)

    with ThreadPoolExecutor(n) as pool:
        return list(pool.map(run, range(n)))


def test_a_store_needs_a_location(workspace):
    with pytest.raises(ValueError, match="needs a location"):
        workspace.store("")


def test_one_location_is_one_store(workspace, tmp_path):
    assert workspace.store(str(tmp_path)) is workspace.store(str(tmp_path) + "/")


def test_a_local_location_is_absolute(workspace, tmp_path, monkeypatch):
    """A later `chdir` cannot move it."""
    monkeypatch.chdir(tmp_path)
    store = workspace.store("relative")
    assert store.uri == (tmp_path / "relative").as_posix()


def test_another_scheme_is_refused(workspace):
    with pytest.raises(ValueError, match="s3://"):
        workspace.store("https://example.org/record")


def test_the_tree_lives_beside_the_layers(store, tree):
    """Each revision is one file under `revisions/`, read back by a new workspace.

    Notes
    -----
    - [the tree beside the layers](https://energy-models.github.io/datarecord/design/layers/#the-tree-beside-the-layers)
    """
    root, child = tree
    fresh = Workspace()
    try:
        again = fresh.store(store.uri)
        assert {r.id for r in again.revisions()} == {root.id, child.id}
        assert again.revision(child.id).ancestry() == [root.id, child.id]
    finally:
        fresh.close()


def test_a_revision_of_another_store_is_not_this_ones(workspace, tmp_path, tree):
    root, _ = tree
    other = workspace.store(str(tmp_path / "other"))
    assert other.revisions() == []
    with pytest.raises(KeyError):
        other.revision(root.id)


def test_a_revision_file_is_written_once(store, tree):
    root, _ = tree
    with pytest.raises(PreconditionFailedError):
        store.files.write_text(store._revision_uri(root.id), "{}", expect=Absent())


def test_a_stale_version_is_refused(store):
    """A `Version` write holds only while the file is as it was read.

    Notes
    -----
    - [files, local and remote](https://energy-models.github.io/datarecord/design/layers/#files-local-and-remote)
    """
    uri = f"{store.uri}/note.txt"
    read = store.files.write_text(uri, "first", expect=None)
    store.files.write_text(uri, "second", expect=read)
    with pytest.raises(PreconditionFailedError):
        store.files.write_text(uri, "third", expect=read)
    assert store.files.read_text(uri)[0] == "second", "the refused write left no trace"


@pytest.mark.parametrize("superset", [True, False], ids=["superset", "incompatible"])
def test_a_widening_that_lost_the_race_is_checked_again(
    workspace, store, monkeypatch, superset
):
    """The loser re-reads the rival's manifest and re-checks against it.

    A superset of the rival's widening still lands; one the race made
    incompatible fails rather than dropping the rival's.

    Notes
    -----
    - [the manifest's compare-and-swap](https://energy-models.github.io/datarecord/design/writing/#the-manifests-compare-and-swap)
    """
    write_schema(_SCHEMA, store)
    rival = widened(_SCHEMA, "rival")
    mine = widened(rival if superset else _SCHEMA, "mine")
    files = RivalWrite(workspace._local, store.manifest_uri, rival.model_dump_json())
    monkeypatch.setattr(workspace, "_local", files)
    source = _Source(mine, attributes={"p_nom": _long()})

    if superset:
        store.root(source)
        assert files.raced, "the rival wrote between the read and the write"
        assert read_schema(store) == mine, "both widenings end in the manifest"
    else:
        with pytest.raises(ValueError, match="'rival' removed"):
            store.root(source)
        assert read_schema(store) == rival, "the rival's widening is kept"
        assert store.revisions() == [], "the losing layer is unreachable"


class _AlwaysLoses:
    """`Files` where every conditional write of `uri` is refused, and counted."""

    def __init__(self, inner, uri):
        self._inner = inner
        self._uri = uri
        self.writes = 0

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def write_text(self, uri, text, *, expect):
        if uri == self._uri and expect is not None:
            self.writes += 1
            raise PreconditionFailedError(uri)
        return self._inner.write_text(uri, text, expect=expect)


def test_a_writer_that_always_loses_gives_up(workspace, store, monkeypatch):
    """As a manifest unreadable for a 403 does: the error names both causes.

    Notes
    -----
    - [the manifest's compare-and-swap](https://energy-models.github.io/datarecord/design/writing/#the-manifests-compare-and-swap)
    """
    files = _AlwaysLoses(workspace._local, store.manifest_uri)
    monkeypatch.setattr(workspace, "_local", files)
    monkeypatch.setattr(write, "sleep", lambda _: None)

    with pytest.raises(RuntimeError, match=r"changed under each.*s3:GetObject"):
        store.root(_Source(_SCHEMA, attributes={"p_nom": _long()}))
    assert files.writes == write._ATTEMPTS, "one write per attempt, then the error"
    assert store.revisions() == [], (
        "the layer that never declared its schema is unreachable"
    )


def test_a_revision_crosses_a_process_boundary(workspace, tree):
    """Serialised as its store's location, read back through the process workspace.

    Read before serialising, so a cached resolver would have to travel if any
    did. The fixture's workspace is not the process one, so the ancestry can
    only come from reading the revision files again.

    Notes
    -----
    - [crossing a process boundary](https://energy-models.github.io/datarecord/design/layers/#crossing-a-process-boundary)
    """
    root, child = tree
    names = list(child.record.attributes)
    assert workspace is not Workspace.process(), "the fixture workspace is its own"
    dumped = child.model_dump_json()
    assert child.store.uri in dumped

    for back in (
        Revision.model_validate_json(dumped),
        pickle.loads(pickle.dumps(child)),
    ):
        assert back.store.workspace is Workspace.process()
        assert back.parent == root.id
        assert back.ancestry() == [root.id, child.id], "the tree is read from files"
        assert list(back.record.attributes) == names

    unpickled = pickle.loads(pickle.dumps(child.store))
    assert unpickled is Workspace.process().store(child.store.uri)


def test_threads_share_one_folded_owner_map(workspace, tree):
    """Each thread reads on its own cursor, and the fold is done once.

    Notes
    -----
    - [a cursor per thread](https://energy-models.github.io/datarecord/design/read-path/#a-cursor-per-thread)
    """
    _, child = tree
    record = child.record

    def read(_):
        rows = record.attributes["p_max_pu"].collect().to_native()
        return workspace.con, len(rows)

    results = _in_threads(8, read)
    cursors = {id(con) for con, _ in results}
    assert len(cursors) == 8, "one cursor per thread"
    assert len({n for _, n in results}) == 1, "every thread reads the same rows"
    tables = workspace.con.sql(
        "SELECT table_name FROM duckdb_tables() WHERE table_name LIKE 'owner_map_%'"
    ).fetchall()
    assert [t for (t,) in tables if child.id.hex in t], "the map is a shared table"


def test_two_threads_missing_the_fold_at_once_both_get_it(store, tree):
    _, child = tree

    def fold(_):
        fresh = store.revision(child.id)
        fresh._resolver = None
        return sorted(fresh.resolver.inputs.fetchall(), key=str)

    first, second = _in_threads(2, fold)
    assert first == second
    assert first


def test_two_threads_adding_one_revision_row_both_succeed(workspace, store, tree):
    _, child = tree
    fresh = Workspace()
    try:
        again = fresh.store(store.uri)
        ids = _in_threads(2, lambda _: again.revision(child.id).id)
        assert ids == [child.id, child.id]
    finally:
        fresh.close()


_NARROW = {"snapshot": nw.Datetime(), "period": nw.Int64()}


def _folded_then_widened(store, partial=frozenset(), *, materialised=False):
    """A root whose fold predates `scenario`, read under a schema declaring it.

    `materialised` persists the root's owner map before the widening and
    returns an empty child reading it; otherwise the root itself, reading the
    shared fold table.
    """
    write_schema(schema(dims=_NARROW, partial=set(partial)), store)
    revision = empty_root(store)
    layer = store.layer_dir(revision.id)
    write_entity_type(layer, "Generator", [{"entity": "wind"}])
    write_input(layer, "p_max_pu", [{"entity": "wind", "value": 0.4}])
    before = revision.resolver.inputs
    assert "scenario" not in str(before.types[before.columns.index("varies")])
    if materialised:
        revision.materialise()
        uri = f"{store.resolved_dir(revision.id)}owner_map/inputs.parquet"
        persisted = store.workspace.con.sql(f"SELECT varies FROM read_parquet('{uri}')")
        assert "scenario" not in str(persisted.types[0]), (
            "the map on disk knows nothing of `scenario`"
        )

    wide = {**_NARROW, "scenario": nw.String()}
    write_schema(schema(dims=wide, partial=set(partial)), store)
    after = store.revision(revision.id)
    assert after.resolver is not revision.resolver
    if materialised:
        return empty_child(after)
    inputs = after.resolver.inputs
    assert "scenario" not in str(inputs.types[inputs.columns.index("varies")]), (
        "the fold table is read as it was folded, not re-folded or cast"
    )
    return after


@pytest.mark.parametrize("materialised", [False, True], ids=["live", "materialised"])
def test_a_fold_reads_under_a_widened_schema(store, materialised):
    """A fold made before a dim was declared reads under the wider schema.

    The fold carries no schema, so it is read as it was folded. A compatible
    widening only adds; the dim it adds has no field in the flag structs,
    which `UNION ALL BY NAME` fills with NULL and which reads as unset - no row
    mentions it.

    Notes
    -----
    - [versioning](https://energy-models.github.io/datarecord/design/schema/#versioning)
    - [the owner map](https://energy-models.github.io/datarecord/design/read-path/#owner-map)
    - [Flags](https://energy-models.github.io/datarecord/design/record/#flags)
    """
    after = _folded_then_widened(store, materialised=materialised)
    rows = after.record.attributes["p_max_pu"].collect()
    assert rows["value"].to_list() == [0.4], (
        "a fold made under the narrower schema reads under the wider one"
    )
    flags = after.record.flags()["p_max_pu"]
    assert "scenario" not in flags.varies
    assert "scenario" not in flags.broadcast, "a missing flag field reads as unset"
    assert "snapshot" in flags.broadcast, "a field the fold had still reads"


def test_a_staged_tail_folds_onto_a_fold_table_from_before_a_widening(store):
    """The tail's flag structs carry `scenario`, the frozen table's do not.

    The two shapes meet in one map, unioned by name; the resolved read and the
    flags both go through it.

    Notes
    -----
    - [the owner map](https://energy-models.github.io/datarecord/design/read-path/#owner-map)
    - [resolving a relation](https://energy-models.github.io/datarecord/design/read-path/#resolving-a-relation)
    """
    after = _folded_then_widened(store, partial={"period"})
    w = WorkingRecord(after.record)
    w.set("p_max_pu", 0.7, entity=["wind"], period=2030, scenario="high")

    inputs = w.resolver.inputs
    assert "scenario" in str(inputs.types[inputs.columns.index("varies")])
    rows = (
        w.attributes["p_max_pu"]
        .collect()
        .select("period", "scenario", "value")
        .sort("period", nulls_last=True)
        .rows()
    )
    assert rows == [(2030, "high", 0.7), (None, None, 0.4)], (
        "the staged row and the frozen one both resolve"
    )
    flags = w.flags()["p_max_pu"]
    assert "scenario" in flags.varies, "the staged row sets it"
    assert "scenario" not in flags.broadcast, "the frozen row's missing field is unset"


def test_an_enum_dim_resolves_from_fold_tables_after_a_widening(store):
    """The axis table holds `scenario` as its file did, a layer row as declared.

    A broadcast row expands against the axis, so the two types meet in one
    key, and neither fold table is cast on the way out.

    Notes
    -----
    - [a cursor per thread](https://energy-models.github.io/datarecord/design/read-path/#a-cursor-per-thread)
    - [the broadcast rule](https://energy-models.github.io/datarecord/design/record/#the-broadcast-rule)
    """
    dims = {**_NARROW, "scenario": nw.Enum(["low", "high"])}
    write_schema(schema(dims=dims), store)
    revision = empty_root(store)
    layer = store.layer_dir(revision.id)
    write_entity_type(layer, "Generator", [{"entity": "wind"}, {"entity": "gas"}])
    write_scenarios(
        layer,
        [{"scenario": "low"}, {"scenario": "high"}],
    )
    write_input(
        layer,
        "p_max_pu",
        [
            {"entity": "wind", "value": 0.4},
            {"entity": "gas", "scenario": "high", "value": 0.9},
        ],
    )
    expected = [("gas", "high", 0.9), ("wind", "high", 0.4), ("wind", "low", 0.4)]

    def resolved(revision):
        frame = revision.record.attributes["p_max_pu"].collect()
        return sorted(frame.select("entity", "scenario", "value").rows())

    assert resolved(revision) == expected
    write_schema(schema(dims={**dims, "region": nw.String()}), store)
    after = store.revision(revision.id)
    assert resolved(after) == expected, "the cached fold reads under the wider schema"
    labels = after.record.dims["scenario"].collect()["scenario"].to_list()
    assert sorted(labels) == ["high", "low"]


def test_a_failed_materialise_leaves_the_node_unmaterialised(store, tree, monkeypatch):
    """`owner_map/inputs.parquet` is the cache's presence, so it is written last.

    Notes
    -----
    - [materialised node caches](https://energy-models.github.io/datarecord/design/layers/#materialised-node-caches)
    """
    from datarecord.layered import resolve

    root, _ = tree

    def fail(*args, **kwargs):
        raise RuntimeError("the owner map write fails")

    monkeypatch.setattr(resolve, "_fold_kind", fail)
    with pytest.raises(RuntimeError):
        root.materialise()
    assert Path(store.resolved_dir(root.id), "dims", "entity.parquet").exists()
    assert not resolve.materialised(root.id, store), "the rest is no cache yet"
    assert not list(Path(store.resolved_dir(root.id)).rglob("*.tmp")), (
        "no temporary file is left behind"
    )


def test_a_relation_from_another_connection_is_rejected(tree):
    """Copying it over would read it on a connection nobody asked to read.

    Notes
    -----
    - [a cursor per thread](https://energy-models.github.io/datarecord/design/read-path/#a-cursor-per-thread)
    """
    root, _ = tree
    foreign = duckdb.connect()
    try:
        w = WorkingRecord(root.record)
        frame = foreign.sql("SELECT 'wind' AS entity, 1.0 AS value")
        with pytest.raises(ValueError, match="another connection or thread"):
            w.set("p_nom", frame)
    finally:
        foreign.close()

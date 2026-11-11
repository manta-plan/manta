# SPDX-FileCopyrightText: datarecord contributors
#
# SPDX-License-Identifier: MIT

"""A store and a standalone directory on S3, against a real server.

Skipped unless `DATARECORD_TEST_S3_ENDPOINT` names an S3 endpoint honouring
conditional writes atomically - SeaweedFS 4.18 or later, which Manta deploys.
A mock would pass exactly the tests the headers exist for. To run them::

    docker run --rm -p 8333:8333 -e AWS_ACCESS_KEY_ID=datarecord \
        -e AWS_SECRET_ACCESS_KEY=datarecord chrislusf/seaweedfs:4.18 server -s3
    DATARECORD_TEST_S3_ENDPOINT=http://localhost:8333 pixi run pytest tests/test_remote.py

Each test creates its own bucket. The credentials are `AWS_ACCESS_KEY_ID` and
`AWS_SECRET_ACCESS_KEY` where set, and `datarecord` otherwise, which the server
above is started with: SeaweedFS 4.18 refuses an unknown key. `AWS_PROFILE`
must be unset, or botocore reads that profile instead.

Notes
-----
- [files, local and remote](https://energy-models.github.io/datarecord/design/layers/#files-local-and-remote)
- [a revision exists only by its file](https://energy-models.github.io/datarecord/design/writing/#a-revision-exists-only-by-its-file)
"""

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pandas as pd
import pytest

from datarecord import Workspace
from datarecord.files import Absent, PreconditionFailedError, RemoteFiles
from datarecord.layered.resolve import read_schema
from tests.fixtures import RivalWrite, relation, widened
from tests.test_write import _SCHEMA, _long, _Source

ENDPOINT = os.environ.get("DATARECORD_TEST_S3_ENDPOINT")

pytestmark = pytest.mark.skipif(
    not ENDPOINT, reason="DATARECORD_TEST_S3_ENDPOINT names no S3 server"
)


@pytest.fixture
def bucket(monkeypatch):
    """A fresh bucket on the test server, with the AWS environment pointing there."""
    monkeypatch.setenv("AWS_ENDPOINT_URL", ENDPOINT)
    for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.setenv(name, os.environ.get(name, "datarecord"))
    monkeypatch.setenv("AWS_REGION", os.environ.get("AWS_REGION", "us-east-1"))
    name = f"datarecord-{uuid4().hex[:16]}"
    RemoteFiles()._s3.create_bucket(Bucket=name)
    return f"s3://{name}"


def test_a_store_writes_and_reads_its_files(workspace, bucket):
    store = workspace.store(f"{bucket}/record")
    root = store.root(_Source(_SCHEMA, attributes={"p_nom": _long()}))
    child = root.child(_Source(_SCHEMA, attributes={"p_nom": _long(value=2.0)}))

    fresh = Workspace()
    try:
        again = fresh.store(store.uri)
        assert read_schema(again) == _SCHEMA
        assert {r.id for r in again.revisions()} == {root.id, child.id}
        back = again.revision(child.id)
        assert back.ancestry() == [root.id, child.id]
        assert list(relation(back, "p_nom").df()["value"]) == [2.0]
    finally:
        fresh.close()


def test_a_standalone_directory_writes_and_reads_its_manifest(workspace, bucket):
    out = f"{bucket}/out"
    workspace.write(_Source(_SCHEMA, attributes={"p_nom": _long()}), out)

    elsewhere = Workspace()
    try:
        record = elsewhere.at(out)
        assert record.schema == _SCHEMA
        rows = record.attributes["p_nom"].collect().to_native()
        assert rows["value"].to_pylist() == [1.0]
    finally:
        elsewhere.close()


def test_a_revision_file_is_written_once(workspace, bucket):
    store = workspace.store(f"{bucket}/record")
    root = store.root(_Source(_SCHEMA, attributes={"p_nom": _long()}))
    with pytest.raises(PreconditionFailedError):
        store.files.write_text(store._revision_uri(root.id), "{}", expect=Absent())


@pytest.mark.parametrize(
    ("superset", "outcome"),
    [(True, "both widenings"), (False, "an incompatibility")],
)
def test_a_widening_that_lost_the_race_ends_in(
    workspace, bucket, monkeypatch, superset, outcome
):
    store = workspace.store(f"{bucket}/record")
    store.root(_Source(_SCHEMA, attributes={"p_nom": _long()}))
    rival = widened(_SCHEMA, "rival")
    mine = widened(rival if superset else _SCHEMA, "mine")
    files = RivalWrite(workspace._remote, store.manifest_uri, rival.model_dump_json())
    monkeypatch.setattr(workspace, "_remote", files)

    source = _Source(mine, attributes={"p_nom": _long()})
    if superset:
        store.root(source)
        assert read_schema(store) == mine, outcome
    else:
        with pytest.raises(ValueError, match="'rival' removed"):
            store.root(source)
        assert read_schema(store) == rival, "the rival's widening is kept"
    assert files.raced


def test_two_writers_widening_at_once_lose_nothing_silently(workspace, bucket):
    """One wins; the other reports the incompatibility rather than overwriting.

    Holds only on a server checking the condition under the object's write
    lock, which SeaweedFS does from 4.18.
    """
    store = workspace.store(f"{bucket}/record")
    store.root(_Source(_SCHEMA, attributes={"p_nom": _long()}))
    widenings = [widened(_SCHEMA, "first"), widened(_SCHEMA, "second")]
    barrier = threading.Barrier(2)

    def write(i):
        barrier.wait()
        try:
            store.root(_Source(widenings[i], attributes={"p_nom": _long()}))
        except ValueError:
            return None
        return widenings[i]

    with ThreadPoolExecutor(2) as pool:
        won = [s for s in pool.map(write, range(2)) if s is not None]
    assert len(won) == 1, "exactly one widening lands, the other is reported"
    assert read_schema(store) == won[0]


def test_a_write_failing_part_way_leaves_no_revision(workspace, bucket):
    store = workspace.store(f"{bucket}/record")
    short = _long().drop(columns=["breakpoint"])
    source = _Source(
        _SCHEMA,
        dims={
            "entity": pd.DataFrame(
                {"entity": ["steel_dri"], "entity_type": ["Process"]}
            )
        },
        attributes={"p_nom": short},
    )
    with pytest.raises(ValueError, match="missing long-schema columns"):
        store.root(source)

    assert store.files.list(f"{store.uri}/layers/"), "part of the layer is left"
    assert store.revisions() == [], "but no revision reaches it"
    assert not store.files.exists(store.manifest_uri), "nor was the manifest widened"


def test_a_standalone_write_to_a_non_empty_uri_is_refused(workspace, bucket):
    out = f"{bucket}/out"
    files = workspace.files(out)
    files.write_text(f"{out}/stray.txt", "x", expect=None)

    with pytest.raises(FileExistsError, match="does not exist yet"):
        workspace.write(_Source(_SCHEMA, attributes={"p_nom": _long()}), out)
    assert files.list(out) == ["stray.txt"], "refused before anything was written"

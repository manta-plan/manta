# SPDX-FileCopyrightText: datarecord contributors
#
# SPDX-License-Identifier: MIT

"""The `Workspace` holding the connection, and the `Store` holding a location.

A workspace is the DuckDB database and the means to reach files, which is all a
standalone directory needs. A store is one location - its manifest, its
revision tree, its layers - and works through a workspace several stores share.

Notes
-----
- [the store](https://energy-models.github.io/datarecord/design/layers/#the-store)
- [module layout](https://energy-models.github.io/datarecord/design/module-layout/)
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse
from uuid import UUID, uuid4, uuid5

import duckdb
from duckdb import DuckDBPyConnection

from datarecord.files import Absent, Files, LocalFiles, RemoteFiles
from datarecord.layered.record import Record
from datarecord.layered.resolve import Resolver, read_schema
from datarecord.layered.sources import DirectorySource, LayerSource
from datarecord.layered.write import layer_data, reconcile_schema, write_layer
from datarecord.record import LayerData, RecordLike
from datarecord.schema import Schema

if TYPE_CHECKING:
    from datarecord.layered.revision import Revision

_REVISIONS = """
CREATE TABLE IF NOT EXISTS revisions (
  location VARCHAR,
  id       UUID,
  parent   UUID,
  PRIMARY KEY (location, id)
)
"""


class _Cursors(threading.local):
    """The calling thread's cursor on one database.

    `threading.local` reruns `__init__` in each thread that first touches it, so
    there is no existence check and no lock, and a thread's cursor goes with it.

    Notes
    -----
    - [a cursor per thread](https://energy-models.github.io/datarecord/design/read-path/#a-cursor-per-thread)
    """

    def __init__(self, db: DuckDBPyConnection) -> None:
        self.con = db.cursor()


class Workspace:
    """A DuckDB database and the files it reaches, shared by every store on it.

    `con` is the calling thread's cursor: one workspace serves every thread, and
    their work shares one database - its tables, never its relations.

    Parameters
    ----------
    database
        DuckDB database, `:memory:` by default. What lives there is a workspace
        and never the record: deleting it loses at most uncommitted edits.

    Notes
    -----
    - [the store](https://energy-models.github.io/datarecord/design/layers/#the-store)
    - [a cursor per thread](https://energy-models.github.io/datarecord/design/read-path/#a-cursor-per-thread)
    """

    def __init__(self, database: str = ":memory:") -> None:
        self._db = duckdb.connect(database)
        self._db.execute(_REVISIONS)
        self._cursors = _Cursors(self._db)
        self._stores: dict[str, Store] = {}
        self._local = LocalFiles()
        self._remote: Files | None = None
        self._remote_lock = threading.Lock()

    @property
    def con(self) -> DuckDBPyConnection:
        """The calling thread's cursor, made on its first use in that thread."""
        return self._cursors.con

    @classmethod
    def process(cls) -> Workspace:
        """The process's workspace, created on first use on `:memory:`.

        What a deserialised `Revision` attaches to, having no workspace passed;
        nothing else reaches it unless named.

        Notes
        -----
        - [crossing a process boundary](https://energy-models.github.io/datarecord/design/layers/#crossing-a-process-boundary)
        """
        global _process
        with _process_lock:
            if _process is None:
                _process = cls()
            return _process

    def files(self, uri: str) -> Files:
        """The `Files` for `uri`'s scheme: local without `://`, remote for `s3://`.

        Raises
        ------
        ValueError
            For any other scheme.
        """
        if "://" not in uri:
            return self._local
        if not uri.startswith("s3://"):
            msg = f"{uri}: a location is a local path or an s3:// URI"
            raise ValueError(msg)
        with self._remote_lock:
            if self._remote is None:
                self._remote = self._connect_remote()
            return self._remote

    def _connect_remote(self) -> Files:
        """Set up boto3 and DuckDB's `httpfs` from the AWS environment, once.

        Never for a local workspace: `PROVIDER credential_chain` probes
        instance-metadata endpoints that hang for minutes where none exist.
        With `AWS_ENDPOINT_URL` set, the secret adds what the chain does not
        supply - the endpoint, path-style addressing, SSL per its scheme - and
        skips that probe, a self-hosted server having no metadata service.

        Raises
        ------
        ImportError
            If boto3, from `datarecord[remote]`, is missing.

        Notes
        -----
        - [files, local and remote](https://energy-models.github.io/datarecord/design/layers/#files-local-and-remote)
        """
        files = RemoteFiles()
        options = ["TYPE s3", "PROVIDER credential_chain"]
        endpoint = os.environ.get("AWS_ENDPOINT_URL")
        if endpoint:
            url = urlparse(endpoint)
            options += [
                f"ENDPOINT '{url.netloc}'",
                "URL_STYLE 'path'",
                f"USE_SSL {str(url.scheme == 'https').lower()}",
                "CHAIN 'env;config'",
            ]
        self._db.execute("INSTALL httpfs; LOAD httpfs;")
        self._db.execute(f"CREATE OR REPLACE SECRET ({', '.join(options)})")
        return files

    def store(self, uri: str) -> Store:
        """This workspace's store at `uri`, one object per normalised location.

        Raises
        ------
        ValueError
            For an empty `uri`.
        """
        if not uri:
            msg = (
                "a store needs a location; an empty one would be the working directory"
            )
            raise ValueError(msg)
        location = _absolute(uri)
        self.files(location)
        return self._stores.setdefault(location, Store(location, self))

    def at(self, uri: str) -> Record:
        """The standalone record at `uri`, read under its own `manifest.json`.

        A local `uri` is resolved, as `store` resolves one, so a later `chdir`
        cannot point it at another record.

        Raises
        ------
        FileNotFoundError
            If `uri` has no manifest: a directory without one is a tree layer,
            read under its store's schema through `Store.layer`.
        ValueError
            If the manifest carries no record id.

        Notes
        -----
        - [the record format](https://energy-models.github.io/datarecord/design/format/)
        - [one schema per record](https://energy-models.github.io/datarecord/design/schema/#one-schema-per-record)
        """
        base = _absolute(uri) + "/"
        found = self.files(base).read_text(base + "manifest.json")
        if found is None:
            msg = (
                f"{base} has no manifest.json; a layer of a tree is read through "
                f"its store's `layer(id)`"
            )
            raise FileNotFoundError(msg)
        id = json.loads(found[0]).get("id")
        if id is None:
            msg = (
                f"{base}manifest.json carries no record id; a standalone "
                f"record's id is minted by `Workspace.write`, so write it again "
                f"through that"
            )
            raise ValueError(msg)
        schema = Schema.model_validate_json(found[0])
        return _record(DirectorySource(base, schema, self, UUID(id)), workspace=self)

    def write(self, source: LayerData | RecordLike, uri: str) -> Record:
        """Write `source` as a standalone record at `uri`, and read it back.

        A standalone record is written to a URI that does not exist yet. The
        directory carries its own manifest, written last, so one whose write
        failed reads as no record. The manifest carries a fresh id, so a
        record written again at `uri` is never read as the one before it.

        Raises
        ------
        FileExistsError
            If anything exists at `uri`: locally the path, even an empty
            directory; remotely any key under it.

        Notes
        -----
        - [writing a whole record](https://energy-models.github.io/datarecord/design/writing/)
        - [a standalone directory](https://energy-models.github.io/datarecord/design/writing/#a-standalone-directory)
        """
        base = _absolute(uri) + "/"
        if self.files(base).exists(base):
            msg = (
                f"{base} already exists; a standalone record is written to a URI "
                f"that does not exist yet"
            )
            raise FileExistsError(msg)
        data = layer_data(source, self.con)
        write_layer(data, base, self, manifest=_manifest(data.schema, uuid4()))
        return self.at(base)

    def close(self) -> None:
        """Close the database, and every thread's cursor with it."""
        self._db.close()


_process: Workspace | None = None
_process_lock = threading.Lock()


class Store:
    """One store location: its manifest, its revision tree, its layers.

    Holds no connection of its own: every read and write goes through its
    workspace, which several stores share.

    Attributes
    ----------
    uri
        The location: absolute, never empty.

    Notes
    -----
    - [the store](https://energy-models.github.io/datarecord/design/layers/#the-store)
    - [the tree beside the layers](https://energy-models.github.io/datarecord/design/layers/#the-tree-beside-the-layers)
    """

    def __init__(self, uri: str, workspace: Workspace) -> None:
        self.uri = uri
        self.workspace = workspace

    def __repr__(self) -> str:
        return f"Store({self.uri!r})"

    def __reduce__(self) -> tuple[Any, ...]:
        return _process_store, (self.uri,)

    @property
    def files(self) -> Files:
        return self.workspace.files(self.uri)

    # -- paths ---------------------------------------------------------------

    @property
    def manifest_uri(self) -> str:
        """The record's one schema, beside `layers/` rather than in any of them."""
        return f"{self.uri}/manifest.json"

    def layer_dir(self, id: UUID | str) -> str:
        """Revision `id`'s layer directory, with a trailing slash.

        Notes
        -----
        - [the record format](https://energy-models.github.io/datarecord/design/format/)
        """
        return f"{self.uri}/layers/{id}/"

    def resolved_dir(self, id: UUID | str) -> str:
        """Revision `id`'s node caches, under its layer where no glob reaches.

        Notes
        -----
        - [materialised node caches](https://energy-models.github.io/datarecord/design/layers/#materialised-node-caches)
        """
        return f"{self.layer_dir(id)}resolved/"

    def owner_map_uri(self, id: UUID | str, kind: str) -> str:
        """Where revision `id`'s `kind` owner map is materialised.

        Notes
        -----
        - [materialised node caches](https://energy-models.github.io/datarecord/design/layers/#materialised-node-caches)
        """
        return f"{self.resolved_dir(id)}owner_map/{kind}.parquet"

    def _revision_uri(self, id: UUID | str) -> str:
        return f"{self.uri}/revisions/{id}.json"

    # -- the tree ------------------------------------------------------------

    def root(self, source: LayerData | RecordLike) -> Revision:
        """A new root revision, with `source` as its layer.

        Raises
        ------
        ValueError
            If `source` fails validation, or its schema is incompatible with
            the store's; nothing is then reachable.

        Notes
        -----
        - [writing a whole record](https://energy-models.github.io/datarecord/design/writing/)
        - [a revision exists only by its file](https://energy-models.github.io/datarecord/design/writing/#a-revision-exists-only-by-its-file)
        """
        return self._write(source, None)

    def _write(self, source: LayerData | RecordLike, parent: UUID | None) -> Revision:
        """Write `source` as a new revision's layer: layer, manifest, revision file.

        The revision file is what makes the layer real, so it is written last;
        the manifest before it is widened only for a layer that exists.
        """
        id = uuid4()
        data = layer_data(source, self.workspace.con)
        parents = [] if parent is None else self.revision(parent).resolver.sources
        write_layer(data, self.layer_dir(id), self.workspace, parents=parents)
        reconcile_schema(data.schema, self)
        return self._create(parent, id)

    def _create(self, parent: UUID | None, id: UUID | None = None) -> Revision:
        """A revision's file, written create-only, and its cached row."""
        from datarecord.layered.revision import Revision

        id = id or uuid4()
        body = json.dumps({"id": str(id), "parent": parent and str(parent)})
        self.files.write_text(self._revision_uri(id), body, expect=Absent())
        self._cache([(id, parent)])
        return Revision(id=id, parent=parent, store=self)

    def _cache(self, rows: list[tuple[UUID, UUID | None]]) -> None:
        """Add `rows` to the workspace's `revisions` table.

        A row never changes once written, so two cursors adding one at once
        write the same thing. The loser fails with a duplicate key, at insert
        or at commit, once the winner's row is there; with a conflict before
        that, so a conflict is retried until the row is visible.
        """
        for id, parent in rows:
            while True:
                try:
                    self.workspace.con.execute(
                        "INSERT OR IGNORE INTO revisions VALUES (?, ?, ?)",
                        [self.uri, id, parent],
                    )
                except duckdb.TransactionException as e:
                    if "duplicate key" in str(e):
                        break
                    if "conflict" not in str(e).lower():
                        raise
                    time.sleep(0.001)
                    continue
                except duckdb.ConstraintException:
                    pass
                break

    def _read_revision(self, id: UUID) -> tuple[UUID, UUID | None] | None:
        found = self.files.read_text(self._revision_uri(id))
        if found is None:
            return None
        raw = json.loads(found[0])
        parent = raw["parent"]
        return UUID(raw["id"]), None if parent is None else UUID(parent)

    def _held(self, id: UUID) -> tuple[UUID, UUID | None] | None:
        return self.workspace.con.execute(
            "SELECT id, parent FROM revisions WHERE location = ? AND id = ?",
            [self.uri, id],
        ).fetchone()

    def revision(self, id: UUID) -> Revision:
        """Look one revision up, reading its file and any parents not yet held.

        Raises
        ------
        KeyError
            If this store has no revision `id`.

        Notes
        -----
        - [the tree beside the layers](https://energy-models.github.io/datarecord/design/layers/#the-tree-beside-the-layers)
        """
        from datarecord.layered.revision import Revision

        row = self._held(id)
        if row is None:
            read = []
            next_id: UUID | None = id
            while next_id is not None and self._held(next_id) is None:
                found = self._read_revision(next_id)
                if found is None:
                    msg = f"No revision {next_id} in {self.uri}"
                    raise KeyError(msg)
                read.append(found)
                next_id = found[1]
            self._cache(read)
            row = read[0]
        return Revision(id=row[0], parent=row[1], store=self)

    def revisions(self) -> list[Revision]:
        """Every revision in this store, unordered.

        One listing of `revisions/`, reading only the files the workspace does
        not already hold.

        Notes
        -----
        - [the tree beside the layers](https://energy-models.github.io/datarecord/design/layers/#the-tree-beside-the-layers)
        """
        from datarecord.layered.revision import Revision

        held = {
            row[0]
            for row in self.workspace.con.execute(
                "SELECT id FROM revisions WHERE location = ?", [self.uri]
            ).fetchall()
        }
        listed = {
            UUID(name.removesuffix(".json"))
            for name in self.files.list(f"{self.uri}/revisions/")
            if name.endswith(".json")
        }
        self._cache(
            [
                row
                for id in listed - held
                if (row := self._read_revision(id)) is not None
            ]
        )
        rows = self.workspace.con.execute(
            "SELECT id, parent FROM revisions WHERE location = ?", [self.uri]
        ).fetchall()
        return [Revision(id=id, parent=parent, store=self) for id, parent in rows]

    def layer(self, id: UUID) -> Record:
        """Revision `id`'s layer read alone, as the one layer it is.

        Under this store's schema: a layer holds only data. Not the revision's
        record - nothing beneath it is folded in.
        """
        return _record(
            DirectorySource(
                self.layer_dir(id),
                read_schema(self),
                self.workspace,
                # Not `id`, whose fold tables hold the whole ancestry's fold.
                uuid5(id, "layer"),
            ),
            workspace=self.workspace,
        )


def _absolute(uri: str) -> str:
    """`uri` without a trailing slash, a local path resolved against the cwd."""
    return Path(uri).resolve().as_posix() if "://" not in uri else uri.rstrip("/")


def _manifest(schema: Schema, id: UUID) -> str:
    """A standalone record's `manifest.json`: `schema`, with its `id` beside it.

    Beside the schema's keys rather than wrapping them, so the file still
    parses as the schema alone. A tree's manifest carries no id, its
    revisions naming its layers.

    Notes
    -----
    - [one schema per record](https://energy-models.github.io/datarecord/design/schema/#one-schema-per-record)
    """
    return json.dumps({"id": str(id), **json.loads(schema.model_dump_json())})


def _process_store(uri: str) -> Store:
    """`uri` as a store of the process workspace, which is what unpickling needs."""
    return Workspace.process().store(uri)


def _record(*sources: LayerSource, workspace: Workspace) -> Record:
    """A record folded over `sources`, root first.

    The last source's `layer_id` names the record and its `schema` is the
    record's - every source in one fold carries the same one.
    """
    return Record(
        Resolver(sources[-1].layer_id, list(sources), workspace, sources[-1].schema)
    )

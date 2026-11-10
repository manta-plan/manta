"""The record catalogue: datarecord stores under one root, opened on demand.

- **A record is a store** under the root (local folder, or `s3://bucket/…`):
  a folder `<id>/` with `revisions/`, and `<id>.json` beside it naming its
  revisions. Or a **plain record**, a folder with `manifest.json` and no
  revisions: one scenario, `inputs`. `<id>.labels.json`, also beside it, is
  optional: per revision a `name`, `description` and `kind`, and under
  `_store` the record's own `name` and `description`.
- **Listing** reads the root: names, sizes, dates. It's refreshed when a
  minute old, so a store uploaded to the root shows without a restart.
- **Opening** a store creates one catalog per scenario,
  `<record>__<scenario>` (`bel_pre_aggregated_perfect__patch`), each with the
  same schemas: datarecord's three (`record.py`) and `manta`. Run results get
  none for now.
- **A store opens when first asked for** (a project using it), and stays open
  for the life of the process. Opens are serialised, so a store opens once
  however many ask at the same time; one that fails is retried on the next
  ask. Replacing a store that's open needs a restart to show.
  Opening runs after the server's lockdown, which is why that lockdown leaves
  external access on (quack.py): datarecord's SQL reads Python objects by
  name, which DuckDB only resolves with it on.
- **Remote stores** are read where they are, through datarecord's remote
  files (boto3) and DuckDB httpfs. datarecord binds parquet files one at a
  time, a round trip each, so opening first reads every file's metadata in
  parallel into DuckDB's metadata caches (enabled in `configure`).
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
from datarecord import Workspace

from .manta_views import SCHEMA
from .record import create_views
from .scenarios import BASE_LABEL, BASE_NAME, Revision, open_revisions, read_json, register_scenarios

LISTING_TTL_S = 60
PREWARM_BATCH = 8
PREWARM_THREADS = 16


def configure(con: duckdb.DuckDBPyConnection) -> None:
    """Settings opening a store relies on; before the configuration is locked."""
    con.execute("SET GLOBAL enable_http_metadata_cache = true")
    con.execute("SET GLOBAL parquet_metadata_cache = true")


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    # An identifier can't start with a digit unquoted.
    return slug if slug[:1].isalpha() else f"r_{slug}"


@dataclass
class StoreFile:
    path: str
    size: int
    modified: datetime


@dataclass
class StoreSummary:
    id: str
    uri: str
    label: str
    description: str
    # Named revisions, from `<id>.json`; a plain record's one is `inputs`.
    revisions: list[str]
    files: list[StoreFile] = field(repr=False)
    # A record without revisions, rather than a store.
    plain: bool = False

    def as_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "revisions": self.revisions,
            "size": sum(f.size for f in self.files),
            "modified": max((f.modified for f in self.files), default=None),
            "files": len(self.files),
        }


@dataclass
class OpenStore:
    summary: StoreSummary
    revisions: list[Revision]
    default_scenario: str
    views: dict[str, list[str]]
    manifest: dict[str, Any]
    seconds: float
    # The relations behind every catalog's views, kept alive with them.
    relations: list[Any] = field(default_factory=list, repr=False)

    def as_json(self) -> dict[str, Any]:
        return {
            "id": self.summary.id,
            "label": self.summary.label,
            "description": self.summary.description,
            "defaultScenario": self.default_scenario,
            "revisions": [r.as_json() for r in self.revisions],
            "views": self.views,
            "manifest": self.manifest,
        }


class Catalogue:
    def __init__(self, ws: Workspace, root: str) -> None:
        self.ws = ws
        self.remote = "://" in root
        self.root = root.rstrip("/") if self.remote else Path(root).resolve().as_posix()
        if self.remote:
            # datarecord sets up boto3, httpfs and the S3 secret on first use;
            # before the configuration is locked, so here.
            ws.files(self.root)
        self._listing_lock = threading.Lock()
        # When the root was last listed (time.monotonic()).
        self._listed: float | None = None
        self._stores: dict[str, StoreSummary] = {}
        self.stores()
        self._open: dict[str, OpenStore] = {}
        self._opening = threading.Lock()
        # Why a store last failed to open, by id.
        self.failed: dict[str, str] = {}

    # Listing

    def _objects(self) -> list[StoreFile]:
        """Every file under the root, relative to it."""
        if not self.remote:
            found = []
            # os.walk, unlike rglob, follows a symlinked store.
            for folder, _, files in os.walk(self.root, followlinks=True):
                for name in sorted(files):
                    if name.startswith("."):
                        continue
                    path = Path(folder, name)
                    stat = path.stat()
                    found.append(StoreFile(path.relative_to(self.root).as_posix(), stat.st_size, datetime.fromtimestamp(stat.st_mtime, UTC)))
            return found
        import boto3
        from botocore.config import Config

        bucket, _, prefix = self.root.removeprefix("s3://").partition("/")
        prefix = f"{prefix}/" if prefix else ""
        style = "path" if os.environ.get("AWS_ENDPOINT_URL") else "auto"
        s3 = boto3.client("s3", config=Config(s3={"addressing_style": style}))
        found = []
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
            found += [StoreFile(o["Key"][len(prefix) :], o["Size"], o["LastModified"]) for o in page.get("Contents", [])]
        return found

    def _list(self) -> dict[str, StoreSummary]:
        objects = self._objects()
        names = {o.path for o in objects}
        by_store: dict[str, list[StoreFile]] = {}
        for o in objects:
            head, _, rest = o.path.partition("/")
            if rest:
                by_store.setdefault(head, []).append(StoreFile(rest, o.size, o.modified))
        stores = {}
        for id, files in sorted(by_store.items()):
            is_store = f"{id}.json" in names and any(f.path.startswith("revisions/") for f in files)
            plain = not is_store and any(f.path == "manifest.json" for f in files)
            if not is_store and not plain:
                continue
            labels = self._labels(id) if f"{id}.labels.json" in names else {}
            store = labels.get("_store", {})
            revisions = [BASE_NAME] if plain else list(read_json(self.ws, f"{self.root}/{id}.json"))
            stores[id] = StoreSummary(
                plain=plain,
                id=id,
                uri=f"{self.root}/{id}",
                label=store.get("name") or id,
                description=store.get("description", ""),
                revisions=revisions,
                files=files,
            )
        return stores

    def stores(self) -> dict[str, StoreSummary]:
        with self._listing_lock:
            if self._listed is None or time.monotonic() - self._listed > LISTING_TTL_S:
                self._stores = self._list()
                self._listed = time.monotonic()
            return self._stores

    def _labels(self, id: str) -> dict[str, dict[str, str]]:
        try:
            return read_json(self.ws, f"{self.root}/{id}.labels.json")
        except FileNotFoundError:
            return {}

    def get(self, id: str) -> StoreSummary:
        return self.stores()[id]

    # Opening

    def is_open(self, id: str) -> bool:
        return id in self._open

    def open(self, id: str) -> OpenStore:
        """The store, opened if it isn't yet. KeyError if there's no such
        store; RuntimeError if it fails to open."""
        if id in self._open:
            return self._open[id]
        summary = self.get(id)
        with self._opening:
            if id not in self._open:
                try:
                    self._open[id] = self._open_store(summary)
                except Exception as e:
                    self.failed[id] = f"{type(e).__name__}: {e}"
                    raise RuntimeError(self.failed[id]) from e
                self.failed.pop(id, None)
        return self._open[id]

    def _layers_used(self, summary: StoreSummary, names: dict[str, str]) -> set[str]:
        """The layers the named revisions read: each one's own and its
        ancestors'. A store also keeps earlier revisions' layers, often most
        of its files, which nothing named reads."""
        used: set[str] = set()
        for revision_id in names.values():
            while revision_id and revision_id not in used:
                used.add(revision_id)
                revision_id = read_json(self.ws, f"{summary.uri}/revisions/{revision_id}.json").get("parent")
        return used

    def _prewarm(self, summary: StoreSummary, names: dict[str, str]) -> None:
        """Read the metadata of every parquet file the record reads, in
        parallel, so datarecord's one-by-one binding finds it cached instead
        of making a round trip per file."""
        used = None if summary.plain else self._layers_used(summary, names)
        uris = [
            f"{summary.uri}/{f.path}"
            for f in summary.files
            if f.path.endswith(".parquet")
            and (used is None or not f.path.startswith("layers/") or f.path.split("/")[1] in used)
        ]
        batches = [uris[i : i + PREWARM_BATCH] for i in range(0, len(uris), PREWARM_BATCH)]

        def read(batch: list[str]) -> None:
            files = ", ".join("'" + uri.replace("'", "''") + "'" for uri in batch)
            # Workspace.con is a cursor per thread.
            self.ws.con.execute(f"SELECT count(*) FROM parquet_metadata([{files}])").fetchall()

        with ThreadPoolExecutor(PREWARM_THREADS) as pool:
            list(pool.map(read, batches))

    def _open_store(self, summary: StoreSummary) -> OpenStore:
        started = time.monotonic()
        labels = self._labels(summary.id)
        names = {} if summary.plain else read_json(self.ws, f"{self.root}/{summary.id}.json")
        if self.remote:
            self._prewarm(summary, names)
        con = self.ws.con
        if summary.plain:
            record = self.ws.at(summary.uri)
            label = labels.get(BASE_NAME, {})
            revisions = [
                Revision(
                    name=BASE_NAME,
                    id=str(record.schema.id),
                    parent=None,
                    kind="scenario",
                    label=label.get("name") or BASE_LABEL,
                    description=label.get("description", ""),
                    record=record,
                )
            ]
        else:
            revisions = open_revisions(self.ws, summary.uri, names, labels)
        scenarios = [r for r in revisions if r.kind == "scenario"]
        if not scenarios:
            raise ValueError(f"{summary.id} has no scenario revisions")
        keep: list[Any] = []
        views: dict[str, dict[str, list[str]]] = {}
        taken = {name for (name,) in con.execute("SELECT database_name FROM duckdb_databases()").fetchall()}
        attached: list[str] = []
        try:
            for r in scenarios:
                catalog = f"{_slug(summary.id)}__{_slug(r.name)}"
                while catalog in taken:
                    catalog += "_"
                taken.add(catalog)
                r.catalog = catalog
                con.execute(f"ATTACH ':memory:' AS {catalog}")
                attached.append(catalog)
                views[r.name] = create_views(con, r.record, catalog, keep)
            tables = register_scenarios(con, self.ws, summary.uri, revisions, attached)
        except Exception:
            # Half a record would shadow the next attempt's catalogs.
            for catalog in attached:
                con.execute(f"DETACH DATABASE IF EXISTS {catalog}")
            raise
        default = next((r for r in scenarios if r.parent is None), scenarios[0])
        served = views[default.name]
        served[SCHEMA] += tables
        return OpenStore(
            summary=summary,
            revisions=revisions,
            default_scenario=default.name,
            views=served,
            manifest=default.record.schema.model_dump(mode="json"),
            seconds=round(time.monotonic() - started, 1),
            relations=keep,
        )

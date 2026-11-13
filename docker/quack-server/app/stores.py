"""The record catalogue: datarecord stores under one root, opened on demand.

- **A record is a store** under the root (local folder, or `s3://bucket/…`):
  a folder `<id>/` with `layers/` and `store.json`, which has the record's
  `label` and `description` and names its revisions (`scenarios.py`). Or a
  **plain record**, a folder with `manifest.json` and no `layers/`: one
  scenario, `inputs`, shown by its folder name. Both are served as written:
  nothing is added to the folder.
- **Listing** reads the root: names, sizes, dates. It's refreshed when a
  minute old, so a store uploaded to the root shows without a restart.
- **Opening** a store creates one catalog per scenario,
  `<record>__<revision>` (`bel_pre_aggregated__patch`), each with the
  same schemas: datarecord's three (`record.py`, views over the revision
  registered in datarecord's own database) and `manta`. A run result
  gets its catalog, alike, when first asked for (`open_revision`): its views
  take several times as long to build as a scenario's, and a record can hold
  many. (A run result a scenario is built on opens with the scenarios: the
  scenario's changes are read against it.)
- **A store opens when first asked for** (a project using it), and stays open
  for the life of the process. Opens are serialised, so a store opens once
  however many ask at the same time; one that fails is retried on the next
  ask. Replacing a store that's open needs a restart to show.
  Opening runs after the server's lockdown (quack.py).
- **Remote stores are copied to local disk** when they open, then opened
  from there: datarecord reads a store's files one at a time, so from a
  bucket every file was a round trip (a minute to open a record or one of
  its run results on Cloud Run, against seconds from disk). Only the files
  the shown revisions read are copied, in parallel, into `cache` (a fresh
  temporary folder by default; on Cloud Run, memory). The bucket stays the
  source: the listing, `store.json` and the manifests are read from it.
"""

from __future__ import annotations

import logging
import os
import tempfile
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
from .scenarios import (
    BASE_LABEL,
    BASE_NAME,
    Layer,
    Revision,
    layer_manifest,
    named_layers,
    open_revisions,
    read_json,
    register_scenarios,
    slug,
)

log = logging.getLogger("uvicorn.error")

LISTING_TTL_S = 60
DOWNLOAD_THREADS = 16


def configure(con: duckdb.DuckDBPyConnection) -> None:
    """Settings opening a store relies on; before the configuration is locked."""
    con.execute("SET GLOBAL enable_http_metadata_cache = true")
    con.execute("SET GLOBAL parquet_metadata_cache = true")


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
    # Named revisions; none for a plain record, and None when `store.json`
    # and the manifests can't give them (the error is in Catalogue.failed).
    layers: list[Layer] | None
    files: list[StoreFile] = field(repr=False)
    # A record without revisions, rather than a store.
    plain: bool = False

    def as_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "revisions": [BASE_LABEL] if self.plain else [layer.label for layer in self.layers or []],
            "size": sum(f.size for f in self.files),
            "modified": max((f.modified for f in self.files), default=None),
            "files": len(self.files),
        }


@dataclass
class OpenStore:
    summary: StoreSummary
    revisions: list[Revision]
    default_scenario: str
    # The `manta` tables about the whole store, in every catalog.
    tables: list[str]
    views: dict[str, list[str]]
    manifest: dict[str, Any]
    seconds: float

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
    def __init__(self, ws: Workspace, root: str, cache: str | None = None) -> None:
        self.ws = ws
        self.remote = "://" in root
        self.root = root.rstrip("/") if self.remote else Path(root).resolve().as_posix()
        # Where remote stores are copied to (unused for a local root). A
        # layer's data file already there with the same size isn't copied
        # again.
        self.cache = Path(cache or tempfile.mkdtemp(prefix="manta-records-")) if self.remote else None
        if self.remote:
            # datarecord sets up boto3, httpfs and the S3 secret on first use;
            # before the configuration is locked, so here.
            ws.files(self.root)
        self._listing_lock = threading.Lock()
        # When the root was last listed (time.monotonic()).
        self._listed: float | None = None
        self._stores: dict[str, StoreSummary] = {}
        # Why a store last failed to open, or to be listed, by id.
        self.failed: dict[str, str] = {}
        self.stores()
        self._open: dict[str, OpenStore] = {}
        self._opening = threading.Lock()

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
        s3, bucket, prefix = self._s3()
        found = []
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
            found += [StoreFile(o["Key"][len(prefix) :], o["Size"], o["LastModified"]) for o in page.get("Contents", [])]
        return found

    def _s3(self) -> tuple[Any, str, str]:
        """A boto3 client for the root's bucket, the bucket, and the root's
        key prefix (with a trailing slash, or empty)."""
        import boto3
        from botocore.config import Config

        bucket, _, prefix = self.root.removeprefix("s3://").partition("/")
        prefix = f"{prefix}/" if prefix else ""
        style = "path" if os.environ.get("AWS_ENDPOINT_URL") else "auto"
        return boto3.client("s3", config=Config(s3={"addressing_style": style})), bucket, prefix

    def _list(self) -> dict[str, StoreSummary]:
        objects = self._objects()
        by_store: dict[str, list[StoreFile]] = {}
        for o in objects:
            head, _, rest = o.path.partition("/")
            if rest:
                by_store.setdefault(head, []).append(StoreFile(rest, o.size, o.modified))
        stores = {}
        for id, files in sorted(by_store.items()):
            # Not `.`/`..`: an id names a folder under the root and the cache.
            if id.startswith("."):
                continue
            is_store = any(f.path.startswith("layers/") for f in files)
            plain = not is_store and any(f.path == "manifest.json" for f in files)
            if not is_store and not plain:
                continue
            uri = f"{self.root}/{id}"
            label, description, layers = id, "", []
            try:
                if not plain:
                    named = read_json(self.ws, f"{uri}/store.json")
                    label, description = named["label"], named.get("description", "")
                    layers = named_layers(self.ws, uri, named["references"])
            except (OSError, LookupError, ValueError) as e:
                self.failed[id] = f"{type(e).__name__}: {e}"
                layers = None
            if layers is not None and id in self._stores and self._stores[id].layers is None:
                self.failed.pop(id)
            stores[id] = StoreSummary(plain=plain, id=id, uri=uri, label=label, description=description, layers=layers, files=files)
        return stores

    def stores(self) -> dict[str, StoreSummary]:
        with self._listing_lock:
            if self._listed is None or time.monotonic() - self._listed > LISTING_TTL_S:
                self._stores = self._list()
                self._listed = time.monotonic()
            return self._stores

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
        if summary.layers is None:
            raise RuntimeError(self.failed[id])
        with self._opening:
            if id not in self._open:
                try:
                    self._open[id] = self._open_store(summary)
                except Exception as e:
                    self.failed[id] = f"{type(e).__name__}: {e}"
                    raise RuntimeError(self.failed[id]) from e
                self.failed.pop(id, None)
        return self._open[id]

    def open_revision(self, id: str, name: str) -> OpenStore:
        """The store, with its revision `name` attached (a run result), if it
        isn't yet. KeyError if there's no such store or revision;
        RuntimeError if it fails to open."""
        store = self.open(id)
        revision = next((r for r in store.revisions if r.name == name), None)
        if revision is None or revision.catalog is None:
            raise KeyError(name)
        if revision.open:
            return store
        with self._opening:
            if not revision.open:
                started = time.monotonic()
                con = self.ws.con
                catalog = revision.catalog
                first = next(r.catalog for r in store.revisions if r.name == store.default_scenario)
                try:
                    con.execute(f"ATTACH ':memory:' AS {catalog}")
                    create_views(con, revision.record, catalog, self.ws.name)
                    for table in store.tables:
                        con.execute(f"CREATE OR REPLACE TABLE {catalog}.{SCHEMA}.{table} AS FROM {first}.{SCHEMA}.{table}")
                except Exception as e:
                    con.execute(f"DETACH DATABASE IF EXISTS {catalog}")
                    raise RuntimeError(f"{type(e).__name__}: {e}") from e
                revision.open = True
                log.info("Opened %s of record %s in %.1f s", name, id, time.monotonic() - started)
        return store

    def _download(self, summary: StoreSummary, revision_ids: list[str]) -> str:
        """Copy the store to `cache`, and return its local path: everything
        but its layers' data first (the layer manifests among it), then the
        layers the named revisions read (each one's own and its ancestors',
        from the copied manifests). A store also keeps earlier revisions'
        layers, often most of its files, which nothing shown reads."""
        started = time.monotonic()
        assert self.cache is not None
        local = self.cache / summary.id
        s3, bucket, prefix = self._s3()

        # A key with `..` would write outside the cache: refused before
        # anything is copied.
        root = local.resolve()
        for f in summary.files:
            if not (local / f.path).resolve().is_relative_to(root):
                raise ValueError(f"{summary.id}: {f.path!r} is outside the store")

        def fetch(files: list[StoreFile], reuse: bool) -> None:
            def one(f: StoreFile) -> None:
                target = local / f.path
                if reuse and target.is_file() and target.stat().st_size == f.size:
                    return
                target.parent.mkdir(parents=True, exist_ok=True)
                # Into place only once whole: a failed copy isn't taken for one.
                partial = target.with_name(f".{target.name}.partial")
                s3.download_file(bucket, f"{prefix}{summary.id}/{f.path}", str(partial))
                partial.replace(target)

            with ThreadPoolExecutor(DOWNLOAD_THREADS) as pool:
                list(pool.map(one, files))

        def is_data(f: StoreFile) -> bool:
            return f.path.startswith("layers/") and f.path.count("/") > 2

        # The small files (manifests, READMEs) are copied every time:
        # rewritten in place, they can keep their size. A layer's data is
        # never rewritten (a new revision is a new layer), so what's already
        # copied is kept.
        first = [f for f in summary.files if not is_data(f)]
        fetch(first, reuse=False)
        used: set[str] = set()
        for revision_id in revision_ids:
            while revision_id and revision_id not in used:
                used.add(revision_id)
                revision_id = layer_manifest(self.ws, local.as_posix(), revision_id).get("parent")
        layers = [f for f in summary.files if is_data(f) and f.path.split("/")[1] in used]
        fetch(layers, reuse=True)
        copied = first + layers
        log.info(
            "Copied record %s (%d files, %.1f MB) in %.1f s",
            summary.id, len(copied), sum(f.size for f in copied) / 1e6, time.monotonic() - started,
        )
        return local.as_posix()

    def _open_store(self, summary: StoreSummary) -> OpenStore:
        started = time.monotonic()
        uri = self._download(summary, [layer.id for layer in summary.layers]) if self.remote else summary.uri
        con = self.ws.con
        if summary.plain:
            record = self.ws.at(uri)
            id = str(record.revision_id or summary.id)
            revisions = [
                Revision(
                    name=BASE_NAME,
                    id=id,
                    parent=None,
                    kind="scenario",
                    label=BASE_LABEL,
                    description="",
                    written=[],
                    record=record,
                )
            ]
        else:
            revisions = open_revisions(self.ws, uri, summary.layers)
        scenarios = [r for r in revisions if r.kind == "scenario"]
        if not scenarios:
            raise ValueError(f"{summary.id} has no scenario revisions")
        # Opened now: the scenarios, and any run result a scenario is built
        # on (its changes are read against it). Other run results on demand.
        parents = {r.parent for r in scenarios}
        now = {r.name for r in revisions if r.kind == "scenario" or r.name in parents}
        views: dict[str, dict[str, list[str]]] = {}
        taken = {name for (name,) in con.execute("SELECT database_name FROM duckdb_databases()").fetchall()}
        attached: list[str] = []
        try:
            for r in revisions:
                catalog = f"{slug(summary.id)}__{slug(r.name)}"
                while catalog in taken:
                    catalog += "_"
                taken.add(catalog)
                r.catalog = catalog
                if r.name not in now:
                    continue
                con.execute(f"ATTACH ':memory:' AS {catalog}")
                attached.append(catalog)
                views[r.name] = create_views(con, r.record, catalog, self.ws.name)
            tables = register_scenarios(con, self.ws, uri, revisions, attached)
            for r in revisions:
                r.open = r.name in now
        except Exception:
            # Half a record would shadow the next attempt's catalogs.
            for catalog in attached:
                con.execute(f"DETACH DATABASE IF EXISTS {catalog}")
            raise
        default = next(r for r in scenarios if r.parent is None)
        served = views[default.name]
        served[SCHEMA] += tables
        return OpenStore(
            summary=summary,
            revisions=revisions,
            default_scenario=default.name,
            tables=tables,
            views=served,
            manifest=default.record.schema.model_dump(mode="json"),
            seconds=round(time.monotonic() - started, 1),
        )

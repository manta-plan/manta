# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""The session: one DuckDB connection with one datarecord workspace, served over Quack.

One thread owns the connection and every datarecord object on it. Each call
runs on that thread, so calls queue in the order they arrive.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Annotated, Any, Literal
from uuid import UUID

import duckdb
from datarecord import Revision, Workspace
from datarecord.store.manifest import Manifest
from pydantic import AfterValidator, BaseModel, TypeAdapter

from datarecord_session import guard
from datarecord_session.config import Settings
from datarecord_session.packs import Pack, create_pack, quote
from datarecord_session.static import create_static_views

CATALOG = "manta"

_REGISTRATION_NAME = re.compile(r"[a-z0-9][a-z0-9_-]{0,62}")
_RESERVED = {"main", "information_schema", "pg_catalog"}
_STORE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_MANIFEST = TypeAdapter(Manifest)


def _registration_name(name: str) -> str:
    if not _REGISTRATION_NAME.fullmatch(name) or name in _RESERVED:
        raise ValueError(
            f"{name!r} is no registration name: {_REGISTRATION_NAME.pattern}, "
            f"not one of {sorted(_RESERVED)}"
        )
    return name


def _store_name(name: str) -> str:
    if not _STORE_NAME.fullmatch(name) or ".." in name:
        raise ValueError(f"{name!r} is no store name: a name under the root, without '/' or '..'")
    return name


RegistrationName = Annotated[str, AfterValidator(_registration_name)]
StoreName = Annotated[str, AfterValidator(_store_name)]


class ViewRegistration(BaseModel, frozen=True):
    kind: Literal["view"]
    store: StoreName
    revision: UUID
    packs: frozenset[Pack] = frozenset()


class NotFoundError(Exception):
    pass


@dataclass(frozen=True)
class Registration:
    request: ViewRegistration
    prefix: str
    manifest: dict[str, Any]
    views: dict[str, list[str]]


def prefix_of(name: str) -> str:
    return f"{CATALOG}.{quote(name)}"


class Session:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._thread = ThreadPoolExecutor(max_workers=1, thread_name_prefix="datarecord")
        self._con: duckdb.DuckDBPyConnection
        self._workspace: Workspace
        self._uri: str
        self._registrations: dict[str, Registration] = {}

    async def call[T](self, fn: Callable[..., T], *args: Any) -> T:
        return await asyncio.wrap_future(self._thread.submit(fn, *args))

    def start(self) -> None:
        settings = self.settings
        self._con = duckdb.connect()
        self._workspace = Workspace(con=self._con, name=CATALOG, credentials=settings.credentials)
        self._workspace.files(settings.store_root)
        self._uri = guard.serve(
            self._con, settings.quack_host, settings.quack_port, settings.quack_token
        )

    def stop(self) -> None:
        guard.stop(self._con, self._uri)
        self._workspace.close()
        self._con.close()
        self._thread.shutdown(wait=False)

    def names(self) -> list[str]:
        return sorted(self._registrations)

    def get(self, name: str) -> Registration:
        if name not in self._registrations:
            raise NotFoundError(f"{name} is not registered")
        return self._registrations[name]

    def register(self, name: str, request: ViewRegistration) -> Registration:
        existing = self._registrations.get(name)
        if existing is not None and existing.request == request:
            return existing
        store = self._workspace.store(self.settings.store_uri(request.store))
        try:
            revision = store.revision(request.revision)
        except KeyError as e:
            raise NotFoundError(f"{request.store} has no revision {request.revision}") from e
        if existing is not None:
            self.unregister(name)
        revision.record.register(name)
        try:
            registration = self._build(name, request, revision)
        except BaseException:
            self._workspace.unregister(name)
            raise
        self._registrations[name] = registration
        return registration

    def _build(self, name: str, request: ViewRegistration, revision: Revision) -> Registration:
        con = self._workspace.con
        prefix = prefix_of(name)
        record = revision.record
        views = {
            "dimensions": sorted(record.dimensions),
            "properties": sorted(record.properties),
            "attributes": sorted(record.attributes),
            "static": create_static_views(con, prefix, record.schema),
        }
        for pack in sorted(request.packs):
            views[pack] = create_pack(con, prefix, pack, record.schema)
        manifest = _MANIFEST.dump_python(revision.manifest, mode="json")
        return Registration(request=request, prefix=prefix, manifest=manifest, views=views)

    def unregister(self, name: str) -> None:
        self.get(name)
        self._workspace.unregister(name)
        del self._registrations[name]

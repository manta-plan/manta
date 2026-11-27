# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""A project folder with two small PyPSA-Eur-like stores, and a session serving it in a subprocess.

The stores are written with the pinned datarecord itself, as no exported store
opens with it. Their root revisions are empty and `base` holds the data. A
connection is a port of an entity, attached to the bus in its `bus` property,
as datarecord 0.1.0a2 stores write them. The stores differ only in their
snapshot: a plain one, or one over period and timestep. The session runs as its
own process, as in its image, so a native Quack client in this process reaches
it over the network.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import duckdb
import httpx
import pytest
from datarecord import (
    AttributeSpec,
    Dimension,
    PropertySpec,
    Revision,
    Schema,
    WorkingRecord,
    Workspace,
)

STORE = "europe"
QUACK_TOKEN = "quack-token"
API_SECRET = "api-secret"

PERIODS = "periods"


@dataclass(frozen=True)
class Snapshots:
    dimensions: dict[str, Dimension]
    labels: dict[str, list[Any]]
    at: dict[str, Any]


SNAPSHOTS = {
    STORE: Snapshots(
        dimensions={"snapshot": Dimension(dtype="int")},
        labels={"snapshot": [0, 1]},
        at={"snapshot": [0, 1]},
    ),
    PERIODS: Snapshots(
        dimensions={
            "period": Dimension(dtype="int"),
            "timestep": Dimension(dtype="int"),
            "snapshot": Dimension(over=["period", "timestep"]),
        },
        labels={
            "period": [2030],
            "timestep": [0, 1],
            "snapshot": [{"period": 2030, "timestep": t} for t in (0, 1)],
        },
        at={"period": 2030, "timestep": [0, 1]},
    ),
}


def _schema(snapshots: Snapshots) -> Schema:
    return Schema(
        dimensions={
            "entity": Dimension(dtype="str"),
            "ctype": Dimension(one_of=["Bus", "Generator", "Line", "Link", "Load"]),
            "bus": Dimension(dtype="str"),
            "port": Dimension(dtype="int"),
            **snapshots.dimensions,
            "connection": Dimension(over=["entity", "port"]),
        },
        properties={
            "entity": {"ctype": PropertySpec(one_of="ctype"), "carrier": PropertySpec(dtype="str")},
            "bus": {
                "carrier": PropertySpec(dtype="str"),
                "location": PropertySpec(dtype="str"),
                "x": PropertySpec(dtype="float"),
                "y": PropertySpec(dtype="float"),
            },
            "connection": {"bus": PropertySpec(one_of="bus")},
        },
        attributes={
            "p_nom": AttributeSpec(dtype="float", dims={"entity"}, default=0.0),
            "p_max_pu": AttributeSpec(dtype="float", dims={"entity", "snapshot"}, default=1.0),
            "p_nom_extendable": AttributeSpec(dtype="bool", dims={"entity"}, default=False),
            "efficiency": AttributeSpec(dtype="float", dims={"connection"}, default=1.0),
            "busmap_1": AttributeSpec(dtype="str", dims={"bus"}, default=""),
        },
        partial={"entity", "bus", "port", "connection"},
    )


@dataclass(frozen=True)
class Empty:
    schema: Schema
    con: duckdb.DuckDBPyConnection
    dimensions: dict = field(default_factory=dict)
    properties: dict = field(default_factory=dict)
    attributes: dict = field(default_factory=dict)

    def flags(self, **categories: object) -> dict:
        return {}


@dataclass(frozen=True)
class Revisions:
    root: str
    base: str


def _base(root: Revision, snapshots: Snapshots) -> Revision:
    with WorkingRecord(root.record) as w:
        w.add(
            "bus",
            ["DE0", "DE1", "EU gas"],
            carrier=["AC", "AC", "gas"],
            location=["DE0", "DE1", "EU"],
            x=[10.0, 11.0, 0.0],
            y=[50.0, 51.0, 0.0],
        )
        w.add(
            "entity",
            ["wind", "line", "load", "chp"],
            ctype=["Generator", "Line", "Load", "Link"],
            carrier=["wind", "AC", "AC", "gas"],
        )
        w.add("port", [0, 1, 2])
        ends = [("wind", 0, "DE0"), ("line", 0, "DE0"), ("line", 1, "DE1"), ("load", 0, "DE1")]
        ends += [("chp", 0, "EU gas"), ("chp", 1, "DE0"), ("chp", 2, "DE1")]
        ports = [{"entity": e, "port": p} for e, p, _ in ends]
        w.add("connection", ports, bus=[b for _, _, b in ends])
        for dim, labels in snapshots.labels.items():
            w.add(dim, labels)
        w.set("p_nom", [100.0, 50.0], entity=["wind", "line"])
        w.set("p_max_pu", [0.3, 0.8], entity="wind", **snapshots.at)
        w.set("p_max_pu", 0.9, entity="line")
        w.set("p_nom_extendable", True, entity="wind")
        w.set("efficiency", [0.98, 0.4], entity=["line", "chp"], port=1)
        w.set("busmap_1", ["Z1", "Z2"], bus=["DE0", "DE1"])
        return root.store.commit(w)


@pytest.fixture(scope="session")
def project(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, Revisions]]:
    folder = tmp_path_factory.mktemp("project")
    ws = Workspace()
    stores = {}
    for name, snapshots in SNAPSHOTS.items():
        empty = Empty(_schema(snapshots), ws.con)
        root = ws.store(str(folder / name)).commit(empty, parent=None)
        stores[name] = Revisions(root=str(root.id), base=str(_base(root, snapshots).id))
    ws.close()
    return folder, stores


@pytest.fixture(scope="session")
def stores(project: tuple[Path, dict[str, Revisions]]) -> dict[str, Revisions]:
    return project[1]


@pytest.fixture(scope="session")
def revisions(stores: dict[str, Revisions]) -> Revisions:
    return stores[STORE]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("localhost", 0))
        return s.getsockname()[1]


def _wait_for(api: httpx.Client, process: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        assert process.poll() is None, "the session exited during start-up"
        try:
            api.get("/health").raise_for_status()
            return
        except httpx.TransportError:
            time.sleep(0.2)
    raise TimeoutError("the session did not report healthy within 60 s")


@dataclass(frozen=True)
class Endpoints:
    api: str
    quack_port: int


@pytest.fixture(scope="session")
def endpoints(project: tuple[Path, dict[str, Revisions]]) -> Iterator[Endpoints]:
    api_port, quack_port = _free_port(), _free_port()
    env = {
        **os.environ,
        "DATARECORD_SESSION_STORE_ROOT": str(project[0]),
        "DATARECORD_SESSION_QUACK_TOKEN": QUACK_TOKEN,
        "DATARECORD_SESSION_API_SECRET": API_SECRET,
        "DATARECORD_SESSION_QUACK_HOST": "localhost",
        "DATARECORD_SESSION_QUACK_PORT": str(quack_port),
        "DATARECORD_SESSION_API_HOST": "localhost",
        "DATARECORD_SESSION_API_PORT": str(api_port),
    }
    script = Path(sys.executable).with_name("datarecord-session")
    process = subprocess.Popen([script], env=env)  # noqa: S603
    endpoints = Endpoints(api=f"http://localhost:{api_port}", quack_port=quack_port)
    try:
        with httpx.Client(base_url=endpoints.api, headers=_auth(API_SECRET)) as api:
            _wait_for(api, process)
        yield endpoints
    finally:
        process.terminate()
        process.wait(timeout=30)


def _auth(secret: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {secret}"}


@pytest.fixture
def api(endpoints: Endpoints) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=endpoints.api, headers=_auth(API_SECRET)) as client:
        yield client


Register = Callable[..., httpx.Response]


@pytest.fixture
def register(api: httpx.Client) -> Iterator[Register]:
    def put(name: str, revision: str, /, **overrides: Any) -> httpx.Response:
        body = {"kind": "view", "store": STORE, "revision": revision, "packs": [], **overrides}
        return api.put(f"/registrations/{name}", json=body)

    yield put
    for name in api.get("/registrations").json():
        api.delete(f"/registrations/{name}").raise_for_status()


@pytest.fixture
def registered(register: Register, revisions: Revisions) -> str:
    response = register("base", revisions.base, packs=["pypsa-eur"])
    response.raise_for_status()
    return response.json()["prefix"]


def attach(port: int, token: str) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.load_extension("httpfs")
    con.load_extension("quack")
    con.execute(f"ATTACH 'quack:localhost:{port}' AS r (TOKEN '{token}')")
    return con


@pytest.fixture(scope="session")
def quack(endpoints: Endpoints) -> Iterator[duckdb.DuckDBPyConnection]:
    con = attach(endpoints.quack_port, QUACK_TOKEN)
    yield con
    con.close()


def remote(quack: duckdb.DuckDBPyConnection, sql: str) -> list[tuple]:
    return quack.execute("FROM quack_query_by_name('r', ?)", [sql]).fetchall()

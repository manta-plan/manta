"""FastAPI front for the record server.

Quack listens on localhost only. This app is what the browser talks to:

- `POST /quack` is relayed byte for byte to Quack, so one public port serves
  both (Cloud Run exposes exactly one) and CORS can be answered here (Quack
  sends no CORS headers),
- `/api/*` is for everything that isn't a read query; it takes the same token,
  as `Authorization: Bearer …`,
- `/` serves an explorer page that attaches the record from DuckDB-Wasm.
"""

from __future__ import annotations

import logging
import os
import secrets
import threading
from contextlib import asynccontextmanager
from pathlib import Path

import duckdb
import httpx
from datarecord import Workspace
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

from . import quack
from .stores import Catalogue, configure
from .scenarios import BASE_NAME, layer_manifest, read_json

log = logging.getLogger("uvicorn.error")

SERVER_ROOT = Path(__file__).resolve().parents[1]
# Where the records are: a local folder, or `s3://bucket/prefix` (datarecord's
# remote stores; the AWS_* environment holds the endpoint and key). Every
# store under it is a record.
RECORDS_ROOT = os.environ.get("RECORDS_ROOT", str(SERVER_ROOT / "data/records"))
# Where an `s3://` root's records are copied to when they open; default, a
# fresh temporary folder. Set it to keep the copies across restarts.
RECORDS_CACHE = os.environ.get("RECORDS_CACHE") or None
# What a project that names no record opens; default: the first store.
DEFAULT_RECORD = os.environ.get("DEFAULT_RECORD")
QUACK_PORT = int(os.environ.get("QUACK_PORT", "9494"))
QUACK_TOKEN = os.environ.get("QUACK_TOKEN") or secrets.token_urlsafe(24)
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")


def default_record(catalogue: Catalogue) -> str | None:
    stores = catalogue.stores()
    return DEFAULT_RECORD if DEFAULT_RECORD in stores else next(iter(stores), None)


def open_in_background(catalogue: Catalogue, id: str) -> None:
    """Open the default record without holding up the start: most projects
    use it, so its first visitor needn't wait for it."""

    def run() -> None:
        try:
            log.info("Opened record %s in %s s", id, catalogue.open(id).seconds)
        except Exception:
            log.exception("Record %s failed to open", id)

    threading.Thread(target=run, name=f"open-{id}", daemon=True).start()


@asynccontextmanager
async def lifespan(app: FastAPI):
    ws = Workspace()
    configure(ws.con)
    catalogue = Catalogue(ws, RECORDS_ROOT, RECORDS_CACHE)
    stores = catalogue.stores()
    app.state.catalogue = catalogue
    uri = quack.serve(ws.con, QUACK_PORT, QUACK_TOKEN)
    app.state.relay = httpx.AsyncClient(
        base_url=f"http://localhost:{QUACK_PORT}", timeout=None
    )
    log.info("Serving %d record(s) from %s over %s", len(stores), catalogue.root, uri)
    if "QUACK_TOKEN" not in os.environ:
        log.info("Explorer: http://localhost:8000/?token=%s", QUACK_TOKEN)
    if default := default_record(catalogue):
        open_in_background(catalogue, default)
    try:
        yield
    finally:
        await app.state.relay.aclose()
        quack.stop(ws.con, uri)
        try:
            ws.close()
        except duckdb.Error as e:
            # A query or a background open may still hold the connection; the
            # process is exiting, so it goes with it.
            log.warning("Closing the database at shutdown: %s", e)


app = FastAPI(title="Manta record server", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def require_token(authorization: str = Header(default="")) -> None:
    expected = f"Bearer {QUACK_TOKEN}".encode()
    if not secrets.compare_digest(authorization.encode(), expected):
        raise HTTPException(status_code=401, detail="Invalid token")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def catalogue_of(request: Request) -> Catalogue:
    return request.app.state.catalogue


@app.get("/api/records", dependencies=[Depends(require_token)])
def records(request: Request) -> dict:
    """The catalogue: every record under the root, without opening any."""
    catalogue = catalogue_of(request)
    return {
        "records": [
            {**store.as_json(), "open": catalogue.is_open(store.id), "error": catalogue.failed.get(store.id)}
            for store in catalogue.stores().values()
        ],
        "default": default_record(catalogue),
    }


@app.post("/api/records/{id}/open", dependencies=[Depends(require_token)])
def open_record(id: str, request: Request, revision: str | None = None) -> dict:
    """Open a record if it isn't yet, then what a client needs to query it: its
    revisions' catalogs, views and manifest. The first open of a record takes
    a while (seconds to tens of seconds for a bucket); later ones answer at
    once. `?revision=` also attaches that run result's catalog, which opening
    the record leaves out (a few seconds more, the first time). A plain `def`:
    FastAPI runs it in a worker thread.

    A client that attached before the record opened doesn't see its catalogs
    as `r.<catalog>`: Quack's client reads the catalog list when it attaches.
    Queries through quack_query_by_name see them."""
    catalogue = catalogue_of(request)
    try:
        opened = catalogue.open_revision(id, revision) if revision else catalogue.open(id)
    except KeyError:
        what = f"revision {revision!r} in record {id!r}" if revision and catalogue.is_open(id) else f"record {id!r}"
        raise HTTPException(status_code=404, detail=f"No {what}") from None
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=f"{f'{revision!r} of record' if revision else 'Record'} {id!r} failed to open: {e}") from None
    return opened.as_json()


@app.get("/api/records/{id}/files", dependencies=[Depends(require_token)])
def record_files(id: str, request: Request) -> dict:
    """A record as stored: every file, the revision names (`revisions.json`),
    and each layer's manifest (`layers/<id>/manifest.json`; a plain record's
    `manifest.json` under the id ""). The schema, which each manifest repeats
    whole, is sent once: the default scenario's. Names and sizes only; the
    data is read through Quack."""
    catalogue = catalogue_of(request)
    try:
        store = catalogue.get(id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"No record {id!r}") from None
    if store.plain:
        names = None
        layers = {"": read_json(catalogue.ws, f"{store.uri}/manifest.json")}
        default = ""
    else:
        names = read_json(catalogue.ws, f"{store.uri}/revisions.json")
        ids = sorted({f.path.split("/")[1] for f in store.files if f.path.startswith("layers/") and f.path.endswith("/manifest.json")})
        layers = {layer: layer_manifest(catalogue.ws, store.uri, layer) for layer in ids}
        default = names.get(BASE_NAME) or next(iter(names.values()))
    schema = layers[default]["schema"]
    return {
        "name": store.id,
        "revisions": names,
        "schema": schema,
        "layers": {layer: {k: v for k, v in manifest.items() if k != "schema"} for layer, manifest in layers.items()},
        "files": [{"path": f.path, "size": f.size} for f in store.files],
    }


@app.post("/quack")
async def relay_quack(request: Request) -> StreamingResponse:
    relay: httpx.AsyncClient = request.app.state.relay
    upstream = await relay.send(
        relay.build_request(
            "POST",
            "/quack",
            content=await request.body(),
            headers={
                "content-type": request.headers.get(
                    "content-type", "application/octet-stream"
                )
            },
        ),
        stream=True,
    )
    return StreamingResponse(
        upstream.aiter_raw(),
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type"),
        background=BackgroundTask(upstream.aclose),
    )


app.mount(
    "/", StaticFiles(directory=Path(__file__).parent.parent / "static", html=True)
)

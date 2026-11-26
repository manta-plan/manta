<!--
SPDX-FileCopyrightText: 2026 Manta contributors

SPDX-License-Identifier: CC-BY-4.0
-->

# Record server (temporary)

> **Temporary.** Copied from baby-manta's `server/` (manta-plan/manta#223) so the Build / Inspect / Analyse tabs can be ported to the frontend before datarecord is integrated into the backend. It runs as the `quack-server` service of `docker/compose-dev-services.yaml` (host port `QUACK_SERVER_PORT`, 8010; token `QUACK_TOKEN`, `devtoken`; both set in `backend/.env`; records mounted read-only from `./data/records`). Remove it once the backend serves Quack itself. The Cloud Run deployment files were not copied. Below is the original README.

## Running in the dev stack

1. **Records.** By default the server reads the example stores from the dev object store (SeaweedFS, `s3://${S3_BUCKET}/example-data`), where the backend puts them at startup when `EXAMPLE_DATA_SEED=true` (see `backend/README.md`, "Example data"). Nothing to copy by hand: start the backend once (with network access), and the stores appear in the server's listing within a minute. Until then it serves no records (and logs `Bucket 'manta' doesn't exist yet` if the backend hasn't created the bucket either). A record is copied to local disk when it first opens; the `quack-cache` volume keeps the copies across restarts.

   To serve a local folder instead (stores in `docker/quack-server/data/records`, git-ignored; a store is a folder with `layers/` and `revisions.json`, optionally with `<store>.labels.json` beside it), set `QUACK_RECORDS_ROOT=/srv/data/records`, for example in your shell or `backend/.env`:

   ```sh
   mkdir -p docker/quack-server/data/records
   cp -R <baby-manta>/server/data/records/. docker/quack-server/data/records/
   ```

2. **Start it** from `docker/`:

   ```sh
   docker compose --env-file ../backend/.env -f compose-dev-services.yaml --profile temporary-quack-setup up --build quack-server
   ```

   The service is in the opt-in compose profile `temporary-quack-setup`, so a plain `up` (and the integration tests) don't build or start it. To run the whole stack with it, drop the service name: `… --profile temporary-quack-setup up --build`.

   Rebuild with `--build` after changing the app.

3. **Check it.** The explorer is at <http://localhost:8010/?token=devtoken>, and:

   ```sh
   curl -H 'Authorization: Bearer devtoken' localhost:8010/api/records
   ```

| Compose env | Value (`backend/.env` unless noted) |
|---|---|
| `QUACK_SERVER_PORT` | `8010` (host port; not 8000, which the backend uses) |
| `QUACK_TOKEN` | `devtoken` |
| `QUACK_RECORDS_ROOT` | `s3://${S3_BUCKET}/example-data` (compose default): the backend's example stores in SeaweedFS. `/srv/data/records` serves the local folder |
| `QUACK_DEFAULT_RECORD` | `BEL-pre-aggregated-incl-patches-incl-results` (compose default): what a project that names no record opens. Not the first store (`BEL-full-res`, the biggest) |

The server reaches SeaweedFS with the backend's own `S3_ACCESS_KEY`, `S3_SECRET_KEY` and `MANTA_JOB_S3_ENDPOINT` from `backend/.env`.

To run without Docker, see "Run" below.

Serves [datarecord](https://github.com/energy-models/datarecord) stores to DuckDB-Wasm in the browser over DuckDB's Quack protocol: every store under one root (a local folder, or a bucket through datarecord's `s3://` remote stores).

```text
browser (DuckDB-Wasm) ──ATTACH 'quack:host:port'──▶ FastAPI :8010 ──POST /quack relay──▶ Quack :9494 (localhost only)
                                                        │                                     │
                                                        └── /api/*                            └── in-process DuckDB: one view per record relation
```

- **The record catalogue** (`app/stores.py`): every datarecord store under `RECORDS_ROOT` is a record, listed by `GET /api/records`. A store is a folder with `layers/` and `revisions.json`, which names its revisions. A plain record (a folder with `manifest.json` and no revisions) is listed too, with one scenario, `inputs`.
- **A record opens on first use**: when a project (or the explorer) first asks for it, then stays open while the server runs. The default record opens in the background at start. The listing refreshes every minute, so a store uploaded to the root shows without a restart; replacing a store that's open needs one.
- **datarecord resolves each scenario.** `app/record.py` has the revision register its views (`datarecord.<catalog>.attributes.p_nom`), and puts a view over each in the scenario's catalog, in the schemas `dims`, `properties` and `attributes`, for example `attributes.p_nom`. The browser never sees layers or parquet files.
- **One catalog per record and scenario:** `<record>__<scenario>`, e.g. `bel_pre_aggregated_incl_patches_incl_results__patch.attributes.p_nom`, all with the same schemas, views and `manta` tables. `manta.revisions.catalog` names them. A client picks a record and scenario by naming the catalog, so the server stays shared and stateless. Run results get a catalog too, attached when first asked for. `docs/views-design.md` has the details.
- **FastAPI is in front because:**
  - Cloud Run exposes only one port.
  - Quack sends no CORS headers.
  - Writes (edits, scenarios as child revisions, solves) will become `/api/*` endpoints instead of raw SQL.
- **Read-only access is enforced by an authorization macro** (`app/quack.py`). See "Lockdown" below.
- **The app's own views live in a `manta` schema** (`app/manta_views.py`): plain SQL over the record views, holding what the app assumes about a record.
  - `bus_location`, `locations`: buses grouped into locations (a bus with an empty `location`, as in PyPSA-Earth, is its own); `EU`, PyPSA-Eur's copper plate, is virtual.
  - `location_zones`: zones from the `busmap_*` attributes, if the record has any.
  - `branches`: input → output pairs of lines, links and transformers, scoped `within`, `between` or `virtual`.
  - `attached`, `regions`: generators/loads/stores at their bus; region polygons as WKT (Shape entities, or the buses' `shape_onshore`/`shape_offshore`).
  - `revisions` and `scenario_changes` (tables built at start, `app/scenarios.py`): a store's named revisions as scenarios and run results, and per scenario each changed value against its parent. Names and descriptions come from `<store>.labels.json` beside the store, if present.
  - `attribute_summary` (a table built at start) and `ctype_attributes`: each attribute's constant value and series rows per entity, bus, carrier, …, so one query fills an item's attribute panel.
  - `uv run pytest` checks them against the sample record.
- **Remote stores** are read where they are. datarecord binds parquet files one by one, a round trip each, so opening a remote store first reads every file's metadata in parallel into DuckDB's caches.

## Run

Needs `uv`; datarecord comes from GitHub (see Findings).

```sh
cd server
uv sync
QUACK_TOKEN=devtoken uv run uvicorn app.main:app --port 8010
```

Then open <http://localhost:8010/?token=devtoken>. Without `QUACK_TOKEN`, a random token is generated and the log prints the explorer's URL. Quack wants a token of at least 4 characters.

`uv run --env-file .env uvicorn app.main:app --port 8010 --reload --reload-dir app` reads `QUACK_TOKEN` (the app's `VITE_RECORD_TOKEN`) and the bucket key from `server/.env`. The records stay local (`data/records`) unless `RECORDS_ROOT=s3://manta-records` is set too; then each record is copied from the bucket when it opens (`RECORDS_CACHE=…` keeps the copies across restarts).

The explorer page (`static/index.html`, Alpine.js, the app's theme tokens) picks a record in its header (`?record=` keeps it) and has two tabs:

- **Files:** the record as stored, from `GET /api/records/{id}/files` (names, sizes, the revision names and each layer's manifest; no data). Clicking a file or folder under `layers/<id>/` shows what that layer's manifest and the schema say about it, and links to the views it backs in its revision's catalog, once that is attached.
- **Views:** the views the browser sees through ATTACH, as scenario → schema → view → column, base case first. Clicking a view previews 200 rows and counts it on the server. The editor runs any SQL in DuckDB-Wasm, against `r.<catalog>.<schema>.<view>` (`r.bel_pre_aggregated_perfect__patch.attributes.p_nom`).

**API.** `/api/*` takes the same token as Quack, as `Authorization: Bearer …`.

| Endpoint | |
|---|---|
| `GET /api/records` | the catalogue: per record its `id`, `label`, `description`, named `revisions`, `size`, `modified`, `files`, and `open`/`error`; and the `default` record |
| `POST /api/records/{id}/open` | what a client needs to query a record: `revisions` (with their catalogs), `defaultScenario`, `views`, `manifest`. Opens the record if it isn't yet: seconds for the first ask (about 17 s from the bucket on Cloud Run), at once after. `?revision=<name>` also attaches that run result (a few seconds, the first time); each revision says whether it's `open`, and a run result lists its `results` attributes |
| `GET /api/records/{id}/files` | the explorer's Files tab |

| Env | Default |
|---|---|
| `RECORDS_ROOT` | `data/records`: a folder of stores, or `s3://bucket[/prefix]` |
| `RECORDS_CACHE` | a fresh temporary folder: where an `s3://` root's records are copied to when they open. A layer's data file already there with the same size isn't copied again; the small files (`revisions.json`, manifests) are, every time |
| `DEFAULT_RECORD` | the first store: what a project that names no record opens |
| `AWS_ENDPOINT_URL`, `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | for an `s3://` root. For GCS: `https://storage.googleapis.com`, `auto`, and a bucket-reader HMAC key (deployment.md). `uv run --env-file .env …` reads them from `server/.env` |
| (file) `<store>.labels.json` | optional, beside the store's folder: per revision name a `name` and `description` to show, and `kind` (`scenario` or `result`) where the guess is wrong; under `_store`, the record's own `name` and `description` |
| `RECORD_TEST_ROOT` | tests only: also run the remote test against this `s3://` root |

Local records live in `data/records` (git-ignored, never in the image), as in the bucket (`gs://manta-records`): the modeller's 11 November combined store, copied as shipped (from the modeller's `11-november-data` folder, baby-manta's `.idea/11-november-data`, or from the bucket). Its `inputs` revision is the base case and `patch` a stress test, each solved three ways (`perfect`, `myopic`, `overnight2050`, and `patch/…`). The tests use it.

```sh
mkdir -p data/records
# The modeller's 11 November store, or from the bucket:
cp -R <path-to>/11-november-data/BEL-pre-aggregated-incl-patches-incl-results data/records/
# gcloud storage cp -r gs://manta-records/BEL-pre-aggregated-incl-patches-incl-results data/records/
```

Without a labels file, the Scenarios panel shows each revision by its name in `revisions.json` (`patch/myopic`), `inputs` as "Base case", and the record by its folder name. `<store>.labels.json` beside the folder, optional, gives nicer names without touching the store:

```json
{
  "_store": { "name": "Belgium, 5 regions: all run types", "description": "…" },
  "patch": { "name": "Wind and solar stress test", "description": "Offshore wind capital cost ×1.3, onshore wind potential ×0.5, solar availability ×0.9" },
  "patch/myopic": { "name": "Wind and solar stress test, myopic" }
}
```
| `QUACK_TOKEN` | random |
| `QUACK_PORT` | `9494` (internal) |
| `CORS_ORIGINS` | `http://localhost:5173` |

From Python:

```python
import duckdb
con = duckdb.connect()
con.sql("LOAD quack")
con.sql("ATTACH 'quack:localhost:8010' AS r (TOKEN 'devtoken')")
con.sql("SELECT ctype, count(*) FROM r.properties.entity GROUP BY ALL").show()
```

## Findings (DuckDB 2.0.0, 2026-10-24)

- **datarecord** comes from `energy-models/datarecord` `main`, pinned to commit `8889d62` (2026-11-10): per-layer manifests (DEP 25) and registered views (DEP 34). A record written by another commit may not open; the 30 October records don't.
- `quack_serve` runs fine inside the Python process. The views and the served catalog are the same database.
- **Two guards make access read-only.** Without them, any client can `read_csv('/etc/passwd')` and `COPY` to any path. That was confirmed on 1.5.5.
  1. DuckDB's own settings: the HTTP file systems switched off (no reads of arbitrary URLs), no extension installs, and the configuration locked. `enable_external_access = false` (with `allowed_directories`) was stricter, but datarecord's SQL reads Python objects by name, which DuckDB only resolves with external access on, and it can't be switched back on: records couldn't open after the lockdown. Bucket reads go through a key that can only read `manta-records`. The local file system stays on, as DuckDB needs it for temp files, so local files are guarded by the macro alone.
  2. An authorization macro, which checks `json_serialize_sql` of each query:
     - Only SELECT statements, plus the bare `BEGIN TRANSACTION` / `COMMIT` / `ROLLBACK` that a DuckDB 2 client wraps around every query.
     - Table functions are limited to the catalog ones the client needs (`duckdb_schemas`, `duckdb_tables`, `duckdb_views`, …).
     - Table names can't be paths or URLs.
- **Remote tables in a non-`main` schema lose their schema name** in client queries (seen on 1.5.5). Views work, which is why the server exposes views rather than copying tables.
- **`r.information_schema` isn't available remotely.** List views with `FROM quack_query_by_name('r', 'FROM duckdb_views()')` or `POST /api/records/{id}/open`.
- **Joins:** a client query that joins two remote views works on 2.0; on 1.5.5 it failed. For anything heavier, `quack_query_by_name('r', $$…$$)` runs the whole query on the server, next to the data.
- Quack listens on `localhost`, which can resolve to `::1`. The relay therefore connects to `localhost`, not `127.0.0.1`.

## The browser (DuckDB-Wasm)

There is no stable duckdb-wasm release for DuckDB 2 yet, so the explorer and the app use a dev build, `1.33.1-dev121.0` (2026-11-20). It reports DuckDB `v2.0.1` and loads the signed Quack extension from DuckDB's own extension repository, with no relabelled or self-built extensions. Confirmed 2026-11-24 against a 2.0.0 server: `LOAD quack`, ATTACH and `quack_query_by_name` work. Move to a stable release once duckdb-wasm publishes one for DuckDB 2.

Older clients can't connect to a 2.0 server:
- DuckDB 1.4.3 (duckdb-wasm 1.32.0, the app's version before the dev builds) has no Quack ATTACH.
- DuckDB 1.5.5 fails to deserialize the 2.0 wire format.

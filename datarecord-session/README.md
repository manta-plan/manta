<!--
SPDX-FileCopyrightText: 2026 Manta contributors

SPDX-License-Identifier: MIT
-->

# datarecord-session

A datarecord session is one user's view of one project's stores, served to the browser over Quack (DuckDB's remote query protocol).
The session opens one DuckDB connection, attaches a datarecord workspace on it as the catalog `manta`, and serves read-only SQL on that connection.
The backend registers revisions through an internal HTTP API, and each registration becomes the DuckDB schema `manta."<name>"`.

## Start-up

The session reads its inputs from the environment.

| Variable | Default | Content |
| --- | --- | --- |
| `DATARECORD_SESSION_STORE_ROOT` | | The project's folder, `s3://<bucket>/<project_uuid>/`, or a local path. |
| `DATARECORD_SESSION_S3_KEY_ID`, `DATARECORD_SESSION_S3_SECRET` | | The S3 key, required for an `s3://` root. |
| `DATARECORD_SESSION_S3_SESSION_TOKEN` | none | The session token of a temporary key. |
| `DATARECORD_SESSION_S3_ENDPOINT`, `DATARECORD_SESSION_S3_REGION` | | The S3 server as `http://host:port`, and its region, required for an `s3://` root. |
| `DATARECORD_SESSION_QUACK_TOKEN` | | The token a Quack client passes as `TOKEN`. |
| `DATARECORD_SESSION_API_SECRET` | | The bearer token of the internal API. |
| `DATARECORD_SESSION_QUACK_HOST`, `DATARECORD_SESSION_QUACK_PORT` | `0.0.0.0`, `9494` | Where Quack listens, as plain HTTP. |
| `DATARECORD_SESSION_API_HOST`, `DATARECORD_SESSION_API_PORT` | `0.0.0.0`, `8080` | Where the internal API listens. |

The session never reads the `AWS_*` variables.
It reports healthy once Quack serves.

## Internal API

Every call needs the header `Authorization: Bearer <API secret>`, and gets `401` without it.

| Call | Body | Answer |
| --- | --- | --- |
| `GET /health` | | `{"status": "ok"}` |
| `PUT /registrations/{name}` | `{"kind": "view", "store": "<store>", "revision": "<uuid>", "packs": ["pypsa-eur"]}` | `{"name": "<name>", "prefix": "manta.\"<name>\""}` |
| `GET /registrations` | | The registered names, as a list. |
| `GET /registrations/{name}` | | The request, the prefix, the revision's manifest, and the view names by kind. |
| `DELETE /registrations/{name}` | | `204` |

A registration name matches `[a-z0-9][a-z0-9_-]{0,62}`, so it has at most 63 characters, and is none of `main`, `information_schema` and `pg_catalog`.
A store name is a folder directly under the root: it matches `[A-Za-z0-9][A-Za-z0-9._-]*` and does not contain `..`.
The session answers `422` to any other name and `404` to an unknown revision or registration.
A second `PUT` of the same body changes nothing, and a `PUT` of another body replaces the registration.

A registration of a revision contains these views:

| View | Content |
| --- | --- |
| `<prefix>.dimensions.<d>`, `<prefix>.properties.<subject>`, `<prefix>.attributes.<A>`, `<prefix>.owner_map` | The views datarecord registers. |
| `<prefix>.static_float`, `static_int`, `static_bool`, `static_str` | Every constant value of an attribute over `entity` or `connection`, as `(entity, bus, attribute, value)`; `bus` is the bus a connection's port attaches to. |
| `<prefix>."pypsa-eur".<view>` | The map and topology views of PyPSA-Eur, when `packs` lists `pypsa-eur`. |

## Tests

The tests start the session as a process and query it with a native Quack client.
The DuckDB extensions `quack` and `httpfs` must be installed once:

```bash
uv run python -c "import duckdb; c = duckdb.connect(); [c.install_extension(e) for e in ('quack', 'httpfs')]"
uv run pytest
```

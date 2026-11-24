# Manta Frontend

<!-- --8<-- [start:docs-setup] -->

The Manta frontend is a [React](https://react.dev/) app built with
[Vite](https://vite.dev/), [TypeScript](https://www.typescriptlang.org/), and
[Tailwind CSS](https://tailwindcss.com/). UI primitives come from
[Base UI](https://base-ui.com/), and icons come from
[React Icons](https://react-icons.github.io/react-icons/).

## Requirements

- Node.js.
- pnpm. This package is pinned to pnpm `11.10.0` in `package.json`.

If you use Corepack, prepare the pinned pnpm version from the repo root:

```bash
corepack pnpm@11.10.0 --version
corepack enable pnpm
```

## First-time Setup

Move into the `frontend` folder, then install the dependencies:

```bash
cd frontend
pnpm install
```

## Record server

The data records (the New Project drawer, the Data Catalog, and the data record of a run) come
from the record server in `docker/quack-server`, which runs only with the
`temporary-quack-setup` Compose profile (see [docker/README.md](https://github.com/manta-plan/manta/blob/main/docker/README.md#services)).
Point the app at it in a file named `.env.local` in the `frontend` folder:

```bash
VITE_RECORD_SERVER=localhost:8010
VITE_RECORD_TOKEN=devtoken
```

The port is `QUACK_SERVER_PORT` in `backend/.env`, and the token must match `QUACK_TOKEN` there.

## Running

Start the Vite dev server:

```bash
pnpm dev
```

Vite prints the local URL, usually `http://localhost:5173`.
<!-- --8<-- [end:docs-setup] -->

## Project tabs

A project has four tabs, switched from the header or with the keys `1` to `4`
(`?` lists the shortcuts):

| Tab     | Route                              | Shows                                                                         |
| ------- | ---------------------------------- | ----------------------------------------------------------------------------- |
| Build   | `/project/:id/build[/:pageId]`     | The record and its scenarios: the level pages, plus drafting scenario changes |
| Run     | `/project/:id/run[/:runId]`        | Runs and playbooks                                                            |
| Inspect | `/project/:id/inspect[/:pageId]`   | The same level pages over a run result                                        |
| Analyse | `/project/:id/analyse[/:reportId]` | Reports (a placeholder for now)                                               |

`/project/:id` opens Build. On Build and Inspect the sidebar holds the
Scenarios panel over the Record tree, and the main area is a **level page**
(`src/features/level/`): the page head (breadcrumb, title, period switch, time
window), stat tiles, a split of Table and Map & graph, and the chart drawer.
Clicking a row of the Record tree, a tile or a table cell opens the page of
that level; each of the table, the Map & graph and the chart drawer opens full
screen. Every read of the record goes through `src/features/project/lib/record-server/`
(`serverName()` names the relations) and the SQL modules next to each block
(`level-sql.ts`, `tiles/tile-sql.ts`, `table/table-queries.ts`, `chart/chart-sql.ts`,
`map-graph/map/map-shading.ts`, `scenarios/change-sql.ts`).

<!-- --8<-- [start:docs-dev] -->

## Design Tokens

Tailwind theme tokens live in `src/index.css` using Tailwind v4's CSS-first
`@theme` configuration. Prefer semantic utilities such as `bg-primary`,
`text-text-secondary`, `border-border`, and `bg-accent` over raw palette values.

## Quality Checks

Format:

```bash
pnpm fmt
```

Check formatting without writing changes:

```bash
pnpm fmt:check
```

Lint:

```bash
pnpm lint
```

Type-check and build:

```bash
pnpm build
```

## Production Preview

Build and serve the production output locally:

```bash
pnpm build
pnpm preview
```

## Before running a playbook

The frontend needs more than `pnpm dev`. Set these up first, in order.

1. **Backend stack.** Start SeaweedFS, Postgres, Keycloak, Prefect and the backend
   (see [backend/README.md](../backend/README.md) and [docker/README.md](../docker/README.md)).
   With `EXAMPLE_DATA_SEED=true` (the default in `backend/.env`), startup downloads the
   example data records into `s3://manta/example-data/<store>`. It also creates the
   `manta-admin` user and its "Example project"
   (`33b9abe3-2f25-4824-89e2-5a3d93671b6c`), then copies every record into
   `s3://manta/33b9abe3-2f25-4824-89e2-5a3d93671b6c/<store>`. See
   [Example data](../backend/README.md#example-data).

2. **Record server (quack).** It serves the data records to the app. From `docker/`:

   ```bash
   docker compose --env-file ../backend/.env -f compose-dev-services.yaml --profile temporary-quack-setup up --build quack-server
   ```

   Check it:

   ```bash
   curl -H 'Authorization: Bearer devtoken' localhost:8010/api/records
   ```

   The response must list the records (for example `BEL-pre-aggregated`). An empty list means
   the records are not in S3 yet: start the backend once, with network access. If the
   container is stopped and `docker start` fails with `network ... not found`, recreate it
   with `up -d --force-recreate --no-deps quack-server` and the same flags.
   More in [docker/quack-server/README.md](../docker/quack-server/README.md).

3. **Data records in every project's S3 path.** A run reads its data record from
   `s3://manta/<project_uuid>/<store>`.
   - The "Example project" already has copies of every record (step 1).
   - Every newly registered user also gets an "Example project" of their own, when
     `EXAMPLE_PROJECT_FOR_NEW_USERS=true` (the default).
   - For any other project, create the path `s3://manta/<project_uuid>/` and copy the
     records into it, following the same layout as the backend. For example,
     `s3://manta/example-data/BEL-pre-aggregated` goes to
     `s3://manta/<project_uuid>/BEL-pre-aggregated`. You can browse and upload in the SeaweedFS
     dashboard at <http://localhost:23646>.

4. **Check in the app.** With the record server running and the records in S3, the data
   catalogue lists the records (their metadata is read from the record server), and you can
   create a project from one. Open the project, create a run, pick a playbook and its
   data record, and run it. If the app shows "Can't reach the record server.", the record
   server is not running or not on the port in `backend/.env`. See [Record server](#record-server).

## Record server

The data records (the New Project drawer, the Data Catalog and the data record of a run) come
from the quack record server in `docker/quack-server`. The dev server proxies `/api` and `/quack`
to it, like the Caddy in the deployed frontend, so the app reaches it on its own origin. The server's
port and token come from `QUACK_SERVER_PORT` and `QUACK_TOKEN` in `backend/.env`, so nothing is needed in
`.env.local`.
<!-- --8<-- [end:docs-dev] -->

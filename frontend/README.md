# Manta Frontend

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

```bash
pnpm install
```

## Running

Start the Vite dev server:

```bash
pnpm dev
```

Vite prints the local URL, usually `http://localhost:5173`.

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

## Record server

The data records (the New Project drawer, the Data Catalog and the data record of a run) come
from the quack record server in `docker/quack-server`. The dev server proxies `/api`, `/quack` and `/ext`
to it, like the Caddy in the deployed frontend, so the app reaches it on its own origin. The server's
port and token come from `QUACK_SERVER_PORT` and `QUACK_TOKEN` in `backend/.env`, so nothing is needed in
`.env.local`.

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

## Record server

The data records (the New Project drawer, the Data Catalog and the data record of a run) come
from the quack record server in `docker/quack-server`. The dev server proxies `/api`, `/quack` and `/ext`
to it, like the Caddy in the deployed frontend, so the app reaches it on its own origin. The server's
port and token come from `QUACK_SERVER_PORT` and `QUACK_TOKEN` in `backend/.env`, so nothing is needed in
`.env.local`.
<!-- --8<-- [end:docs-dev] -->

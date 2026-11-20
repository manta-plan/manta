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
to it on `localhost:8010` (`QUACK_URL=http://127.0.0.1:<port> pnpm dev` for another port), like the Caddy
in the deployed frontend, so the app reaches it on its own origin. It only needs the shared dev token in `.env.local`:

```bash
VITE_RECORD_TOKEN=devtoken
```

Leave `VITE_RECORD_SERVER` unset (its default is the app's own origin); set it only for a record server elsewhere.

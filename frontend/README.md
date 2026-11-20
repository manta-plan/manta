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

3. **Point the app at it.** Create `frontend/.env.local`:

   ```bash
   VITE_RECORD_SERVER=localhost:8010
   VITE_RECORD_TOKEN=devtoken
   ```

   Without `VITE_RECORD_SERVER` the data catalogue and the New Project drawer show
   "Can't reach the record server." Restart `pnpm dev` after changing it.

4. **Data records in every project's S3 path.** A run reads its data record from
   `s3://manta/<project_uuid>/<store>`.
   - The "Example project" already has copies of every record (step 1).
   - Every newly registered user also gets an "Example project" of their own, when
     `EXAMPLE_PROJECT_FOR_NEW_USERS=true` (the default).
   - For any other project, create the path `s3://manta/<project_uuid>/` and copy the
     records into it, following the same layout as the backend. For example,
     `s3://manta/example-data/BEL-pre-aggregated` goes to
     `s3://manta/<project_uuid>/BEL-pre-aggregated`. You can browse and upload in the SeaweedFS
     dashboard at <http://localhost:23646>.

5. **Check in the app.** With the record server running and the records in S3, the data
   catalogue lists the records (their metadata is read from the record server), and you can
   create a project from one. Open the project, create a run, pick a playbook and its
   data record, and run it.

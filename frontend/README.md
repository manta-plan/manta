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

## TEMPORARY: example data records for runs

This section describes a stopgap and should be removed once the backend can list a
project's data records.

When you open the app for the first time, the frontend creates a new project, because it
has no way to ask the backend which projects you already own. That project is only a
database row, so it starts out empty. The example data records and their revisions are not
in the database. They are files in S3 (SeaweedFS), stored under the project's own folder
(`s3://manta/<project_uuid>/<store>/`). The backend checks for the revision's
`<store>/layers/<revision>/manifest.json` before it starts a run, and fails with
`Revision <uuid> not found in 's3://…'` when it is missing.

The frontend hardcodes the record names and revision IDs in
`src/features/runs/exampleDataRecords.ts`. They must match the seeded data version (see
"Example data" in `backend/README.md`). For now, someone has to put the matching files into
the project's S3 folder. Your project's uuid is in the browser, under DevTools →
Application → Local Storage → `manta.defaultProjectUuid.<sub>`.

### Option 1: copy the stores yourself

This copies every store from the project the backend already seeded (the `manta-admin`
"Example project", `33b9abe3-2f25-4824-89e2-5a3d93671b6c`) into your project's folder. It
needs the dev services running (SeaweedFS on `localhost:8333`, credentials from
`backend/.env`) and the backend's Python environment, which has `boto3`. It refuses to run
if the target folder is not empty. Set `TARGET` to your project's uuid, then run from
`backend/`:

```bash
TARGET=<your-project-uuid> .venv/bin/python - <<'EOF'
import os
import boto3

BUCKET = "manta"
SOURCE = "33b9abe3-2f25-4824-89e2-5a3d93671b6c/"
TARGET = os.environ["TARGET"] + "/"

s3 = boto3.client(
    "s3",
    endpoint_url="http://localhost:8333",
    aws_access_key_id="dev",
    aws_secret_access_key="dev",
    region_name="us-east-1",
)
assert s3.list_objects_v2(Bucket=BUCKET, Prefix=TARGET).get("KeyCount", 0) == 0, "target not empty"

count = 0
for page in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=SOURCE):
    for obj in page.get("Contents", []):
        s3.copy_object(
            Bucket=BUCKET,
            Key=TARGET + obj["Key"][len(SOURCE):],
            CopySource={"Bucket": BUCKET, "Key": obj["Key"]},
        )
        count += 1
print("copied", count, "objects")
EOF
```

On Windows PowerShell, use `.venv\Scripts\python.exe` and set the variable first with
`$env:TARGET = "<your-project-uuid>"`, and pipe the script in with a here-string instead of
`<<'EOF'`.

### Option 2: ask Claude to do it

Open Claude Code in the repository and paste this, with your project uuid filled in:

```text
My frontend project is <your-project-uuid>. Copy the example data stores (every store,
with its revisions) from the seeded project 33b9abe3-2f25-4824-89e2-5a3d93671b6c into
s3://manta/<your-project-uuid>/ in the local SeaweedFS (localhost:8333, credentials in
backend/.env). Check first that the target folder is empty, never overwrite anything, and
afterwards confirm the object count and total size match the source and that
<your-project-uuid>/ac-dc-meshed/layers/<revision>/manifest.json exists for the `inputs`
revision in the backend/README.md "Example data" table.
```

### Without copying anything

Point the browser at the seeded project instead: set the `localStorage` key
`manta.defaultProjectUuid.<sub>` to `33b9abe3-2f25-4824-89e2-5a3d93671b6c` and reload. This
only works for the user who owns that project (`manta-admin`).

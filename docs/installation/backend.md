<!--
SPDX-FileCopyrightText: Manta contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Backend

This page shows how to run the backend on your own machine and call its REST API, without building the frontend.
You need [uv](https://docs.astral.sh/uv/getting-started/installation/), Docker and a [clone of the repository](full-stack.md#1-clone-the-repository).

## Start the services

When the backend starts, it applies database migrations, creates the storage bucket and checks that Prefect is reachable.
So it needs every service from Docker running first.
Start them as [step 2 of Full stack](full-stack.md#2-start-the-services) shows, and leave them running.
Then open a second terminal in the `backend` folder for the steps below.

--8<-- "backend/README.md:docs-setup"

!!! warning "Without a frontend build"

    `uv run manta` serves the frontend from `frontend/dist`, and refuses to start when that folder does not exist.
    To start the backend without a frontend build, set `FASTAPI_ENV` to `development`:

    ```bash
    FASTAPI_ENV=development uv run manta
    ```

    The backend then logs a warning about the missing folder and serves the API alone.

## Check the API

Ask the backend for its health status:

```bash
curl http://127.0.0.1:8000/v1/health
```

```json
{"status":"ok"}
```

The backend is answering on port 8000.
FastAPI's interactive API docs are at `http://127.0.0.1:8000/docs`, and the [REST API reference](../reference/backend/rest-api.md) lists every route.

## Next steps

- To run the web app against this backend with live reloading, read [Frontend](frontend.md).
- To change the database schema, run the tests or lint your code, read [Contributing: Backend](../contributing/backend.md).
- To stop the services, follow [Stopping](full-stack.md#stopping) on the Full stack page.

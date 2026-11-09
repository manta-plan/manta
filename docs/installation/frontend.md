<!--
SPDX-FileCopyrightText: Manta contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Frontend

This page shows how to run the frontend's development server, which reloads the web app as you edit its source.
The development server sends every request under `/v1` to a backend at `http://127.0.0.1:8000`.
So before you start, run the backend as [Backend](backend.md) shows.

--8<-- "frontend/README.md:docs-setup"

## Open the web app

Go to `http://localhost:5173` and log in with the account that [Full stack](full-stack.md#5-open-manta) names.
The page reloads when you save a change to a file in `frontend/src`.
If the page loads but login fails, check that the backend answers on port 8000, as [Check the API](backend.md#check-the-api) shows.

## Next steps

- To format, lint and type-check your change, read [Contributing: Frontend](../contributing/frontend.md).
- To stop the services, follow [Stopping](full-stack.md#stopping) on the Full stack page.

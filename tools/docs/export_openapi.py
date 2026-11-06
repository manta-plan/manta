# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Write the OpenAPI schema of Manta's REST API to `docs/reference/backend/openapi.json`.

Builds a bare FastAPI app with the v1 router, because `manta.main` runs migrations at
import. Run from the repository root with `uv run --project backend python tools/docs/export_openapi.py`.
"""

import json
from pathlib import Path

from fastapi import FastAPI
from manta.routes.v1 import router

OUTPUT = Path(__file__).parents[2] / "docs" / "reference" / "backend" / "openapi.json"


def main() -> None:
    app = FastAPI(title="Manta")
    app.include_router(router)
    OUTPUT.write_text(json.dumps(app.openapi(), indent=2) + "\n")


if __name__ == "__main__":
    main()

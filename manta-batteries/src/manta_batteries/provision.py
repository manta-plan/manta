# SPDX-FileCopyrightText: 2026 Manta Blocks contributors
#
# SPDX-License-Identifier: MIT

"""Make a Prefect installation ready to run any playbook of this library's blocks.

    pixi run -e pypsa python -m manta_batteries.provision

Run it inside the `pypsa` environment, so every block can be imported and described.
It creates one process work pool per environment and registers one deployment per
block plus the playbook orchestrator, against the Prefect server at `PREFECT_API_URL`.
Running it again is harmless: pools and deployments are created or updated, never
duplicated.

Process pools are the simplest thing Prefect offers: each job runs as a subprocess of
the worker draining its pool, and a worker is started inside the matching pixi
environment:

    pixi run -e pypsa prefect worker start --pool manta-pypsa

That is this library's own path - what its tests use and what a power user runs
against their own Prefect. An installation wanting per-run isolation creates its pools
itself (Manta's compose stack gives each block its own container; see
`docker/provision.py` there) and this script is not involved.
"""

import os
import sys

from manta_blocks import catalogue
from manta_playbooks import provision_catalogue

DEFAULT_ORCHESTRATOR_ENV = "orchestrator"
"""The environment the playbook orchestrator runs in.

Kept in step with `MANTA_ORCHESTRATOR_ENV` in the Manta backend: the backend starts
runs on the deployment this name produces.
"""


def main() -> int:
    described = catalogue()
    if not described.blocks:
        print(
            "No blocks could be imported here, so there is nothing to provision. "
            "Run this in the `pypsa` environment.",
            file=sys.stderr,
        )
        return 1

    orchestrator_env = os.environ.get(
        "MANTA_ORCHESTRATOR_ENV", DEFAULT_ORCHESTRATOR_ENV
    )
    ids = provision_catalogue(described, orchestrator_env=orchestrator_env)
    print(
        f"Provisioned {len(described.blocks)} block(s) and the orchestrator "
        f"({len(ids)} deployment(s)) on process pools"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

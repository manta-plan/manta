<!--
SPDX-FileCopyrightText: 2026 Manta contributors

SPDX-License-Identifier: MIT
-->

# runner

A playbook execution runtime built on Prefect: the flows that run a playbook,
and the transport that runs each of its blocks in isolation.

It sits between two things that must not know about each other:

- **[`playbook`](../playbook)** owns the playbook *language* and engine — which
  steps run, what feeds what, where outputs go — and never imports Prefect or
  Docker. It exposes a `StepRunner` protocol; this package implements it.
- **The blocks image** holds only a block library (e.g.
  [`playbook-library`](../playbook-library)) and its own dependencies. It is what
  a block author writes, tests and runs against.

This package depends on `playbook`, never on any particular block library. It is
meant to be published later so that any block library's own author can reuse it
to run and test their own playbooks; depending on one specific library would
make that a cycle. `tests/test_isolation.py` checks this rather than only
promising it.

| Module | What it is |
| --- | --- |
| `flows.py` | the `run-playbook` and `run-block` flows, and `PrefectStepRunner` |
| `config.py` | the images, pools, network and object store, all from the environment |
| `deploy.py` | creates the work pools and registers the deployments (`python -m runner.deploy`) |

## How a run executes

`run-playbook` runs on a **process** work pool (`manta-playbooks`). A playbook
run holds one worker slot for its whole duration while its steps run, so a
container per run would idle for hours and take the run down with it if it were
evicted. It is also why a playbook run survives a restart of whatever dispatched
it.

Each step is dispatched at the `run-block` deployment on a **docker** work pool
(`manta-blocks`), so the worker starts a fresh container for it. Steps come back
as child flow runs of the playbook's flow run, named `<step>[<block>]`, which is
what groups a run's steps under it in Prefect.

A step's output record travels back through Prefect's result storage, which
points at the object store rather than a shared volume — a volume would be the
one thing tying every container to a single machine. Only the small record
pointers go that way; model data never passes through Prefect or the
orchestrator at all.

### The catalogue crosses as a JSON string, never a dict

`run-playbook` never imports a block library, so it cannot resolve a block by
name on its own the way `playbook.blocks.resolve_block` normally would. Whatever
dispatches a run has to hand it a `Catalogue` describing every block the
playbook could use; `catalogue_parameter()` / `parse_catalogue_parameter()` are
how that crosses.

It must be a JSON **string**, never a plain dict parameter: Prefect walks a
dict flow parameter and resolves any `{"$ref": ...}` inside it as its own
block-document reference. A catalogue of JSON schemas is full of `$ref`s, so
passing one as a dict crashes the flow run with `Block document ID
'#/$defs/...' is not a valid UUID`. This cost a full debug cycle once — don't
revert it.

### Job containers must import their block library before looking anything up

`run-block` executes inside a fresh container that has a block library
installed but has imported nothing yet. `MANTA_BLOCK_SOURCES` (set on every job
container by `config.job_environment`) names that library; `run_block` calls
`load_block_sources()` — which reads that same variable — before `get_block()`,
every time. Skip that call and every run fails with `BlockNotRegisteredError`, since
nothing has run the library's own `register_lazy` calls yet.

## Why block containers hold Prefect, and why the bare image still exists

A Prefect worker never marks a flow run `COMPLETED`. It starts the
infrastructure and waits, and reports `CRASHED` only on a non-zero exit
(`prefect/workers/base.py`); the terminal state and the result are reported by
the Prefect engine *inside* the container. A container with no Prefect would run
its block correctly, exit 0, and leave the flow run `PENDING` for ever.

So the image a block runs in is built in two layers:

```
blocks-runner:<env>   the artifact a block author writes, tests and runs
        │ FROM         against. No Prefect. No orchestration code.
        ▼
exec:<env>            + prefect, prefect-aws, runner.
                       Built and registered by whatever deploys this runtime;
                       block authors never build it, name it, or depend on it.
```

Running a block library's own test suite inside the base image stays an exact
environment-parity check, and the ~15 lines that reach the execution image
(`run_block`) import a block only when asked for one by name.

TODO(post-MVP): both layers are built with the library baked in at image-build
time today. The intended direction is run-time, per-step resolution — a
playbook names the blocks it needs, and the container fetches exactly those
from whichever library publishes them (see `MantaBlock.MANIFEST` /
`EnvironmentSpec.manifest` / `.image`, unused today) — so the targeted library
can change per run with no image rebuild. `config.exec_image()` staying the
single place a declared environment becomes something concrete is what will
keep that change to one function plus a fetch step. That fetch step will also
need a cached or prebuilt environment layer underneath it: installing a
PyPSA/HiGHS stack from scratch at container start takes minutes, not seconds.

## Configuration

Everything in `config.py` is read from the environment (`MANTA_*`, `S3_*`,
`PREFECT_API_URL`, ...), never from code — see the module for the full list and
its defaults. Only the provisioner (`python -m runner.deploy`) reads most of it;
once a work pool's job template carries a value, every block run inherits it
without anything here being consulted again.

## Testing

```bash
uv sync
uv run pytest
```

Tests live in `tests/`, exercising the flows through their undecorated
functions and `PrefectStepRunner` with `run_deployment` stubbed — no live
Prefect server or Docker daemon needed. `tests/test_isolation.py` is the
boundary this package cannot afford to lose by accident: that it never imports
this monorepo's own backend or a block library.

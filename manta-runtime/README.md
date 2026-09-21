# manta-runtime

Manta's playbook execution runtime: the Prefect flows that run a playbook, and
the transport that runs each of its blocks in isolation.

It sits between two things that must not know about each other:

- **`manta-blocks`** owns the playbook *language* and engine — which steps run,
  what feeds what, where outputs go — and never imports Prefect or Docker. It
  exposes a `StepRunner` protocol; this package implements it.
- **The blocks image** holds only `manta-blocks` and the blocks' own
  dependencies. It is what a block author writes, tests and runs against.

The Manta backend does not import a flow at request time; it dispatches runs by
deployment name.

| Module | What it is |
| --- | --- |
| `flows.py` | the `run-playbook` and `run-block` flows, and `PrefectStepRunner` |
| `config.py` | the images, pools, network and object store, all from the environment |
| `deploy.py` | creates the work pools and registers the deployments (`python -m manta_runtime.deploy`) |

## How a run executes

`run-playbook` runs on a **process** work pool. A playbook run holds one worker
slot for its whole duration while its steps run, so a container per run would
idle for hours and take the run down with it if it were evicted. It is also why a
run is unaffected by restarting the backend.

Each step is dispatched at the `run-block` deployment on a **docker** work pool,
so the worker starts a fresh container for it. Steps come back as child flow runs
of the playbook's flow run, named `<step>[<block>]`, which is what groups a run's
steps under it in Prefect and behind `GET /v1/runs/{uuid}/steps`.

A step's output record travels back through Prefect's result storage, which
points at the object store rather than a shared volume — a volume would be the
one thing tying every container to a single machine. Only the small record
pointers go that way; model data never passes through Prefect or the
orchestrator at all.

## Why block containers hold Prefect, and why the bare image still exists

A Prefect worker never marks a flow run `COMPLETED`. It starts the
infrastructure and waits, and reports `CRASHED` only on a non-zero exit
(`prefect/workers/base.py`); the terminal state and the result are reported by
the Prefect engine *inside* the container. A container with no Prefect would run
its block correctly, exit 0, and leave the flow run `PENDING` for ever.

So the image a block runs in is built in two layers:

```
manta-blocks-runner:<env>   the artifact a block author writes, tests and runs
        │ FROM              against. No Prefect. No Manta.
        ▼
manta-exec:<env>            + prefect, prefect-aws, manta-runtime.
                            Built and registered by Manta; block authors never
                            build it, name it, or depend on it.
```

Running a block library's own test suite inside the base image stays an exact
environment-parity check, and the ~15 lines of Manta that reach the execution
image (`run_block`) import a block only when asked for one by name.

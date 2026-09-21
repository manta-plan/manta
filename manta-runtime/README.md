# manta-runtime

Manta's playbook execution runtime: the Prefect flow that runs a playbook, and
the transport that runs each of its blocks in isolation.

It sits between two things that must not know about each other:

- **`manta-blocks`** owns the playbook *language* and engine — which steps run,
  what feeds what, where outputs go — and never imports Prefect or Docker. It
  exposes a `StepRunner` protocol; this package implements it.
- **The block image** holds only `manta-blocks` and the blocks' own
  dependencies. It runs the orchestration-agnostic `python -m blocks.run_one`
  entrypoint, so it is exactly what an outside block author tests against.

Everything Prefect- or Docker-shaped lives here. The Manta backend does not
import the flow at request time; it dispatches runs by deployment name.

| Module | What it is |
| --- | --- |
| `flows.py` | the `run-playbook` flow, the `run_block` task, and `DockerStepRunner` |
| `config.py` | image name, docker network, and the object-store endpoint as containers see it |
| `serve.py` | registers the deployment and executes its runs |

Tracking: one flow run per playbook run (named `run-<run uuid>` by the
backend), one task run per executed step (named `<step>[<block>]`).

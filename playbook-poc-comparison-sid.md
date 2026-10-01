# Playbook PoC Comparison -- Sid

A human comparison of:

| Label | Branch | Head commit | Shorthand |
| --- | --- | --- | --- |
| **A** | `sid/docker-pools-in-docker-dir` | `67975b1` | Docker-Pools |
| **B** | `sid/prefect-isolation-fixes-poc` | `15bef38` | Backend-Isolation |

Both branch from `main` at `2e17900`.
They share `playbook.py`, `validation.py`, `yaml_io.py`, `graph.py` and the four PyPSA blocks.
They differ mostly in the boundary between the Manta backend and the blocks/playbook library.
B now has a separate `manta-runtime` package, which holds all of its Prefect code.

## Requirements

Modified slightly from `playbooks-requirements-proposal.md` and also from Kristijan's prompt for PR #167:

1. **Model-agnostic**: adding a block that uses a different modeling framework or dependency
   environment should be easy.
2. **Modular**: reusing parts of a workflow to build a new one should be easy. Post-MVP,
   users assemble workflows from existing blocks through the UI or a text representation.
3. **Reproducible**: Manta must record which input data, playbook, blocks, and environments
   produced a given output, so the run can be reproduced.
4. Manta users must be able to view each block's output after a playbook runs.
5. **Configurable**: playbooks need flexible, layered configs, so one playbook covers many
   related workflows. Example: a playbook-level config sets `solver=highs` for every block
   that calls a solver; a block-level config can still override it for one block.
6. **Validating**: Manta should catch common workflow errors early — a missing `scenario`
   dimension, or an output of the wrong kind, for example.
7. **Contribution**: a modeler outside the Manta team should be able to write and test new
   blocks and playbooks easily. In particular:
   - (a) without a PR to the `manta` repo, since they aren't app developers
   - (b) run blocks and playbooks without having the Manta app setup or running
   - (c) without maintaining two separate orchestration setups for block contributors and for Manta.

Both PoCs either satisfy, or can easily be amended to satisfy the above requirements.

## Other Citeria

| Criteria | (A) Docker-Pools | (B) Backend-Isolation |
| --- | --- | --- |
| **Kubernetes**: it should be easy to migrate to the k8s production environment | Yes, `docker/provision.py` is the only docker-aware code and swapping its pool type is the change — but still blocked on Todo A1, since results travel on a shared docker volume no k8s pool can provide. Also: it's one pool per environment (so N k8s pools), and the pool's container command is `pixi run -e <env> prefect flow-run execute`, a pixi-ism that has to survive the move | Yes, same seam, and Todos B1–B3 are now done: `manta_runtime/deploy.py` holds the pool, results are already on S3, and `PrefectStepRunner` picks the image per step via `job_variables` rather than per pool — so it's one pool whichever type it is |
| The definition of blocks and playbooks is separated from the library of blocks and playbooks | Yes, `manta-blocks` and `manta-batteries`, and a third-party library registers itself through `register_lazy` + `MANTA_BLOCK_SOURCES` | No. `blocks/library/` and `playbooks/library/` are subpackages of `manta-blocks`, and `blocks/registry.py` hardcodes the four library blocks in a `_LAZY` dict. Todo B4, which now also means making the registry pluggable |
| Can independent blocks in future playbooks be run in parallel? | Neither does today as the YAML syntax forces sequentiality. A's blocks are subflows, so using `.submit()` would mostly do it | B needs modification of `manta-runtime` (Todo B6) |
| Do in-flight flow runs survive a backend restart? | Yes, on the `manta-orchestrator` process pool worker | Yes now (Todo B2 done): a `prefect-worker-orchestrator` compose service on a process pool, and the backend only calls `run_deployment(..., timeout=0)` |
| Are we rolling our own logs mechanism? | No, Prefect's — but the backend endpoints need to be added | No, Prefect's (Todo B1 done). Each step is its own flow run, and `GET /runs/{id}/steps` and `/steps/{step}/logs` expose them |
| Retries, concurrency limits, and state tracking | From Prefect — blocks are flow runs on a work pool. Nothing is configured yet in either | Same, now that blocks are flow runs on a work pool. Nothing is configured yet in either |
| Updating the Prefect version | Needs updating in backend, docker-compose, `manta-blocks` (hard dependency), and `manta-batteries` (all four blocks `from prefect import task`). A 3rd-party block library is pinned to Manta's Prefect | Needs updating in backend, docker-compose, and `manta-runtime`. `manta-blocks` has no Prefect, and neither does the image a block author builds and tests against (`blocks-runner.Dockerfile`) |
| How do we support compute resources per block? | Per pool (one docker pool per environment, via `job_template`) or per deployment (`to_deployment(job_variables=...)`). Not per step | Per step: `PrefectStepRunner` already passes `job_variables={"image": ...}` on every `run_deployment`; cpu/memory go the same way |
| What is a block, concretely? | A Prefect flow — `MantaBlock.as_flow` wraps it, and all four library blocks call `task` / `.submit()` inside | A plain class with `run(record, output_base)`. Nothing in `manta-blocks` imports Prefect |
| Who decides where a block's output goes? | The block: `patch_record` writes a `sibling_url` next to its input | The caller: `execute_playbook` passes `output_base = <output_prefix>/<step>` and the block appends its own suffix |

## To Do on each PoC

Sid's suggestions for ways to improve each PoC to meet the requirements better / learn from each other's strengths:

### (A) Docker-Pools

All three are still open on `67975b1`:

1. Use S3-backed Prefect result storage instead of the shared Docker volume
2. Make the playbook orchestrator run on a slim image
3. Use one image per block environment. This will be required once 3rd party block contributors contribute non-PyPSA blocks.

And two more, from reading B:

4. Expose per-step status and logs from the backend. `control.run_status` already computes the step map and nothing calls it.
5. Decide whether `manta_playbooks.control` is dead code — today the backend re-implements start and status against Prefect directly.

An implementation plan for the first three is at the end of `playbooks-requirements-proposal.md` in `sid/docker-poolss-in-docker-dir`.

### (B) Backend-Isolation

1. ~~Use the docker work pool (like used by Docker-Pools) instead of `DockerStepRunner`~~ — done, in `manta_runtime.deploy` and `PrefectStepRunner`
2. ~~Run the playbook orchestrator on a process work pool instead of a subprocess of the backend~~ — done, as the `prefect-worker-orchestrator` compose service
3. ~~Run each block environment in a separate image~~ — done, `blocks-runner.Dockerfile` per environment plus the `exec.Dockerfile` layer

Still open:

4. Separate the library of PyPSA blocks into a new top-level directory & package `manta-batteries` (but let's call it something else). This now also means replacing the hardcoded `_LAZY` dict in `blocks/registry.py` with something a library can register into — A's `register_lazy`, or entry points.
5. Delete `blocks/run_one.py` and the `MANTA_BLOCK_RESULT` protocol; nothing dispatches through it any more.
6. Add support for independent blocks to be run in parallel.
7. Amend block input handling and output processing to fit with the `datarecord` vision (e.g. no need to copy inputs to run folder since datarecords are immutable).

I implemented 1–3 in [`sid/prefect-isolation-fixes-poc`](https://github.com/manta-plan/manta/compare/prefect-isolation-backend-integration-claude-poc...sid/prefect-isolation-fixes-poc), which also adds the `manta-runtime` package.

### Other Implementation Decisions

1. Go with B's approach of `PrefectStepRunner` passing `job_variables` per step, vs A's job templates per pool?
1. In both, a way to pin block and playbook versions, for reproducibility.
1. Pass the whole catalogue as a per-run parameter as in A, or bake it into the orchestrator image as in B?
1. Should we merge global config with per-block config, latter wins?

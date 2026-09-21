# Playbook PoC Comparison -- Sid

A human comparison of:

| Label | Branch | Head commit | Shorthand |
| --- | --- | --- | --- |
| **A** | `sid/docker-pools-in-docker-dir` | `67975b1` | Docker-Pool |
| **B** | `prefect-isolation-backend-integration-claude-poc` | `cfcc840` | Backend-Isolation |

Both branch from `main` at `2e17900`.
They share `playbook.py`, `validation.py`, `yaml_io.py`, `graph.py` and the four PyPSA blocks. 
They differ mostly in the boundary between the Manta backend and the blocks/playbook library.

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

| Criteria | (A) Docker-Pool | (B) Backend-Isolation |
| --- | --- | --- |
| **Kubernetes**: it should be easy to migrate to the k8s production environment | Yes, it's a configuration change to switch from a docker work pool to a k8s one (assuming Todo A1) | No, needs a k8s equivalent of `DockerStepRunner`. TODO maybe easier if we migrate `DockerStepRunner` -> docker work pool? |
| The definition of blocks and playbooks is separated from the library of blocks and playbooks | Yes, `manta-blocks` and `manta-batteries` | No both are in `manta-blocks`, but it can (and should) be done (Todo B4) |
| Can independent blocks in future playbooks be run in parallel? | Yes, utilizes Prefect's ability to run subflows in parallel | No, but perhaps it can be modified to support this (Todo B1) |
| Do in-flight flow runs survive a backend restart? | Yes, they are run on Prefect | No, but this can be changed (Todo B2) |
| Are we rolling our own logs mechanism? | No, we use Prefect's | Yes, but can be changed (Todo B1) |
| Retries, concurrency limits, and state tracking | Yes, all from Prefect | No, but maybe with the proposed changes below? |
| Updating the Prefect version | Needs updating in backend, docker-compose, manta-blocks, and manta-batteries. Would upgrading Prefect in Manta still allow running 3rd party blocks backward compatibly? | Needs updating backend and docker-compose only |
| How do we support compute resources per block? | Prefect supports setting pod resources for flows, and blocks are flows | TODO: is it even possible, since blocks are tasks? We might need to make blocks flows, and definitely need Todo B1 so that blocks are run by a work pool instead of manually |

## To Do on each PoC

Sid's suggestions for ways to improve each PoC to meet the requirements better / learn from each other's strengths:

### (A) Docker-Pool
- 1. Use S3-backed Prefect result storage instead of the shared Docker volume
- 2. Make the playbook orchestrator run on a slim image
- 3. Use one image per block environment. This will be required once 3rd party block contributors contribute non-PyPSA blocks.

An implementation plan for these is at the end of `playbooks-requirements-proposal.md` in `sid/docker-pools-in-docker-dir`.

### (B) Backend-Isolation
- 1. Use the docker work pool (like used by Docker-Pool) instead of `DockerStepRunner`
- 2. Run the playbook orchestrator on a process work pool instead of a subprocess of the backend. This allows in-flight flows to survive a backend restart.
- 3. Run each block environment in a separate image. This will be required once 3rd party block contributors contribute non-PyPSA blocks.
- 4. Separate the library of PyPSA blocks into a new top-level directory & package `manta-batteries` (but let's call it something else)

I tested the implementation of the first 3 above in [`sid/prefect-isolation-fixes-poc`](https://github.com/manta-plan/manta/compare/prefect-isolation-backend-integration-claude-poc...sid/prefect-isolation-fixes-poc)

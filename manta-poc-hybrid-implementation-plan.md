# Manta PoC Implementation Plan: The Hybrid

[manta-poc-comparison.md](manta-poc-comparison.md) recommends building on Backend-Isolation's
package boundary and adopting Docker-Pools' Prefect-native dispatch mechanism in place of
Backend-Isolation's raw Docker SDK calls. This document lists every PR needed to get there —
common groundwork, the dispatch-mechanism swap, and production hardening — as one build order.
Each PR is scoped to review in one sitting and leaves the codebase working end to end.

## The concrete shape, and one tension worth being precise about

The codebase this hybrid starts from is Backend-Isolation. Its `manta-blocks` package, its
`execute_playbook` engine, its `StepRunner` seam, its double-gated validation, and its
per-run provenance all carry over untouched. What changes is a single implementation behind
that seam: `DockerStepRunner`, which calls `docker.from_env()` directly, is replaced by one
that dispatches through a real Prefect deployment and work pool, the way Docker-Pools already
dispatches blocks.

One detail needs to be stated precisely, because it is not free. Docker-Pools' job template
sets every spawned container's command to `pixi run -e {env} prefect flow-run execute`
(`docker/provision.py`) — a Prefect work pool's worker spawns a container and expects that
container to run Prefect's own flow-execution protocol inside it, which requires Prefect
installed in the image. That is exactly why Docker-Pools' base class wraps every block as a
Prefect `Flow` and why its job image bundles Prefect: there is no way to get a container
dispatched and tracked as a first-class Prefect deployment run without Prefect present inside
that container.

Backend-Isolation's block image today has none of that — no Prefect, only `manta-blocks` and
the blocks' own dependencies. Adopting Prefect-native dispatch means giving up that fully bare
image. What it does not require giving up is keeping Prefect out of block code. The plan below
adds a small, backend-owned flow — not part of `manta-blocks`, containing no modeling logic —
whose only job is to run the existing `python -m blocks.run_one` entrypoint as a subprocess and
relay its result. That flow, and Prefect itself, live in the runner image alongside
`manta-blocks`; the block classes a contributor writes still import nothing from Prefect,
which is the property that mattered most in the comparison (requirement 1, and `manta-blocks`'
repo-separation story). The image is no longer orchestration-free; the code a contributor
writes still is.

## 1. Common groundwork

Independent of the dispatch-mechanism swap below. None of these PRs depend on it, and all can
land before or alongside it.

**PR 1 — Layered config resolution.** Replace the flat per-step config lookup Backend-Isolation
uses today with one shared resolver: playbook defaults, then playbook-level `globals`, then
per-step overrides, merged through a single function. Today a playbook-wide default like
`solver=highs` has to be repeated on every step that needs it. Self-contained: a config dict
in, a resolved per-step dict out, testable without touching execution or dispatch code.

**PR 2 — Run provenance: block and image versioning.** Record, per run, which version of the
block library and which runner image, by digest, actually executed — alongside the playbook
and config metadata already persisted today. Without this, two runs of "the same" playbook can
silently use different block code. Self-contained: a schema addition and one resolution point.
Once PR 7 and PR 8 below exist, the natural place to capture the digest is at deployment
registration, but the schema itself does not depend on that.

**PR 3 — Single validation gate, exposed pre-flight.** Make playbook validation reachable from
exactly one call site inside the shared engine, used by every execution and dispatch entry
point. Expose the same check as a stand-alone API endpoint so a future UI can validate a
playbook before a user submits a run. Validation logic already exists; this makes it
unconditional and gives it a caller-facing surface. Dispatch-mechanism agnostic — it validates
`execute_playbook`'s input regardless of which `StepRunner` executes a step.

**PR 4 — Per-step status and output surfacing.** Add a `GET /runs/{id}/steps` route (or
equivalent) returning each step's state and the outputs it produced. Read-only and additive;
no execution-path changes.

**PR 5 — Playbook registration API.** Replace registering a new playbook by committing a YAML
file under `manta-blocks/src/playbooks/library/` with an API that registers a playbook document
against a `PlaybookRegistry` interface Manta owns. This is the concrete step that makes
requirement 7's "no PR to the `manta` repo" promise true for playbooks, not just blocks. Flag:
keep the registry's storage (a database table today) behind the interface — a future collection
of playbooks split into its own repo would otherwise force whatever registration mechanism
ships first to be redone rather than pointed at a new source.

**PR 6 — Step-level retry and timeout policy (shape).** Define a retry and timeout policy per
block — attempt count, backoff, wall-clock limit — as data on a block or step, independent of
how it gets enforced. Land the policy's shape now; PR 9 below is where it becomes enforceable,
once block dispatch goes through a real Prefect deployment with native retry and timeout
options.

## 2. Dispatch-mechanism swap

The core of the hybrid. Five PRs, run in this order — each depends on the one before it.

**PR 7 — Add the block-runner flow, and build it into the runner image.** A small Prefect flow,
owned by the backend, whose body runs `python -m blocks.run_one` as a subprocess and parses its
`MANTA_BLOCK_RESULT` line into the flow's own result — the same contract `DockerStepRunner`
reads today, just invoked as a subprocess inside the flow's own container instead of a sibling
container the backend spawns itself. Extend the existing `blocks-runner` image to also hold
Prefect and this flow's code. Reviewable and testable on its own: the flow can run directly,
unwrapped by any deployment, and its subprocess/result-parsing logic is tested the same way
`DockerStepRunner`'s unit tests already fake `blocks.run_one`'s output today.

**PR 8 — Register one deployment on a docker-type work pool.** Deploy the PR 7 flow once — a
single generic deployment, not one per block or per environment — and stand up a docker-type
work pool and worker for it, reusing the job-template mechanism `docker/provision.py` already
implements on Docker-Pools. Infrastructure only: a work pool, a worker service, a job template.
No change to how a block's own code runs. This is what moves Docker socket access off the
backend and onto the worker, a dedicated, non-HTTP-facing service — closing the security gap
the comparison raised, as a consequence of this PR rather than a separate one.

**PR 9 — Swap `DockerStepRunner` for a deployment-dispatching `StepRunner`.** Replace the
`StepRunner` implementation the backend uses for block execution with one that calls
`run_deployment()` against the PR 8 deployment and reads the result back from the flow run's
own state and logs, the way Docker-Pools' own dispatch code already does. The `StepRunner`
interface itself, defined in `manta-blocks`, does not change — this is an implementation swap
behind a seam that already exists. Once this lands, retries, timeouts, and concurrency limits
become deployment or task options on the PR 7 flow rather than code to write: this is what
closes PR 6's retry/timeout gap for block execution, as configuration rather than new logic.

**PR 10 — Retire the raw-Docker code path.** Delete `_run_block_in_container`,
`_docker_client`, and the backend's direct dependency on the Docker SDK, once PR 9 has run in
parallel long enough to trust it. Kept separate from PR 9 so a revert of that PR alone remains
possible without also restoring dead code.

**PR 11 — Automated coverage for the new dispatch path.** Extend the existing
`testcontainers`-based integration test to run a real block through the PR 8 work pool end to
end: register the pool, dispatch a deployment run, confirm the result and outputs land
correctly. Test-only; the existing coverage of `LocalStepRunner` and validation stays as is.

### What this swap needs from Docker-Pools' design, and what it doesn't

**Does not need: S3-backed Prefect result storage.** Docker-Pools needs this because its
orchestrator and job containers hand off a block's result through Prefect's local-disk result
storage, mounted as a shared Docker volume — the design's own Kubernetes blocker (see the
comparison). This hybrid never adopts that mechanism. A block's result is a small parsed value,
relayed through Prefect's own log store the same way `DockerStepRunner` reads it from a live
log stream today; block *outputs* already go straight to S3 through `blocks/storage.py`,
unchanged from Backend-Isolation. No shared volume, no single-host assumption, nothing to undo
before a Kubernetes move.

**Does not need: removing Prefect from block implementations.** `manta-blocks` in
Backend-Isolation never had it — there is nothing to remove.

**Does not need: packaging `manta-batteries` as a separate library.** This hybrid keeps
Backend-Isolation's layout, one `manta-blocks` package holding both the block library and the
playbook engine, not Docker-Pools' `manta-blocks`/`manta-batteries` split.

## 3. Production hardening

Land any time after PR 9 confirms the new dispatch path works, except PR 16, which should
wait for PR 11.

**PR 12 — Durable flow-serving.** Run the playbook-level `run-playbook` flow's `.serve()` as
its own long-lived service instead of a subprocess spawned at app startup, so in-flight
playbook runs survive an app restart — a gap already flagged as a TODO in Backend-Isolation's
own `main.py`. A process-lifecycle change, independent of flow or task logic. Block-level
durability is already handled as a side effect of PR 8 and PR 9, since a work pool's worker
tracks in-flight block runs independently of the backend process; this PR closes the remaining
gap at the playbook level.

**PR 13 — Package `manta-blocks` for real separation.** Publish `manta-blocks` as a versioned
artifact — an internal package index is enough — and have the backend depend on that instead
of an editable relative path. Packaging and dependency-declaration change only. Required before
a repo split; skipping it means the split forces this exact change later.

**PR 14 — Containerize the backend.** Add a Dockerfile and compose service for the backend
itself, matching how every other service in the stack runs today. Infra-only, no application
code change. Needed regardless of a repo split or runtime target.

**PR 15 — Per-environment runner images.** Build one image per declared block environment,
already named by the catalogue, instead of one shared image, once more than one environment is
in real use. Build-pipeline change — CI, image tagging, job-template image selection —
independent of application code. Scoped to the PR 7 image.

**PR 16 — Kubernetes work pool.** Register the PR 7 flow against a kubernetes-type work pool
instead of a docker-type one. Prefect's own Kubernetes worker does the pod scheduling; the PR 7
flow body needs no change, since it never talks to Docker or Kubernetes itself — only the pool
registration and job template do. This is the PR that delivers the comparison's Kubernetes
claim: a pool-type change, not a hand-written Kubernetes Jobs client.

## Order of work

PRs 1–6 can run before or alongside PRs 7–11; none of them depend on the dispatch mechanism.
PRs 7 through 11 are strictly sequential. PRs 12–15 can start any time after PR 9 confirms the
new dispatch path works. PR 16 should wait for PR 11, so the docker-pool path has real test
coverage before the same mechanism is pointed at a second runtime.

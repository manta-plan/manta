# Manta PoC Comparison: Playbook Orchestration

Two branches implement the block/playbook orchestration layer described in the product
requirements: `sid/docker-pools-in-docker-dir` ("Docker-Pools") and
`prefect-isolation-backend-integration-claude-poc` ("Backend-Isolation"). Both diverge from
`main` at the same commit. This document compares them and recommends a direction.

## Conclusion

Build the next iteration on Backend-Isolation, but replace its container-launch mechanism
with Prefect's own deployment and work-pool dispatch, the mechanism Docker-Pools already
uses. Backend-Isolation's block and playbook code never imports Prefect or Docker, confirmed
by an exhaustive grep of every file in the package. Docker-Pools' block bodies call Prefect's
`task`/`.submit()`/`.result()` API directly in four of four real block implementations, a
framework dependency baked into modeling code. That works against requirement 1
(model-agnostic) and against the repo-separation goal, since a block library that imports
Prefect stays tied to one orchestrator wherever it lives. Backend-Isolation also validates
every playbook run twice before any container starts, records run provenance independent of
Prefect's own retention, and is the only one of the two PoCs whose container-execution path
has real automated test coverage, including a genuine end-to-end run through Docker and
Prefect. Docker-Pools' matching mechanism, a native Prefect docker work pool, is exercised
only by hand; its own integration test says so directly. Docker-Pools still has real,
specific advantages: block dispatch reuses Prefect's own primitives instead of reimplementing
them, its path to a Kubernetes work pool is a pool-type swap rather than a hand-written pod
client, and its Docker socket access is confined to an internal batch worker rather than a
process the API backend spawns. The recommendation keeps that mechanism, grafted onto
Backend-Isolation's cleaner package boundary, rather than adopting either PoC whole. See
[A hybrid worth considering](#a-hybrid-worth-considering) and the
[Recommendation](#recommendation).

## What each branch actually builds

### Docker-Pools (`sid/docker-pools-in-docker-dir`)

A block is a Prefect flow. Deploying it with `Flow.to_deployment()` registers it against a
work pool. Manta's dev stack uses a **docker**-typed pool, so Prefect's own `DockerWorker`
spawns a throwaway container per block run (`docker/provision.py`, `manta_blocks/entrypoint.py`).
A playbook is a second Prefect flow, built by walking a Pydantic step graph at deploy time.
A same-environment step calls its block's flow directly; a different-environment step
dispatches through `run_deployment` and polls for a result. The playbook flow deploys to a
**process**-typed pool, since it waits out an entire run and a container per playbook run
would sit idle for hours. `docker/` owns all Docker-specific work-pool code; `manta-blocks`
(the framework) and `manta-batteries` (the PyPSA block library) carry none of it. A
contributor writes and tests blocks and playbooks entirely inside those two packages, using
the same Prefect-based engine Manta itself uses, pointed at process-type pools instead of
docker-type ones for local testing.

### Backend-Isolation (`prefect-isolation-backend-integration-claude-poc`)

A playbook is one generic Prefect flow, `run-playbook`, parameterized by the playbook
document itself rather than compiled per playbook — there is exactly one deployment. Inside
that flow, each block step is a Prefect task whose body calls the Docker SDK directly
(`docker.from_env().containers.run(...)`, `backend/src/manta/workflows/playbook_flows.py`) to
spawn and drive a container. It never touches a Prefect work pool or worker.
`manta-blocks` — holding both the block library and the playbook engine in this PoC — imports
neither Prefect nor Docker anywhere; all orchestration-specific code lives in the backend's
own `playbook_flows.py`. A contributor writes and tests blocks and playbooks in pure Python,
no Prefect or Docker involved, using a `LocalStepRunner` that calls the same
`execute_playbook` function Manta's Prefect-backed `DockerStepRunner` does. The branch's
design notes (`QA.md`) state this is deliberately one orchestration engine with a swappable
last-mile transport, not two.

## Comparison by dimension

### Fit to the requirements

| # | Requirement | Docker-Pools | Backend-Isolation |
|---|---|---|---|
| 1 | Model-agnostic | Partial — blocks are wrapped as Prefect flows; real blocks call Prefect's task API directly | Satisfies — zero Prefect/Docker imports in block or playbook code |
| 2 | Modular | Satisfies — named steps, nested playbooks as steps | Satisfies — same graph model, same nesting |
| 3 | Reproducible | Partial — playbook, config, frozen input recorded; no block/image version | Partial — playbook doc, config, I/O URLs recorded; no block/image version |
| 4 | Output visibility | Satisfies — live S3-prefix listing per run | Satisfies — live S3-prefix listing per run |
| 5 | Configurable | Partial — flat per-step config; globals don't reach block settings | Partial — same gap, plus no partial-config merge at the API |
| 6 | Validating | Mostly — one path (`build_flow`/`to_flow`) skips validation | Satisfies unconditionally — validated at the API and again inside the flow |
| 7 | Contribution | Satisfies for code; a new playbook needs a hand-authored DB migration | Satisfies for code; a new playbook needs a repo commit, no migration |

**1. Model-agnostic.** Docker-Pools only partially satisfies this. `MantaBlock.flow` is
implemented as a Prefect `Flow` (`manta_blocks/core.py:191-226`), so every block's `flow()`
method is bound by that wrapping. Real block implementations go further:
`time_cluster.py:7`, `overnight_capacity_expansion.py:7`, `myopic_capacity_expansion.py:7`,
and `rolling_horizon_dispatch.py:7` each `from prefect import task` and call
`.submit()...result()` inside `flow()`. A block author has to know Prefect's task API, not
just domain logic. Backend-Isolation satisfies it: no file under `manta-blocks/src/blocks` or
`manta-blocks/src/playbooks` imports Prefect or Docker. A block is a plain Python class, and
swapping the orchestrator underneath would touch nothing in this package.

**2. Modular.** Both satisfy this equally. Both represent a playbook as a named list of
steps, and both let a playbook step be another whole playbook. Neither has built the
post-MVP drag-and-drop UI target — out of scope for a PoC either way.

**3. Reproducible.** Both partially satisfy this, and miss the same thing. Docker-Pools
records the playbook, by foreign key to an immutable `playbooks` row, its resolved config,
and a frozen copy of the input; a code comment flags that a full document snapshot is
deferred until playbooks become editable. Backend-Isolation records the playbook document,
resolved config, and input/output URLs directly on the run row, independent of Prefect's own
retention. Neither records which version of the block library, or which image digest,
actually ran a given block — two runs of "the same" playbook could silently use different
block code in both.

**4. Output visibility.** Both satisfy this the same way: a `GET /runs/{id}/outputs` route
lists S3 objects under a per-run prefix, and blocks write outputs directly to that prefix
rather than through the orchestrator, so the listing is live while a run is still in
progress.

**5. Configurable.** Both partially satisfy this, with the identical documented gap: a step
only ever sees `config[step.name]`. A playbook-level `globals` value reaches `when:`
conditions and nested-playbook inheritance, never an individual block's settings — so a
playbook-wide default like `solver=highs` still has to be repeated on every step that needs
it, in both branches. Backend-Isolation adds a second, unrelated restriction at the API
boundary: a run takes either a playbook's full default config or a fully specified override,
never a partial one, by explicit design choice. Neither branch has a generic layered-merge
mechanism; both need one.

**6. Validating.** Docker-Pools validates on every path that actually starts a run —
`deploy()`, `run_playbook_locally()`, and the backend's own `create_run` all validate first —
but `build_flow`, and the `Playbook.to_flow` method that calls it, do not validate, so a
caller reaching execution through that entry point bypasses the gate. Backend-Isolation
validates unconditionally on both entry points that exist: the API request, and again inside
the flow itself. No route to execution skips it.

**7. Contribution.** This is the requirement most likely to separate the two approaches, so
it gets the most space here.

Both PoCs get the hard part right. A modeler outside the Manta team can write a block,
register it, and run a full test suite against it with zero Prefect, zero Docker, and zero
access to the `manta` repo's CI or backend. Docker-Pools' loop is `uv sync && uv run pytest`
inside `manta-blocks`/`manta-batteries`, or `playbook.run(record, config)` to execute a whole
playbook in one process. Backend-Isolation's loop is the same shape: `uv run pytest` against
`LocalStepRunner`, or `playbook.run(...)` with local filesystem paths standing in for S3. For
this first step, both are equally light.

They diverge on two things past that: what a contributor needs Prefect for, and what it
takes to make new work visible through Manta.

*Testing dispatch, not just block logic.* Docker-Pools ships its Prefect wiring — the
flow-of-flows, the deployment registration, dispatch across environments — inside
`manta_playbooks`, the same portable package a contributor imports. A contributor who wants
to exercise real dispatch, not just a block's own logic, runs a bare, non-Docker Prefect
server and process-type work pool workers on their own machine, and gets the identical
dispatch code path Manta's production docker pool uses, differing only in pool type.
Backend-Isolation's dispatch code — the actual Prefect flow, the container-spawning logic —
lives in `backend/src/manta/workflows/playbook_flows.py`, inside the app, not inside
`manta-blocks`. A contributor has no way to exercise real Prefect-driven dispatch without
running the Manta backend itself. The closest self-contained check is running the block
library's own test suite inside the `blocks-runner` image, which verifies environment parity,
not dispatch or nesting behavior under Prefect. This is a real edge for Docker-Pools.

*Getting new work in front of Manta users.* Docker-Pools needs two monorepo-touching steps
to make new work visible: committing a regenerated `catalogue.json`, needed either way, and
hand-authoring an Alembic migration that inserts a row into the `playbooks` table, since no
`POST /playbooks` route exists yet. Writing a database migration is a backend-engineering
task, not a modeling task, which works against requirement 7's premise that a contributor
isn't an app developer. Backend-Isolation needs the same catalogue commit, but a new playbook
only needs a YAML file committed under `manta-blocks/src/playbooks/library/`; the backend
reads the library at request time, with no database row and no migration to author. A new
block needs nothing beyond the catalogue commit — the single runner image installs whatever
`manta-blocks` contains, so a new block is included automatically on the next rebuild.

Net: for a block, both are equally light. For a playbook, Backend-Isolation's path back into
the product is lighter. For exercising genuine Prefect dispatch outside of Manta,
Docker-Pools' path is more complete.

### Fit to forward-looking constraints

**Repo separation.** Docker-Pools' `manta-blocks` (the framework) has no monorepo-relative
code and would separate cleanly on its own. `manta-batteries` (the actual block library) is
different: its `pixi.toml` hardcodes `manta-blocks = { path = "../manta-blocks" }`, assuming
both packages sit in one checkout; `docker/job.Dockerfile` and `docker/control.Dockerfile`
both `COPY` both directories from a single repo-root build context; `docker/provision.py`
hardcodes the in-image path both packages land at. Splitting `manta-batteries` into its own
repo today breaks the pixi manifest and both Dockerfiles — real code changes, not mechanical
ones. Its blocks also import Prefect directly, which ties the library to one orchestrator
regardless of which repo it lives in.

Backend-Isolation's `manta-blocks` — holding both the block library and the playbook engine
in this PoC — imports nothing from Manta, Prefect, or Docker anywhere, and its own README
states the intent to lift it out unchanged. The coupling instead sits on the backend's side:
`backend/pyproject.toml` depends on it through an editable relative path, and the backend
imports its modules directly and non-trivially — parsing playbook documents, validating them,
listing the catalogue — all in-process. Splitting the repo would need the backend to depend
on a real, versioned release of `manta-blocks` instead of a path. That is packaging
discipline, not a code or infrastructure rewrite, and it touches one dependency declaration
and a release process, not multiple Dockerfiles.

Verdict: Backend-Isolation's contributor-facing code is already fully decoupled; what remains
is a packaging step on Manta's side. Docker-Pools' contributor-facing code has three separate
coupling points — a path dependency, two Dockerfiles, and direct Prefect imports — that would
all need to change at once.

**Kubernetes runtime.** Docker-Pools' block execution already goes through a pool-type seam
Prefect itself defines (`pool_factory`, documented in `manta_playbooks/deploy.py` as "where
Kubernetes will attach"). Swapping the docker pool for Prefect's native Kubernetes work pool
needs no new pod-lifecycle code, since Prefect's Kubernetes worker already implements it.
What does have to change is real: block and playbook containers today share a Docker volume
carrying Prefect's local-disk result storage between the orchestrator and job containers on
one host, and a Kubernetes work pool schedules pods onto any node, with no shared filesystem
by default. Getting this design onto Kubernetes needs S3-backed Prefect result storage — a
documented but unimplemented plan in this branch — before the pool-type swap can work at all.

Backend-Isolation's `_run_block_in_container` is Docker-SDK-specific from top to bottom:
image lookup, container spawn, log streaming, wait, cleanup, all behind a `StepRunner`
protocol built for exactly this kind of swap. The design notes name the concrete plan, a
`K8sJobStepRunner` behind the same seam. Getting there needs a full rewrite of that
container-lifecycle code against the Kubernetes Jobs/Pods API — work Prefect's own Kubernetes
worker already does, and that Docker-Pools would inherit for free by changing a pool type.
Backend-Isolation also currently needs the backend process itself, or a subprocess it spawns
sharing its environment, to hold Docker daemon access; the design notes call this
root-equivalent and name the Kubernetes swap as the fix.

Verdict: Docker-Pools' path to Kubernetes is a configuration and result-storage change.
Backend-Isolation's is a from-scratch reimplementation of container lifecycle against a
different API, though one already contained by an interface that exists today.

### Mapping to Prefect

| | Docker-Pools | Backend-Isolation |
|---|---|---|
| A block is | a Prefect deployment (a flow, deployed to a work pool) | a Prefect task whose body drives a container directly |
| A playbook is | a Prefect flow of flows/deployments, dispatched with `run_deployment` | one generic Prefect flow, parameterized by the playbook document |
| Fits Prefect's grain | Yes — every unit of work is a Prefect-native construct | Only at the playbook level; block isolation steps outside Prefect's dispatch machinery |
| Leaks Prefect into modeling code | Yes — real blocks call Prefect's task API directly | No — zero Prefect/Docker imports in blocks or playbooks |
| Free from Prefect | Retries, concurrency limits, state tracking, the UI — reachable via native deployment/work-pool options, though mostly unconfigured today | Playbook-level dispatch, state, and UI; nothing at the block level |
| Reimplements | Little — the graph-walking and validation layer, which Prefect has no equivalent for | Container lifecycle, log capture, exit-code handling: roughly 70 lines standing in for what a work pool's worker would otherwise provide |

Docker-Pools maps a block onto exactly the primitive Prefect built for this: a deployment,
dispatched to a worker pulling from a pool. Retries, concurrency limits, and state tracking
are a configuration change away, not something to build. The cost is structural, not
incidental: a Prefect docker work pool's job template sets every spawned container's command
to `pixi run -e {env} prefect flow-run execute` (`docker/provision.py`), so a container must
have Prefect installed to be trackable as a deployment run at all. That is why the block image
bundles Prefect, why the base class wraps every block as a `Flow`, and why real blocks reach
for Prefect's task API directly inside that same code — the framework leaks upward into
modeling code as a direct, structural consequence of the mapping chosen, not a choice
Docker-Pools could avoid while keeping this mapping.

Backend-Isolation only maps the playbook level onto Prefect. A block is a Prefect task, but
the task's body steps outside Prefect entirely to talk to the Docker daemon, so none of
Prefect's dispatch, retry, or concurrency machinery for deployments applies to a block's
container. The design notes name this choice deliberately: using Prefect's docker work-pool
worker for blocks would put Prefect and flow code inside the block image, the exact coupling
this approach exists to avoid. The trade is real — this branch owns roughly 70 lines of
container-lifecycle code that a Prefect work pool's own worker would otherwise supply, and it
currently has no retry or timeout on a block run as a direct result.

### Software qualities

**Elegance.** Docker-Pools' "block equals deployment" contract has one real complication:
cross-environment dispatch goes through `run_deployment` and polls for a result rather than a
direct call, so the graph-walking code has two different paths for same-environment versus
different-environment steps. Backend-Isolation's `execute_playbook` is a single,
orchestration-agnostic function, called identically by the local and Manta-backed paths; what
differs between them is a roughly 30-line `StepRunner` implementation, not a structural
branch in the engine. This is a materially simpler design.

**Maintainability.** Docker-Pools spreads Docker-specific logic correctly into `docker/`, but
the split leaves three places that must move together for a change to take effect:
`docker/provision.py`'s job template, `manta_playbooks/deploy.py`'s deployment registration,
and the compose file's worker services. Backend-Isolation centralizes the equivalent logic in
one module, `playbook_flows.py` — a change to how a block's container runs touches one file.

**Extensibility.** Both support a new dependency environment by adding a new pixi/uv
environment name, and both currently bake every environment into one shared image rather than
building one image per environment. Docker-Pools' resource-profile story is closer to native,
since a work pool's job template already expresses CPU/memory per job; Backend-Isolation would
need to add resource limits to its own `containers.run()` call by hand.

**Scaling.** Docker-Pools scales block concurrency the way Prefect scales any work pool: more
workers, or, once configured, a work-pool concurrency limit. A Kubernetes work pool inherits
this directly. Backend-Isolation scales however many `run_block` tasks the backend's own
process can drive concurrent Docker SDK calls for, with no concurrency limit configured today
— a bottleneck that needs explicit throttling code, where Docker-Pools' bottleneck (worker
count) is already a tunable, first-class Prefect concept.

**Robustness.** Neither branch has retries or timeouts configured on a block run — an
identical gap in both. Docker-Pools tolerates Prefect's and Manta's state disagreeing (a flow
run Prefect no longer knows about reports as `"UNKNOWN"` rather than erroring) and always
removes a crashed container through `auto_remove`. Backend-Isolation always removes a crashed
or failed container through a `finally` block and distinguishes three block failure modes —
non-zero exit, missing image, silent success with no result — but neither branch separately
times out a genuinely hung container. Backend-Isolation also concedes durability Docker-Pools
already has: its playbook-serving process is a subprocess the app spawns at startup and does
not survive an app restart, flagged as a TODO in its own `main.py`, while Docker-Pools'
playbook flow runs in an independent, long-lived worker container.

### Operational and security posture

Neither PoC's dev stack is meant for production as shipped — both READMEs say so directly.
Beyond Prefect server and Postgres, both need an S3-compatible store (SeaweedFS in dev) and,
unrelated to playbook execution, Keycloak. Neither uses Docker-in-Docker and neither runs a
privileged container.

Where they differ is who holds the Docker socket. Docker-Pools mounts
`/var/run/docker.sock` into one dedicated internal worker container, which has no HTTP
interface and is never reachable from outside the stack; the API-serving backend never
touches Docker at all. Backend-Isolation's Docker access is held by the backend's own process
tree: the app calls `docker.from_env()` from a subprocess it spawns at startup, sharing its
environment, and this branch does not containerize the backend at all, so in practice that
access exists wherever the backend itself runs. Root-equivalent Docker access sitting behind
a request-serving API surface is a materially larger blast radius than the same access
confined to an internal batch worker with no external interface. Backend-Isolation's design
notes acknowledge this cost directly and name the Kubernetes migration as the intended fix,
not a stopgap already applied.

### Developer and debugging experience

Both let an engineer run a single block or a whole playbook in one process with no
infrastructure — `playbook.run(...)` in Docker-Pools, `LocalStepRunner` in Backend-Isolation
— and both surface failures the same way at the infrastructure layer: a failed run's state
and logs live in Prefect, read through its API or UI.

One real asymmetry: Backend-Isolation's block-level failures carry more specific information
back. A `BlockRunFailedError` distinguishes a non-zero exit, a missing runner image, and a
clean exit with no result line, each with its own message. Docker-Pools' worker surfaces
whatever Prefect reports for a deployment's flow run — accurate, but coarser, since the
failure detail lives inside the deployed flow rather than in a purpose-built error type at the
dispatch boundary.

Testability differs more. Both frameworks have thorough, infrastructure-free unit suites
using fakes. The gap is at the orchestration-mechanism layer: Backend-Isolation's Docker SDK
calls are fully mocked in unit tests and additionally exercised by a real end-to-end
integration test that boots Docker, Prefect, and real containers through `testcontainers`.
Docker-Pools' equivalent mechanism — the actual docker-type work pool — has no automated
coverage. Its own integration test registers a process-type pool instead and notes that
exercising the real docker pool "is exercised outside the test suite for now." The mechanism
Docker-Pools would actually ship to production is the one piece of either PoC that no test
runs.

### End-user experience

**Manta users.** Both expose the same run lifecycle: submit a playbook and config, watch a
run's state, then list its outputs through `GET /runs/{id}/outputs`, a live S3-prefix listing
in both cases. Provenance is available the same way in both: the run row carries the playbook
and config that produced it. Neither yet exposes per-step status or per-step logs through a
Manta-owned route. Docker-Pools' framework already computes a `{step_name: state}` map that
nothing in the backend calls yet; Backend-Isolation has the equivalent information queryable
from Prefect directly but no dedicated route either. This is a shared gap, not a
differentiator — see
[manta-poc-hybrid-implementation-plan.md](manta-poc-hybrid-implementation-plan.md).

**External contributors.** Covered under requirement 7 above: Backend-Isolation is lighter
for getting a new playbook live; Docker-Pools is more complete for testing real Prefect
dispatch outside Manta.

### Config and validation mechanics

Covered under requirements 5 and 6 above. The headline: neither branch has a generic
layered-config mechanism, and Backend-Isolation is the more consistently validated of the
two. Both need the same fix — see
[manta-poc-hybrid-implementation-plan.md](manta-poc-hybrid-implementation-plan.md).

### A hybrid worth considering

The strongest version of either PoC borrows from the other, with one detail that has to be
stated precisely rather than glossed over. Genuine Prefect-native dispatch needs Prefect
present inside whatever container gets spawned: a Prefect docker work pool's job template
runs `prefect flow-run execute` in every job container it starts (`docker/provision.py`), so
there is no way to get a container dispatched and tracked as a first-class deployment run
without Prefect installed in it. The hybrid below cannot keep Backend-Isolation's block image
exactly as bare as it is today. It can still keep Prefect out of block code.

The shape: keep Backend-Isolation's package boundary — a `manta-blocks` with zero Prefect or
Docker imports, one generic step-execution engine, and a `StepRunner`-shaped seam for how a
step actually runs. Add one small, backend-owned flow, not part of `manta-blocks`, whose
entire job is to run the existing `python -m blocks.run_one` entrypoint as a subprocess and
relay its result — the same contract Backend-Isolation's `DockerStepRunner` already reads,
just invoked one layer further in. Build that flow, and Prefect itself, into the runner image
alongside `manta-blocks`. Deploy that one flow, not each block individually, to a work pool
the way Docker-Pools already deploys blocks, and have the `StepRunner` implementation call
`run_deployment` against it instead of the Docker SDK directly.

That gets native retries, concurrency limits, and state tracking, moves Docker or Kubernetes
socket access onto a dedicated worker instead of the API backend, and turns the eventual
Kubernetes swap into a pool-type change for that one flow instead of a rewrite of
container-lifecycle code. What it costs: the runner image is no longer free of orchestration
framework code — only the block classes a contributor writes still are.
[manta-poc-hybrid-implementation-plan.md](manta-poc-hybrid-implementation-plan.md) sequences
every PR for exactly this shape.

## Recommendation

Build on Backend-Isolation. Its block and playbook code has no framework coupling to remove
later, its validation and reproducibility model has no gap Docker-Pools doesn't share, and it
is the only one of the two whose actual isolation mechanism has real test coverage today,
including a genuine end-to-end run.

The strongest argument against this pick: Backend-Isolation's block dispatch works against
Prefect's own grain, not with it. It reimplements roughly 70 lines of container lifecycle
management that Prefect's own docker work pool already provides, it has no retry or timeout
on a block today, and its Docker access sits behind the API-serving backend rather than an
isolated worker — three real costs Docker-Pools doesn't carry, because Docker-Pools dispatches
blocks the way Prefect expects deployments to be dispatched. If Manta's priority is minimizing
new infrastructure code and keeping every unit of work inside Prefect's own primitives,
accepting Docker-Pools' cost of Prefect leaking into block code and a rougher
repo-separation story for `manta-batteries` in exchange, Docker-Pools is the better foundation
instead.

This recommendation does not depend on today's repo layout or today's runtime. If anything,
it gets stronger once those change. A repo split rewards Backend-Isolation's already-clean
package boundary and costs it only a packaging step: a versioned `manta-blocks` release
instead of a path dependency. Docker-Pools' equivalent split has to rewrite two Dockerfiles
and a pixi manifest, and still carries Prefect coupling inside the block library that moves
with it. A Kubernetes migration rewards reusing Prefect's own Kubernetes work pool for the
wrapper flow the hybrid above dispatches blocks through — Docker-Pools' mechanism today,
adopted behind Backend-Isolation's `StepRunner` seam — over hand-writing a Kubernetes Jobs
client against Backend-Isolation's current Docker SDK code. Either way, the shape to build
toward is the hybrid described above: Backend-Isolation's boundary, Docker-Pools' dispatch
mechanism, and Prefect confined to the runner image rather than block code.

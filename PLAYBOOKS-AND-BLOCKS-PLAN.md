# Playbooks and blocks — plan

## 1. The problem and the shape of the solution

Today Manta can run exactly one thing. `POST /v1/runs` takes a single number, `num_pi_digits`, and submits a hardcoded Prefect deployment named by a constant in [run_service.py:25](backend/src/manta/services/run_service.py:25). There is no way to say *what* to run, because there is nothing to choose from. The preceding PR fixed how work executes — each job now gets its own container — but it did not change what can be asked for. The contract is still "run the one job we know about."

What we are building is the part that makes that contract general. Two ideas:

- A **block** is one unit of energy-modelling work — cluster a network's time series, solve a capacity expansion. Blocks live in a separate repository, carry their own dependencies, and know nothing about Manta.
- A **playbook** is a recipe naming blocks in order, saying which block's output feeds which block's input. Playbooks are rows in Manta's database, written as YAML.

Starting a run becomes: pick a playbook, press go.

The division of labour is strict and worth stating once, plainly:

- **Manta owns the playbook.** It stores the document, and it owns the **interpreter** — the code that reads a playbook and decides what runs, in what order, with which inputs. That is Manta's own code, in Manta's repository.
- **The blocks repository owns the blocks.** Manta holds no block code, imports no block code, and has no opinion about what a calculation means.
- **The interpreter spawns one container per block.** For each step, it starts a fresh container that pulls that block's code and dependencies from the blocks repository, hands it its configuration and its inputs, and takes back a reference to what it produced. "Please run this" and "what was the result" is the entire conversation.

This is more than a feature. It is where Manta stops being an application with a calculation bolted on and becomes a platform that runs other people's modelling work. The property that matters most is that **adding a block requires no change to Manta at all** — no migration, no deploy, no new image. Someone commits to the blocks repository, and a playbook can name it the same day.

There is an extensive proof of concept in the blocks repository covering both halves. Its `playbooks` package is the interpreter we are adopting, and it moves into Manta. Its `blocks` package stays where it is, largely untouched. Prefect remains under the hood and stays there — it appears in no request, no response, and no vocabulary a user reads.

## 2. Entity definitions, as code

### 2.1 The Playbook entity

```python
# backend/src/manta/entities/playbook.py
from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from manta.entities.base import Base


class Playbook(Base):
    __tablename__ = "playbooks"

    name: Mapped[str]
    description: Mapped[str | None] = mapped_column(Text)
    # The playbook document and the settings document, verbatim YAML. The
    # interpreter (`manta_playbooks`) owns their shape; the database stores
    # them as written so what a user wrote is what gets executed.
    definition: Mapped[str] = mapped_column(Text)
    configuration: Mapped[str] = mapped_column(Text)
```

The decisions behind it:

**One entity, and only one.** No step table, no input table. The interpreter already models the document; putting the same structure in SQL would mean two definitions of one thing, kept in step forever, for queries nobody is making.

**YAML, stored verbatim.** The document is the thing users author, and the interpreter already parses YAML. Storing text means comments and formatting survive a round trip.

**Two documents, one row.** The PoC separates the recipe from its settings — a playbook says *what runs in what order*, the settings document says *with which values*, filed by step name plus a shared `globals` section. Worth keeping, and it costs a column rather than an entity.

**Which block version to run is not stored here.** It lives in the definition, on the step, next to the block it pins — see §3.

**Identity.** Inherits `Base` ([base.py](backend/src/manta/entities/base.py)) for the house dual key: internal integer `id` for foreign keys, public `uuid` as the only identifier crossing the API boundary.

**Not scoped to a project.** A playbook describes a procedure, not a dataset — the same recipe applies to any network you point it at. Scoping now would mean copying playbooks to reuse them. Runs stay scoped to projects, so nothing the frontend does today changes.

**Mutable.** No version table, no locking once a run exists. What a run submitted is captured in its flow run's parameters, so an in-flight run is unaffected by an edit.

### 2.2 Changes to the Run entity

```diff
 class Run(Base):
     __tablename__ = "runs"

     project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
+    # TODO: a run can currently only be started from a stored playbook. Runs
+    # that execute something never persisted as a playbook — an ad-hoc
+    # document, a one-off block — are a later problem, as is recording which
+    # version of a playbook a given run actually executed.
+    playbook_id: Mapped[int | None] = mapped_column(
+        ForeignKey("playbooks.id", ondelete="SET NULL")
+    )
     prefect_flow_run_id: Mapped[UUID] = mapped_column(unique=True)
```

That is the entire change. `SET NULL` for the same reason `project_id` already uses it: a run outlives its parents.

**No per-step table, and no block registry table.** Per-step state is already tracked — each step is a child flow run. A block registry would mirror a repository Manta does not own, which means a sync job, a staleness question, and a failure mode where a block exists but Manta refuses to run it. It would also make adding a block require a write on Manta's side, which is the one thing this design exists to prevent.

## 3. One worked example

A playbook that solves capacity expansion, then runs rolling-horizon dispatch against the capacities the first step produced. Both blocks are real ones from the PoC's library, and the wiring is genuine — `RollingHorizonDispatch` declares `INPUTS = {"capacity_source"}`.

`playbooks.definition`:

```yaml
name: expand-then-dispatch

steps:
  - name: expansion
    block: overnight_capacity_expansion
    version: 9f2c1ab4d0e7c5b18a3f6d92e4c7b0a1f8d3e6c2

  - name: dispatch
    block: rolling_horizon_dispatch
    version: 9f2c1ab4d0e7c5b18a3f6d92e4c7b0a1f8d3e6c2
    inputs:
      capacity_source: ${steps.expansion.output}
```

`playbooks.configuration`:

```yaml
globals: {}

expansion: {}

dispatch:
  optimize_config:
    horizon: 168
    overlap: 24
```

`version` is a git ref in the blocks repository, pinned per step so a run is reproducible. It is optional; omitted, the runner uses the repository's default branch, and the run is then only as reproducible as that branch is stable. Two steps may pin different versions — each step gets its own container and its own checkout, so nothing forces them to agree.

End to end:

1. **`POST /v1/runs {"project_uuid": ..., "playbook_uuid": ...}`.** `RunService` loads the playbook row and calls `run_deployment("run-playbook/manta", parameters={"definition": <yaml>, "configuration": <yaml>, "record": {...}}, timeout=0)` — the same fire-and-forget shape as today's [create_run](backend/src/manta/services/run_service.py:76). One row goes into `runs` holding the returned flow run id; the API returns `201` immediately. Sending the documents rather than a reference means a mid-run edit is harmless.

2. **The watcher starts one container** from the worker image — the interpreter. Same image, same mechanism as any other job; the watcher does not know this one orchestrates.

3. **The interpreter reads the documents.** `manta_playbooks.document.parse` turns them into a `Playbook`; `execution.build_flow` compiles it. Steps run in list order, threading a record — `{"url": ...}`, a reference to data, never the data — from step to step.

4. **The interpreter spawns a container for `expansion`.** It submits a block job carrying `{"block": "overnight_capacity_expansion", "version": "9f2c1ab…", "config": {...}, "inputs": {}, "record": {"url": "..."}}` and waits. A block name, a version, its configuration, its inputs: that is the entire contract, and Manta never sends anything else.

5. **The block container runs.** Its runner checks out the blocks repository at `9f2c1ab…`, enters `library/overnight_capacity_expansion/`, builds *that block's own* pixi environment, and runs the block inside it. The block fetches whatever its input record points at, solves, writes its result wherever it chooses, and returns a new `{"url": ...}`. The container exits.

6. **The interpreter spawns a container for `dispatch`.** Its `capacity_source` input resolves to the record `expansion` returned and is merged into its configuration. A third container starts, builds a completely separate environment, and runs the dispatch block.

7. **Reading it back.** `GET /v1/runs/{uuid}` gives overall status, `GET /v1/runs/{uuid}/steps` gives each step's state, and `GET /v1/runs/{uuid}/logs` returns lines from the interpreter and both block containers, each attributed to its step.

Three containers, two independently-built environments, and nothing in Manta that knows what PyPSA is.

## 4. What transfers from the PoC

### 4.1 Into Manta

This table is only what lands in **Manta's repository** — which is to say, the interpreter and nothing else. Every row comes from the PoC's `playbooks` package. The PoC's `blocks` package is not here because none of it is coming: `MantaBlock`, `DataRecord`, the registry, the block entrypoint, the environment handling, the library blocks and the PyPSA helpers all stay in the blocks repository, where Manta never sees them.

Anything not listed is not being transferred for now, mostly because it supports validation, graph drawing, or playbook nesting — all out of scope for this slice.

| PoC component | Verdict | Reasoning | Adjustments needed |
|---|---|---|---|
| `yaml_io.py` — `PlaybookDoc`, `StepDoc`, `InitialDataDoc`, `WhenDoc`, `parse_doc`, `playbook_from_doc`, `load_config` | transfer with changes | The document format we are adopting wholesale; it already accepts the identical document from a file or a browser | `StepDoc` gains an optional `version`. The `Catalogue`/`BlockSpec` resolution goes — a step's block is a name and a version, and Manta resolves it no further. Nested-playbook loading goes with it |
| `playbook.py` — `Playbook`, `BlockStep`, `OutputRef`, `When`, `StepHandle`, `Playbook.active` | transfer with changes | The in-memory model and its reference resolution are the interpreter | `BlockStep` holds a name and a version instead of a `BlockSpec`, so nothing needs the `blocks` package importable |
| `${steps.<step>.output}` reference syntax and `_REF_RE` | transfer as-is | Readable, implemented, and backward-only by construction, which keeps a future DAG additive | None |
| Separate settings document (`globals` + per-step sections) | transfer as-is | Keeps the recipe readable and lets one recipe run with different values | Stored as a second column rather than a second file |
| `execution.py` — `build_flow`, the sequential spine, `_wire_up`, `_run_block_step` | transfer with changes | The sequential spine plus explicit wires is the execution model | Every step spawns a container. The in-process branch, the `dispatch` flag and `run_playbook_locally` all go |
| `dispatch_block` | transfer with changes | The mechanism for "run this step elsewhere and wait for its record" | Becomes the block-container spawn, targeting one generic `run-block/manta` deployment with the block name and version as parameters, rather than a deployment per block. See §5 |
| `control.py` — `start_run` sending the document rather than a reference | transfer with changes | Sending what was on screen is why a mid-run edit is harmless | Becomes `RunService.create_run` |
| `control.py` — `run_status`, `_step_states` | transfer with changes | Walking child runs for per-step state is exactly what the steps endpoint needs | Becomes `RunService.get_run_steps`, returning Manta's status vocabulary rather than Prefect's |
| Frozen Pydantic models throughout | transfer as-is | Good convention, and it matches Manta's existing DTO style | None |

### 4.2 Changes needed in the blocks repository

Nothing is added to the blocks repository and nothing moves into it. Four changes are needed there, all consequences of decisions made on Manta's side:

| Change | Reasoning |
|---|---|
| Split the repository-wide `pixi.toml` into one `pixi.toml` and lockfile per block, and move `library/` out of the installable package | Each block owns its environment. See §6.1 |
| `MANIFEST` and `ENV` resolve against the block's own directory by convention | Follows from the split; the PoC already has `MANIFEST` for pointing a block at its own manifest |
| `entrypoint.py` — `run_block` takes a block name, configuration and inputs as plain JSON, and returns a record as plain JSON | It is now invoked by a runner that has no playbook context, and the wire format has to be readable by an interpreter that cannot import `blocks` |
| Remove `src/playbooks/` | The interpreter moves to Manta. The PoC already guarantees `blocks` never imports `playbooks`, so this is a clean deletion |

## 5. The playbook interpreter

The interpreter is **Manta's code**, in Manta's repository. It is adopted from the PoC's `playbooks` package rather than written from scratch, but ownership moves: this is the piece that decides what runs and in what order, and that decision belongs to the application, not to the library of calculations.

It lives in a new package in the monorepo, alongside `backend/`, `frontend/` and `worker/`:

```
playbooks/
└── src/manta_playbooks/
    ├── document.py     # PlaybookDoc, StepDoc, WhenDoc, parse — the YAML shape
    ├── playbook.py     # Playbook, BlockStep, OutputRef, active() — the model
    └── execution.py    # build_flow — the spine, the wiring, the spawn per step
```

A third package rather than a folder inside one, because it has two consumers: the **worker** executes it, and the **backend** reads a stored document to list a run's steps for the steps endpoint. One owner, one definition of the format, and neither the backend nor the worker depends on the other — preserving the separation the preceding PR established.

Responsibilities:

- **`document.py`** — turns the two YAML documents into a `Playbook`. Validates the document is a playbook at all, and resolves each input's `${steps.<step>.output}` into an `OutputRef`.
- **`playbook.py`** — the in-memory model. `Playbook.active(config)` decides which steps run, in the one place everything consults.
- **`execution.py`** — compiles the playbook into a Prefect flow. The spine threads a record step to step; `_wire_up` pulls a named earlier result into a named setting; each step spawns a container.

Crucially, **`manta_playbooks` does not import the blocks package**. A step holds a block name and a version, and the interpreter never resolves either to a class, a schema, or a description. It passes them to the container and receives `{"url": ...}` back. This is what lets the interpreter live in Manta without Manta acquiring any modelling dependency, and it is why the PoC's `Catalogue` and `BlockSpec` resolution is dropped rather than carried.

Three changes from the PoC, all forced by containers:

**Execution always spawns.** The PoC can run a step in-process when the block's environment matches the current one. Under container-per-block there is no such case — the interpreter never has block dependencies. The in-process branch goes.

**One deployment instead of one per block.** The PoC registers a Prefect deployment per `(block, environment)` pair. Under that scheme, adding a block means registering a deployment — an operation outside the blocks repository, breaking the rule that adding a block is purely additive. So the spawn targets a single permanent `run-block/manta` deployment and passes the block's identity as parameters.

**The interpreter asks the watcher for containers; it does not call Docker.** It spawns a container per block by submitting a block job, and the watcher — unchanged from the preceding PR — turns that into a container. Keeping one component responsible for containers is what makes the Kubernetes move a swap rather than a rebuild, and it means the interpreter is testable without a Docker socket.

The Prefect surface is then three things: **a playbook run is one flow run, each step is a child flow run, and two deployments exist forever.** No tasks, no caching, no retries, no work-pool arithmetic.

One piece of Prefect configuration this does require: **result persistence must be turned on**, pointing at a shared volume locally. The PoC gets away without it because its tests run in one process; once a step's record has to come back out of a container, Prefect needs somewhere durable to have put it. A settings change, not a code change, and the item most worth proving first.

## 6. The block contract

Everything in this section is the **blocks repository**. Manta gains nothing here and loses nothing here.

### 6.1 What a block is

What the PoC already made it — a `MantaBlock` subclass, registered by name, declaring what it needs as class attributes — now living in its own directory with its own environment:

```
library/overnight_capacity_expansion/
├── pixi.toml        # this block's dependencies, and nobody else's
├── pixi.lock
└── block.py
```

```python
# library/overnight_capacity_expansion/block.py
@register()
class OvernightCapacityExpansion(MantaBlock):
    """Capacity expansion treating the model as a single moment."""

    ENV = "default"
    CONFIG = OvernightExpansionConfig
    DIMS = BlockDims(requires=frozenset({"snapshot"}))

    def flow(self, record: DataRecord) -> DataRecord:
        ...
```

```toml
# library/overnight_capacity_expansion/pixi.toml
[workspace]
channels = ["conda-forge"]
platforms = ["linux-64"]

[dependencies]
python = ">=3.12"
pypsa = "*"

[pypi-dependencies]
manta-blocks = { path = "../..", editable = true }   # the framework only
```

**Each block owns its environment.** The PoC has one repository-wide `pixi.toml` with `dev`, `pypsa` and `full` environments shared across all blocks, which quietly recreates the problem blocks exist to solve: two blocks wanting different versions of the same library have nowhere to put that disagreement. Splitting per block removes the shared surface. This is not a new mechanism — the PoC already carries a `MANIFEST` attribute for pointing a block at its own `pixi.toml`, used as `pixi run --manifest-path <M> -e <ENV>`. That path becomes the normal case, and by convention it is the block's own directory.

**There is no bespoke manifest file.** An earlier draft invented a `block.toml` and a `requirements.txt`; both are gone and are not coming back. The `pixi.toml` above is not that — it is the dependency tool the repository already uses, applied per block instead of once globally. Everything a bespoke manifest would restate is already declared: dependencies in `pixi.toml` with a committed lockfile; parameters in `CONFIG`, a Pydantic model that is strictly more precise than a table of names; inputs and outputs in `INPUTS` and `OUTPUTS`, with `__init_subclass__` already enforcing that a wired input can hold a record and has a default; and identity in the registered name, which by convention is also the directory name so the runner can find a block before importing any Python.

Writing a new block is therefore: a directory, a `pixi.toml`, and a module. Nothing else, nowhere else.

The repository's top-level `pixi.toml` survives for the framework — the thing that is not a block — and `library/` moves out of the installable package so the framework stays block-free and installable on its own.

### 6.2 Identification and pinning

A block is named by its registered name and pinned by a git ref in the blocks repository, written on the step. Name plus version identifies it completely: the version fixes the code, the `pixi.lock` beside it fixes the dependencies, and together they make a step reproducible. Pinning per step is possible precisely because environments are now per block. Branch names are accepted and discouraged; a mutable ref is an unreproducible run.

### 6.3 How the container gets the code and its dependencies

The worker image is generic. It contains `git`, `pixi`, the interpreter, and a thin runner — and **no block implementation, and not even the blocks framework**. Everything block-related arrives at run time:

1. Fetch the blocks repository into a bare mirror on a named volume, then check out the commit the step pinned.
2. Enter `library/<block name>/` and build that block's environment with `pixi install`, against its own `pixi.toml` and lockfile. This is also what installs the framework, as a path dependency.
3. Run the block inside it — `pixi run -e <ENV> …` — handing it the configuration and inputs as JSON. The registry imports the block by name; `merge_config` folds the wired inputs into its settings; `flow(record)` runs.
4. Stream the container's output into the flow run's logs, and return the resulting record as JSON.

This is what makes a new block free: a block that did not exist when the worker image was built runs in that image without rebuilding it, because the image never contained any blocks to begin with.

**Failure.** Any non-zero exit — checkout, environment build, or the block itself — fails the step, and the logs already carry the reason. Conflicts cannot arise *between* blocks, since no two share an environment; a conflict *within* one block is caught by `pixi` against its committed lockfile, in the blocks repository, before anything reaches Manta.

**Caching.** Cached on one named volume: the git mirror, and each block environment keyed by block name and commit. Nothing per-run is cached. The cost is a volume that grows with no invalidation beyond deleting it — acceptable because the key includes the commit, so a stale entry is impossible by construction, and because the lockfile makes a rebuild deterministic. The benefit is that the second run of a block starts in seconds rather than minutes. Per-block environments do mean identical dependencies get built more than once; pixi's package cache absorbs most of that, and the isolation is worth the rest.

### 6.4 How Manta learns which blocks exist

**It does not, and this is a deliberate revision to the preceding PR.** That PR's registration handshake assumed job code shipped inside the worker image, so registering a job type and building the image were one act. That no longer holds. If the handshake stayed per-job, adding a block would mean rebuilding and redeploying the worker image.

So the handshake's granularity changes, and nothing else about it does. The worker still announces itself at startup, but registers two generic entrypoints — "I can run a playbook" and "I can run a block" — rather than one per job. Manta consequently cannot answer "what blocks exist"; the blocks repository is the answer. Nothing asks until there is a UI that browses blocks, and when there is, the PoC's catalogue is the prior art to return to.

### 6.5 Blocks repository layout

```
blocks/
├── pixi.toml                 # the framework only — no block dependencies
├── src/blocks/               # framework: core, registry, entrypoint, environments
└── library/
    ├── overnight_capacity_expansion/
    │   ├── pixi.toml
    │   ├── pixi.lock
    │   └── block.py
    └── rolling_horizon_dispatch/
        ├── pixi.toml
        ├── pixi.lock
        └── block.py
```

`src/playbooks/` is gone — it is now Manta's. The pi-digit job is not converted, and Manta's copy is not deleted; it simply stops being reachable once `POST /v1/runs` takes a playbook instead of a digit count, which the brief accepts. Nothing is removed from Manta beyond the request field that has to change.

## 7. Execution flow

**One container per block execution, plus one per playbook run for the interpreter.**

Per block, not per playbook run, because the entire reason blocks exist is that they carry incompatible dependencies — and with per-block environments, two steps in one playbook may legitimately want different versions of the same library. Sharing a container would put that disagreement back. One container per block also makes a failure survivable and the logs separable.

The interpreter gets its own container rather than running in the backend, because it is long-lived and must not occupy a request thread; and rather than becoming a new always-on service, because the watcher already knows how to start containers from job requests. A second container type costs nothing; a second background service costs a lifecycle.

Responsibilities:

- **The backend** writes one row and submits one job request, then forgets the run until asked.
- **The watcher**, unchanged from the preceding PR, turns every job request into a container. It does not know that some interpret and others calculate.
- **The interpreter container** parses the documents, compiles the flow, and spawns one block container per active step in order, waiting for each.
- **Each block container** checks out the pinned commit, builds that block's environment, and runs the block.

**Outputs between blocks.** A block returns `{"url": ...}` — a reference, not data. The next block receives it merged into its configuration and fetches whatever it points at itself. Manta and the worker never read or write modelling data, which keeps the container boundary cheap and lets a block choose its own storage. Getting that reference back out of a container is Prefect's result path, hence the result-persistence requirement in §5.

**Status and logs.** Each step is a child flow run, so its state is tracked without any new record; the PoC's `_step_states` already walks child runs to produce exactly this. Logs come back as they already do — each container's output goes to its flow run, and `GET /v1/runs/{uuid}/logs` collects the interpreter's flow run plus its children, attributing each line to its step.

**Failure partway through.** The failed step's container exits non-zero, its flow run fails, the wait raises in the interpreter, and the run fails. Later steps never start. No rollback, no cleanup, no resume — whatever an earlier block wrote stays where it wrote it, which is the first thing anyone debugging will want.

## 8. API surface

**New — playbooks.** YAML travels as a string field.

```
POST /v1/playbooks                                      -> 201
  {"name": "Expand then dispatch",
   "description": null,
   "definition": "name: expand-then-dispatch\nsteps:\n  - name: expansion\n...",
   "configuration": "globals: {}\nexpansion: {}\n..."}
  -> {"uuid": "...", "name": "...", "created_at": "..."}

GET  /v1/playbooks                                      -> 200
  -> {"items": [{"uuid": "...", "name": "...", "description": null,
                 "created_at": "..."}]}

GET  /v1/playbooks/{playbook_uuid}                      -> 200
  -> {"uuid": "...", "name": "...", "description": null, "created_at": "...",
      "definition": "...", "configuration": "..."}
```

**Changed — starting a run.** `CreateRunRequest` loses `num_pi_digits` and gains a playbook. `project_uuid` stays: runs remain scoped to projects even though playbooks are not.

```diff
-POST /v1/runs  {"project_uuid": "...", "num_pi_digits": 100000}
+POST /v1/runs  {"project_uuid": "...", "playbook_uuid": "..."}
   -> {"uuid": "...", "project_uuid": "...", "created_at": "..."}
```

This is a breaking change to the only run-creation path. The frontend's hardcoded `defaultRunPayload` in `frontend/src/features/runs/api.ts` and the `"Pi digit statistics"` placeholders in `toRunListItem` change with it; the runs table already renders a `playbook` column, so it starts showing a real value.

**New — per-step state.** The backend reads the run's playbook document with `manta_playbooks` to know the full list of steps, and fills in each one's state from its child flow run.

```
GET /v1/runs/{run_uuid}/steps                           -> 200
  -> {"uuid": "...", "steps": [
        {"name": "expansion", "block": "overnight_capacity_expansion",
         "status": "SUCCEEDED", "started_at": "...", "finished_at": "..."},
        {"name": "dispatch", "block": "rolling_horizon_dispatch",
         "status": "RUNNING", "started_at": "...", "finished_at": null}]}
```

Step status uses Manta's own vocabulary — `PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED` — not Prefect's state names. This is new surface, so there is no reason to leak through it.

**Unchanged in shape.** `GET /v1/runs`, `GET /v1/runs/summary`, `GET /v1/runs/{uuid}` and `GET /v1/runs/{uuid}/logs` keep their response models. `/logs` changes only internally, to include child flow runs.

## 9. The path to Kubernetes

Unchanged in a cluster: the worker image, the interpreter, the block contract, the blocks repository, the document format, every API endpoint, and the fact that a block execution is a container that builds an environment and runs a class. Because only references cross between steps, data flow needs no change — there is no shared volume to lose.

Swapped: the watcher, exactly as the preceding PR described. Instead of asking the local Docker daemon for a container, it asks the cluster for a pod. Same image, same parameters, same job request. This is why the interpreter asks the watcher for containers rather than calling Docker itself — otherwise the interpreter would need swapping too.

New infrastructure:

- **An image registry**, so any node can pull the worker image — the item the preceding PR already flagged.
- **Cluster egress to the git host.** Every block container checks out the blocks repository. A cluster without outbound access cannot run anything.
- **Shared storage for Prefect results**, since a step's returned reference must be readable by an interpreter on a different node. Locally a volume; on a cluster, object storage — a settings change.
- **A home for the pixi cache.** The named volume holding the git mirror and the built environments is the one host-local assumption here. On a cluster it becomes either a read-write-many volume or nothing, in which case every block execution pays a cold environment build. Neither changes any code — the cache is a path, and its absence is already a supported state.

Nothing else makes the move harder: no host paths, no node affinity, no local sockets in the execution path, and no assumption that two containers can see each other.

## 10. Verification

Start the normal services and the app — `docker compose … up` for infrastructure, `uv run manta` for the application. Nothing else, by hand, ever.

1. `POST /v1/playbooks` with the two documents from §3 and a real commit SHA. Confirm `201`, and that the stored YAML comes back byte-identical from `GET /v1/playbooks/{uuid}`.
2. `POST /v1/runs`. Confirm `201` returns immediately rather than blocking for the length of the run.
3. Watch `docker ps`. Expect the interpreter first, then the `expansion` container, then — only after it exits — the `dispatch` container. Three containers in that order is the architecture proving itself.
4. `GET /v1/runs/{uuid}/steps` while it runs. Expect `expansion` to move `PENDING → RUNNING → SUCCEEDED` and `dispatch` to stay `PENDING` until it does.
5. Confirm `dispatch` received the reference `expansion` returned — a record crossed a container boundary and the second block resolved it. This proves result persistence is configured, and is the step most likely to fail first.
6. `GET /v1/runs/{uuid}/logs`. Confirm lines from both blocks, each attributed to its step.
7. **Prove isolation**: confirm each block container built its environment from its own directory's `pixi.toml`, that the two environments are separately materialised, and that the interpreter container has no PyPSA and no solver.
8. **Prove Manta holds no block code**: grep the Manta repository for any block implementation, PyPSA import, or modelling dependency, and confirm `manta_playbooks` imports nothing from `blocks`. There should be none, before or after this change.
9. **Prove additivity**: add a block — a directory, a `pixi.toml`, a module — to the blocks repository, create a playbook naming it at the new commit, and run it, without restarting Manta, rebuilding any image, or running a migration. This is the test that matters most.
10. **Prove failure is clean**: run a playbook whose second block raises. Confirm the run fails, the second step reads `FAILED`, a third stays `PENDING`, and the traceback is in the logs.

## 11. Deliberately deferred

- **Validation.** The PoC's `validation.py` is good work and none of it comes across yet. A bad reference or unknown block fails the run with a clear message, which is enough until people are authoring playbooks by hand at volume.
- **Graph drawing.** `graph.py` and the Mermaid renderer stay behind until there is a UI to draw into.
- **Nested playbooks.** Composition machinery — nested steps, child configs, loaders, circular-reference detection — for a use case nobody has yet.
- **Conditional steps.** `when:` parses, since the document model comes across whole, but branching is not something to rely on in this slice.
- **The block catalogue.** Needed the day there is a block picker; the PoC has the design ready.
- **Recording what a run executed.** A run points at a playbook, not a snapshot of it. Reconstructing an old run after its playbook was edited is the TODO on `Run`.
- **Playbooks scoped to projects.** Global for now; scoping is easy to add and hard to remove.
- **Playbook editing and deletion.** Create, list and get only — the minimum to start a run.
- **Sharing environments between blocks that genuinely agree.** Every block builds its own, even where two are identical. Deduplicating is an optimisation; isolation is the point.
- **Retries, scheduling, triggers, concurrency limits, cancellation.** The preceding PR already deferred the queueing questions.
- **An image registry**, and **per-block prebuilt images.** Not needed on one machine. If environment builds become painful even when warm, prebuilt images slot in behind the same contract.

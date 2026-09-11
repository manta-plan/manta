# Playbooks and blocks — plan

## 1. The problem

Manta can run exactly one thing.
`POST /v1/runs` takes a single number, `num_pi_digits`, and submits a hardcoded Prefect deployment named by a constant in [run_service.py:25](backend/src/manta/services/run_service.py:25).
A request cannot say what to run, because there is nothing to choose from.
The preceding PR changed how work executes, and each job now gets its own container.
It did not change what can be asked for, so the contract is still "run the one job we know about".

## 2. Blocks and playbooks

Two ideas make that contract general.

- **A block is one unit of energy-modelling work.**
  Clustering a network's time series is a block, and so is solving a capacity expansion.
  Blocks live in a separate repository, carry their own dependencies, and know nothing about Manta.
- **A playbook is a recipe naming blocks in order.**
  It says which block's output feeds which block's input.
  Playbooks are rows in Manta's database, written as YAML.

Starting a run is then picking a playbook and pressing go.

The division of labour is strict.

- **Manta owns the playbook.**
  It stores the document, and it owns the interpreter: the code that reads a playbook and decides what runs, in what order, with which inputs.
  That is Manta's own code, in Manta's repository.
- **The blocks repository owns the blocks.**
  Manta holds no block code, imports no block code, and has no opinion about what a calculation means.
- **The interpreter spawns one container per block.**
  For each step it starts a fresh container.
  That container pulls the block's code and dependencies from the blocks repository, takes its configuration and its inputs, and hands back a reference to what it produced.
  "Please run this" and "what was the result" is the entire conversation.

**Adding a block requires no change to Manta.**
No migration, no deploy, no new image.
Someone commits to the blocks repository, and a playbook can name that commit the same day.
Every decision below protects that property.

A proof of concept (PoC) in the blocks repository already covers both halves.
Its `playbooks` package is the interpreter, and it moves into Manta.
Its `blocks` package stays where it is, largely untouched.
Prefect stays under the hood: it appears in no request, no response, and no vocabulary a user reads.

## 3. The entities

### 3.1 The playbook entity

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

**One entity is enough.**
There is no step table and no input table.
The interpreter already models the document.
Putting the same structure in SQL would mean two definitions of one thing, kept in step forever, for queries nobody is making.

**The documents are stored as verbatim YAML.**
The document is the thing users author, and the interpreter already parses YAML.
Storing text means comments and formatting survive a round trip.

**The recipe and its settings are two documents in one row.**
The PoC separates them.
A playbook says what runs in what order, and the settings document says with which values, filed by step name plus a shared `globals` section.
That split is worth keeping, and it costs a column rather than an entity.

**Which block version to run is not stored here.**
It lives in the definition, on the step, next to the block it pins.
See §4.

**The dual key comes from `Base`.**
[base.py](backend/src/manta/entities/base.py) supplies the house pair: an internal integer `id` for foreign keys, and a public `uuid` as the only identifier crossing the API boundary.

**A playbook is not scoped to a project.**
It describes a procedure, not a dataset, and the same recipe applies to any network you point it at.
Scoping now would mean copying playbooks to reuse them.
Runs stay scoped to projects, so nothing the frontend does today changes.

**A playbook stays editable.**
There is no version table and no locking once a run exists.
What a run submitted is captured in its flow run's parameters, so an in-flight run is unaffected by an edit.

### 3.2 Changes to the run entity

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

That is the entire change.
`SET NULL` is there for the same reason `project_id` already uses it: a run outlives its parents.

**There is no per-step table and no block registry table.**
Per-step state is already tracked, because each step is a child flow run.
A block registry would mirror a repository Manta does not own, which means a sync job, a staleness question, and a failure mode where a block exists but Manta refuses to run it.
It would also make adding a block require a write on Manta's side, which is the one thing this design exists to prevent.

## 4. A worked example

This playbook solves capacity expansion, then runs rolling-horizon dispatch against the capacities the first step produced.
Both blocks are real ones from the PoC's library, and the wiring is genuine: `RollingHorizonDispatch` declares `INPUTS = {"capacity_source"}`.

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

`version` is a git ref in the blocks repository, pinned per step so a run is reproducible.
The field is optional.
Without it the runner uses the repository's default branch, and the run is then only as reproducible as that branch is stable.
Two steps may pin different versions, because each step gets its own container and its own checkout.

A run then goes like this.

1. **The API receives `POST /v1/runs {"project_uuid": ..., "playbook_uuid": ...}`.**
   `RunService` loads the playbook row and calls `run_deployment("run-playbook/manta", parameters={"definition": <yaml>, "configuration": <yaml>, "record": {...}}, timeout=0)`.
   That is the same fire-and-forget shape as today's [create_run](backend/src/manta/services/run_service.py:76).
   One row goes into `runs` holding the returned flow run id, and the API returns `201` immediately.
   Sending the documents rather than a reference means a mid-run edit is harmless.

2. **The watcher starts one container** from the worker image, and that container is the interpreter.
   It is the same image and the same mechanism as any other job, and the watcher does not know this one orchestrates.

3. **The interpreter reads the documents.**
   `manta_playbooks.document.parse` turns them into a `Playbook`, and `execution.build_flow` compiles it.
   Steps run in list order, threading a record from step to step.
   A record is `{"url": ...}`, a reference to data, never the data.

4. **The interpreter spawns a container for `expansion`.**
   It submits a block job carrying `{"block": "overnight_capacity_expansion", "version": "9f2c1ab…", "config": {...}, "inputs": {}, "record": {"url": "..."}}` and waits.
   The entire contract is a block name, a version, its configuration and its inputs.
   Manta never sends anything else.

5. **The block container runs.**
   Its runner checks out the blocks repository at `9f2c1ab…`, enters `library/overnight_capacity_expansion/`, builds that block's own pixi environment, and runs the block inside it.
   The block fetches whatever its input record points at, solves, writes its result wherever it chooses, and returns a new `{"url": ...}`.
   The container exits.

6. **The interpreter spawns a container for `dispatch`.**
   Its `capacity_source` input resolves to the record `expansion` returned, and that record is merged into its configuration.
   A third container starts, builds a completely separate environment, and runs the dispatch block.

7. **The API reads the run back.**
   `GET /v1/runs/{uuid}` gives overall status, `GET /v1/runs/{uuid}/steps` gives each step's state, and `GET /v1/runs/{uuid}/logs` returns lines from the interpreter and both block containers, each attributed to its step.

The run uses three containers and two independently built environments, and nothing in Manta knows what PyPSA is.

## 5. The transfer from the proof of concept

### 5.1 What lands in Manta

The table below lists only what lands in Manta's repository, which is the interpreter and nothing else.
Every row comes from the PoC's `playbooks` package.
None of the PoC's `blocks` package comes across.
`MantaBlock`, `DataRecord`, the registry, the block entrypoint, the environment handling, the library blocks and the PyPSA helpers all stay in the blocks repository, where Manta never sees them.

Anything not listed stays behind.
Most of it supports validation, graph drawing or playbook nesting, and all three are out of scope for this slice.

| PoC component | Verdict | Reasoning | Adjustments needed |
|---|---|---|---|
| `yaml_io.py` — `PlaybookDoc`, `StepDoc`, `InitialDataDoc`, `WhenDoc`, `parse_doc`, `playbook_from_doc`, `load_config` | transfer with changes | The document format we are adopting wholesale; it already accepts the identical document from a file or a browser | `StepDoc` gains an optional `version`. The `Catalogue`/`BlockSpec` resolution goes — a step's block is a name and a version, and Manta resolves it no further. Nested-playbook loading goes with it |
| `playbook.py` — `Playbook`, `BlockStep`, `OutputRef`, `When`, `StepHandle`, `Playbook.active` | transfer with changes | The in-memory model and its reference resolution are the interpreter | `BlockStep` holds a name and a version instead of a `BlockSpec`, so nothing needs the `blocks` package importable |
| `${steps.<step>.output}` reference syntax and `_REF_RE` | transfer as-is | Readable, implemented, and backward-only by construction, which keeps a future DAG additive | None |
| Separate settings document (`globals` + per-step sections) | transfer as-is | Keeps the recipe readable and lets one recipe run with different values | Stored as a second column rather than a second file |
| `execution.py` — `build_flow`, the sequential spine, `_wire_up`, `_run_block_step` | transfer with changes | The sequential spine plus explicit wires is the execution model | Every step spawns a container. The in-process branch, the `dispatch` flag and `run_playbook_locally` all go |
| `dispatch_block` | transfer with changes | The mechanism for "run this step elsewhere and wait for its record" | Becomes the block-container spawn, targeting one generic `run-block/manta` deployment with the block name and version as parameters, rather than a deployment per block. See §6 |
| `control.py` — `start_run` sending the document rather than a reference | transfer with changes | Sending what was on screen is why a mid-run edit is harmless | Becomes `RunService.create_run` |
| `control.py` — `run_status`, `_step_states` | transfer with changes | Walking child runs for per-step state is exactly what the steps endpoint needs | Becomes `RunService.get_run_steps`, returning Manta's status vocabulary rather than Prefect's |
| Frozen Pydantic models throughout | transfer as-is | Good convention, and it matches Manta's existing DTO style | None |

### 5.2 What changes in the blocks repository

Nothing is added to the blocks repository and nothing moves into it.
Four changes are needed there, and all four follow from decisions made on Manta's side.

| Change | Reasoning |
|---|---|
| Split the repository-wide `pixi.toml` into one `pixi.toml` and lockfile per block, and move `library/` out of the installable package | Each block owns its environment. See §7.1 |
| `MANIFEST` and `ENV` resolve against the block's own directory by convention | Follows from the split; the PoC already has `MANIFEST` for pointing a block at its own manifest |
| `entrypoint.py` — `run_block` takes a block name, configuration and inputs as plain JSON, and returns a record as plain JSON | It is now invoked by a runner that has no playbook context, and the wire format has to be readable by an interpreter that cannot import `blocks` |
| Remove `src/playbooks/` | The interpreter moves to Manta. The PoC already guarantees `blocks` never imports `playbooks`, so this is a clean deletion |

## 6. The interpreter

The interpreter is Manta's code, in Manta's repository.
It is adopted from the PoC's `playbooks` package rather than written from scratch, but ownership moves.
This is the piece that decides what runs and in what order, and that decision belongs to the application rather than to the library of calculations.

It lives in a new package in the monorepo, alongside `backend/`, `frontend/` and `worker/`:

```
playbooks/
└── src/manta_playbooks/
    ├── document.py     # PlaybookDoc, StepDoc, WhenDoc, parse — the YAML shape
    ├── playbook.py     # Playbook, BlockStep, OutputRef, active() — the model
    └── execution.py    # build_flow — the spine, the wiring, the spawn per step
```

It is a third package rather than a folder inside one, because it has two consumers.
The worker executes it, and the backend reads a stored document to list a run's steps for the steps endpoint.
One owner holds one definition of the format, and neither the backend nor the worker depends on the other.
That preserves the separation the preceding PR established.

Each module has one job.

- **`document.py` turns the two YAML documents into a `Playbook`.**
  It validates that the document is a playbook at all, and resolves each input's `${steps.<step>.output}` into an `OutputRef`.
- **`playbook.py` holds the in-memory model.**
  `Playbook.active(config)` decides which steps run, in the one place everything consults.
- **`execution.py` compiles the playbook into a Prefect flow.**
  The spine threads a record step to step, `_wire_up` pulls a named earlier result into a named setting, and each step spawns a container.

**`manta_playbooks` does not import the blocks package.**
A step holds a block name and a version, and the interpreter never resolves either to a class, a schema or a description.
It passes them to the container and receives `{"url": ...}` back.
This is what lets the interpreter live in Manta without Manta acquiring any modelling dependency.
It is also why the PoC's `Catalogue` and `BlockSpec` resolution is dropped rather than carried.

Containers force three changes from the PoC.

**Execution always spawns.**
The PoC can run a step in-process when the block's environment matches the current one.
Under container-per-block there is no such case, because the interpreter never has block dependencies.
The in-process branch goes.

**One deployment serves every block.**
The PoC registers a Prefect deployment per `(block, environment)` pair.
Under that scheme, adding a block means registering a deployment.
That is an operation outside the blocks repository, and it breaks the rule that adding a block is purely additive.
So the spawn targets a single permanent `run-block/manta` deployment and passes the block's identity as parameters.

**The interpreter asks the watcher for containers, and does not call Docker.**
It spawns a container per block by submitting a block job, and the watcher turns that into a container, unchanged from the preceding PR.
Keeping one component responsible for containers is what makes the Kubernetes move a swap rather than a rebuild.
It also means the interpreter is testable without a Docker socket.

The Prefect surface is then three things.
A playbook run is one flow run, each step is a child flow run, and two deployments exist forever.
There are no tasks, no caching, no retries and no work-pool arithmetic.

One piece of Prefect configuration is required: result persistence, pointing at a shared volume locally.
The PoC gets away without it because its tests run in one process.
Once a step's record has to come back out of a container, Prefect needs somewhere durable to have put it.
It is a settings change rather than a code change, and it is the item most worth proving first.

## 7. The block contract

Everything in this section is the blocks repository.
Manta gains nothing here and loses nothing here.

### 7.1 Block layout

A block is what the PoC already made it: a `MantaBlock` subclass, registered by name, declaring what it needs as class attributes.
It now lives in its own directory with its own environment.

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

**Each block owns its environment.**
The PoC has one repository-wide `pixi.toml` with `dev`, `pypsa` and `full` environments shared across all blocks, which recreates the problem blocks exist to solve.
Two blocks wanting different versions of the same library have nowhere to put that disagreement.
Splitting per block removes the shared surface.
This is not a new mechanism.
The PoC already carries a `MANIFEST` attribute for pointing a block at its own `pixi.toml`, used as `pixi run --manifest-path <M> -e <ENV>`.
That path becomes the normal case, and by convention it is the block's own directory.

**There is no bespoke manifest file.**
A `block.toml` or a `requirements.txt` would restate what a block already declares.

- **Dependencies live in `pixi.toml`,** with a committed lockfile beside it.
- **Parameters live in `CONFIG`,** a Pydantic model, which is strictly more precise than a table of names.
- **Inputs and outputs live in `INPUTS` and `OUTPUTS`.**
  `__init_subclass__` already enforces that a wired input can hold a record and has a default.
- **Identity is the registered name.**
  By convention it is also the directory name, so the runner can find a block before importing any Python.

Writing a new block therefore takes a directory, a `pixi.toml` and a module, and nothing else.

The repository's top-level `pixi.toml` survives for the framework, which is the thing that is not a block.
`library/` moves out of the installable package so the framework stays block-free and installable on its own.

### 7.2 Identification and pinning

A block is named by its registered name and pinned by a git ref in the blocks repository, written on the step.
Name plus version identifies it completely.
The version fixes the code, the `pixi.lock` beside it fixes the dependencies, and together they make a step reproducible.
Pinning per step is possible precisely because environments are now per block.
Branch names are accepted and discouraged, because a mutable ref is an unreproducible run.

### 7.3 Code and dependencies at run time

The worker image is generic.
It contains `git`, `pixi`, the interpreter and a thin runner.
It contains no block implementation, and not even the blocks framework.
Everything block-related arrives at run time.

1. Fetch the blocks repository into a bare mirror on a named volume, then check out the commit the step pinned.
2. Enter `library/<block name>/` and build that block's environment with `pixi install`, against its own `pixi.toml` and lockfile.
   This is also what installs the framework, as a path dependency.
3. Run the block inside it with `pixi run -e <ENV> …`, handing it the configuration and inputs as JSON.
   The registry imports the block by name, `merge_config` folds the wired inputs into its settings, and `flow(record)` runs.
4. Stream the container's output into the flow run's logs, and return the resulting record as JSON.

This is what makes a new block free.
A block that did not exist when the worker image was built still runs in that image, without a rebuild.
The image never contained any blocks to begin with.

**Any non-zero exit fails the step**, whether it comes from the checkout, the environment build or the block itself.
The logs already carry the reason.
Conflicts cannot arise between blocks, since no two share an environment.
A conflict within one block is caught by `pixi` against its committed lockfile, in the blocks repository, before anything reaches Manta.

**One named volume holds the cache.**
It holds the git mirror, and each block environment keyed by block name and commit.
Nothing per-run is cached.
The cost is a volume that grows with no invalidation beyond deleting it.
That is acceptable, because the key includes the commit, so a stale entry is impossible by construction, and because the lockfile makes a rebuild deterministic.
The benefit is that the second run of a block starts in seconds rather than minutes.
Per-block environments do mean identical dependencies get built more than once, and pixi's package cache absorbs most of that.

### 7.4 Block discovery

**Manta does not learn which blocks exist, and that revises the preceding PR.**
That PR's registration handshake assumed job code shipped inside the worker image, so registering a job type and building the image were one act.
That no longer holds.
If the handshake stayed per-job, adding a block would mean rebuilding and redeploying the worker image.

So the handshake's granularity changes, and nothing else about it does.
The worker still announces itself at startup, but registers two generic entrypoints rather than one per job: "I can run a playbook" and "I can run a block".
Manta consequently cannot answer "what blocks exist", and the blocks repository is the answer.
Nothing asks until there is a UI that browses blocks, and the PoC's catalogue is the prior art to return to when there is.

### 7.5 Repository layout

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

`src/playbooks/` is gone, because it is now Manta's.
The pi-digit job is not converted, and Manta's copy is not deleted.
It stops being reachable once `POST /v1/runs` takes a playbook instead of a digit count, which the brief accepts.
Nothing is removed from Manta beyond the request field that has to change.

## 8. Execution

**Each block execution gets one container, and each playbook run gets one more for the interpreter.**

The unit is a block rather than a playbook run, because the entire reason blocks exist is that they carry incompatible dependencies.
With per-block environments, two steps in one playbook may legitimately want different versions of the same library.
Sharing a container would put that disagreement back.
One container per block also makes a failure survivable and the logs separable.

The interpreter gets its own container rather than running in the backend, because it is long-lived and must not occupy a request thread.
It is not a new always-on service either, because the watcher already knows how to start containers from job requests.
A second container type costs nothing, and a second background service costs a lifecycle.

Each part has one job.

- **The backend** writes one row and submits one job request, then forgets the run until asked.
- **The watcher** turns every job request into a container, unchanged from the preceding PR.
  It does not know that some containers interpret and others calculate.
- **The interpreter container** parses the documents, compiles the flow, and spawns one block container per active step in order, waiting for each.
- **Each block container** checks out the pinned commit, builds that block's environment, and runs the block.

**A block returns a reference, not data.**
It returns `{"url": ...}`, and the next block receives it merged into its configuration and fetches whatever it points at itself.
Manta and the worker never read or write modelling data, which keeps the container boundary cheap and lets a block choose its own storage.
Getting that reference back out of a container is Prefect's result path, hence the result-persistence requirement in §6.

**Each step is a child flow run, so its state needs no new record.**
The PoC's `_step_states` already walks child runs to produce exactly this.

**Logs come back as they already do.**
Each container's output goes to its flow run, and `GET /v1/runs/{uuid}/logs` collects the interpreter's flow run plus its children, attributing each line to its step.

**A failed step fails the run.**
The step's container exits non-zero, its flow run fails, the wait raises in the interpreter, and the run fails.
Later steps never start.
There is no rollback, no cleanup and no resume.
Whatever an earlier block wrote stays where it wrote it, which is the first thing anyone debugging will want.

## 9. The API

**Three new playbook endpoints.**
YAML travels as a string field.

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

**Starting a run changes shape.**
`CreateRunRequest` loses `num_pi_digits` and gains a playbook.
`project_uuid` stays, because runs remain scoped to projects even though playbooks are not.

```diff
-POST /v1/runs  {"project_uuid": "...", "num_pi_digits": 100000}
+POST /v1/runs  {"project_uuid": "...", "playbook_uuid": "..."}
   -> {"uuid": "...", "project_uuid": "...", "created_at": "..."}
```

This is a breaking change to the only run-creation path.
The frontend's hardcoded `defaultRunPayload` in [api.ts](frontend/src/features/runs/api.ts) and the `"Pi digit statistics"` placeholders in `toRunListItem` change with it.
The runs table already renders a `playbook` column, so it starts showing a real value.

**One new endpoint reports per-step state.**
The backend reads the run's playbook document with `manta_playbooks` to get the full list of steps.
It fills in each step's state from that step's child flow run.

```
GET /v1/runs/{run_uuid}/steps                           -> 200
  -> {"uuid": "...", "steps": [
        {"name": "expansion", "block": "overnight_capacity_expansion",
         "status": "SUCCEEDED", "started_at": "...", "finished_at": "..."},
        {"name": "dispatch", "block": "rolling_horizon_dispatch",
         "status": "RUNNING", "started_at": "...", "finished_at": null}]}
```

Step status uses Manta's own vocabulary — `PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED` — rather than Prefect's state names.
This is new surface, so there is no reason to leak through it.

**Four endpoints keep their response models.**
`GET /v1/runs`, `GET /v1/runs/summary`, `GET /v1/runs/{uuid}` and `GET /v1/runs/{uuid}/logs` are unchanged in shape.
`/logs` changes only internally, to include child flow runs.

## 10. The path to Kubernetes

These do not change in a cluster: the worker image, the interpreter, the block contract, the blocks repository, the document format, every API endpoint, and the fact that a block execution is a container that builds an environment and runs a class.
Data flow needs no change either, because only references cross between steps and there is no shared volume to lose.

The watcher is swapped, exactly as the preceding PR described.
Instead of asking the local Docker daemon for a container, it asks the cluster for a pod.
Same image, same parameters, same job request.
This is why the interpreter asks the watcher for containers rather than calling Docker itself, because otherwise the interpreter would need swapping too.

A cluster needs four things that one machine does not.

- **An image registry lets any node pull the worker image.**
  The preceding PR already flagged it.
- **Cluster egress to the git host is required.**
  Every block container checks out the blocks repository, so a cluster without outbound access cannot run anything.
- **Prefect results need shared storage.**
  A step's returned reference must be readable by an interpreter on a different node.
  Locally that is a volume, and on a cluster it is object storage, which is a settings change.
- **The pixi cache needs a home.**
  The named volume holding the git mirror and the built environments is the one host-local assumption here.
  On a cluster it becomes either a read-write-many volume or nothing, in which case every block execution pays a cold environment build.
  Neither changes any code, because the cache is a path and its absence is already a supported state.

Nothing else makes the move harder.
There are no host paths, no node affinity, no local sockets in the execution path, and no assumption that two containers can see each other.

## 11. Verification

Start the normal services with `docker compose … up`, then start the application with `uv run manta`.
Nothing else is set up by hand at any point.

1. `POST /v1/playbooks` with the two documents from §4 and a real commit SHA.
   Confirm `201`, and that the stored YAML comes back byte-identical from `GET /v1/playbooks/{uuid}`.
2. `POST /v1/runs`.
   Confirm `201` returns immediately rather than blocking for the length of the run.
3. Watch `docker ps`.
   Expect the interpreter first, then the `expansion` container, then the `dispatch` container only after `expansion` exits.
   Three containers in that order is the design working.
4. `GET /v1/runs/{uuid}/steps` while it runs.
   Expect `expansion` to move `PENDING → RUNNING → SUCCEEDED`, and `dispatch` to stay `PENDING` until it does.
5. Confirm that `dispatch` received the reference `expansion` returned.
   That means a record crossed a container boundary and the second block resolved it.
   It proves result persistence is configured, and it is the step most likely to fail first.
6. `GET /v1/runs/{uuid}/logs`.
   Confirm lines from both blocks, each attributed to its step.
7. **Prove isolation.**
   Confirm that each block container built its environment from its own directory's `pixi.toml`, that the two environments are separately materialised, and that the interpreter container has no PyPSA and no solver.
8. **Prove Manta holds no block code.**
   Grep the Manta repository for any block implementation, PyPSA import or modelling dependency, and confirm that `manta_playbooks` imports nothing from `blocks`.
   There should be none, before or after this change.
9. **Prove additivity.**
   Add a block to the blocks repository as a directory, a `pixi.toml` and a module, create a playbook naming it at the new commit, and run it, without restarting Manta, rebuilding any image, or running a migration.
   This is the test that matters most.
10. **Prove failure is clean.**
    Run a playbook whose second block raises.
    Confirm the run fails, the second step reads `FAILED`, a third stays `PENDING`, and the traceback is in the logs.

## 12. Deferred work

- **None of the PoC's `validation.py` comes across yet.**
  It is good work.
  A bad reference or unknown block fails the run with a clear message, which is enough until people author playbooks by hand at volume.
- **Graph drawing stays behind.**
  `graph.py` and the Mermaid renderer wait for a UI to draw into.
- **Nested playbooks are out.**
  The composition machinery covers nested steps, child configs, loaders and circular-reference detection, and nobody has the use case yet.
- **Conditional steps parse, and are not something to rely on.**
  `when:` parses, since the document model comes across whole.
  Branching is out of scope for this slice.
- **The block catalogue waits for a block picker.**
  The PoC has the design ready.
- **A run points at a playbook, not a snapshot of it.**
  Reconstructing an old run after its playbook was edited is the TODO on `Run`.
- **Playbooks are global rather than scoped to projects.**
  Scoping is easy to add and hard to remove.
- **Playbooks cannot be edited or deleted.**
  Create, list and get are the minimum to start a run.
- **Every block builds its own environment, even where two are identical.**
  Deduplicating is an optimisation, and isolation is the point.
- **Retries, scheduling, triggers, concurrency limits and cancellation stay out.**
  The preceding PR already deferred the queueing questions.
- **Neither an image registry nor per-block prebuilt images are needed on one machine.**
  If environment builds become painful even when warm, prebuilt images slot in behind the same contract.

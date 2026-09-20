# Comparing two orchestration proof-of-concepts

Two branches implement Manta's block and playbook layer.
This document compares them and ends in a recommendation.

Both branches fork from `main` at commit `2e17900`.
Throughout, they are named by what they do rather than by branch:

- **the work-pool approach** is branch `sid/docker-pools-in-docker-dir`;
- **the step-runner approach** is branch `prefect-isolation-backend-integration-claude-poc`.

## Conclusion

The step-runner approach comes out ahead, on one decisive point and one supporting one.
The decisive point is that its block framework has no dependency on Prefect or Docker, so a modeller writes a block as plain Python and tests it with `pytest` alone.
The work-pool approach makes the block itself a Prefect flow: its framework package depends on `prefect>=3.7.8,<4`, the method a block author implements is named `flow`, and the one shipped example block imports `from prefect import task` and calls `.submit().result()`.
That binds modelling code to one orchestration tool at the point where Manta least wants it bound.
The supporting point is that the step-runner approach routes every block execution through a single interface Manta owns, `StepRunner`, so moving from Docker to Kubernetes replaces one class.
The work-pool approach is not far behind on portability, and it is ahead on two things the other branch has not built.
It has a real mechanism for registering external block libraries, and a separate library package that proves the multi-environment story.
Those gaps are roughly forty lines of code plus a configuration value, and the code already exists on the other branch.
The Prefect coupling is not a gap of that kind, because the dispatch mechanism and the coupling are the same thing.

## What each branch implements

### The work-pool approach

A block becomes a Prefect deployment.
Each dependency environment gets its own Prefect work pool, named `manta-<env>`.
Each block gets a deployment on the pool for the environment it declares, and every one of those deployments runs the same flow, `run_block`, with the block's name as a parameter (`manta-blocks/src/manta_blocks/entrypoint.py:32-44`).
A playbook becomes a Prefect flow built at run time from its document, with nested playbooks as subflows (`manta-blocks/src/manta_playbooks/execution.py:56-94`).
The playbook flow dispatches each step by calling `run_deployment` and blocks until the child run finishes (`execution.py:32-53`).

Three container services carry this in the dev stack.
A one-shot provisioner reads a committed catalogue file and creates the pools and deployments (`docker/provision.py`).
A long-lived orchestrator worker drains a *process* pool and runs whole playbooks in its own process.
A second worker drains a *docker* pool and asks the host Docker daemon to start one throwaway container per block run.
That second worker is the only container that mounts `/var/run/docker.sock` (`docker/compose-dev-services.yaml:179`).
Blocks and the orchestrator share a Docker volume so the orchestrator can read each block's persisted Prefect result.

The backend stores playbooks as documents in a new `playbooks` table, validates a config against a catalogue before starting anything, freezes the run's input into a per-run S3 prefix, and calls `run_deployment` (`backend/src/manta/services/playbook_service.py:106-181`).
The backend never imports a block and never talks to Docker.

Concrete blocks live in a separate top-level package, `manta-batteries`, with its own `pixi.toml` declaring two environments and its own generated `catalogue.json`.

### The step-runner approach

A block becomes a process.
The playbook engine is a plain sequential function that hands one fully specified block invocation at a time to a `StepRunner` (`manta-blocks/src/playbooks/execution.py:29-47`).
The default runner calls the block in the current process.
Manta plugs in a `DockerStepRunner` that turns each call into a Prefect task run, which starts one container from one image and runs `python -m blocks.run_one` inside it (`backend/src/manta/workflows/playbook_flows.py:63-190`).
The container talks back through its own stdout: ordinary log lines, then one final `MANTA_BLOCK_RESULT` line carrying the output record (`manta-blocks/src/blocks/run_one.py:24-42`).

A playbook becomes one Prefect flow, `run-playbook`, and each executed step becomes one Prefect task run inside it, named `<step>[<block>]` (`playbook_flows.py:150,193`).
There is exactly one Prefect deployment in the whole system, and it is served by a subprocess of the backend (`playbook_flows.py:213-217`).
Playbooks, configs, records, and output locations all travel as flow-run parameters, so editing a playbook deploys nothing.

The block image is `python:3.12-slim` plus `manta-blocks[s3,pypsa]`, with no Prefect and no Manta in it (`docker/blocks-runner.Dockerfile`).
The backend holds the Docker client and starts block containers itself, using the `docker` Python package added to `backend/pyproject.toml`.

Concrete blocks live inside the framework package, under `manta-blocks/src/blocks/library/`.

### The step-runner branch tried the work-pool design first

This matters for the comparison, so it belongs in the record.
Commit `b4d4817` on that branch added a third package, `manta-runtime`, installed into the block image.
It declared two Prefect flows, created a Docker work pool, and let Prefect's own worker spawn a container per flow run.
A block was a child flow run that imported and executed the block in-process inside its own container.
Results crossed between containers as `.record.json` files in S3.
That is the work-pool approach in miniature.

Commit `d09b365` deleted all of it and gave four reasons.
The block image should contain only `manta-blocks` and block dependencies, because that is what an outside author tests against; the work-pool design put Prefect and flow code in it.
The S3 result side-channel was retry-unsafe and could go stale.
Pinning Prefect in three places rather than two, with the deployment name duplicated across packages, cost more than it bought.
Steps as task runs of one flow run make `/runs/{uuid}/steps` a single indexed query.

The commit also names what the change gave up: the backend now owns roughly sixty lines of container plumbing, in-flight runs no longer survive an application restart, and a Kubernetes move becomes a runner implementation rather than a work-pool swap.
So the choice between these two branches was already made once, deliberately, with the costs written down.

### What the two branches share

A large part of the model is byte-identical, because both descend from the same earlier proof-of-concept.
`graph.py`, `validation.py`, and `yaml_io.py` differ only in import paths: four, six, and six lines respectively.
Both define a block as a `MantaBlock` subclass carrying `ENV`, `CONFIG`, `DIMS`, `INPUTS`, and `OUTPUTS` as class variables, checked at class-creation time.
Both generate a JSON catalogue by importing blocks inside an environment that can hold them, and both let the backend read that catalogue without importing anything.
Both ship the same four PyPSA blocks and the same `cluster-expand-dispatch` example playbook.

Three limitations are common to both, so they separate nothing.
Neither models a block's compute resources: no CPU, memory, or GPU field exists in either tree.
Neither merges a playbook-level config option into a block's settings.
Both record a step's result under the literal key `"output"` regardless of what the block declared in `OUTPUTS`, so a block with two named outputs would validate and then fail at run time.

## Fit to the requirements

### 1. Model-agnostic

**Both partially satisfy this. The work-pool approach demonstrates it; the step-runner approach only makes room for it.**

Adding a block that uses a different framework means adding a dependency environment.
The work-pool approach has a working answer.
The provisioner creates one Docker work pool per environment named in the catalogue, and each pool's job template activates its environment with `pixi run -e <env>` (`docker/provision.py:50-76,125-128`).
A second framework means a second pixi environment, a second pool, and a catalogue entry.
No Manta code changes.

Be precise about how far the demonstration goes.
The committed catalogue declares one block environment, `pypsa`, so exactly one Docker pool exists today.
Two environments are nonetheless in live use: the orchestrator runs in a PyPSA-free environment on a process pool, which is what shows a block's dependencies staying inside the block's environment.
The mechanism for a third is configuration, not code.

The step-runner approach declares environments in the same way but never acts on them.
`DockerStepRunner` forwards only the block's name, and `_run_block_in_container` uses one global image for every step (`playbook_flows.py:80,182-189`).
A block's `ENV` is load-bearing for validation and error messages, not for dispatch.
The branch says so and names the seam where per-environment images belong (`docker/blocks-runner.Dockerfile:10-13`).
The seam is the right one, but a second framework today means a second image and code to choose between them.

Neither approach carries a caveat the other avoids: both bake one image per build and rebuild it when block code changes.

### 2. Modular

**Both satisfy the reuse half. Only the work-pool approach satisfies the assembly half today.**

The playbook model is shared and good on both branches.
A playbook is a list of named steps, each naming a block or a nested playbook, with inputs wired by `${steps.<step>.<output>}` references and steps switched on or off by `when:` conditions.
Nested playbooks compose without special cases.
Both serialise completely to YAML and both can draw a playbook as Mermaid without executing it.

The difference is where playbooks live.
The work-pool approach stores playbooks as JSONB documents in a `playbooks` table and runs whatever document the row holds.
That is what an ephemeral, user-assembled playbook needs: nothing is deployed per playbook, because deployments exist per block.
The step-runner approach has no playbook table.
Its flow resolves playbooks from a hardcoded built-in library at run time, so only Manta-authored playbooks can run.
Adding the table is straightforward, and the flow already accepts the playbook document as a parameter, so no execution change is needed.

### 3. Reproducible

**Both partially satisfy this, and both have the same weak link. The step-runner approach records the playbook more durably.**

The step-runner approach snapshots the playbook document onto the run.
Its `runs` row carries `playbook_name`, `playbook_doc` as submitted, `playbook_config`, `input_url`, and `output_prefix`, so a run stays reproducible from Manta's own records even after Prefect's history is pruned (`backend/src/manta/entities/run.py:16-24`).

The work-pool approach stores a foreign key to the playbook row instead, alongside `playbook_config` and `input_key`.
That foreign key deliberately refuses to let a playbook be deleted out from under its runs.
It does not stop the playbook being edited, and the code says so: "snapshot the playbook doc itself here once playbooks become editable — the playbook row is enough provenance only while playbooks are immutable."
Since that branch is also the one that makes playbooks editable, the gap is live rather than theoretical.

Both freeze the run's input into a per-run prefix before anything starts, so the source file cannot change under a finished run.

Neither records which environment produced an output.
There is no image digest, no lock-file hash, and no environment name on any artifact or run row, on either branch.
The work-pool approach leaves the environment implicit in the Prefect deployment name a step was dispatched to, which is not reachable from the outputs listing.
The step-runner approach leaves it implicit in whatever `manta-blocks-runner:latest` happened to be.
A run is reproducible in terms of playbook, config, and input on both branches, and not in terms of code and dependencies on either.

The work-pool approach also carries a provenance risk the other does not.
Its example playbook is seeded by a database migration that inlines a copy of the YAML file, with nothing checking the two stay in step (`backend/src/manta/migrations/versions/851030073080_create_playbooks_table_and_extend_runs.py:20-59`).

### 4. Users can view each block's output

**The step-runner approach satisfies this. The work-pool approach partially satisfies it.**

The difference is who chooses where a block writes.
In the step-runner approach the engine chooses, and passes `output_base` to the block: step `cluster` writes to `<prefix>/cluster`, and the block appends the extension its format needs (`playbooks/execution.py:102`, `blocks/core.py:190-200`).
A finished run is a folder with one file per executed step, named after the step.
Nested playbooks nest their paths.

In the work-pool approach the block chooses, by deriving a sibling name from its input: `runs/1/start.nc` plus the label `cluster_time` becomes `runs/1/start-cluster_time.nc` (`manta-blocks/src/manta_blocks/records.py:50-62`).
The label is hardcoded inside each block (`manta-batteries/src/manta_batteries/time_cluster.py:46`).
Two steps running the same block on the same record would write the same key.
The branch's own to-do list names this: "Figure out a nice way for blocks to write results to S3 without each block def in manta-batteries having to know about S3."

Both expose a run's outputs as a listing of one S3 prefix, which is a good answer on both branches.
Both make the files browsable in the SeaweedFS admin UI.

### 5. Configurable

**Both miss this, identically.**

Requirement 5 asks for a playbook-level `solver=highs` to reach every solving block, with a block-level override still possible.
Neither branch does this.
A block receives exactly the sub-document filed under its step name, and nothing else:

```python
step_config = config.get(step.name, {})
```

That line is `manta_playbooks/execution.py:126` on one branch and `playbooks/execution.py:109` on the other.
`globals` exists in the config document but only drives two things: `when:` conditions, and inheritance into nested playbooks.
That inheritance is the only layering code in either tree, and it is hardcoded to the literal string `"globals"`.
It is also all-or-nothing: a child that declares any `globals` discards the parent's entirely.
The function is `child_config`, at `manta_playbooks/playbook.py:87-97` on one branch and `playbooks/playbook.py:80-90` on the other.

Both branches document the gap and both point at the same single line as the place to fix it.
The work-pool branch does so in a code comment; the step-runner branch does so in its design notes.
This requirement therefore does not separate the two approaches, and the work to satisfy it is identical either way.

The one generic merge that does exist is the same on both: wired input records override typed settings for the same key, and the merged result is re-validated in full (`core.py:179-189`).

Both also treat a playbook's default config as all-or-nothing at run creation: a submitted config replaces the defaults rather than layering over them.
The step-runner branch states the reasoning, that a partial config on top of defaults is easy to get subtly wrong.
That reasoning stops holding once layered resolution exists, because layering is exactly what makes a partial config well-defined.

### 6. Validating

**Both satisfy this, with near-identical code.**

`validation.py` differs by six lines between the branches, all import paths.
It produces a list of issues rather than raising, each carrying a kind, a message, the step path, and the offending field.
It catches:

- step names that collide or are not valid identifiers;
- references to steps that do not exist, or that do not run earlier than the step referring to them;
- cycles through nested playbooks;
- `when:` conditions pointing at a setting nobody set;
- an active step fed by a step the conditions switched off;
- a missing dimension, naming the step that removed it;
- unknown config keys and badly typed settings;
- two blocks describing one environment differently.

Validation runs before any block runs, on both branches.
Both validate twice: once in the backend when a run is created, and again inside the orchestrator before the first step.
The work-pool approach also validates at deploy time, before any deployment is applied.
Both fall back to JSON Schema when a block cannot be imported, which means cross-field rules expressed in Python are checked only where the block is importable.

The work-pool approach exposes validation as its own endpoint, `POST /v1/playbooks/{uuid}/validate`, returning 200 with issues rather than an error status.
That is the right shape for an editor validating as a user types.
The step-runner approach validates only on run creation and returns 422.

Both have the same escape hatch: calling the engine's lower-level entry points skips validation entirely.

### 7. Contribution

**Neither satisfies this today. The work-pool approach has built the half that lets Manta discover an outside block. The step-runner approach has built the half that lets an outsider write one. The second half is much cheaper to add than the first.**

This requirement is the one that decides the comparison, so it needs unpacking.
An outside modeller getting a block into Manta without a PR needs four things to be true.

**(a) The framework installs on its own.**
Both branches satisfy this.
Both `manta-blocks` packages are standalone hatchling projects with their own lock files and no imports of the `manta` backend.
The step-runner version is cleaner: its dependencies are `pydantic`, `pyyaml`, and `jsonschema`, and its `pyproject.toml` already names a separate repository as its homepage.
The work-pool version adds `prefect>=3.7.8,<4`, which a contributor must then keep in step with Manta's server.

**(b) Writing a block needs no orchestration knowledge.**
The step-runner approach satisfies this; the work-pool approach does not.
Compare the same block on both branches.
On the step-runner branch it is plain Python: a helper method, and `run(self, record, output_base)` that calls it and writes the result.
On the work-pool branch the same block imports `from prefect import task`, decorates the helper with `@task`, implements a method named `flow`, and calls `self.cluster.submit(...).result()`.
The base class invites more of this: "You can split that work into as many Prefect `task` methods as you like and call them from `flow`."
A modeller writing a block on that branch must understand Prefect's task-submit-result model.
This is a deliberate choice on that branch, recorded in its proposal document, which reasons that running without Prefect is not a requirement.
That reasoning holds for *running*.
It does not hold for *authoring*, which is what requirement 7 is about.

**(c) The dependency environment can be declared and built outside `manta`.**
The work-pool approach satisfies this; the step-runner approach does not.
A block declares `MANIFEST` pointing at a third-party pixi manifest, and the work-pool renderer emits the exact commands to start a worker against it: `pixi run --manifest-path <manifest> -e <env> prefect worker start --pool <pool>` (`manta_playbooks/deploy.py:101-108`).
An outside project can host its own environment and its own worker.
The step-runner approach has no resolver for `MANIFEST` anywhere, and its `EnvironmentSpec.image` field is never populated by anything.
One image serves every block.

**(d) Manta can learn about the block without importing it, and route work to it.**
The work-pool approach satisfies this; the step-runner approach does not.
On the work-pool branch, a library announces its blocks with `register_lazy(name, "module:Class")`, which makes a name known without importing the module that would pull in PyPSA (`registry.py:237-251`).
Which libraries a process knows comes from `MANTA_BLOCK_SOURCES`, a comma-separated list of modules read from the environment (`registry.py:254-271`).
`python -m manta_blocks my_library` prints that library's catalogue, `merge_catalogues` unions catalogues built in different environments, and the backend reads the result from a path given by `MANTA_CATALOGUE_PATH`.
A contributor therefore delivers a package and a catalogue fragment, and Manta needs no code change.

On the step-runner branch the corresponding table is a hardcoded dict of the four built-in blocks (`registry.py:221-232`).
`python -m blocks` takes no arguments and rejects any (`__main__.py:20-25`).
The flow that runs playbooks calls `library_catalogue()`, an import of the built-in library, rather than reading a configured catalogue (`playbook_flows.py:202`).
A contributor's block cannot be named to Manta without editing `manta-blocks`.

**Weighing the two gaps.**
Each approach is missing half of requirement 7, so the question is which half costs more to add.

The step-runner approach's missing half is additive and small.
Copying `register_lazy` and `load_block_sources` is about forty lines.
Restoring module arguments to `python -m blocks` is a few more.
Replacing the hardcoded `library_catalogue()` with a configured catalogue path is one function, and the other branch already has it, including the environment-variable escape hatch for deployments that are not a checkout on disk.
None of these touch how blocks execute.

The work-pool approach's missing half is not additive.
`as_flow` is the only Prefect-using member of `MantaBlock` and could move out of the class.
The abstract method could be renamed from `flow` to `run`.
But the dispatch mechanism is `run_deployment(deployment_path(block, env))`, and a block's environment must therefore contain a Prefect client pinned to the server's version.
A contributor's environment carries that pin whether or not their block code mentions Prefect.
Removing Prefect from the contributor's surface means replacing the execution model, and the execution model is the branch.

## Fit to forward-looking constraints

### Repo separation

**Both framework packages can be cut out mechanically. The work-pool approach's library package cannot, and it is the one that must move first.**

Neither `manta-blocks` imports the backend.
Neither reads a path relative to the repository root.
Both use `importlib.resources` for package data.
On the step-runner branch, extraction costs one README link, one README paragraph, and one line in `backend/pyproject.toml`.
On the work-pool branch, extraction costs four comment and documentation references, the same backend dependency line, and moving a CI job that already runs the folder standalone.

The library packages differ.
The step-runner approach has no separate library package: its blocks live inside the framework at `manta-blocks/src/blocks/library/`.
That is a design problem for requirements 2 and 7, but it creates no cross-folder coupling to unpick.

The work-pool approach has a real `manta-batteries` package, which is the right structure, and it is coupled to the repository in three places.
`manta-batteries/pixi.toml:33` depends on `manta-blocks` by relative path.
`docker/job.Dockerfile:15-16` copies both folders from the repository root into one image.
`docker/compose-dev-services.yaml:132` bind-mounts `../manta-batteries/catalogue.json` into the provisioner.
All three are the kind of change the constraint calls mechanical: a published version pin, a build context, and a catalogue delivered by URL or volume instead of a relative path.
The backend's default catalogue path resolves four directories up from a source file, and the code says plainly that any deployment other than a checkout on disk must set `MANTA_CATALOGUE_PATH` (`backend/src/manta/config/playbooks_config.py:11-19`).
That is an owned interface with today's layout behind it, which is the right shape.

One coupling on the work-pool branch does not disappear with a repo split.
Prefect's version is pinned by hand in four places: the framework package, the library's pixi manifest, the backend, and the Prefect server image.
Each comment says so.
Once the library lives in another repository, that pin becomes a cross-repository version contract, held by convention.

### Kubernetes runtime

**Neither approach needs Docker-in-Docker or a privileged container. Both need Docker daemon access today, and both describe a credible path off it. The step-runner approach's path is smaller; the work-pool approach's path is better supported by Prefect.**

State the shared fact first.
No `privileged`, `cap_add`, `security_opt`, or Docker-in-Docker setting appears in either branch's compose file.
Block containers are siblings on the host daemon, not nested containers.
The cost is real but different from privileged mode: access to the Docker socket is root-equivalent control of the host.

Where that access sits differs, and it matters.
The work-pool approach confines it to one dedicated worker container whose only job is to start other containers (`compose-dev-services.yaml:176-179`).
The backend has no Docker dependency.
The step-runner approach puts it in the application: `backend/pyproject.toml` gains `docker>=7.1.0`, and `playbook_flows.py:48` calls `docker.from_env()` in the process that also serves the API and holds database and identity credentials.
The branch's own notes call this out as root-equivalent and name the Kubernetes runner as the fix.

For a move to Kubernetes, each approach must replace its isolation mechanism.

The step-runner approach replaces one class.
`DockerStepRunner` is thirty lines behind a protocol the engine never sees past.
A `K8sJobStepRunner` creates a Job, waits, reads the pod's logs for the result marker, and deletes the Job.
The block image needs no change, because it already contains nothing but the block framework and its dependencies.
Nothing above the runner changes.

The work-pool approach swaps Prefect's Docker work pool for Prefect's Kubernetes work pool, which is a supported Prefect feature and a genuinely smaller conceptual step.
The `pool_factory` parameter is already the seam for it and is already exercised by the Docker provisioner (`deploy.py:143-149`).
Two things must change first.
The shared `prefect-results` volume must go, because it is the only reason the orchestrator and the block containers must sit on one machine.
The branch's proposal document specifies that change in full, including the Prefect S3 storage block and the failure signature to watch for.
The block image must also keep carrying Prefect, because a Kubernetes work pool runs `prefect flow-run execute` inside the pod.
That is normal Prefect practice and it works.
It also means the image-to-server version contract survives the move, and third-party images inherit it.

Three smaller host assumptions on the work-pool branch would need attention.
An image is referenced by bare local name with `image_pull_policy: IfNotPresent`.
A Docker network name is derived from the compose project.
A `LocalStorage` pull step points at a fixed absolute path inside the image.
The step-runner branch has the equivalent of the first two and not the third.

### A note on fighting the runtime

One incident on the work-pool branch is worth recording, because it is evidence about grain rather than opinion.
Prefect's default deployment storage step recursively copies a deployment's working directory before every run, gated on whether pull steps are empty and not on the entrypoint type.
Because the block image's working directory also holds multi-gigabyte baked pixi environments, every block run copied them onto themselves.
The I/O was enough to crash the shared Postgres container mid-run.
The fix was to attach a `LocalStorage` pull step meaning "the code is already here", which Prefect treats as a cheap directory change (`deploy.py:154-163`, `docker/provision.py:146-151`).
Run time went from roughly fifteen minutes and a crash to under a minute.
The bug exists because the block image is also a Prefect code location.
The step-runner approach cannot have this class of bug, because Prefect never looks at the block image.

The step-runner branch hit an operational bug of its own, and it belongs beside that one.
The application spawned its flow-serving subprocess with `stdout=subprocess.PIPE` and never read the pipe.
Prefect echoes every relayed container log line to stdout, the 64 KB pipe buffer filled, and runs froze mid-step while their containers had already exited cleanly.
The fix was to discard that stream (`backend/src/manta/main.py:36-43`), and the code now carries a standing warning never to restore the pipe.
That bug exists because the orchestrator is a child process of the application.
It is the same shape of problem as the other: each branch pays for the place it chose to put the orchestrator.

## Mapping to Prefect

**The step-runner mapping fits Prefect's grain better. The work-pool mapping uses more of Prefect's primitives, and pays for them by putting Prefect inside the block.**

### What a block becomes

In the work-pool approach a block is three Prefect things at once.
It is a deployment, one per block-and-environment pair, addressed as `run_block/<block>-<env>`.
It is a flow, created per use by `as_flow` with a synthesised signature so Prefect sees each wired input as its own parameter (`core.py:191-226`).
Its internals may be tasks.

In the step-runner approach a block is one Prefect task run, and nothing else.
The block's own code knows nothing about any of it.

### What a playbook becomes

In the work-pool approach a playbook is a flow, built fresh from its document at run time, with nested playbooks as subflows and each step as a child flow run started through a deployment.
In the step-runner approach a playbook is a flow with one task run per step, and nested playbooks flatten into the same task list with their nesting encoded in storage paths.

### Which fits the grain

Prefect's model is flows that call tasks, with deployments as the unit of "work someone can start by name."
The work-pool approach uses deployments as the unit of "a place where this code can run", which is a different job.
Three consequences follow from that.
`run_deployment` must block the parent for the whole child run.
Child results must be persisted and read back out of a result store.
The orchestrator and the block containers must share a volume for that store to work.
Prefect can do all of this.

Four workarounds follow from it too.
The branch needed the `LocalStorage` pull step to stop Prefect copying the block image's working directory before every run.
It needed the catalogue passed as a JSON string, because Prefect resolves `{"$ref": ...}` inside dict parameters as its own block-document references.
It needed `inspect.Signature` surgery so wired inputs stay visible to Prefect as separate parameters.
It needed two environment variables for block sources, because importing the module named by one of them has side effects the provisioner must avoid.

The step-runner approach uses Prefect for what a deployment is for.
One deployment, started by name, with everything else as parameters.
No result store, no shared volume, no `$ref` hazard, no signature surgery.

### What leaks upward

This is the sharpest difference.
The work-pool approach leaks Prefect into the block definition.
`manta-blocks` depends on Prefect, `core.py` imports it at module scope, and a concrete block in the library imports `prefect.task` directly.
The Manta-facing interface on that branch also returns Prefect vocabulary: `RunStatus.state` is documented as "Prefect's own word for it" (`manta_playbooks/control.py:56`).
Playbook *definitions* stay clean on both branches: `yaml_io.py` and `graph.py` have no Prefect references on either.

The step-runner approach leaks nothing.
A search for `prefect` across its entire `manta-blocks` tree, including lock files and documentation, returns nothing.

### What each gets free, and what each builds

The work-pool approach gets more from Prefect.
Every block run is a first-class flow run with its own state, logs, retries, timeouts, and UI page.
Work pools give per-environment concurrency limits without any Manta code.
Container logs are captured by Prefect's own worker.
Per-step states come from one parent-child flow-run query.

The step-runner approach builds three things Prefect would otherwise supply.
It relays container logs into the task logger by reassembling the byte stream into lines (`playbook_flows.py:138-147`).
It marshals the block's result through a stdout marker line rather than a result store (`run_one.py:24-42`).
It passes arguments as JSON on a command line rather than as flow-run parameters.
That is roughly a hundred lines of transport, and the printer and parser sit in one file so the protocol cannot drift.
Per-step retries, timeouts, and concurrency limits remain available as ordinary Prefect task options; neither branch sets any of them.

### Surviving a change of orchestrator

The step-runner approach would survive one.
Its framework has no orchestration dependency, its engine is a plain function, and the Prefect-specific code is two decorators and a `serve` call in one backend module.
Replacing Prefect means rewriting that module.

The work-pool approach would not survive one intact.
Prefect appears in the framework package's dependencies, in the block base class, in the shipped block library, in the deployment model, and in the Manta-facing status types.
Blocks written against it carry the dependency with them.

## Software qualities

### Elegance

**The step-runner approach expresses the model more directly.**

Its engine is forty lines: walk the active steps, wire the inputs, hand one call to a runner, record the result.
The thing that runs a block is a protocol with one method.
Read `execution.py` and you have read the orchestration.

The work-pool approach spreads the same model across `execution.py`, `deploy.py`, `entrypoint.py`, and `control.py`, and the reader must hold Prefect's deployment model to follow it.
It carries more incidental complexity, and most of it is Prefect-shaped: the four workarounds listed under the Prefect mapping, plus a work-pool routine that deletes and recreates a pool when its type changes.
Its incidental complexity in the backend is lower, because the backend only calls `run_deployment`.

The step-runner approach's own incidental complexity is the stdout marker protocol and the log reassembly.
That is real, and it is confined to one file with the printer and the parser adjacent.

### Maintainability

**The step-runner approach centralises orchestration; the work-pool approach distributes it.**

On the step-runner branch, every orchestration decision lives in two files: the engine in `manta-blocks`, and `playbook_flows.py` in the backend.
Changing how a step runs means editing one class.

On the work-pool branch, a change to how blocks run can require edits in the framework's `deploy.py`, the repository's `docker/provision.py`, a compose file, and a Dockerfile, with a pool-name convention shared by all four by string agreement.
The convention is `manta-<env>`, produced by one function and re-derived by hand in three other places, including two that bypass the function for the orchestrator pool.
Adding a block is cheaper on that branch, because it is a catalogue entry rather than code.

The step-runner branch has no CI for `manta-blocks`.
The work-pool branch has one, scoped to the folder, running `ruff` and `pytest` (`.github/workflows/manta-blocks-test.yml`).
It has no CI for `manta-batteries` and says so on purpose.

### Extensibility

**The work-pool approach extends better for environments. The step-runner approach extends better for isolation mechanisms.**

Adding a dependency environment on the work-pool branch means a pixi environment, a catalogue entry, and a pool.
No core change.
On the step-runner branch it means building a second image and writing the code that picks between images, because nothing reads `ENV` at dispatch time.

Adding a new kind of isolation is the reverse.
On the step-runner branch it is one class implementing one method.
On the work-pool branch it is a `pool_factory` plus a job template plus whatever the new worker type needs, and the block image must keep carrying Prefect.

Resource profiles are unavailable on both, because neither models resources at all.
The work-pool approach is closer: a Prefect work pool's job template is exactly where CPU and memory limits belong, and the template already exists.
The step-runner approach would add them as arguments to `containers.run`.

### Scaling

**Both are bound to a single host today. The work-pool approach has a second bottleneck the other does not, and the better scaling model once the runtime moves.**

Both start block containers on one Docker daemon, so concurrent block executions are bounded by one machine.
The step-runner approach adds a second limit: every block container is driven by the backend's flow-serving subprocess, so that one process holds a thread per in-flight step and its death takes every in-flight run with it.
The work-pool approach's orchestrator is a separate long-lived worker container, which is better on that count.
It adds a pin the other branch does not have.
The shared results volume means the orchestrator and every block container must sit on one machine, even after the daemon problem is solved.

Once the runtime moves to Kubernetes, the work-pool approach scales the way Prefect scales.
More workers drain a pool, the pool caps concurrency, and each run is a Job.
The step-runner approach scales by running more copies of whatever hosts the flow, with concurrency capped by Prefect task tags.
Both are credible.
Neither runs a playbook's independent steps in parallel today: both engines are sequential loops, and on the step-runner branch making them parallel is an engine-only change behind the same interfaces.

### Robustness

**Both handle a crashing block correctly and neither handles a hanging one. The work-pool approach survives an application restart; the step-runner approach does not.**

A block that exits non-zero fails cleanly on both branches.
The step-runner approach raises `BlockRunFailedError` with the exit code, removes the container in a `finally` block, fails the task, and fails the flow (`playbook_flows.py:120-134`).
It also fails a block that exits zero without reporting a result, which is a good check.
The work-pool approach lets the child flow run fail, which fails the `run_deployment` call in the parent.

A block that hangs hangs the run on both branches.
Neither sets a task timeout, a flow timeout, or a container timeout.
The step-runner approach blocks in `container.wait()` with nothing to interrupt it.
Neither sets retries.

The states a failed run leaves behind differ.
The step-runner approach leaves an S3 prefix with the outputs of the steps that succeeded, and no container, because cleanup is unconditional.
A retried step would overwrite its own `output_base`, which is the idempotent behaviour you want.
The work-pool approach leaves the same partial S3 prefix, no container because `auto_remove` is set, and one persisted Prefect result per completed block on the shared volume.

The decisive robustness difference is durability.
The step-runner approach serves its flow from a subprocess of the application, so restarting the application kills every in-flight run and orphans their containers.
The branch names this as its top production gap and calls the fix mechanical: serve the flow from its own long-lived service, since the API already dispatches by name.
The work-pool approach already runs the orchestrator as its own container, so an application restart does not touch a running playbook.

Both share one orphan window: they start the Prefect run and then commit the database row, so a commit failure leaves a run executing that Manta has no record of.
The work-pool approach logs exactly that and says so.

## Operational and security posture

**The work-pool approach has the better security boundary today. The step-runner approach has the smaller footprint and the shorter path to removing the boundary problem entirely.**

Neither needs a privileged container and neither uses Docker-in-Docker.
Both need Docker daemon access, which is root-equivalent on the host.
The work-pool approach puts that access in a worker container that does nothing else.
The step-runner approach puts it in the application process, alongside the database session and the identity integration.
If the application is compromised, the second arrangement hands over the host.
That is the strongest operational argument against the step-runner approach as it stands, and the fix is either a separate runner service or the Kubernetes runner.

Both hand static S3 credentials to block containers through environment variables, readable by anyone who can inspect containers on the host.
Both leave the Prefect server unauthenticated in the dev stack.

Footprint at moderate scale differs mainly in idle cost.
The work-pool approach runs Postgres, a Prefect server, a one-shot provisioner, and two long-lived workers, one of which runs the roughly two-gigabyte block image purely because both pixi environments were built into one image.
The branch's own plan moves that worker to the slim image.
The step-runner approach runs Postgres, a Prefect server, and no workers, with the flow served inside the application.
That is cheaper and less durable, and the fix for durability adds one service back.
Per-run cost is the same on both: one container per step, plus Prefect's flow-run and log history growing unbounded in Postgres on both branches.

Portability across a laptop, CI, and production favours the step-runner approach.
Its block image is `python:3.12-slim` plus a pip install, and its test suite needs neither Docker nor Prefect.
The work-pool approach needs pixi and a locked multi-platform environment, and a platform gap already cost one commit and a five-thousand-line relock when the job image failed to build on ARM.
Neither locks Manta to a cloud.
Both assume an S3-compatible store reached through standard AWS environment variables, which SeaweedFS, MinIO, and S3 all satisfy.

## Developer and debugging experience

**The step-runner approach is better for both audiences, by a wide margin on local testing.**

Running one block locally on the step-runner branch is a method call, or `python -m blocks.run_one <block> --record ... --output-base ...` for the process-level path.
Running a whole playbook locally is `playbook.run(record, config, output_prefix=tmp_path)` with the default in-process runner.
The loop is `uv sync --extra pypsa && uv run pytest`.
No Docker, no Prefect, no S3: `DataRecord.url` takes local paths and `blocks.storage` never touches boto3 for them.

On the work-pool branch, running a playbook locally is `run_playbook_locally(playbook, record, config)` with dispatch off, which runs every block in one process.
That works, but the package's `conftest.py` starts a `prefect_test_harness()` for the whole session, so every test in the suite boots a throwaway Prefect database.
Testing a block therefore requires Prefect to be installed and working.
Testing `manta-batteries` additionally requires pixi and the PyPSA environment.

Failure diagnosis is good on both, by different routes.
The step-runner approach relays each container's stdout line by line into its Prefect task run, so a solver's output appears next to the step it belongs to in the Prefect UI and under `GET /v1/runs/{uuid}/logs`.
Exit codes surface in the error message.
The work-pool approach gets the same effect from Prefect's own worker capturing container logs, with each block as its own flow run with its own page.

Automated testing favours the step-runner approach for the same reason local execution does.
Its engine takes a runner, so a test passes a recording fake and asserts on the calls, with no process or container involved.
Its backend ships an end-to-end integration test that boots an isolated stack on random ports and runs a playbook through the API into real containers.
The work-pool branch tests the framework thoroughly and has an integration test for the playbook routes, but has no equivalent end-to-end proof that a run reaches containers, and no CI for the library package.

One asymmetry favours the step-runner approach and deserves naming.
Because the block image is exactly `manta-blocks` plus block dependencies, a contributor can run their own test suite inside the production image and get an exact environment-parity check.
On the work-pool branch the equivalent image also contains Prefect and both pixi environments, so it is not the environment the contributor develops against.

## End-user experience

### What a Manta user sees

Both give the same shape.
A user creates a project, uploads or names an input file, picks a playbook, supplies a config, and starts a run.
The run goes `PENDING → RUNNING → COMPLETED` over a couple of minutes for the example playbook, with container start-up on top of each block's solve.
Both expose run status, aggregated logs, and an outputs listing.
The work-pool approach adds per-step states derived from Prefect's child flow runs; the step-runner approach adds the same from its task runs, in start order.

Outputs become visible as each step finishes, on both branches, because blocks write straight to S3 and the outputs endpoint lists a prefix.
The step-runner approach names them better, as discussed under requirement 4.
Neither offers a download route: both return `s3://` URLs, not presigned links.

Provenance is visible on both as the run row plus the Prefect run.
Neither exposes the environment or image that produced an output, so a user cannot fully reproduce a run from what Manta shows them.

### What an external contributor does

On the step-runner branch the authoring loop is complete and the delivery step is missing.
A contributor installs `manta-blocks`, subclasses `MantaBlock`, implements `run`, writes a pytest that calls it with a `tmp_path`, validates and draws their playbook without executing it, then runs the whole playbook in-process.
Everything up to that point needs no Manta, no Prefect, no Docker, and no S3.
Then they stop, because there is no way to tell Manta about their block without editing `manta-blocks` and rebuilding the runner image.

On the work-pool branch the delivery step is designed and the authoring loop is compromised.
A contributor writes a block whose method is called `flow`, decorating internal steps with Prefect tasks if they want parallelism, in a package that depends on Prefect pinned to Manta's version.
They declare a pixi environment, point `MANIFEST` at it, call `register_lazy` from their package's `__init__`, and generate a catalogue with `python -m manta_blocks their_library`.
Manta picks the blocks up by adding their module to `MANTA_BLOCK_SOURCES` and their catalogue to the provisioner, with no `manta` PR.
They still need somewhere to run a worker for their environment, and Manta still needs to trust their code enough to import it in a job container.

Both leave the same question unanswered: nothing sandboxes a third party's block beyond the container boundary, and both hand that container the S3 credentials.

## Config and validation mechanics

**Config layering is missing from both, identically, and the mechanism that would implement it is generic on both. Validation is present on both, early on both, and near-identical in code.**

Both implement config as a separate document keyed by step name, with a `globals` section.
Neither resolves a layered override.
The one merge that exists, wired inputs over typed settings, is generic over any key: `cls.CONFIG.model_validate({**base, **inputs})`.
The one inheritance that exists, `globals` into nested playbooks, is bespoke to that literal key and merges nothing.
Implementing requirement 5 is the same work on both branches, in the same place, and needs no per-option code: resolve defaults, then globals, then the step's own settings, once, before the block sees anything.

Validation runs before any block starts on both branches, from the same code, returning the same issue objects with step and field attached.
The work-pool approach validates at one more moment than the other, deploy time, and exposes validation as a first-class endpoint.
Both check cross-field Python rules only where the block can be imported, and fall back to JSON Schema where it cannot.
A rule like "exactly one of `segments` or `n_hours`" is therefore caught in the runner environment and not in the backend.

## A hybrid worth building

A hybrid would outperform either branch alone, and most of it is transplant rather than design.

Take the step-runner approach as the base: the Prefect-free framework, the plain-Python block, the `StepRunner` seam, the caller-chosen `output_base`, the single parameterised deployment.
Then take five mechanisms from the work-pool branch.

Take `register_lazy` and `MANTA_BLOCK_SOURCES`, so a block library announces itself without being imported and without being in `manta-blocks`.
Take the separate `manta-batteries` package with its own environment manifest, so the library is not inside the framework.
Take the catalogue as a configured path rather than an import, with the environment-variable override already written.
Take the `playbooks` table and the `/validate` endpoint, so user-assembled playbooks and editor-time validation both work.
Take the architectural lesson that the orchestrator belongs in its own long-lived service rather than in the application process.

Leave behind the deployment-per-block dispatch, the shared result volume, and the Prefect dependency in the block framework.
Keep the Prefect work pool idea in reserve for a different purpose: a job template is the natural place for per-block CPU and memory limits once resources are modelled, and a Kubernetes work pool would supply that for free.

## Recommendation

**Build on the step-runner approach.**

The reason is requirement 7 read together with the repo-separation constraint.
A block or playbook folder becoming its own repository is the end state of that requirement.
The step-runner approach is already shaped for it: a framework package with no orchestration dependency, blocks that are plain Python, and one interface between the engine and whatever runs a block.
Its requirement 7 gaps are discovery gaps, and the code that fixes them exists on the other branch and can be copied.
The work-pool approach's requirement 7 gap is that the block itself is a Prefect object, and that is not a gap you close by adding code.

### The strongest argument against this pick

Two things, and they are the same thing seen twice.

The step-runner approach hands the application process root-equivalent control of the host Docker daemon, and runs the orchestrator inside the application, so an application restart kills every in-flight run.
The work-pool approach has neither problem today: the socket lives in a dedicated worker, and the orchestrator is its own container.
Both fixes are known and both are contained, but they are real work that the other branch has already done.

The deeper version of the argument is about Kubernetes.
Prefect's Kubernetes work pool is a supported product feature.
`K8sJobStepRunner` is code Manta would write and maintain, including Job creation, log streaming, result extraction, and cleanup.
Choosing the step-runner approach means choosing to own that code in exchange for keeping blocks free of Prefect.
That is the trade, and it should be made deliberately.

### What would make the other approach the better choice

Two conditions, either of which would flip it.

If Manta reads requirement 7 as "no PR to the `manta` repo" rather than "no orchestration knowledge", the work-pool approach's Prefect coupling stops being a cost.
Under that reading it is ahead: its discovery mechanism works, its library package is properly separate, and its environment story is demonstrated rather than designed.

If Manta decides to own as little execution machinery as possible and to let Prefect's workers be the runtime, the work-pool approach is the right shape.
It uses Prefect's pools, templates, workers, and result storage rather than reimplementing the parts of them it needs.
A small team that would rather configure than maintain should weigh this seriously.

### Does the recommendation survive the repo split and the move to Kubernetes

Yes, and it strengthens.

After a repo split, the step-runner framework is a package with three dependencies and no version contract with Manta.
The work-pool framework is a package whose Prefect pin must track Manta's server across repository boundaries, held by convention in four places.
Every block written against it inherits that contract.

After a move to Kubernetes, the step-runner approach's isolation mechanism becomes one new class behind an unchanged interface, and the block image needs no change because it contains nothing but the block.
The work-pool approach's move is well supported at the pool level and requires the shared results volume to be removed first, which its own plan specifies.
The block image keeps carrying Prefect after the move, so the version contract survives the transition as well.

One qualification.
The recommendation depends on Manta actually doing the transplant described above.
The step-runner approach as it stands on the branch does not satisfy requirement 7, and shipping it unchanged would leave external contributors with a complete authoring loop and no way to deliver.

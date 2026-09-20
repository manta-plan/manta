# Taking the orchestration layer to production

This lists the pull requests that turn the block and playbook proof-of-concepts into production work.
It is a companion to [manta-poc-comparison.md](manta-poc-comparison.md), which recommends building on the step-runner approach.
The plan does not assume that recommendation: group 1 is needed either way, and groups 2 and 3 cover the two approaches separately.

Each PR below is sized for one careful review sitting, and each leaves the system working.
Where a PR must pick something concrete for today, it puts that choice behind an interface Manta owns.

Two standing constraints shape every entry.
A folder holding blocks or playbooks is a future separate repository, not a subfolder.
The runtime is a future Kubernetes cluster, not a Docker daemon.
Any PR that a repo split or a Kubernetes move would force us to redo, rather than extend, is flagged **Redo risk**.

---

## Group 1: common groundwork

This work is needed whichever execution approach wins.
It is ordered so that each PR depends only on the ones before it.

### 1.1 Split the block library out of the block framework

**What it does.** Moves concrete blocks and playbooks out of the framework package into a library package of their own, with its own dependency manifest and its own generated catalogue.
The framework keeps only the base class, the registry, the playbook model, validation, and the storage helpers, plus a handful of fake blocks for its own tests.

**Why it is its own PR.** This is the structural decision every later PR builds on, and it is a pure move with no behaviour change, which makes it reviewable as a move.
Doing it first means no later PR has to be redone when the library leaves the repository.

**Interface Manta owns.** The library depends on the framework by version, not by relative path, from the first commit.
A workspace or path source may satisfy that version locally, but nothing may import across the two folders by filesystem position, and no image build may assume both folders share a build context.

### 1.2 External block registration

**What it does.** Gives any installable Python package a supported way to announce its blocks without being imported, and gives Manta a supported way to name which packages to load.
Replaces any hardcoded table of built-in blocks.
The built-in library becomes an ordinary consumer of this mechanism, which is how we know it works.

**Why it is its own PR.** This is requirement 7's discovery half, and it is the single change that decides whether an outside contributor needs a PR to `manta`.
It is also self-contained: registration and lookup, with no execution changes.

**Interface Manta owns.** A registration call plus a configured source list.
Packaging entry points are the eventual mechanism and should be the goal; an environment-variable source list is an acceptable first step, provided the lookup code does not care which one supplied the names.

### 1.3 The catalogue as a build artifact

**What it does.** Makes the block catalogue something generated in an environment that can import blocks, published, and then read by everything else from a configured location.
Adds a CI job that regenerates the catalogue and fails on drift.
Removes any code path that obtains the catalogue by importing the built-in library.

**Why it is its own PR.** The catalogue is the contract between environments that can import blocks and environments that cannot, which includes the backend.
A stale catalogue is a silent correctness bug, so the drift check is the point of the PR, not a detail of it.

**Interface Manta owns.** One function that returns the catalogue, with its source configured rather than compiled in.
A checkout-relative default is fine as the local development case if the configured override is the documented path for everything else.

### 1.4 Layered config resolution

**What it does.** Implements requirement 5.
Resolves a block's settings once, from the playbook's declared defaults, then playbook-level globals, then the step's own settings, with later layers overriding earlier ones per key.
Makes a submitted partial config well-defined by layering it over the defaults.
Records the fully resolved config on the run.

**Why it is its own PR.** Both proof-of-concepts leave this unimplemented at the same single line, and both engines are otherwise ready for it.
It is also the PR where the config document's shape stops being provisional, so it should land before any UI is built against it.

**Interface Manta owns.** Resolution happens in the engine, once, before a block sees anything.
It must stay generic over keys: no config option may need its own code.

### 1.5 Playbook storage and a validation endpoint

**What it does.** Stores playbooks as documents in the application database, and adds an endpoint that validates a playbook document against a config and returns the problems as data with a success status.
Built-in playbooks are seeded into that store by a startup or deploy-time sync rather than inlined into a migration.

**Why it is its own PR.** It is what turns "run one of our playbooks" into "run a playbook", which requirement 2 needs post-MVP and which the drag-and-drop UI needs absolutely.
The validation endpoint is in the same PR because it is the same document model seen from the other side, and an editor needs both together.

**Redo risk: none, but note the seeding.** Seeding built-in playbooks from a library package is a cross-package read.
Keep it behind the same configured-source idea as the catalogue, so a library living in another repository still seeds.

### 1.6 Run provenance

**What it does.** Implements requirement 3 properly.
Snapshots onto the run everything needed to reproduce it: the playbook document as executed, the resolved config, the input record URL, the catalogue version, and the identity of the environment each step ran in.
Pins the block image by digest rather than by a moving tag, and records the digest.

**Why it is its own PR.** Neither proof-of-concept records the environment that produced an output, which is the weak link in both.
Fixing it touches the run model, the runtime, and the image build, so it needs to be one coherent change rather than three partial ones.

**Interface Manta owns.** The runtime reports back an opaque environment identity per step; the run model stores it without interpreting it.
Under Docker that identity is an image digest, under Kubernetes it can be the same, and neither the run model nor the API needs to know.

### 1.7 Per-step outputs, states, and logs

**What it does.** Fixes output addressing so the orchestrator chooses where each step writes and the block chooses only the format, giving one file per step at a predictable path, with nested playbooks nesting their paths.
Exposes per-step states in execution order, aggregated logs, and an outputs listing with download links.

**Why it is its own PR.** This is requirement 4 end to end, and it is the first thing a user sees.
The addressing change and the endpoints belong together because the endpoints are meaningless if two steps can write the same key.

**Redo risk: none.** Download links should be presigned URLs minted by the backend, not raw `s3://` addresses, so the storage backend stays replaceable.

### 1.8 Multiple named outputs, and step identity under nesting

**What it does.** Makes a block's declared `OUTPUTS` real: a step's results are recorded under the names the block declared, not under a single hardcoded key.
Gives every step a stable identity that survives nesting, so two nested playbooks reusing a leaf step name do not collide in storage paths or in per-step reporting.

**Why it is its own PR.** Both proof-of-concepts have the same latent bug here: a block declaring two outputs validates cleanly and then fails at run time.
Both also key per-step reporting by a name that can collide across nesting levels.
These are small fixes that are easy to review together and hard to notice inside a larger PR.

### 1.9 Block resource declarations

**What it does.** Lets a block declare what it needs to run: CPU, memory, and optionally a GPU or an accelerator class.
Carries that declaration through the catalogue to the runtime as an opaque profile, and applies it where the runtime can.

**Why it is its own PR.** Neither proof-of-concept models resources at all, and the block concept is defined partly in terms of them.
It is also the PR that stops one runaway block taking down a shared host, which is a prerequisite for running untrusted contributor code.

**Interface Manta owns.** A resource profile on the block, translated by the runtime.
Under Docker that becomes container limits; under Kubernetes it becomes a pod resource spec; under a Prefect work pool it becomes job-template variables.
The block never names any of those.

---

## Group 2: approach-specific work for `docker-pools-in-docker-dir`

These apply if Manta builds on the work-pool approach.
The first three come from that branch's own proposal document, which specifies them in more detail than this plan needs to.

### 2.1 Move Prefect result storage off the shared volume

**What it does.** Points Prefect's default result storage at the object store, and deletes the shared `prefect-results` volume along with the mounts, the volume configuration, and the local storage path that go with it.

**Why it is its own PR.** That volume is the only reason the orchestrator and the block containers must run on the same machine.
Removing it is the single highest-value change on this branch and is independently verifiable: a run completes, no results volume exists, and objects appear in the store.

**Redo risk: none. This is the prerequisite for Kubernetes**, and nothing else on this branch should be attempted before it.

### 2.2 One image per block environment

**What it does.** Builds one image per dependency environment rather than one image carrying every framework, and resolves each environment's image from the catalogue.
Falls back to a configured mapping, then to today's single image, so the change lands without breaking the current stack.

**Why it is its own PR.** Requirement 1 is the reason this approach exists, and today a block run pulls an image containing every framework in the system.
The change is contained: an image build argument, a resolution order, and a catalogue field that already exists but is never populated.

**Interface Manta owns.** The image is a property of the environment, written into the catalogue by whatever built it.
Nothing in the framework should know how an image is named.

### 2.3 Run the orchestrator on a slim image

**What it does.** Builds the orchestrator worker from the control image rather than the heavyweight block image, and adds an explicit build-only service so the block image still gets built.

**Why it is its own PR.** The orchestrator never imports a block, so it needs neither pixi nor a solver stack.
It is a small, verifiable change and it removes a multi-gigabyte idle container from the footprint.

### 2.4 Take Prefect out of the block author's surface

**What it does.** Renames the block's abstract method from `flow` to something orchestration-neutral, moves the flow-wrapping classmethod off the base class, and removes Prefect imports from the shipped block library.
The framework package keeps its Prefect dependency for execution; block definitions stop carrying it.

**Why it is its own PR.** It is the largest single step this approach can take toward requirement 7, and it is a breaking change to every existing block, so it should not be bundled with anything.

**Redo risk: high, and worth stating plainly.** This PR reduces the symptom without removing the cause.
A block's environment must still contain a Prefect client pinned to the server, because the dispatch mechanism is a Prefect deployment run.
If Manta later decides contributor environments must be Prefect-free, this PR is redone rather than extended, and so is the dispatch model underneath it.

### 2.5 A Kubernetes pool factory

**What it does.** Adds a pool factory that creates Kubernetes work pools with job templates carrying the environment's image and resource profile, selected by configuration.
Moves provisioning out of the local Docker folder into whatever owns production infrastructure.

**Why it is its own PR.** The seam already exists and is already exercised by the Docker provisioner, so this is an implementation of an established interface rather than a redesign.
It depends on 2.1 and should not be attempted before it.

### 2.6 Third-party environment hosting

**What it does.** Documents and supports the path where a contributor's environment is hosted outside Manta: how their worker authenticates, which pool it drains, and how Manta learns the environment exists.
Adds the version contract between a contributor's Prefect client and Manta's server as a checked constraint rather than a comment.

**Why it is its own PR.** It is the remaining half of requirement 7 on this branch, and it is an operational and trust question rather than a code question.
Reviewing it as code buried in another PR would hide that.

---

## Group 3: approach-specific work for `prefect-isolation-backend-integration-claude-poc`

These apply if Manta builds on the step-runner approach.
The first two are that branch's own stated top gaps.

### 3.1 Serve the playbook flow from its own service

**What it does.** Moves flow serving out of a subprocess of the API into a long-lived service built from the same codebase and image.
The API keeps dispatching by name and needs no change.

**Why it is its own PR.** Today an application restart kills every in-flight run and orphans its containers.
This is the branch's top production gap, the fix is mechanical, and it is independently testable: restart the application mid-run and watch the run finish.

**Redo risk: none. It reduces under Kubernetes**, where the same service becomes a deployment with its own lifecycle.

### 3.2 Formalise the block runner interface

**What it does.** Promotes the step-runner protocol into a stated `BlockRunner` interface Manta owns, and gives it the operational properties a production runner needs: a per-step timeout, retries with idempotent output paths, cancellation that also kills the step's work, and a cap on concurrent steps.

**Why it is its own PR.** The interface is the whole portability argument for this approach, so it deserves to be defined deliberately rather than inferred from its one implementation.
Timeouts and cancellation belong here because they are properties of the interface, not of Docker: a hanging block hangs a run today, with nothing to interrupt it.

**Interface Manta owns.** This is that interface.
Every later runner implements it, and nothing above it may branch on which runner is in use.

### 3.3 Per-environment images

**What it does.** Makes a block's declared environment decide which image its step runs in, resolved from the catalogue, instead of using one global image for every block.

**Why it is its own PR.** Requirement 1 is structurally satisfied on this branch and not actually satisfied: nothing reads a block's environment at dispatch time.
This is the PR that closes that gap, and it depends on 1.3 for the catalogue and 3.2 for the interface.

### 3.4 Take Docker access out of the application

**What it does.** Removes the Docker client from the API process.
Either the flow-serving service from 3.1 becomes the only thing with daemon access, or step execution moves behind a small runner service with a narrow API.

**Why it is its own PR.** Today the process that holds database and identity credentials also holds root-equivalent control of the host.
This is the branch's strongest security objection and it should be fixed as its own reviewable change, not as a side effect of a Kubernetes migration that may be a year away.

### 3.5 A Kubernetes job runner

**What it does.** Implements the runner interface against the Kubernetes Jobs API: create a Job, stream its logs, read its result, clean it up.
Replaces the local-image precheck with a registry and an image pull policy, the fixed network name with cluster DNS, and environment-variable credentials with cluster secrets or workload identity.

**Why it is its own PR.** It is one implementation of an interface defined in 3.2, and it supersedes 3.4 rather than conflicting with it.
Listing the three replaced assumptions explicitly is the point: they are the parts of the migration that are not covered by the interface.

### 3.6 Orphan-free run creation

**What it does.** Writes the run row before dispatching, adds an idempotency key, and reconciles rows whose dispatch never completed.

**Why it is its own PR.** Both branches have this bug, and both log it rather than fix it, so it is easy to leave forever.
It is small, it is testable by killing the process between the two steps, and it has nothing to do with any other PR here.

---

## What this plan deliberately does not do

It does not design the drag-and-drop playbook editor.
It does not cover retention for Prefect's flow-run and log history, which grows unbounded in Postgres on both branches, or lifecycle rules for block outputs, which grow as steps multiplied by model size because networks cannot be stored as diffs.
It does not address authentication on the Prefect server or the new endpoints.
It does not run a playbook's independent steps in parallel, which both engines could do behind their existing interfaces once there is a reason to.
Each of those is real work and none of it blocks the orchestration layer from reaching production.

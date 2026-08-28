# 08 — Open questions

Decisions not yet made, gaps between the two repositories, and risks that need
closing. Ordered roughly by how much they block progress.

## Blockers

### Record storage and format

Block library code writes result files beside the input file on a local filesystem,
because a record is currently a path to a PyPSA netCDF file. Manta's data layer is an
S3-compatible object store, managed with DuckDB.

Two separate questions hide here:

1. **Where records live.** Local paths do not work once steps run in different
   containers. This must become object-store URLs. The change is confined to one
   module in `blocks` by design, but somebody has to own the URL scheme and decide how
   credentials reach a worker.
2. **What a record *is*.** The security review specifies DuckDB over S3 for model
   data; `blocks` currently assumes netCDF, and writes a whole new network each time
   because PyPSA cannot yet store a difference. These need reconciling — a record
   might be a netCDF object in the store today and a DuckDB-managed dataset later, but
   the interface between them should be decided rather than discovered.

**Proposed division:** Manta owns record identity and lifecycle — what a record is
called, which project it belongs to, when it can be deleted. `blocks` owns record
input/output — how a block reads and writes one. The contract between them is the URL
scheme plus credentials.

This is the single largest gap between the two designs, and it blocks Kubernetes
entirely.

### Prefect result persistence across processes

The orchestrator reads each step's return value across a process boundary. That
requires Prefect result persistence configured with storage both sides can reach, and
it is not configured today. The proof of concept passes because its tests run in one
process.

This is the classic failure that works locally and breaks the moment execution is
genuinely distributed. It should be verified on the Compose stack with separate worker
processes before anything else is built on top of it.

### Resource requirements are not modelled

No block declares CPU, memory or wall time. On Kubernetes this is not optional.

The declaration belongs on the block, because only its author knows what it needs. The
`blocks` README suggests declaring requirements *relative to the data*, so absolute
requirements can be computed from the record being processed — attractive, and
considerably more work than a static declaration. **Open:** static declaration first,
or hold out for the data-relative model?

## Security

### The plug-in trust boundary

A Plug-in Developer supplies arbitrary Python, with arbitrary dependencies, packaged
as a container image, which Manta then executes inside its own infrastructure. At M4
that infrastructure also handles client Confidential data.

Nothing in the current design addresses this. The questions:

- **Who may publish a block?** Is the catalogue curated by OET, or can a deployment
  add third-party blocks? On-premise clients will certainly want the latter.
- **What may an execution pod reach?** Network policy is the primary control:
  object store and Prefect API only, no outbound internet, no access to the
  application database.
- **How is data scoped?** A block sees whatever record it is handed. Credentials
  scoped per run, rather than a shared bucket credential, limit the blast radius of a
  malicious or merely careless block.
- **Is the image trusted?** Signing, provenance, scanning — and who is accountable
  when a third-party image carries a vulnerable dependency.
- **What does the user see?** A block being third-party should be visible in the
  interface, not implicit.

This should feed the M3 threat-modelling exercise. It is not urgent for M1–M3 (public
data, curated blocks) but it is the security question that most shapes the
architecture, and deciding it late would be expensive.

## Design decisions

### Should Manta store the final output record?

Run state and logs stay in Prefect — settled. But a completed run produces a URL
pointing at its result artefact, and that is arguably a product object rather than an
execution detail: Prefect's retention policy will eventually discard the flow run that
knows about it, while the artefact itself is something a user expects to still be
there.

**Proposed:** store the output record URL on the run row when it reaches a terminal
state, while continuing to read status and logs live. This is a narrow exception to
"no run state in Manta's database", justified because it is not state — it is a
pointer to a durable artefact.

**Open:** who writes it, given nothing currently observes run completion? Options: on
first read after completion; a Prefect automation calling back into Manta; a periodic
reconciliation job.

### Catalogue versioning and playbook pinning

Does a saved playbook pin the catalogue version it was authored against?

- **Pin:** a playbook authored a year ago still validates and runs against the blocks
  it was written for. Requires keeping old catalogues and old deployments alive, and
  users eventually need a migration path.
- **Always latest:** simpler, but a block changing its settings silently invalidates
  saved playbooks, and a user's saved work can break without them touching it.

Reproducibility is listed as a quality goal for v1, which argues for pinning. This
needs deciding before playbooks are persisted, because it determines what a playbook
row must contain.

### Where do playbooks come from?

The `blocks` repository ships example playbooks as YAML. Manta stores user-authored
playbooks in its database. Are these the same kind of thing?

**Open:** does Manta ship a library of curated starter playbooks — imported from
`blocks` at release time, or authored in Manta and versioned somewhere? The roadmap
speaks of a "simple, modular playbook system" at MVP advancing to "user-defined
playbooks", which implies both exist. The relationship between them is undefined.

### Who creates work pools?

Currently: an operator, from commands the provisioner prints. That is right for
development and probably wrong for a managed SaaS, where adding an environment should
not require a human running `prefect work-pool create`.

**Proposed:** pools and workers are declared in the cluster manifests alongside every
other piece of infrastructure, so adding an environment is a manifest change with
review and rollback. Neither library creates them at run time.

### Orchestrator resilience

If the orchestrator worker dies mid-playbook, the parent run fails while its
already-dispatched children continue, orphaned. Running it on a stable process pool
makes this unlikely rather than impossible.

**Open:** is that acceptable, or does the orchestrator need to be resumable — able to
pick up a partially-completed playbook and continue from the last finished step? The
latter is a meaningful piece of work, and for long-running capacity-expansion
playbooks it may be worth it.

### Multi-tenancy of work pools

Every run in a deployment currently shares one pool per environment. For OET's SaaS
that means one tenant's large job can starve another's.

**Open:** per-tenant pools, per-tenant concurrency limits within a shared pool, or
priority queues. Prefect supports concurrency limits and work queues with priorities
within a pool, which is probably sufficient and considerably simpler than pool
proliferation. Not needed before M3's guest-access model, which already restricts size
and run limits.

## Smaller items

### Rename `Renderer` to `Provisioner`

The interface that turns a deployment plan into real infrastructure is called
`Renderer` in the code. It reads as frontend vocabulary and describes the wrong thing:
it creates infrastructure, it does not render anything. `Provisioner` — with
`ProcessPixiProvisioner` and `KubernetesProvisioner` — matches the plan/apply
vocabulary the design already implies. These documents use `Provisioner` throughout.

### Explicit inputs instead of ambient defaults

Two library defaults are convenient for a command-line user and wrong for a service:

- `start_run` deploys before every run, touching the Prefect API once per block on
  each request. Deployment should be a release-time or save-time action.
- The orchestrator environment defaults to whatever environment the calling process is
  in. Manta's backend does not run under Pixi, so this silently resolves to a pool
  that does not exist.

Both should become required arguments.

### Conditions cannot look at data

`when` clauses inspect settings only, never the data. This is a deliberate trade —
it is what makes a playbook checkable and drawable before it runs — but it rules out
"only run this step if the network has more than N buses".

**Open:** is that limitation acceptable long-term, and if not, what replaces it
without giving up up-front validation? No answer is needed yet; it should be recorded
as a known boundary of the model rather than rediscovered later.

### Monitoring a queue with no worker

A flow run queued to a pool with no running worker sits in `PENDING` indefinitely and
nothing surfaces it. Prefect can emit automations on late runs; Manta could surface
queue age on the run endpoint. **Open:** which, and what the user is told.

### Observability beyond Prefect

Prefect covers run state and logs. It does not cover the API, the database, or the
workers themselves as processes. **Open:** what carries metrics and traces, and how
run identifiers correlate across Manta's logs, Prefect's logs and the audit trail the
security policy requires.

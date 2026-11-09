<!--
SPDX-FileCopyrightText: Manta contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Open questions

This page lists the design questions about Manta's architecture that are not decided yet, with the options on the table and what each costs.
Decided work that is not built yet is on [Planned changes](planned-changes.md).
The questions come first by how much they hold up other work.

## Questions that hold up other work

### Who owns a record

A record is a store URL and a revision uuid, and `playbook-library` reads and writes it through the datarecord package.
What is not decided is who names a record, which project it belongs to, and when it can be deleted.
The likely split is that Manta owns a record's identity and lifetime, and a block library owns how a block reads and writes one.
The contract between the two is then the URL scheme and the way credentials reach a block.
Today every block container gets one credential for the whole bucket.

### Resource requirements

A block is to declare the resources it needs, as [Planned changes](planned-changes.md#resource-requirements) states.
A fixed declaration, such as 8 CPUs and 32 GiB, is simple to build.
A declaration relative to the data, such as memory per snapshot and per bus, gives each run what it needs, but costs considerably more work.
The open question is whether to start with the fixed form or wait for the relative one.

### The trust boundary for third-party blocks

A block author supplies Python code with any dependencies, packaged as an image, and Manta runs it on its own infrastructure.
Later, that infrastructure also holds confidential client data.
Nothing in the design answers these questions yet:

- Who may publish a block: only Open Energy Transition, or also a client on its own deployment?
- What may a step reach? The planned network policy allows the Prefect API and the object store only, with no internet and no application database.
- How is data scoped? A step sees every record it is handed, and credentials scoped to one run limit what a careless or hostile block can reach.
- Is the image trusted? Signing, provenance and scanning, and who answers for a vulnerable dependency in a third-party image.
- What does the user see? Whether a block comes from a third party should show in the web app.

These questions feed the threat model before the MVP.
They matter little while Manta uses public data and curated blocks.
But they shape the architecture more than any other security question, and answering them late costs the most.

## Design questions

### Storing a run's final record

Run state and logs stay in Prefect.
A finished run also produces a record, and that record is arguably part of the user's work rather than a detail of the run.
Prefect's retention eventually removes the flow run that knows about it, while the user expects the result to stay.

One proposal is to store the final record on the `runs` row when the run ends, and keep reading state and logs from Prefect.
That would be a narrow exception to keeping run state out of Manta's database.
It is justified because a record points at lasting data rather than describing the run.
The open part is what writes it, since nothing in Manta watches a run end.
Three options exist: the first read after the run ends, a Prefect automation that calls Manta, or a periodic job that reconciles runs.

### Catalogue versions and pinned playbooks

A saved playbook could pin the catalogue it was written against, or always use the latest one.

Pinning means a playbook written a year ago still checks and runs against the blocks it was written for.
It needs old catalogues and old block images kept alive, and users eventually need a way to move a playbook to newer blocks.
Always using the latest catalogue is simpler.
But a block that changes its settings then breaks saved playbooks, without their owners changing anything.

Reproducible analysis is a goal of milestone M4, which argues for pinning.
This needs deciding before Manta stores playbooks, because it decides what a stored playbook contains.

### Where playbooks come from

`playbook-library` ships playbooks as YAML files, and Manta is to store playbooks that users write.
The roadmap moves from a simple set of ready-made playbooks to playbooks that users define.
How the two kinds relate is not decided.
Manta could import the shipped playbooks as starting points, or keep them apart from the ones users write and version them elsewhere.

### Passing the catalogue by reference

Today the backend passes the whole catalogue to each `run-playbook` flow run, as a JSON string.
That makes each run self-contained, and the catalogue that checked a playbook is the one that dispatches it.
But Prefect stores the parameters of every flow run in its database and shows them in its UI, and the catalogue grows with every block.

The alternative is to pass a catalogue version and the catalogue's address in the object store, which the playbook worker fetches and caches by version.
The object store suits this because every worker already reaches it, and workers never call the backend.
Building the catalogue into the runner image is the option to avoid.
The backend could then check a playbook against one catalogue while the worker dispatches against an older one.

### Choosing a block's image for each run

Today `MANTA_ENV_IMAGES` maps each environment to an image that contains a whole block library, built when the stack starts.
A third party who adds a modelling framework therefore needs a change to Manta's repository and a rebuild of its images.

One option is to resolve each step's environment when it runs.
A step's container would fetch exactly the blocks its playbook names, from whichever library publishes them.
`MantaBlock.MANIFEST`, `EnvironmentSpec.manifest` and `EnvironmentSpec.image` exist for this, and nothing uses them yet.
It needs a way to fetch a library, and a cached environment underneath, because installing a solver stack takes minutes.
What `MANIFEST` means once every environment is an image is open too: drop it, or read it as where to build the image from.
`runner.config.exec_image` is the one place an environment name becomes an image, so either choice changes one function.

### Resuming a run

If the playbook worker stops during a run, the run fails and a step it already started runs on without a parent.
Running the playbook flow on a long-lived process worker makes that rare, not impossible.
The open question is whether a run should resume from its last finished step.
That is substantial work, and may pay off for capacity expansion playbooks that run for hours.

### Sharing pools between tenants

Every run in a deployment shares one block pool.
On a hosted service, a large run of one tenant could then hold back the runs of another.
The options are a pool per tenant, a concurrency limit per tenant within a shared pool, or work queues with priorities.
Prefect supports concurrency limits and prioritised work queues within one pool, which is likely enough and far simpler than many pools.
The MVP's guest access already limits the size and number of runs, so this is not needed before then.

## Smaller questions

### Conditions on data

A `when` condition reads only settings, never the data, which makes a playbook checkable before it runs.
It rules out a step such as "run only if the network has more than 100 buses".
The open question is whether that limit is acceptable for good, and if not, what could replace it without losing the checks before a run.
Nothing needs it yet, and recording it here keeps it from being rediscovered later.

### A queue with no worker

A flow run queued to a pool with no worker waits as `PENDING` with no end, and nothing reports it.
Prefect can raise an automation on a late run, or Manta could report how long a run has waited on the run endpoint.
Which one, and what the user is told, is open.

### Observability beyond Prefect

Prefect covers the state and logs of runs.
It does not cover the backend, the databases or the workers as processes.
What carries metrics and traces is open.
So is how one run's id ties together the backend's log, Prefect's log and the audit records the security policy asks for.

## Reading this page

Each question names its options and what they cost, so you can tell when a change you make answers one.
A change that answers a question here moves it into the code and onto the page that explains that part.

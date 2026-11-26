<!--
SPDX-FileCopyrightText: Manta contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Planned changes

This page lists the changes to Manta's architecture that are decided but not built, and what exists in their place today.
Questions that are not decided yet are on [Open questions](open-questions.md).
The [GitHub milestones](https://github.com/manta-plan/manta/milestones) track the work itself, and they win where this page and a milestone differ.

!!! warning "Not built yet"

    Everything on this page describes how Manta is meant to work, not how it works today.
    Each section states what exists today first.

## Milestones and security focus

Manta's milestones run from a working vertical slice to a release with the features of proprietary tools:

- [M1: Vertical Slice](https://github.com/manta-plan/manta/milestone/5): a user loads a model, runs a playbook on it and views the results, end to end.
- The M2 milestones: run a simple PyPSA playbook, integrate the datarecord package, move the web app from its prototype, and welcome outside contributors.
- [M3: MVP Launch](https://github.com/manta-plan/manta/milestone/1): a live production instance, hosted by Open Energy Transition, with monitoring.
- [M4: Feature Parity](https://github.com/manta-plan/manta/milestone/2): the features of proprietary tools, still built on PyPSA, with reproducible and auditable analysis.
- [M5: Flexible, Multi-framework](https://github.com/manta-plan/manta/milestone/3): more than one modelling framework, and blocks that users extend.

Manta's security review sets a security focus for each phase.
Up to the M2 milestones, Manta runs on development machines with public test data, and the repository gets its security tooling, branch protection and policies.
The MVP stays on public data, offers anonymous guest access, and gets an external penetration test and a threat model before launch.
The first release for confidential data adds single sign-on with multi-factor authentication, role-based access control, a vulnerability disclosure programme and service levels.

## Playbooks stored in Manta

Today a run names a playbook that `playbook-library` ships, and the request carries the settings.
The `runs` row keeps the playbook's name, and the backend reads the settings and the playbook document back from the Prefect flow run.

The plan is a `playbooks` table, scoped to a project, that holds a playbook document and its settings document.
A run then refers to a stored playbook and its stored settings, rather than resupplying the settings with each request.
Endpoints to create, read and update a playbook come with it.

A nested playbook names another playbook by locator.
Manta is to add a `PlaybookLoader` that finds a locator in this table, keyed by the playbook's uuid.
The check for a playbook inside itself compares the keys a loader reports, so the key has to be stable.
An unstable key would miss a real loop or report a false one.

## Block and drawing endpoints

Today `GET /v1/playbooks/{playbook_name}` returns each step's block summary and settings schema.
No endpoint returns the whole catalogue, and nothing draws a playbook.

The plan adds two endpoints:

- `GET /v1/blocks` returns the catalogue, so that the web app can offer every block and build a settings form for each one.
- A drawing endpoint returns a playbook as plain nodes and edges: which steps run, the dimensions before each step, and what each wire connects.

`playbook` is to work out the drawing, without running any step, because drawing a playbook must never start a solver.
The web app then draws the playbook, greys out the steps the settings switch off, and colours each step with its state during a run.
It marks a problem on the step and the field that each issue names.

The drawing data is to carry a version integer, as the catalogue carries `catalogue_version`.
A change to the shape of nodes or edges would otherwise make an old web app draw the wrong picture without any error.
The `/v1` REST API is the contract the web app relies on, so the backend can translate between shapes.
`catalogue_version` is to guard the catalogue file itself, which the backend should refuse at startup if it cannot read the shape.
Manta builds no negotiation between versions until something needs it.

## The log of each step

Today `GET /v1/runs/{run_uuid}/logs` returns the log of the `run-playbook` flow run only.
Each block's log stays on its own `run-block` flow run.
The web app needs the log of each step, to show next to the step that failed.

## Runs that start from and return records

Today a run request names its starting record as a store URL and a revision uuid.
The backend lists a run's outputs by listing a folder in the object store, which no block writes to.

With the datarecord integration of milestone M2.2, Manta is to track data records in its own database.
A run then starts from the project's model, and lists the records it produced.
A record's content is to be served from its own endpoint, under `/v1/data-records/`.
Whether the run row also keeps its final record is still open, as [Open questions](open-questions.md#storing-a-runs-final-record) states.

## Resource requirements

Today no block states the CPU, memory or time it needs.
On one machine that is tolerable, but a solver pod with no memory limit on a cluster can take down its node.

Only the block author knows that a model needs 32 GiB, so the requirement is to be declared on the block.
It then passes with each step to the infrastructure that starts the step, such as a Kubernetes Job.
Whether the requirement is a fixed number or depends on the size of the data is [open](open-questions.md#resource-requirements).

## Block libraries outside this repository

Today `playbook-library` lives in this repository.
The backend imports it to read its playbooks and catalogue, and the block image is built from it here.
So a new block, or a new modelling framework, needs a change to this repository.

The plan has four parts:

- `playbook` and `runner` are published to PyPI and conda-forge, each from its own folder, with CI that versions them apart from the application.
- `playbook-library` moves to a repository of its own, which depends on the published `playbook` and serves as the example for every other block library.
- Each block library builds and publishes its own `bare` image, and Manta builds only the `block-prefect-runtime` layer on top of it.
- The backend stops importing any block library, and a library's catalogue and playbooks reach it through endpoints for syncing.

A block library then pins the version of `playbook` it was built against, as Manta pins any other dependency.
A new catalogue then reaches a running backend without a redeploy of Manta.

## Kubernetes

Today Manta runs only as a Docker Compose stack, and [Deployment topology](deployment.md#kubernetes) describes the planned Kubernetes target.

Running on Kubernetes needs five things:

- The block pool changes to type `kubernetes`, and the playbook pool stays a `process` pool.
- Kubernetes manifests create the workers, with the image, namespace, service account, secrets and resource limits of each, in a repository of their own.
- Block images are pushed to a container registry, which the step pods pull from.
- Blocks declare their resource requirements, as the section above describes.
- Each step pod gets credentials scoped to its run's data, and a network policy that allows only the Prefect API and the object store.

Two prerequisites are already in place.
Records live in the object store, so a fresh pod with an empty disk reads its input.
Prefect's result storage is on the object store, so the playbook worker reads each step's result across machines.
Both deployments record their flow as a module path, `runner.flows:<flow>`, which resolves the same way inside any image that installs `runner`.

## External systems

Manta is to talk to three external systems that it does not talk to today:

- An identity provider that a client already runs, over OpenID Connect or SAML, for single sign-on. The local stack runs Keycloak for sign-in today.
- A licence server for commercial solvers, from which a block checks out a licence.
- A provider of language models for assistance in the web app, either Ollama on the client's own servers or a commercial provider.

Audit records are to live in PostgreSQL with the rest of the application state, kept in one place with tightly controlled access.

## Reading this page

Each section names what exists today, so you can judge whether a change you plan builds on the design or on a stopgap.
Code that leans on a stopgap, such as the backend's import of `playbook-library`, has to change again when the planned design is built.

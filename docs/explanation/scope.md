<!--
SPDX-FileCopyrightText: Manta contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Users and scope

Manta's architecture follows from who uses it and where it runs.
This page names the users Manta is designed for, the places it is meant to run, and the constraints those place on the design.
The rest of the explanation pages refer back to these constraints.

!!! warning "Aims, not the state of Manta today"

    Most of this page states what Manta is designed to become, from its roadmap and its security review.
    Where a section describes what Manta does today, it says so.

## What Manta is

Manta is an open-source web application for energy system modelling and analysis, built by Open Energy Transition.
It aims to make energy modelling possible without writing code.
Its features fall into four groups:

- Data: inspect and manage energy system data.
- Modelling: build and configure models.
- Orchestration: run analyses as playbooks, and scale the compute they need.
- Results: explore results in interactive charts, and build reports.

Three properties set Manta apart from other modelling tools.
It is open source.
It is not tied to one modelling framework.
And a user can change a modelling analysis by choosing blocks and settings, without writing code.

## Who uses Manta

Manta is designed for six kinds of user, and each one asks something different of the architecture:

| User             | What they do                                              | What the architecture owes them                                          |
| ---------------- | --------------------------------------------------------- | ------------------------------------------------------------------------ |
| Analyst          | Runs playbooks and analyses scenarios                     | A way to set up and start a run without code, and to follow it            |
| Modeller         | Builds models and the playbooks that analysts run         | Checks that catch a mistake before a run starts                           |
| Block author     | Writes new blocks, in a block library of their own        | A way to ship block code with its own dependencies, which Manta then runs |
| Stakeholder      | Reads and explores results and reports                    | Ways to read results without knowing how runs work                         |
| Administrator    | Manages who can access what                               | Access control that maps onto projects and runs                           |
| Maintainer       | Builds Manta and runs a hosted service of it              | Monitoring, logs, isolated failures, and parts that upgrade on their own  |

The web app serves the analyst first.
The [user guide](../user-guide/index.md) calls its reader a modeller, because today one person does both jobs.

The block author has the largest effect on the architecture.
Their code comes with dependencies that Manta's own backend could never install side by side, and Manta still has to run it.
The environment per block, the catalogue and the container per step all follow from that one need.
[Blocks, playbooks and the catalogue](blocks-and-playbooks.md) and [Deployment topology](deployment.md) explain those parts.

Manta's main users are grid operators and regulators.
They need security fit for industry, deployment on their own servers, and playbooks they can change without code.
Researchers, think tanks and Open Energy Transition's own modellers come second.
They can already model without Manta, but may want its charts, reports and model building.

## Where Manta runs

Manta is a web application, hosted on a cloud service or on a client's own servers.
A desktop application is out of scope.
A user who wants to can still run the whole stack on one machine, with Docker.

So one system has to run in three places.
These are a developer's Docker Compose stack, a service that Open Energy Transition hosts, and a client's own cluster.
Nothing in how runs execute may assume one machine or a shared file system.
That is why records are pointers into an object store, and why each step runs in a container of its own.

## Data and security

Manta's security review classes it as high-risk, because its later releases are meant to handle confidential client data and personal information.
Until those releases, Manta uses public data only and collects no personal information beyond what a sign-in needs.
The [security policy](https://github.com/manta-plan/manta/blob/main/SECURITY.md) states what Manta guarantees today, which is nothing beyond best effort while it is in alpha.

Manta is designed for the data it handles to move from public data to internal and confidential data.
A block runs code from a block author, so that code is meant to run next to confidential grid data one day.
So keeping runs apart from each other is a security control, not only a convenience for operators.
[Open questions](open-questions.md#the-trust-boundary-for-third-party-blocks) lists what is still to decide about third-party blocks.

Deployments that Open Energy Transition runs are to be hosted in the EU, for GDPR and data residency.
Development, staging and production are to be kept apart, with isolated production keys.
Nothing is to be pushed from a local machine straight to production.

## Open source and open governance

Manta lives in its own GitHub organisation, so that its governance can be shared later.
So its parts have boundaries that an outside contributor can work within.
`playbook` in particular is meant to be usable, and testable, without the rest of Manta.
[Architecture](architecture.md#the-packages-and-their-dependencies) lists the tests that keep it so.

## Audit

All application state is meant to live in PostgreSQL: users, projects, runs, solver licences and audit records.
Audit logs are meant to be kept in one place, with access tightly controlled.
Today the database holds users, projects and runs, and Prefect's own database holds run state.
Manta keeps no audit records and manages no solver licences yet.

With these users and constraints in mind, you can judge whether a design choice serves the block author and the analyst together.
A choice that needs one machine, one shared environment for all blocks, or a backend that imports block code works against them.

# 01 — Vision and scope

Condensed from *Project Manta: Security Review Summary* (12 August 2026, Lauren
Clisby & Siddharth Krishna). This document keeps the parts that constrain the
architecture; the security review remains the authority on security and privacy
commitments.

## What Manta is

Manta is an enterprise-grade, open-source web application for energy system modelling
and analysis, built by Open Energy Transition (OET). Its ambition is to become the
global standard for energy transition planning by making energy modelling accessible
without writing code.

Four capabilities define it:

1. **Data** — inspecting and managing energy system data.
2. **Modelling** — building and configuring models.
3. **Orchestration** — running analysis workflows and scaling the compute they need.
4. **Results** — interactive visualisation and report generation.

What sets it apart: fully open source, not tied to a single modelling framework, and
able to customise modelling and analysis workflows without coding.

## Who uses it

| Role | What they do | What the architecture owes them |
| --- | --- | --- |
| **Analyst** | Runs workflows, analyses scenarios. The primary user. | A no-code way to configure and launch a run, and to watch it progress |
| **Modeller** | Builds models and authors the workflows Analysts run | Authoring and validation that catches mistakes before a run starts |
| **Plug-in Developer** | Extends the workflow system with new units of work | A way to ship code with its own dependencies that Manta can execute without installing it |
| **Stakeholder** | Views and explores results and reports | Read paths that do not require understanding the machinery |
| **Admin** | Manages system access | Access control that maps onto projects and runs |
| **Maintainer** | The Manta team | Operability: observable runs, isolated failure domains, upgradeable parts |

The Plug-in Developer role is the one with the largest architectural consequence. It
means third-party code, with dependency sets Manta's own backend could never install,
must be executable by the platform. Nearly everything in
[04](04-blocks-and-playbooks.md) and [07](07-deployment-topology.md) follows from that
single requirement.

The primary user base is energy grid operators and regulators, for whom industry-grade
security, on-premise deployment, and no-code custom workflows are critical. Academics,
think tanks and OET's own modellers are a secondary audience — they can already model
without Manta, but may want its visualisation and model-building capabilities.

## Where it runs

A web application, deployed on-premise or on the cloud. Desktop applications are
explicitly out of scope, though a power user can run the whole stack locally under
Docker or Kubernetes.

This means the deployment target is a variable, not a constant: the same system must
run as a developer's `docker compose` stack, as an OET-managed cloud SaaS, and inside
a client's own cluster. The architecture treats the execution target as a pluggable
concern for exactly this reason.

## Roadmap

| Milestone | Timeframe | Phase | Security focus |
| --- | --- | --- | --- |
| **M1** | End Aug 2026 | Vertical slice | Low risk. Local dev-only deployments, no external exposure, public test data only |
| **M2** | End Sep 2026 | Public announcement (OpenMod) | Visibility. Repository security tooling, branch protection, `SECURITY.md`, `CONTRIBUTING.md` |
| **M3** | Dec 2026 | MVP (cloud) | Security roadmap. Public data only; OET-hosted with anonymous guest access; external penetration test and threat modelling |
| **M4** | Jun–Dec 2027 | v1 launch | Confidentiality. Full SaaS, SSO/MFA, RBAC, vulnerability disclosure programme, SLAs |

The project is classified **High-Risk**, because it will eventually handle client
confidential data and personal information — though not before M4. Until then the
platform uses open public data only and collects no personal information.

## Constraints this places on the architecture

**Compute must scale from a laptop to a cluster.** The MVP is an OET-managed cloud
deployment; v1 adds infrastructure-as-code for on-premise installation and solver
licence management. Nothing in the execution model may assume a single machine or a
shared filesystem.

**Data classification will tighten.** Public at MVP; Internal and Confidential at v1.
Anything that executes user-supplied or plug-in-supplied code will eventually do so
next to confidential grid data. Isolation between runs is a security control, not
just an operational nicety — see [08](08-open-questions.md) on the plug-in trust
boundary.

**Deployments are EU-hosted and environment-separated.** OET-managed deployments run
on EU-based servers for GDPR and data residency. Development, staging and production
are strictly logically separated, with production keys isolated and no direct
local-to-production pushes.

**Open source and open governance.** Manta is built in a separate GitHub organisation
with a view to shared open governance post-MVP. Component boundaries need to be
boundaries an outside contributor can work within, and the block/playbook framework in
particular is designed to be usable — and testable — without the rest of Manta.

**Auditability.** All application state lives in PostgreSQL, including jobs, users,
solver licensing and audit records. Audit logs are centralised with strictly
controlled access.

## Agreed technology

From the security review, and assumed throughout these documents:

| Layer | Choice |
| --- | --- |
| Frontend | TypeScript, React |
| Everything else | Python |
| Orchestration | Prefect |
| Compute | Prefect workers on Docker or Kubernetes |
| Application database | PostgreSQL |
| Model data | S3-compatible object store, managed with DuckDB; DuckDB WASM for the local/demo playground |
| Authentication | Undecided for MVP; v1 uses an IdP with OIDC or SAML |
| LLM assistance | Post-MVP: Ollama on-premise, or a commercial provider |

## What these documents cover

**In scope:** the workflow execution stack — how a unit of modelling work is defined,
composed into a playbook, validated, dispatched to an environment that can run it, and
observed to completion.

**Out of scope here:** the frontend's internal architecture, the data layer's DuckDB
storage and patching model, authentication and RBAC design, and the reporting and
visualisation subsystem. These interact with what is described here — most obviously
the data layer, which supplies and stores everything a run reads and writes — but each
warrants its own design document.

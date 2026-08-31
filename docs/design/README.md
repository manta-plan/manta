# Manta Architecture Design

This directory describes Manta's **target architecture**: how the system is meant to
fit together once the MVP implementation is complete. It is written for the Manta team, to give everyone a high-level understanding of all other components in the system and to help them implement and integrate their work into other components. As it's in markdown, it's also easy to feed this as context to AI agents.

This doc is **WIP**, so nothing is set in stone, and a **living document**, so it should be updated by any PR that changes an architectural decision (use an AI to speeden up this check / draft updates to this doc!).
## Contents

| Doc | What it covers |
| --- | --- |
| [01 — Vision and scope](01-vision-and-scope.md) | What Manta is, who it is for, the roadmap, and the constraints those place on the architecture |
| [02 — System architecture](02-system-architecture.md) | The components and how they relate, as C4 context / container / component diagrams |
| [03 — Workflow orchestration](03-workflow-orchestration.md) | A Prefect primer, and exactly how Manta uses it. **Read this before 04–07.** |
| [04 — Blocks and playbooks](04-blocks-and-playbooks.md) | The domain model: what a block is, what a playbook is, how they are described and checked |
| [05 — Repository interface](05-repository-interface.md) | The seam between the `manta` and `blocks` repositories, and who owns what |
| [06 — Execution lifecycle](06-execution-lifecycle.md) | End to end, from block release through playbook authoring to a finished run |
| [07 — Deployment topology](07-deployment-topology.md) | Local development, cloud, and Kubernetes; how environments become work pools and images |
| [08 — Open questions](08-open-questions.md) | Decisions not yet made, known gaps, and risks that need closing |

**Still to come**: the frontend's internal architecture, the data layer's DuckDB
storage and patching model, authentication and RBAC design, and the reporting and
visualisation subsystem. These interact with what is described here — most obviously
the data layer, which supplies and stores everything a run reads and writes — but each
warrants its own design document.

## Technology stack

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
| LLM assistance | Ollama on-premise, or a commercial provider |

## Status and conventions

These documents describe an **end state**, not what is currently merged. Where
present-day reality differs, it is called out inline. 

Throughout:

- **Decided** means the approach is agreed and the code either exists or is planned
  against it.
- **Proposed** means this document is making a recommendation that has not been
  ratified.
- Anything  undecided lives in [08 — Open questions](08-open-questions.md)
.

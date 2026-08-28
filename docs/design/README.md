# Manta Architecture Design

This directory describes Manta's **target architecture**: how the system is meant to
fit together once the workflow-execution stack is complete. It is written for a
software engineer joining the project who knows what a workflow orchestrator is in
general terms, but has never used Prefect specifically.

## Read in this order

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

## Status and conventions

These documents describe an **end state**, not what is currently merged. Where
present-day reality differs, it is called out inline. As of August 2026:

- Manta's Prefect integration exists as a demonstration flow that computes digits of
  pi. It proves the submit-and-observe plumbing; it is not the real workload.
- The blocks and playbooks engine exists as a proof of concept on the
  `feature/playbooks` branch of the `blocks` repository. Its shape is settled; its
  integration with Manta is not yet built.

Throughout:

- **Decided** means the approach is agreed and the code either exists or is planned
  against it.
- **Proposed** means this document is making a recommendation that has not been
  ratified.
- Anything genuinely undecided lives in [08 — Open questions](08-open-questions.md)
  rather than being quietly resolved in prose.

These docs supersede `docs/prefect.md`, which was written as an implementation plan
for a single pull request rather than as a description of the system.

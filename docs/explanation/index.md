<!--
SPDX-FileCopyrightText: Manta contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Explanation

These pages explain why we have built Manta in the way we have.
For exact interfaces, see the [reference pages](../reference/index.md).

## Why Manta exists

This page is for anyone who wants to know what Manta is for, with no technical background needed.

- [Manta's purpose](purpose.md): open it to see the problem Manta answers, and why it is built around a community.

## How Manta works

These pages describe Manta as it is in the code today.
They are aimed at a developer who wants to understand the system before changing it.

- [Users and scope](scope.md): open it to see who Manta is designed for, where it runs, and the constraints that shape its design.
- [Architecture](architecture.md): open it to see how the packages and services fit together, and how one playbook run moves through them.
- [Orchestration with Prefect](orchestration.md): open it to learn the Prefect ideas Manta relies on, and how Manta runs playbooks with them.
- [Blocks, playbooks and the catalogue](blocks-and-playbooks.md): open it to see why blocks are described as data, and how playbooks chain and check them.
- [Run lifecycle](run-lifecycle.md): open it to follow a run from the block image to its result, and see where each check and failure happens.
- [Deployment topology](deployment.md): open it to see how environments become images, how the stack is set up, and what changes on Kubernetes.

## Where Manta is going

These pages describe work that is decided but not built, and questions that are still open.

- [Planned changes](planned-changes.md): open it to see the decided changes and what stands in their place today.
- [Open questions](open-questions.md): open it to see the design questions still to answer, and the options for each.

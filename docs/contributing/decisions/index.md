<!--
SPDX-FileCopyrightText: Manta contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Architecture decision records

An architecture decision record (ADR) is a page that records one decision about how Manta is built: what was decided, why, and the design that came out of it.
It is written for Manta developers who were not part of the discussion.

## When to write one

Write an ADR for a decision that is costly to reverse or that reaches across services.
Examples are a service boundary, where data lives, a tool the services depend on, the protocol between the frontend, backend, and runner, and how Manta is deployed.
Decisions about how the team works, such as sprint length, need no ADR.
Neither does a choice inside one module that the code and its review explain.

## From plan to record

A large decision, such as a new service, starts as a detailed plan and ends as an ADR that summarizes it.

A plan PR adds the ADR as `NNNN-title.md` with the status Proposed, and the detailed implementation plan in a folder `NNNN-title/` next to it.
The ADR states the decision and a summary of the design, and links to the plan.
The team reviews both in the plan PR.
Implementation PRs link to the plan, and update it where the build departs from it.

Once the team agrees on the plan, it continues in one of two ways:

- **The plan PR merges before the implementation**, with the status Accepted.
  This suits a plan built over several PRs, which then link to the plan on `main`.
  When the last of them is merged, a final PR rewrites the ADR's design section to describe the design as built, deletes the plan folder, and sets the status to Implemented.
- **The plan PR stays open during the implementation.**
  This suits a plan built in one PR, or one the team expects to change while it is built.
  Once the implementation is approved and merged, the plan PR rewrites the ADR's design section to describe the design as built, deletes the plan folder, sets the status to Implemented, and merges.
  The plan folder never reaches `main`.

Either way, the ADR then links to the plan at its last commit, so the detail stays reachable in the history.

A small decision needs no plan.
Its ADR is usually written after the decision was made in a meeting, an issue, or a PR review, and links to where it was made.

An implemented ADR is not edited, except for its status.
To change a decision, write a new ADR and set the old one's status to "Superseded by ADR N".
This includes a decision made for the MVP and revisited after it.

## How to write one

1. Copy the [template](template.md) to `NNNN-title.md`, with the next free number and the decision as the title, such as `0001-one-session-container-per-user-and-project.md`.
2. Fill it in.
   Link to discussions and comparisons rather than copying them in.
3. Add a row to the table below.

## Decisions

| ADR | Title | Status |
| --- | ----- | ------ |

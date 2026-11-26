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

## Plans

An ADR has no plan, a short plan, or a long plan:

- **No plan.**
  The ADR records a decision made in a meeting, an issue, or a PR review, and links to where it was made.
- **A short plan.**
  The plan is the ADR's design section, so the decision and the plan are one page.
- **A long plan.**
  When the plan is too long to review as one page, it goes in a folder `NNNN-title/` next to the ADR for review and implementation.
  The ADR summarises the plan and links to it.
  Implementation PRs link to the plan, and update it where the build departs from it.
  The plan folder is **removed** once implementation is complete, and the ADR retains a final summary.

The last PR to merge, whether the ADR PR or an implementation PR, completes the ADR.
It rewrites the design section to describe the design as built, deletes any plan folder, and sets the status to Implemented.
The ADR then links to the plan at its last commit, so the detail stays in the history.

An implemented ADR is not edited, except to update its status or to make its prose clearer.
To change a decision, write a new ADR and set the old one's status to "Superseded by ADR N".
This includes a decision made for the MVP and revisited after it.

## How to write one

1. Copy the [template](_template.md) to `NNNN-title.md`, with the decision as the title.
   `NNNN` is the number of the PR that adds the ADR, or of the issue where the decision was made, padded to four digits.
   For PR #303, that is `0303-one-session-container-per-user-and-project.md`.
   Issues and PRs share one sequence of numbers on GitHub, so two ADRs never get the same number, and none is renumbered when another is rejected.
   Open the PR as a draft to learn its number before naming the files.
2. Fill it in.
   Link to discussions and comparisons rather than copying them in.
3. Add a row to the table below.

## Decisions

| ADR | Title | Status |
| --- | ----- | ------ |

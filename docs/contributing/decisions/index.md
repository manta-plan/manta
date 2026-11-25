<!--
SPDX-FileCopyrightText: Manta contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Architecture decision records

An architecture decision record (ADR) is a short page that records one decision about how Manta is built, and why.
Its reader is someone who joins later and asks why the code is the way it is.

## When to write one

Write an ADR for a decision that is costly to reverse or that reaches across services.
Examples are a service boundary, where data lives, a tool the services depend on, the protocol between the frontend, backend, and runner, and how Manta is deployed.
Decisions about how the team works, such as sprint length, need no ADR.
Neither does a choice inside one module that the code and its review explain.

Most decisions are made in a meeting, an issue, or a PR review.
The ADR records the outcome afterwards and links to where it was made.
To propose a decision instead, open a PR that adds an ADR with the status Proposed, and discuss it there.

## How to write one

1. Copy the [template](template.md) to `NNNN-title.md`, with the next free number and the decision as the title, such as `0001-one-session-container-per-user-and-project.md`.
2. Fill it in.
   Link to design plans, comparisons, and discussions rather than copying them in.
3. Add a row to the table below.

An accepted ADR is not edited, except for its status.
To change a decision, write a new ADR and set the old one's status to "Superseded by ADR N".
This includes a decision made for the MVP and revisited after it.

## Decisions

| ADR | Title | Status |
| --- | ----- | ------ |

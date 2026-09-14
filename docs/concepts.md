---
title: Core concepts
description: The essential building blocks of the Manta operating model.
sidebar:
  order: 2
---

## Projects

Projects provide a shared boundary for related work. They keep the runs, context, and results for one operational purpose together.

## Playbooks

A playbook is a repeatable process. It gives a team a common way to express work without forcing every workflow into the same shape.

## Runs

A run is one execution of a playbook. Manta records its current state, when it started, how long it took, and the result it produced.

Runs move through states as work progresses. The exact state comes from the execution system so the product can preserve the most useful operational detail.

## Results

Results are the durable output of a run. They are where the work becomes useful to the people making decisions, reviewing outcomes, or starting the next operation.

:::note
Manta is designed to keep the relationship between a playbook and its runs visible. That history is the foundation for learning from operational work over time.
:::

## A useful mental model

| Building block | Answers the question |
| --- | --- |
| Project | What work belongs together? |
| Playbook | How do we repeat this work? |
| Run | What happened this time? |
| Result | What did the work produce? |

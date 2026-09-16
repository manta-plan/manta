<!--
SPDX-FileCopyrightText: 2026 Manta Blocks contributors

SPDX-License-Identifier: MIT
-->

# Manta Blocks

A **block** is one unit of work on an energy model. A **playbook** chains blocks
together into something you can run.

This package is the *framework only*: what a block is, what a playbook is, and how
they are described, checked, drawn, deployed, and run. Concrete blocks live in block
libraries — [`manta-batteries`](../manta-batteries) is the one Manta ships — so that
each library can bring its own dependencies (PyPSA and friends) without this package
needing any of them.

Blocks are written in Python. Playbooks can be written in YAML or Python. Each block
declares which environment it needs, so one playbook can span environments that could
never be installed side by side: each step runs where it belongs, and the results are
passed along.

> This directory is developed inside the `manta` monorepo for now, but is written as
> a standalone package destined for PyPI/conda-forge, so third-party modellers can
> define blocks without touching the Manta app. Nothing in here may depend on the
> Manta backend.

## Layout

```text
src/
  manta_blocks/      A block, and everything needed to describe one without running it
    core.py          DataRecord, BlockDims, ConfigSchema, MantaBlock
    registry.py      Which blocks exist, and the catalogue that describes them
    environments.py  The environments blocks run in
    records.py       Reading/writing the data a record points at (local paths or S3)
    deployment.py    What needs deploying, and the one place deployment names are made
    entrypoint.py    The Prefect flow every block deployment runs
  manta_playbooks/   Blocks chained together
    playbook.py      What a playbook is: steps, wiring, conditions
    validation.py    Everything that can be checked before running
    yaml_io.py       Playbooks as documents: reading, writing, sending
    graph.py         A playbook as boxes and arrows, worked out without running it
    execution.py     Running a playbook, here or across environments
    deploy.py        Working out what to deploy, and creating it
    control.py       The front door: deploy, start a run, ask how it is doing
```

`manta_blocks` never imports `manta_playbooks`. That way `manta_playbooks` can become
its own project later without anything having to be untangled first.

## Getting started

```bash
uv sync
uv run pytest
```

## Writing a block

```python
from manta_blocks import BlockDims, ConfigSchema, DataRecord, MantaBlock, register


class ShrinkConfig(ConfigSchema):
    factor: int = 2


@register("shrink")
class Shrink(MantaBlock[ShrinkConfig]):
    """Make the model smaller."""

    ENV = "pypsa"
    CONFIG = ShrinkConfig
    DIMS = BlockDims(requires=frozenset({"snapshot"}))

    def flow(self, record: DataRecord) -> DataRecord: ...
```

What a block declares:

| Declaration | Meaning |
| --- | --- |
| `ENV` | the pixi environment it needs |
| `MANIFEST` | for a third-party block, where to find that environment |
| `CONFIG` | its settings, as a pydantic model |
| `DIMS` | the dimensions it needs, adds, and removes |
| `INPUTS` | settings that another block fills in, rather than the user |
| `OUTPUTS` | the results it offers to later blocks |

A block class is checked as soon as it is written: every name in `INPUTS` has to be a
setting that can hold a `DataRecord` and has a default, so a block is always usable
with nothing wired to it.

### Block libraries

A library announces its blocks by calling `register_lazy` when it is imported, naming
the module each block lives in without importing it — which is what keeps everything
else usable without the library's dependencies installed:

```python
# my_library/__init__.py
from manta_blocks import register_lazy

register_lazy("shrink", "my_library.shrink:Shrink")
```

Which libraries a process should know about is either passed explicitly
(`load_block_sources(["my_library"])`, or `python -m manta_blocks my_library`) or
read from the `MANTA_BLOCK_SOURCES` environment variable — that is how Prefect
workers learn what they serve.

### Records

A `DataRecord` is only ever a pointer to data — a local path or an `s3://bucket/key`
url. `manta_blocks.records` stages S3 data to a local file on the way into a block
and publishes results on the way out (`stage`, `stage_output`, `sibling_url`), using
boto3's standard `AWS_*` environment variables. Install with the `s3` extra
(`manta-blocks[s3]`) where records live in object storage.

## Writing a playbook

```yaml
name: cluster-expand-dispatch

initial_data:
  dims: [snapshot]

steps:
  - name: cluster
    block: cluster_time

  - name: expansion_overnight
    block: overnight_capacity_expansion
    when:
      config: globals.expansion_mode
      equals: overnight

  - name: dispatch
    block: rolling_horizon_dispatch
    when:
      config: globals.expansion_mode
      equals: overnight
    inputs:
      capacity_source: ${steps.expansion_overnight.output}
```

Settings live in a separate document, filed by step name plus a `globals` section
everything can see. Keeping them apart is what lets one playbook be run several ways.

### How work flows between steps

Every step is handed the record the previous step produced. On top of that, a step can
reach back for a *particular* earlier step's result and put it into one of its settings
(`${steps.<step>.<output>}`). Those are separate things: in the example above,
`dispatch` receives the record from the step before it *and* the capacities that the
expansion step specifically decided.

### Using a block more than once

Each step has its own name, so `overnight_capacity_expansion` can appear as both
`expansion_2030` and `expansion_2040`, each with its own settings.

### Conditions

`when: {config: <dotted path>, equals: <value>}` switches a step on or off based on the
settings alone, never on the data. So which steps will run is known before anything
runs, which is what makes a playbook checkable and drawable up front.

Which steps run is decided in exactly one place, so what gets checked, drawn, deployed,
and run can never disagree.

### Playbooks inside playbooks

A step can be another playbook: `playbook: <path>` in YAML, or
`Playbook.add_playbook(name, other)` in Python. A browser with no filesystem can also
send the inner playbook written out in place.

Anything the inner playbook does not wire up itself is offered to the outer one as
`<step>.<setting>`, to be fed exactly like a block's own inputs. Its settings live
under its step's name, and it inherits the outer `globals` unless it has its own.

## Checking a playbook

`playbook.issues(config)` returns everything wrong with a playbook without raising;
`playbook.validate_playbook(config)` raises instead. Each problem names the step it is
about and, where it applies, the exact setting, so an editor can mark the right box and
the right field.

What is checked: step names are unique and usable; every reference points at an earlier
step that really offers that result; a step that runs is not fed by one that does not;
every step finds the dimensions it needs still present; settings belong to a step and
match what that step accepts; and blocks sharing an environment name agree on what it is.

All of this works for blocks this environment cannot import, which is the ordinary case
for anything driving playbooks from outside — a block's description says enough. The one
thing that cannot travel is a rule a block expresses in code, such as "exactly one of
these two settings": that can only be checked where the block itself can be imported.

## Drawing a playbook

`playbook.to_graph(config)` gives boxes and arrows as plain data — nodes, arrows, which
steps run, and the dimensions at each point. `playbook.to_mermaid(config)` renders that
as a diagram. Neither runs any of the playbook.

## Running and deploying

Each environment gets a Prefect work pool, and each block is deployed onto the pool for
the environment it needs. A worker started inside that environment picks the work up,
so nothing ever has to activate an environment itself.

Two ways to make that happen:

- **Per playbook** (power users, no Manta app): `manta_playbooks.control.deploy`
  registers exactly what one playbook needs; work pools are created by the operator
  (`ProcessPixiRenderer.work_pool_commands(plan)` prints the commands).
- **Per catalogue** (a managed installation): `provision_catalogue(catalogue, env)`
  creates the pools and one deployment per catalogued block, plus the playbook
  orchestrator. After that, any playbook of catalogued blocks starts with a single
  `run_deployment` call — this is what Manta's docker setup runs at start-up.

```python
from manta_playbooks.control import deploy, start_run, run_status

deploy(playbook, config)  # make everything ready
info = start_run(doc, config, record)  # start it, return straight away
run_status(info.flow_run_id)  # how is it going
```

To run in one process instead — as the tests do — use `playbook.run(record, config)`.
With `dispatch=True`, any step needing a different environment is handed off to it.

## Describing every block at once

No single environment can import every block, so each one describes what it can:

```bash
pixi run -e full python -m manta_blocks my_library > full.json
pixi run -e other python -m manta_blocks other_library > other.json
```

`merge_catalogues` combines those into one description of every block in the system:
names, settings as JSON schema, dimensions, and which settings are wired rather than
typed in (marked `x-manta-input`). That is enough to draw a playbook, offer its
settings, and check how it is wired, from a process that could not import a single one
of the blocks it is describing.

## Current limitations

- A block writes a whole new file rather than only what it changed, because PyPSA
  cannot yet compare two networks or store a difference. Confined to
  `manta_batteries.pypsa_helpers`. Once real record storage exists, `initial_data`
  can go too: the dimensions would be read from the incoming record instead of
  declared.
- Resource requirements (cpu, memory, walltime) are not modelled yet. The intent is to
  declare them relative to the data, so absolute requirements can be worked out from
  the record being processed.
- Only the pixi-and-process renderer exists. `Renderer` is the seam for containers or a
  cluster.
- A playbook-wide `globals` section is only read by `when` conditions and nested
  playbooks; it is not yet merged into each block's settings (see
  `execution._run_block_step` for where that would happen).
- Conditions can only look at settings, not at the contents of the data.
- A block declares `OUTPUTS`, but every block so far produces exactly one result.

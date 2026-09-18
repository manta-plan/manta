<!--
SPDX-FileCopyrightText: 2026 Manta Blocks contributors

SPDX-License-Identifier: MIT
-->

# Manta Blocks

A **block** is one unit of work on an energy model. A **playbook** chains blocks
together into something you can run.

Blocks are written in Python. Playbooks can be written in YAML or Python. Each block
declares which environment it needs, so one playbook can span environments that could
never be installed side by side: each step runs where it belongs, and the results are
passed along.

This package is deliberately unaware of any orchestration tool. Running a block is a
plain method call; everything about *where* and *how* those calls happen in
production - containers, schedulers - lives in Manta's backend (see
[backend playbook runs](../backend/README.md#playbook-runs)). That is what lets this
package move to its own repository, and lets modelers write and test blocks without
knowing anything about Manta's infrastructure.

> **Note**: this package lives inside the `manta` repository only for the MVP. It is
> designed to be lifted out into its own `manta-blocks` repository unchanged: nothing
> in here imports Manta, and Manta only consumes it as a normal Python dependency.

## Layout

```text
src/
  blocks/          A block, and everything needed to describe one without running it
    core.py        DataRecord, BlockDims, ConfigSchema, MantaBlock
    registry.py    Which blocks exist, and the catalogue that describes them
    environments.py  The environments blocks run in
    storage.py     Where a record's bytes live (local files or S3)
    library/       The blocks that ship with Manta (these need PyPSA)
  playbooks/       Blocks chained together
    playbook.py    What a playbook is: steps, wiring, conditions
    validation.py  Everything that can be checked before running
    yaml_io.py     Playbooks as documents: reading, writing, sending
    graph.py       A playbook as boxes and arrows, worked out without running it
    execution.py   Running a playbook, in-process or through a pluggable StepRunner
    library/       The playbooks that ship with Manta, with default settings
```

`blocks` never imports `playbooks`. That way `playbooks` can become its own project
later without anything having to be untangled first.

## Getting started

```bash
uv sync                                  # the framework, without PyPSA
uv run pytest                            # runs everything that works without PyPSA
uv sync --extra pypsa && uv run pytest   # everything, including the PyPSA blocks
```

The default environment deliberately has no PyPSA. That the tests pass without it is
the proof that a block's own dependencies stay its own.

## Writing a block

```python
from blocks import BlockDims, ConfigSchema, DataRecord, MantaBlock, register


class ShrinkConfig(ConfigSchema):
    factor: int = 2


@register("shrink")
class Shrink(MantaBlock[ShrinkConfig]):
    """Make the model smaller."""

    ENV = "pypsa"
    CONFIG = ShrinkConfig
    DIMS = BlockDims(requires=frozenset({"snapshot"}))

    def run(self, record: DataRecord, output_base: str) -> DataRecord: ...
```

What a block declares:

| Declaration | Meaning |
| --- | --- |
| `ENV` | the named environment it needs |
| `MANIFEST` | for a third-party block, where to find that environment |
| `CONFIG` | its settings, as a pydantic model |
| `DIMS` | the dimensions it needs, adds, and removes |
| `INPUTS` | settings that another block fills in, rather than the user |
| `OUTPUTS` | the results it offers to later blocks |

`run` receives the record to work on and `output_base`: where the caller wants the
result produced, as a URL without an extension. The block writes its output there,
appending whatever suffix fits its format, and returns a record pointing at the exact
URL written. Records can point at local files or `s3://` URLs; `blocks.storage`
handles both, configured purely through the standard `AWS_*` environment variables.

A block class is checked as soon as it is written: every name in `INPUTS` has to be a
setting that can hold a `DataRecord` and has a default, so a block is always usable
with nothing wired to it.

The blocks that ship with Manta are registered by name without being imported, which
is what keeps everything else usable without PyPSA installed.

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

Or the same thing in Python:

```python
pb = Playbook(name="cluster-expand-dispatch", initial_dims=frozenset({"snapshot"}))
pb.add("cluster", ClusterTime)
overnight = pb.add(
    "expansion_overnight",
    OvernightCapacityExpansion,
    when=When(config="globals.expansion_mode", equals="overnight"),
)
pb.add(
    "dispatch",
    RollingHorizonDispatch,
    inputs={"capacity_source": overnight.output},
    when=When(config="globals.expansion_mode", equals="overnight"),
)
```

Settings live in a separate document, filed by step name plus a `globals` section
everything can see. Keeping them apart is what lets one playbook be run several ways.

The playbooks that ship with Manta live in `playbooks/library/`, each with a default
settings document under `configs/`; `playbooks.library.library_playbooks()` lists
them, which is how Manta offers them to users.

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

Which steps run is decided in exactly one place, so what gets checked, drawn, and run
can never disagree.

### Playbooks inside playbooks

A step can be another playbook: `playbook: <path>` in YAML, or
`Playbook.add_playbook(name, other)` in Python. A browser with no filesystem can also
send the inner playbook written out in place.

Anything the inner playbook does not wire up itself is offered to the outer one as
`<step>.<setting>`, to be fed exactly like a block's own inputs. Its settings live
under its step's name, and it inherits the outer `globals` unless it has its own.

Checking and dimension folding recurse. A problem inside a nested playbook is
reported against its full path, and a playbook that ends up containing itself is
reported rather than followed until the process runs out of stack.

## Checking a playbook

`playbook.issues(config)` returns everything wrong with a playbook without raising;
`playbook.validate_playbook(config)` raises instead. Each problem names the step it is
about and, where it applies, the exact setting, so an editor can mark the right box and
the right field.

What is checked: step names are unique and usable; every reference points at an earlier
step that really offers that result; a step that runs is not fed by one that does not;
every step finds the dimensions it needs still present; settings belong to a step and
match what that step accepts; and blocks sharing an environment name agree on what it is.

Dimensions are the interesting one. Each block says which it needs, adds, and removes,
and those are followed from `initial_dims` through the steps that will run. If a step
needs something an earlier step removed, the message says which step removed it.

All of this works for blocks this environment cannot import, which is the ordinary case
for anything driving playbooks from outside - a block's description says enough. The one
thing that cannot travel is a rule a block expresses in code, such as "exactly one of
these two settings": that can only be checked where the block itself can be imported.

## Drawing a playbook

`playbook.to_graph(config)` gives boxes and arrows as plain data - nodes, arrows, which
steps run, and the dimensions at each point. `playbook.to_mermaid(config)` renders that
as a diagram.

Neither runs any of the playbook. That matters with real blocks: asking for a picture
should not start a solver.

Steps switched off by a condition stay in the graph, marked as not running, so the
branch not taken is still visible.

## Running a playbook

```python
result = playbook.run(record, config, output_prefix="s3://bucket/some/run")
```

The playbook is checked first, then each step runs in turn. Step `cluster` writes its
output to `<output_prefix>/cluster.<suffix>`; a step inside a nested playbook writes
under its nesting step's name. A finished run is therefore a browsable folder of
every step's output.

By default every block runs in the current process, which is what tests and local use
want. To run blocks anywhere else, pass a `StepRunner`:

```python
class StepRunner(Protocol):
    def run_block(self, block, *, step_name, config, record, inputs, output_base): ...
```

`execute_playbook` walks the playbook, decides which steps run, wires inputs, and
hands the runner one fully spelled-out block invocation at a time. Manta's runtime
implements this protocol to run every block in its own container; this package never
learns how.

## Describing every block at once

No single environment can import every block, so each one describes what it can:

```bash
python -m blocks > catalogue.json
```

Run once per environment, `merge_catalogues` combines the results into one description
of every block in the system: names, settings as JSON schema, dimensions, and which
settings are wired rather than typed in (marked `x-manta-input`). That is enough to
draw a playbook, offer its settings, and check how it is wired, from a process that
could not import a single one of the blocks it is describing.

A generated catalogue of this library's blocks ships inside the package
(`src/blocks/library/catalogue.json`, loaded via `blocks.library.library_catalogue()`)
so that Manta's backend can list blocks and validate playbooks without PyPSA; see
`blocks/library/__init__.py` for how it is regenerated.

## Current limitations

- Records point at PyPSA netCDF files for now, and a block writes a whole new file
  rather than only what it changed, because PyPSA cannot yet compare two networks or
  store a difference. Both are confined to `blocks/library/pypsa_helpers.py`.
  Once real record storage exists, `initial_data` can go too: the dimensions would be
  read from the incoming record instead of declared.
- Resource requirements (cpu, memory, walltime) are not modelled yet. The intent is to
  declare them relative to the data, so absolute requirements can be worked out from
  the record being processed.
- Conditions can only look at settings, not at the contents of the data.
- A block declares `OUTPUTS`, but every block so far produces exactly one result.

<!--
SPDX-FileCopyrightText: 2026 Manta contributors

SPDX-License-Identifier: MIT
-->

# playbook

A **block** is one unit of work on an energy model. A **playbook** chains blocks
together into something you can run.

Blocks are written in Python. Playbooks can be written in YAML or Python. Each block
declares which environment it needs, so one playbook can span environments that could
never be installed side by side: each step runs where it belongs, and the results are
passed along.

This package is the *framework*: what a block is, what a playbook is, and how to run
one. It ships no blocks and no playbooks of its own — the ones Manta ships live next
door in [`playbook-library`](../playbook-library), which imports this package exactly
the way your own library would.

## What is deliberately not here

**Nothing about orchestration.** Running a block is a plain method call. Everything
about *where* and *how* those calls happen in production — containers, schedulers,
Prefect — lives in Manta's backend, behind the `StepRunner` seam described below.
Nothing in this package imports Prefect, Docker, or Manta, and nothing ever should:
that is what lets a modeller write and test a block without knowing anything about
Manta's infrastructure, and what lets this package move to its own repository later.

**Checking a playbook before running it.** Validation (are the steps wired to results
that exist? does each block find the data it needs?) and drawing a playbook as a
diagram are not part of this package yet. A playbook is taken as given when it runs.
They are coming as a follow-up; this is the minimum that runs.

## Layout

```text
src/playbook/
  blocks/          A block, and everything needed to describe one without running it
    core.py        DataRecord, BlockDims, ConfigSchema, MantaBlock
    registry.py    Which blocks exist, and the catalogue that describes them
    environments.py  The environments blocks run in
    storage.py     Where a record's bytes live (local files or S3)
    run_one.py     Running a single block from the command line
  playbooks/       Blocks chained together
    playbook.py    What a playbook is: steps, wiring, conditions
    yaml_io.py     Playbooks as documents: reading, writing, sending
    execution.py   Running a playbook, in-process or through a pluggable StepRunner
```

`blocks` never imports `playbooks`. A block library only depends on the half it
needs.

## Getting started

```bash
uv sync
uv run pytest
```

The tests need nothing installed beyond this package. That they pass without PyPSA —
or any other modelling framework — is the proof that a block's own dependencies stay
its own.

## Writing a block

```python
from playbook.blocks import BlockDims, ConfigSchema, DataRecord, MantaBlock


class ShrinkConfig(ConfigSchema):
    factor: int = 2


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
URL written. Records can point at local files or `s3://` URLs; `playbook.blocks.storage`
handles both, configured purely through the standard `AWS_*` environment variables.

A block class is checked as soon as it is written: every name in `INPUTS` has to be a
setting that can hold a `DataRecord` and has a default, so a block is always usable
with nothing wired to it.

### Making a block findable

A playbook names a block by name, in processes that often cannot import it. So a
block library announces its blocks without importing them:

```python
# playbook_library/__init__.py
from playbook.blocks import register_lazy

register_lazy("shrink", "playbook_library.shrink:Shrink")
```

The name becomes known everywhere; the import happens only where the block actually
runs. A process learns which libraries to load from the `MANTA_BLOCK_SOURCES`
environment variable (comma-separated module names), or is told explicitly via
`load_block_sources([...])`.

Blocks that live in the same environment as the code using them can skip the
indirection and use the `@register("name")` decorator on the class instead.

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
runs, which is what will make a playbook checkable and drawable up front.

Which steps run is decided in exactly one place (`Playbook.active`), so what gets run
can never disagree with what a reader of the playbook expects.

### Playbooks inside playbooks

A step can be another playbook: `playbook: <path>` in YAML, or
`Playbook.add_playbook(name, other)` in Python. A browser with no filesystem can also
send the inner playbook written out in place.

Anything the inner playbook does not wire up itself is offered to the outer one as
`<step>.<setting>`, to be fed exactly like a block's own inputs. Its settings live
under its step's name, and it inherits the outer `globals` unless it has its own. A
playbook that ends up containing itself is reported rather than followed until the
process runs out of stack.

## Running a playbook

```python
result = playbook.run(record, config, output_prefix="s3://bucket/some/run")
```

Each step runs in turn. Step `cluster` writes its output to
`<output_prefix>/cluster.<suffix>`; a step inside a nested playbook writes under its
nesting step's name. A finished run is therefore a browsable folder of every step's
output.

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

## Running one block

```bash
python -m playbook.blocks.run_one <block> --source <your library> \
    --record '{"url": "in.nc"}' --output-base out/cluster \
    [--config '<json>'] [--inputs '<json>']
```

Plain arguments in, ordinary log output, and one final `MANTA_BLOCK_RESULT` line on
stdout saying where the output record landed; the exit code says whether the block
succeeded. This is the whole contract between a block and whatever drives it, and the
quickest way to try a block you are writing.

`--source` names the library holding the block, since this package ships none itself;
`MANTA_BLOCK_SOURCES` says the same thing for a process that takes no arguments. Run
it inside the environment the block needs — for the blocks Manta ships, that is
`pixi run -e pypsa` in [`playbook-library`](../playbook-library).

## Describing every block at once

No single environment can import every block, so each one describes what it can:

```bash
python -m playbook.blocks <your library> > catalogue.json
```

Run once per environment, `merge_catalogues` combines the results into one description
of every block in the system: names, settings as JSON schema, dimensions, and which
settings are wired rather than typed in (marked `x-manta-input`). That is enough to
offer a playbook's settings and check how it is wired, from a process that could not
import a single one of the blocks it is describing.

## Testing your contribution

```bash
uv run pytest                 # the whole suite
uv run ruff check src         # lint
uv run ruff format --check src
```

Tests live beside the code they cover, in `tests/` inside each layer, plus
`playbook/tests/` for the two boundaries the package as a whole has to keep: that
nothing here imports an orchestration tool, and that `blocks` never imports
`playbooks`. Breaking either is a one-line accident that nothing else would notice,
which is why they are tested rather than only written down.

The fake blocks the tests share are in `blocks/tests/fakes.py` — each fake just
appends its name to the record's url, so a finished run reads as a record of which
blocks ran and in what order. Add fakes there rather than registering new ones in a
test module: a block name can only be claimed once per process.

A pull request is expected to keep this suite green and to add tests for what it
changes. If you are adding a real block rather than a framework feature, it belongs in
[`playbook-library`](../playbook-library), which has its own suite and its own
instructions.

## Current limitations

- Resource requirements (cpu, memory, walltime) are not modelled yet.
- Conditions can only look at settings, not at the contents of the data.
- A block declares `OUTPUTS`, but every block so far produces exactly one result.
- `initial_data.dims` has to be declared on a playbook, because a record does not yet
  describe the data it points at. Once it does, the dimensions can be read from the
  incoming record instead.

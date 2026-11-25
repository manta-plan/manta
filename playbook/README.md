<!--
SPDX-FileCopyrightText: 2026 Manta contributors

SPDX-License-Identifier: MIT
-->

# playbook

A **block** is one unit of work in an energy model workflow. A **playbook** chains blocks
together into something you can run.

Blocks are written in Python. Playbooks are written in YAML. Each block declares which
environment it needs, so one playbook can span environments that could never be
installed side by side: each step runs where it belongs, and the results are passed
along.

This package is the *framework*: what a block is, what a playbook is, and how to run
one. It ships no blocks and no playbooks of its own — the ones Manta ships live next
door in [`playbook-library`](../playbook-library), which imports this package exactly
the way your own library would.

## What is deliberately not here

**Nothing about orchestration.** Running a block is a plain method call. Everything
about *where* and *how* those calls happen in production — containers, schedulers,
Prefect — lives in Manta's backend, behind the `BlockRunner` seam described below.
Nothing in this package imports Prefect, Docker, or Manta, and nothing ever should:
that is what lets a modeller write and test a block without knowing anything about
Manta's infrastructure, and what lets this package move to its own repository later.

## Layout

```text
src/playbook/
  blocks/          A block, and everything needed to describe one without running it
    core.py        RevisionRef, BlockDims, ConfigSchema, MantaBlock
    registry.py    Which blocks exist, and the catalogue that describes them
    environments.py  The environments blocks run in
    run.py         Running a block on its revisions (needs the `run` extra)
    run_one.py     Running a single block from the command line
  playbooks/       Blocks chained together
    syntax.py      The playbook document format, and its inputs
    playbook.py    What a playbook is: steps and nested playbooks
    yaml_io.py     Playbooks as documents: reading, writing, sending
    expressions.py The `${{ ... }}` expressions, parsed and evaluated without eval
    inputs.py      Resolving the inputs a run is given against their declarations
    planner.py     What a playbook will run with given inputs, without reading data
    issues.py      How a problem with a playbook is reported
    validation.py  Checking a playbook and its inputs before it runs
    schema.py      Writing playbook.schema.json for editors
    execution.py   Running a playbook, in-process or through a pluggable BlockRunner
```

`blocks` never imports `playbooks`. A block library only depends on the half it
needs.

## Getting started
<!-- --8<-- [start:docs-setup] -->

```bash
uv sync
uv run pytest
```

The tests need nothing installed beyond this package and its `run` extra. That they
pass without PyPSA — or any other modelling framework — is the proof that a block's
own dependencies stay its own.

Running a block opens datarecord stores, so a process that runs blocks installs
`playbook[run]`. One that only passes revisions along, such as an orchestrator or a
web backend, installs plain `playbook`: everything outside `playbook.blocks.run`
imports without datarecord.
<!-- --8<-- [end:docs-setup] -->

## Writing a block

```python
from datarecord import Revision

from playbook.blocks import BlockDims, ConfigSchema, MantaBlock


class ShrinkConfig(ConfigSchema):
    factor: int = 2


class Shrink(MantaBlock[ShrinkConfig]):
    """Make the model smaller."""

    ENV = "pypsa"
    CONFIG = ShrinkConfig
    DIMS = BlockDims(requires=frozenset({"snapshot"}))

    def run(self, base: Revision) -> Revision: ...
```

What a block declares:

| Declaration | Meaning |
| --- | --- |
| `ENV` | the named environment it needs |
| `MANIFEST` | for a third-party block, where to find that environment |
| `CONFIG` | its settings, as a pydantic model |
| `DIMS` | the dimensions it needs, adds, and removes |

`run` receives the datarecord `Revision` to work on, commits its result as a new
revision through `base.store`, and returns that revision. Every revision a block run
touches shares one `Workspace`, opened by whatever runs the block (`LocalBlockRunner`,
`run_one`) before the block runs and closed after it, so a block never opens a store of
its own.

Between processes a revision travels as a `RevisionRef`: a `store` (a local directory
or an `s3://` URL) and the `id` of one revision in it.

A block class is checked as soon as it is written: it has to set `ENV` and `CONFIG`.

A block refuses a setting it does not have, so a misspelt name is an error rather than
a silent fall back to the default. The block's JSON schema says the same
(`additionalProperties: false`), so a process that cannot import the block refuses the
setting too.

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

A playbook is a YAML document with a `name`, the dimensions of its starting data under
`initial_data`, the `inputs` a user can set, and a list of `steps`. Its keys loosely follow the
[workflow syntax of GitHub Actions](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax),
so that Manta does not design a YAML workflow syntax from nothing. This one optimises
capacities in one of three ways:

```yaml
name: expand

initial_data:
  dims: [snapshot]

inputs:
  expansion_mode:
    type: choice
    options: [overnight, myopic, perfect]
    default: overnight

steps:
  - id: expansion_overnight
    block: overnight_capacity_expansion
    if: ${{ inputs.expansion_mode == 'overnight' }}

  - id: expansion_myopic
    block: myopic_capacity_expansion
    if: ${{ inputs.expansion_mode == 'myopic' }}

  - id: expansion_perfect
    block: perfect_capacity_expansion
    if: ${{ inputs.expansion_mode == 'perfect' }}
```

Run with `{"expansion_mode": "myopic"}`, only `expansion_myopic` runs. That step needs a
`period` dimension, which `initial_data` does not list, so the
[check](#checking-a-playbook) reports it before anything runs.

Read a playbook with `Playbook.from_yaml(path)`, or with `load_playbook(locator, loader)`
where nested playbooks are found by a loader of your own. A key the format does not
have is refused when the document is read. For editor completion, point the YAML
language server at `playbooks/playbook.schema.json`, as the shipped playbooks do in
their first line. [The playbook syntax](../docs/reference/playbook/syntax.md) lists
every key, with an example of each in YAML and in Python.

### Steps

Steps run in list order. Each step has an `id`, unique within its playbook, and runs
exactly one of these:

| Key | What the step runs |
| --- | --- |
| `block` | One block, by its registered name. |
| `playbook` | Another playbook, by locator or written out in place. |

Each step receives the revision of the step above it that ran. The first step receives
the revision the run starts from. A playbook cannot hand a step the revision of any
other step.

### Inputs

An input is a value a user sets for one run. Each input has a `type` (`string`,
`number`, `boolean` or `choice`, which takes a list of `options`), an optional
`description` and an optional `default`. An input without a `default` is required.

Inputs are resolved before anything runs. An unknown name, a missing required input,
a value of the wrong type and a choice outside `options` are all refused.

### Expressions

An expression is a whole string of the form `${{ ... }}`. It reads a value with a
dotted name rooted at `inputs`, such as `${{ inputs.expansion_mode }}`.
It can compare values with `==`, `!=`, `<`, `<=`, `>` and `>=`, and combine them with
`&&`, `||`, `!` and brackets. Literals are `'text'`, numbers, `true`, `false` and
`null`. An expression keeps the type of its result, so `${{ inputs.n_hours }}` stays a
number. Text with `${{` inside it that is not one whole expression is refused.

### Settings with `with`

`with` sets a block's settings. A value can be written in place or read from an
expression, at any depth:

```yaml
  - id: dispatch
    block: rolling_horizon_dispatch
    with:
      optimize_config:
        horizon: ${{ inputs.horizon }}
        overlap: 24
```

A playbook has no other place for block settings. A setting a run should be able to
change has to be an input that `with` reads.

Each step has its own `id`, so `overnight_capacity_expansion` can appear as both
`expansion_2030` and `expansion_2040`, each with its own settings.

### Conditions with `if`

`if` holds an expression. When it is false, the step does not run, and the next step
receives the revision the skipped step would have received.

Currently `if` can only read inputs. So which steps run is known before anything runs,
which is what lets a playbook be [checked](#checking-a-playbook) up front. Which steps
run is decided in exactly one place (`plan`), so what gets run can never disagree with
what a check of the playbook expects.

### Playbooks inside playbooks

A `playbook` step runs another playbook as a group of its steps. `with` sets the
nested playbook's inputs. With `inputs: inherit`, every input of the nested playbook
that `with` does not set becomes an input of the outer playbook:

```yaml
name: expand_and_dispatch

steps:
  - id: plan
    playbook: expand.yaml
    inputs: inherit

  - id: dispatch
    block: rolling_horizon_dispatch
    if: ${{ inputs.expansion_mode == 'overnight' }}
```

A run of `expand_and_dispatch` now takes `expansion_mode`. An inherited input with the
same name as an input of the outer playbook is a `structure` issue. A playbook document
that nests itself, directly or through another playbook, raises `PlaybookLoadError`
when it is read.

## Checking a playbook

Check a playbook against the inputs it will run with before you run it. Every
mistake is reported at once, with the step, input or setting it is about:

```python
from playbook.playbooks import find_playbook_issues

for issue in find_playbook_issues(playbook, inputs):
    print(issue)
```

Run against the shipped `expand` playbook with `{"expansion_mode": "greenfield"}`, that
prints:

```text
[inputs] playbook, input 'expansion_mode': 'greenfield' is not one of ['overnight', 'myopic', 'perfect']
```

A playbook whose `cluster` step runs `cluster_time` with `n_hour: 3`, a misspelling of
`n_hours`, prints:

```text
[config] step 'cluster', setting 'n_hour': there is no setting called 'n_hour'
```

`find_playbook_issues` returns a `list[PlaybookIssue]`, empty when nothing is wrong.
`raise_for_playbook_issues` raises `PlaybookHasIssuesError` instead, carrying the same
list. `Playbook.find_issues` and `Playbook.raise_for_issues` do the same as methods.

| Field | What it holds | Example |
| --- | --- | --- |
| `kind` | The check it failed (see below). | `"config"` |
| `message` | What is wrong, in words. | `"there is no setting called 'n_hour'"` |
| `step_path` | The step, as ids from the outermost playbook inwards. It is empty for the playbook as a whole. | `("plan", "expansion_myopic")` |
| `input_path` | The input value at fault, or `None`. | `("expansion_mode",)` |
| `setting_path` | Where in the step's settings the problem is, or `None`. | `("optimize_config", "horizon")` |

The checks, by `kind`:

| Kind | Reported when |
| --- | --- |
| `structure` | Two steps share an id, two inherited inputs clash, or a playbook contains itself. |
| `reference` | An expression reads an input that does not exist, or a nested playbook is given an input it does not declare. |
| `inputs` | An input value is unknown, missing, of the wrong type, or not one of its options. |
| `dims` | A step needs a dimension that neither `initial_data` lists nor an earlier step adds, or that an earlier step removed. |
| `config` | Settings do not fit what a block accepts. |
| `environment` | Two blocks describe the same environment differently. |

Without inputs, `find_playbook_issues(playbook)` runs only the `structure` and
`reference` checks, which hold whatever the inputs are. With inputs, it plans the run
and checks the steps that will run. Settings of a step that does not run are not
checked. The `dims` check starts from the dimensions `initial_data` lists, and a nested
playbook requires the dimensions its own `initial_data` lists.

Where a block can be imported, its own settings model checks its settings. Where it
cannot, its JSON schema from a [catalogue](#describing-every-block-at-once) does. The
schema catches wrong types, missing settings and unknown ones. It cannot carry a rule a
block writes in code, such as `cluster_time` needing exactly one of `n_hours` and
`segments`. Where the block cannot be imported, that rule is only enforced when the
block runs.

## Running a playbook

```python
result = playbook.run(revision, inputs)
```

`run` [checks](#checking-a-playbook) the playbook against `inputs` first. If anything
is wrong, it raises `PlaybookHasIssuesError` before any step runs. Otherwise each step
runs in turn on the revision the step above it returned, so a finished run is a chain
of revisions in the input revision's store. `revision` and `result` are `RevisionRef`s.

By default every block runs in the current process, which is what tests and local use
want. To run blocks anywhere else, pass a `BlockRunner`:

```python
class BlockRunner(Protocol):
    def run_block(
        self,
        block: BlockSpec,
        *,
        step_path: tuple[str, ...],
        config: dict,
        revision: RevisionRef,
    ) -> RevisionRef: ...
```

`execute_playbook` checks and plans the playbook, walks it, and hands the runner one
block at a time with its settings worked out. `step_path` names the step by its ids,
such as `("plan", "expansion_myopic")`. Manta's
runtime implements this protocol to run every block in its own container; this package
never learns how.

## Running one block

```bash
python -m playbook.blocks.run_one <block> --source <your library> \
    --revision '{"store": "<store>", "id": "<revision>"}' \
    [--config '<json>']
```

Plain arguments in, ordinary log output, and one final `MANTA_BLOCK_RESULT` line on
stdout saying where the output revision landed; the exit code says whether the block
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
of every block in the system: names, settings as JSON schema and dimensions. That is enough to
offer a playbook's settings and [check](#checking-a-playbook) a playbook against them
without importing a single block.

`playbooks/playbook.schema.json` is the JSON schema of a playbook document, for
editors. Regenerate it after changing the document format:

```bash
uv run python -m playbook.playbooks.schema
```

A test checks that the committed file matches the format.

## Testing your contribution
<!-- --8<-- [start:docs-testing] -->

```bash
uv run pytest                 # the whole suite
uv run ruff check src         # lint
uv run ruff format --check src
```

Tests live beside the code they cover, in `tests/` inside each layer, plus
`playbook/tests/` for the boundaries the package as a whole has to keep: that nothing
here imports an orchestration tool, that `blocks` never imports `playbooks`, and that
passing revisions along never imports datarecord. Breaking any of them is a one-line
accident that nothing else would notice, which is why they are tested rather than only
written down.

The fake blocks the tests share are in `blocks/tests/fakes.py` — each fake just
commits an empty revision labelled with its name, so `steps(result)` reads the lineage
of a finished run as a record of which blocks ran and in what order. Add fakes there
rather than registering new ones in a test module: a block name can only be claimed
once per process.

A pull request is expected to keep this suite green and to add tests for what it
changes. If you are adding a real block rather than a framework feature, it belongs in
[`playbook-library`](https://github.com/manta-plan/manta/tree/main/playbook-library), which has its own suite and its own
instructions.
<!-- --8<-- [end:docs-testing] -->

## Current limitations

- Resource requirements (cpu, memory, walltime) are not modelled yet.
- `if` can only read inputs, not the contents of the data.
- A playbook cannot pass the revision of one step into the settings of another.
- `initial_data.dims` has to be declared on a playbook, because a `RevisionRef` does not
  describe the data it points at. A dimension it lists that the starting data does not
  populate is found only when the block runs.

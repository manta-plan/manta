<!--
SPDX-FileCopyrightText: 2026 Manta contributors

SPDX-License-Identifier: MIT
-->

# playbook

A **block** is one unit of work in an energy model workflow. A **playbook** chains blocks
together into something you can run.

Blocks are written in Python, and playbooks in YAML. Each block declares the
environment it needs, so one playbook can span environments that could never be
installed side by side. Each step runs in the environment of its block, and its result
passes to the next step.

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

When Python defines a block class, `MantaBlock` checks that it sets `ENV` and `CONFIG`.

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

A playbook is a YAML document with a `name`, a list of `steps`, and optionally
`initial_data` and `inputs`. `initial_data` lists the dimensions the data has before
the first step, and `inputs` declares the values a user can set for a run. Rather than
design a new YAML syntax, we loosely follow the
[workflow syntax of GitHub Actions](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax).
This playbook has one step for each of three ways to optimise capacities, and the
`expansion_mode` input sets which one runs:

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

With `{"expansion_mode": "myopic"}` as inputs, only `expansion_myopic` runs. Its block
needs a `period` dimension, which `initial_data` does not list, so the
[check](#checking-a-playbook) reports a `dims` issue before any step runs.

To read a playbook from a file, call `Playbook.from_yaml(path)`. To fetch playbooks
from somewhere other than files, pass a loader of your own to
`load_playbook(path, loader)`. A document with a key the format does not have is
refused when it is read. For completion in your editor, point the YAML language server
at `playbooks/playbook.schema.json`, as each shipped playbook does in a comment below
its licence header. For every key, with an example in YAML and in Python, see
[the playbook syntax](../docs/reference/playbook/syntax.md).

### Steps

Steps run in list order. Each step has an `id`, unique within its playbook, and
exactly one of these keys:

| Key | Value |
| --- | --- |
| `block` | The registered name of one block. |
| `playbook` | The locator of another playbook, or that playbook written out in place. |

Each step runs on the revision returned by the last step above it that ran. The first
step to run gets the revision the run starts from. The format has no key to pass any
other step's revision to a step.

### Inputs

An input is a value a user sets for one run. Each input has a `type`, an optional
`description`, and an optional `default`. The `type` is `string`, `number`, `boolean`,
or `choice`, and a `choice` input also lists its `options`. An input without a
`default` is required.

Before any step runs, `playbook` checks the input values a run is given and fills in
each missing one from its default. It refuses an unknown name, a missing required
input, a value of the wrong type, and a choice outside `options`.

### Expressions

An expression is a string of the form `${{ ... }}` that computes a value from the
inputs. Inside it, `inputs.<name>` is the value of an input, as in
`${{ inputs.expansion_mode }}`. The operators are `==`, `!=`, `<`, `<=`, `>`, and `>=`
for comparison, and `&&`, `||`, and `!` for logic, with brackets for grouping.
Literals are `'text'`, numbers, `true`, `false`, and `null`.

The value of an expression keeps its type, so `${{ inputs.n_hours }}` is a number, not
a string. When it reads a document, `playbook` refuses a string that contains `${{` but
is not one whole expression.

### Settings with `with`

`with` sets a block's settings. Each value, at any depth, is either written in place
or an expression:

```yaml
  - id: dispatch
    block: rolling_horizon_dispatch
    with:
      optimize_config:
        horizon: ${{ inputs.horizon }}
        overlap: 24
```

Here `horizon` takes the value of the `horizon` input, and `overlap` is always 24.

A playbook has no other place for block settings. To let a run change a setting, read
an input in `with`.

Each step has its own `id`, so `overnight_capacity_expansion` can appear as both
`expansion_2030` and `expansion_2040`, each with its own settings.

### Conditions with `if`

`if` is an expression. When it is false, `playbook` skips the step, and the next step
runs on the revision the skipped step would have run on.

Currently `if` can only refer to inputs. So `playbook` knows which steps run before any
step runs, and can [check](#checking-a-playbook) a playbook up front. The function
`plan` alone decides which steps run, so a check of a playbook and its run always
agree on them.

### Playbooks inside playbooks

In a `playbook` step, the steps of another playbook run as one group. `with` sets the
inputs of the nested playbook. With `inputs: inherit`, every input of the nested
playbook that `with` does not set becomes an input of the outer playbook:

```yaml
name: expand_and_dispatch

initial_data:
  dims: [snapshot]

steps:
  - id: plan
    playbook: expand.yaml
    inputs: inherit

  - id: dispatch
    block: rolling_horizon_dispatch
    if: ${{ inputs.expansion_mode == 'overnight' }}
```

So `expand_and_dispatch` takes the `expansion_mode` input of `expand.yaml`, and the
`if` of `dispatch` can refer to it. If the outer playbook already has an input of the
same name as an inherited one, the check reports a `structure` issue.
`load_playbook` raises `PlaybookLoadError` for a playbook document that nests itself,
directly or through another playbook.

## Checking a playbook

Before you run a playbook, check it against the inputs it will run with.
`find_playbook_issues` reports every problem at once, each with the step, input, or
setting it is about:

```python
from playbook.playbooks import find_playbook_issues

for issue in find_playbook_issues(playbook, inputs):
    print(issue)
```

For the shipped `expand` playbook with `{"expansion_mode": "greenfield"}`, the loop
prints:

```text
[inputs] playbook, input 'expansion_mode': 'greenfield' is not one of ['overnight', 'myopic', 'perfect']
```

`greenfield` is not one of the options, so no step is checked.

For a playbook whose `cluster` step sets `n_hour: 3` for `cluster_time`, a misspelling
of `n_hours`, the loop prints:

```text
[config] step 'cluster', setting 'n_hour': there is no setting called 'n_hour'
```

The issue gives the path to the misspelt key within the step's `with`.

`find_playbook_issues` returns a `list[PlaybookIssue]`, empty when nothing is wrong.
`raise_for_playbook_issues` raises `PlaybookHasIssuesError` instead, carrying the same
list. `Playbook.find_issues` and `Playbook.raise_for_issues` do the same as methods.

| Field | Value | Example |
| --- | --- | --- |
| `kind` | The check it failed (see below). | `"config"` |
| `message` | What is wrong, in words. | `"there is no setting called 'n_hour'"` |
| `step_path` | The step, as ids from the outermost playbook inwards. It is empty for the playbook as a whole. | `("plan", "expansion_myopic")` |
| `input_path` | The input at fault, as a path of names, or `None`. | `("expansion_mode",)` |
| `setting_path` | The setting at fault, as a path of keys and list indexes, or `None`. | `("optimize_config", "horizon")` |

The checks, by `kind`:

| Kind | Reported when |
| --- | --- |
| `structure` | Two steps share an id, two inherited inputs clash, or a playbook contains itself. |
| `reference` | An expression refers to an input that does not exist, or `with` sets an input the nested playbook does not declare. |
| `inputs` | An input value is unknown, missing, of the wrong type, or not one of its options. |
| `dims` | A step needs a dimension that neither `initial_data` lists nor an earlier step adds, or that an earlier step removed. |
| `config` | A step's settings do not fit what its block accepts. |
| `environment` | Two blocks describe the same environment differently. |

Without inputs, `find_playbook_issues(playbook)` runs only the `structure` and
`reference` checks, which do not depend on the inputs. With inputs, it plans the run
and checks only the steps that will run, so it does not check the settings of a
skipped step.

The `dims` check starts from the dimensions that `initial_data` lists. A `playbook`
step needs the dimensions that the `initial_data` of its nested playbook lists.

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
runs in turn on the revision the step above it returned. A finished run is therefore a
chain of revisions in the store of the input revision. `revision` and `result` are `RevisionRef`s.

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

`execute_playbook` checks and plans the playbook, then walks the plan and passes each
block to the runner in turn, with its settings evaluated. `step_path` is the step's
ids from the outermost playbook inwards, such as `("plan", "expansion_myopic")`.
Manta's runtime implements this protocol to run every block in its own container.
This package never learns how.

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

Run this once per environment. `merge_catalogues` then combines the results into the
catalogue, the description of every block in the system: names, settings as JSON
schema, and dimensions. With the catalogue, a process can offer a playbook's settings
and [check](#checking-a-playbook) a playbook against them without importing a single
block.

`playbooks/playbook.schema.json` is the JSON schema of a playbook document, for
editors. After you change the document format, regenerate it:

```bash
uv run python -m playbook.playbooks.schema
```

The command overwrites the file and prints nothing. A test checks that the committed
file matches the format.

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
- `if` can only refer to inputs, not to the contents of the data.
- The settings of a step cannot refer to the revision of another step.
- `initial_data.dims` has to be declared on a playbook, because a `RevisionRef` does not
  describe the data it points at. If `initial_data.dims` lists a dimension that the
  starting data does not populate, a block finds the problem only when it runs.

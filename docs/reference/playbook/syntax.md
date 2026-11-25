<!--
SPDX-FileCopyrightText: Manta contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Playbook syntax

A playbook is blocks chained together into something you can run, written as a YAML document.
A block is one unit of work in an energy model workflow, such as aggregating the time series or optimising capacities.
This page lists every key a playbook document accepts, and how `playbook` checks a document before it runs.
The keys loosely follow the [workflow syntax of GitHub Actions](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax).
For where the two differ, see [the playbook format](../../explanation/blocks-and-playbooks.md#the-playbook-format).

The smallest playbook has a `name`, the dimensions of its starting data in `initial_data`, and a list of `steps`:

=== "YAML"

    ```yaml title="cluster_and_expand.yaml"
    name: cluster_and_expand

    initial_data:
      dims: [snapshot]

    steps:
      - id: cluster
        block: cluster_time
        with:
          n_hours: 3

      - id: expansion
        block: overnight_capacity_expansion
    ```

=== "Python"

    ```python
    from playbook.playbooks import BlockStepDoc, PlaybookDoc, playbook_from_doc
    from playbook.playbooks.syntax import InitialDataDoc
    from playbook_library import library_catalogue

    doc = PlaybookDoc(
        name="cluster_and_expand",
        initial_data=InitialDataDoc(dims=["snapshot"]),
        steps=[
            BlockStepDoc(id="cluster", block="cluster_time", with_={"n_hours": 3}),
            BlockStepDoc(id="expansion", block="overnight_capacity_expansion"),
        ],
    )
    playbook = playbook_from_doc(doc, catalogue=library_catalogue())
    ```

`cluster` merges every three hours of the time series into one, and `expansion` then optimises capacities on the shorter time series.

## Documents and playbooks

Every example on this page defines one playbook twice, and both tabs build the same `Playbook`.
The YAML tab is the document as you write it in a file.
In the Python tab, the same document is built from the classes in `playbook.playbooks` and `playbook.playbooks.syntax`.
It is then passed to `playbook_from_doc`, with the catalogue of the blocks that `playbook-library` ships.
In Python, `if` and `with` are written `if_` and `with_`, because both are Python keywords.

| Function | Reads | Returns |
| --- | --- | --- |
| `Playbook.from_yaml(path, catalogue)` | A YAML file. A nested playbook is read from a file whose path is relative to the file that refers to it. | A `Playbook`. |
| `load_playbook(path, loader, catalogue)` | The playbook a `PlaybookLoader` finds under `path`, and the playbooks it nests. | A `Playbook`. |
| `parse_doc(raw)` | A mapping loaded from YAML or JSON. | A `PlaybookDoc`. |
| `playbook_from_doc(doc, loader, catalogue)` | A `PlaybookDoc`. | A `Playbook`. |
| `Playbook.to_doc()` | A `Playbook`. | A `PlaybookDoc`, with nested playbooks written out in place. |

`playbook_from_doc` looks up each block by its name, where the block can be imported, or else in the description of every block (the `catalogue`).
For a block it finds neither way, `playbook_from_doc` raises `PlaybookLoadError`:

```text
step 'cluster': No block registered under 'clusterr_time'. Available blocks: ['cluster_time', 'myopic_capacity_expansion', 'overnight_capacity_expansion', 'perfect_capacity_expansion', 'rolling_horizon_dispatch']
```

`parse_doc` refuses a key the format does not have, with `PlaybookLoadError`.
For a document with `stpes:` in place of `steps:`, `Playbook.from_yaml` raises:

```text
invalid playbook /path/to/cluster_and_expand.yaml: 2 validation errors for PlaybookDoc
steps
  Field required [type=missing, input_value={'name': 'cluster_and_exp...t_capacity_expansion'}]}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.13/v/missing
stpes
  Extra inputs are not permitted [type=extra_forbidden, input_value=[{'id': 'cluster', 'block...ht_capacity_expansion'}], input_type=list]
    For further information visit https://errors.pydantic.dev/2.13/v/extra_forbidden
```

The first error is about the missing key `steps`, and the second about the unknown key `stpes`.
Each shipped playbook has a `# yaml-language-server: $schema=` comment at its top, with the path to `playbook/src/playbook/playbooks/playbook.schema.json`.
With that comment, an editor that runs the YAML language server completes and checks the keys.
The [playbook schema](schema.md) lists every definition in that file.

## `name`

`name` is the playbook's name, as text, and is required.
`playbook-library` finds a shipped playbook by the name in its document, not by the name of its file.

## `initial_data`

`initial_data` lists the dimensions the starting data has, under `dims`, such as `snapshot` or `period`.
It is optional, and without it `dims` is empty.
`find_playbook_issues` checks each step against these dimensions, as the [`dims` check](#checking-a-playbook) describes.

!!! note

    `initial_data` is what the playbook author states about the starting record.
    We aim to drop it once the backend can read the data record itself, because the check needs to know whether a dimension is populated in the record, and the record's manifest only shows that the dimension is recorded.

This playbook runs a myopic capacity expansion, which needs both `snapshot` and `period`:

=== "YAML"

    ```yaml title="expand_myopic.yaml"
    name: expand_myopic

    initial_data:
      dims: [snapshot, period]

    steps:
      - id: expansion
        block: myopic_capacity_expansion
    ```

=== "Python"

    ```python
    from playbook.playbooks import BlockStepDoc, PlaybookDoc, playbook_from_doc
    from playbook.playbooks.syntax import InitialDataDoc
    from playbook_library import library_catalogue

    doc = PlaybookDoc(
        name="expand_myopic",
        initial_data=InitialDataDoc(dims=["snapshot", "period"]),
        steps=[BlockStepDoc(id="expansion", block="myopic_capacity_expansion")],
    )
    playbook = playbook_from_doc(doc, catalogue=library_catalogue())
    ```

With `dims: [snapshot]` in place of `[snapshot, period]`, `find_playbook_issues(playbook, {})` reports:

```text
[dims] step 'expansion': needs the 'period' dimension, which the data does not have at this point (it has: ['snapshot'])
```

## `inputs`

An input is a value a user sets for one run.
`inputs` maps each input's name to its declaration.
A name starts with a letter or an underscore, and contains only letters, digits, and underscores.

Each declaration has a `type`, an optional `description`, and an optional `default`.
An input without a `default` is required.
`default: null` is a default, so an input with it is optional.

| `type` | Value | Other keys |
| --- | --- | --- |
| `string` | Text. | |
| `number` | An integer or a float. `true` and `false` are not numbers. | |
| `boolean` | `true` or `false`. | |
| `choice` | One of `options`. | `options`, a list of at least one text or number. A `default` has to be one of them. |

This playbook lets a run set how many hours `cluster` merges and how long each dispatch window is:

=== "YAML"

    ```yaml title="cluster_and_dispatch.yaml"
    name: cluster_and_dispatch

    initial_data:
      dims: [snapshot]

    inputs:
      n_hours:
        type: number
        default: 3
        description: How many hours to merge into one.
      horizon:
        type: number
        default: 168
        description: How many hours each dispatch window spans.

    steps:
      - id: cluster
        block: cluster_time
        with:
          n_hours: ${{ inputs.n_hours }}

      - id: dispatch
        block: rolling_horizon_dispatch
        with:
          optimize_config:
            horizon: ${{ inputs.horizon }}
            overlap: 24
    ```

=== "Python"

    ```python
    from playbook.playbooks import BlockStepDoc, PlaybookDoc, playbook_from_doc
    from playbook.playbooks.syntax import InitialDataDoc, NumberInput
    from playbook_library import library_catalogue

    doc = PlaybookDoc(
        name="cluster_and_dispatch",
        initial_data=InitialDataDoc(dims=["snapshot"]),
        inputs={
            "n_hours": NumberInput(
                type="number", default=3, description="How many hours to merge into one."
            ),
            "horizon": NumberInput(
                type="number",
                default=168,
                description="How many hours each dispatch window spans.",
            ),
        },
        steps=[
            BlockStepDoc(
                id="cluster", block="cluster_time", with_={"n_hours": "${{ inputs.n_hours }}"}
            ),
            BlockStepDoc(
                id="dispatch",
                block="rolling_horizon_dispatch",
                with_={"optimize_config": {"horizon": "${{ inputs.horizon }}", "overlap": 24}},
            ),
        ],
    )
    playbook = playbook_from_doc(doc, catalogue=library_catalogue())
    ```

With the inputs `{"horizon": 336}`, `n_hours` resolves to its default `3`, and `horizon` to `336`.

Manta resolves the inputs before any step runs.
An unknown name, a missing required input, a value of the wrong type, and a choice outside `options` are each an `inputs` issue.
With the inputs `{"n_hours": "3"}`, `find_playbook_issues` reports for the same playbook:

```text
[inputs] playbook, input 'n_hours': '3' is not a number
```

## `steps`

`steps` is a list of at least one step.
A step is one block or one nested playbook, and it has exactly one of these keys:

| Key | What the step runs |
| --- | --- |
| [`block`](#block) | One block, by its registered name. |
| [`playbook`](#playbook) | Another playbook, as a group of its steps. |

Steps run in list order.
A revision is one version of the model data in a datarecord store.
Each step receives the revision of the step above it that ran, and the first step receives the revision the run starts from.
Each block writes its result as a new revision in the same store.
A step cannot receive the revision of any other step.

`parse_doc` refuses a step without `block` or `playbook`:

```text
invalid playbook: 1 validation error for PlaybookDoc
steps.0
  A step needs one of `block` or `playbook` [type=step_kind, input_value={'id': 'cluster', 'with': {}}, input_type=dict]
```

### `id`

`id` is the step's name, and is required.
It follows the same rule as an input's name.
An `id` must be unique within one playbook document.
Two steps with the same `id` are a `structure` issue, `duplicate step id`.

In an issue, a step is written as its path of ids, from the outermost playbook inwards, such as `plan/expansion_myopic`.

### `block`

`block` is the name of the block the step runs, as the block library registered it, such as `cluster_time`.
The step's [`with`](#with) sets the block's settings.

### `playbook`

`playbook` is the name of another playbook, which runs in this step as a group of its own steps.
The name is whatever the loader finds a playbook by.
For `Playbook.from_yaml`, it is a file path relative to this file.
`playbook` can also be a whole playbook document, written out in place.

On a `playbook` step, [`with`](#with) sets the nested playbook's inputs.
Setting an input the nested playbook does not declare is a `reference` issue.

With `inputs: inherit`, every input of the nested playbook that `with` does not set becomes an input of the outer playbook:

=== "YAML"

    ```yaml title="expand_and_dispatch.yaml"
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

    ```yaml title="expand.yaml"
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

=== "Python"

    ```python
    from playbook.playbooks import BlockStepDoc, PlaybookDoc, PlaybookStepDoc, playbook_from_doc
    from playbook.playbooks.syntax import ChoiceInput, InitialDataDoc
    from playbook_library import library_catalogue

    expand = PlaybookDoc(
        name="expand",
        initial_data=InitialDataDoc(dims=["snapshot"]),
        inputs={
            "expansion_mode": ChoiceInput(
                type="choice", options=["overnight", "myopic", "perfect"], default="overnight"
            )
        },
        steps=[
            BlockStepDoc(
                id="expansion_overnight",
                block="overnight_capacity_expansion",
                if_="${{ inputs.expansion_mode == 'overnight' }}",
            ),
            BlockStepDoc(
                id="expansion_myopic",
                block="myopic_capacity_expansion",
                if_="${{ inputs.expansion_mode == 'myopic' }}",
            ),
            BlockStepDoc(
                id="expansion_perfect",
                block="perfect_capacity_expansion",
                if_="${{ inputs.expansion_mode == 'perfect' }}",
            ),
        ],
    )
    doc = PlaybookDoc(
        name="expand_and_dispatch",
        initial_data=InitialDataDoc(dims=["snapshot"]),
        steps=[
            PlaybookStepDoc(id="plan", playbook=expand, inputs="inherit"),
            BlockStepDoc(
                id="dispatch",
                block="rolling_horizon_dispatch",
                if_="${{ inputs.expansion_mode == 'overnight' }}",
            ),
        ],
    )
    playbook = playbook_from_doc(doc, catalogue=library_catalogue())
    ```

`expand_and_dispatch` has the input `expansion_mode`, and the `if` of its own `dispatch` step refers to it.

With `with: {expansion_mode: myopic}` in place of `inputs: inherit`, the nested playbook always runs `expansion_myopic`, and the outer playbook has no inputs.
The `if` of `dispatch` then refers to an input that does not exist:

```text
[reference] step 'dispatch': reads inputs.expansion_mode, but there is no input 'expansion_mode' (inputs: [])
```

An inherited input with the same name as an input of the outer playbook is a `structure` issue:

```text
[structure] step 'plan', input 'expansion_mode': inherits input 'expansion_mode', which the playbook already has
```

`load_playbook` refuses a playbook that nests itself, directly or through another playbook, with `PlaybookLoadError` and the chain of files.
When step `m` of `a.yaml` nests `b.yaml`, and step `n` of `b.yaml` nests `a.yaml`, it raises:

```text
step 'n': circular playbook reference: /path/to/a.yaml -> /path/to/b.yaml -> /path/to/a.yaml
```

A `Playbook` built in Python that contains itself is a `structure` issue instead.

### `with`

`with` sets a block's settings, as a mapping.
A value is written out in place, or read from an [expression](#expressions) at any depth of the mapping.
In [the inputs example](#inputs), `with` reads `n_hours` at the top of the mapping and `horizon` inside `optimize_config`.

A playbook has no other place for a block's settings.
So a setting that a run can change must be an input, read in `with` through an expression.

`find_playbook_issues` checks `with` against the block's own settings model where the block can be imported.
Where the block cannot be imported, `find_playbook_issues` checks `with` against the block's JSON schema from the catalogue.
That check finds wrong types and missing or unknown settings.
A setting that does not fit is a `config` issue, with the path to the setting.

On a `block` step, `with` must be a mapping, and `parse_doc` refuses a single expression.
On a `playbook` step, `with` sets the [nested playbook's inputs](#playbook).

### `if`

`if` is an [expression](#expressions).
When it is false, the step does not run, and the next step receives the revision the skipped step would have received.
The [`expand` example](#playbook) has an `if` on each step, so a run with `{"expansion_mode": "myopic"}` runs only `expansion_myopic`.

An `if` can refer only to inputs, so the inputs alone decide which steps run, before any step starts.
[Conditions look only at inputs](../../explanation/blocks-and-playbooks.md#conditions-look-only-at-inputs) explains why.

## Expressions

An expression is a whole string of the form `${{ ... }}`.
It refers to a value by a dotted name that starts at `inputs`, such as `${{ inputs.horizon }}`.
`if` and any value in `with` can be an expression.

| Part | Written as |
| --- | --- |
| A comparison | `==`, `!=`, `<`, `<=`, `>`, and `>=`. |
| A combination | `&&`, `||`, and `!`, with brackets. |
| A literal | `'text'`, a number, `true`, `false`, and `null`. A `'` inside text is written `''`. |

An expression keeps the type of its result, so `${{ inputs.horizon }}` stays a number.
For an expression that orders a number against text, `find_playbook_issues` and `execute_playbook` raise `ExpressionError`, such as `Cannot order 1 > 'a'`.

`parse_doc` refuses text with `${{` inside it that is not one whole expression:

```text
invalid playbook: 1 validation error for PlaybookDoc
steps.0.block.with
  Value error, 'h_${{ inputs.n_hours }}' mixes an expression with other text; a value must be one whole `${{ ... }}` expression or contain none [type=value_error, input_value={'n_hours': 'h_${{ inputs.n_hours }}'}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.13/v/value_error
```

An expression that refers to an input the playbook does not have is a `reference` issue:

```text
[reference] step 'cluster': reads inputs.n_hour, but there is no input 'n_hour' (inputs: ['horizon', 'n_hours'])
```

## Checking a playbook

`find_playbook_issues` checks a playbook against the inputs of one run.
It returns every problem it finds, each with the step, input, or setting it is about:

```python
from playbook.playbooks import find_playbook_issues, playbook_from_doc
from playbook_library import library_catalogue
from playbook_library.playbooks import library_playbooks

playbook = playbook_from_doc(library_playbooks()["expand"], catalogue=library_catalogue())
for issue in find_playbook_issues(playbook, {"expansion_mode": "greenfield"}):
    print(issue)
```

This prints one issue, because `greenfield` is not one of the options of `expansion_mode`:

```text
[inputs] playbook, input 'expansion_mode': 'greenfield' is not one of ['overnight', 'myopic', 'perfect']
```

A misspelt setting is found the same way.
This playbook sets `n_hour` on `cluster_time`, which has a setting called `n_hours`:

=== "YAML"

    ```yaml title="cluster_and_expand.yaml"
    name: cluster_and_expand

    initial_data:
      dims: [snapshot]

    steps:
      - id: cluster
        block: cluster_time
        with:
          n_hour: 3

      - id: expansion
        block: overnight_capacity_expansion
    ```

=== "Python"

    ```python
    from playbook.playbooks import BlockStepDoc, PlaybookDoc, playbook_from_doc
    from playbook.playbooks.syntax import InitialDataDoc
    from playbook_library import library_catalogue

    doc = PlaybookDoc(
        name="cluster_and_expand",
        initial_data=InitialDataDoc(dims=["snapshot"]),
        steps=[
            BlockStepDoc(id="cluster", block="cluster_time", with_={"n_hour": 3}),
            BlockStepDoc(id="expansion", block="overnight_capacity_expansion"),
        ],
    )
    playbook = playbook_from_doc(doc, catalogue=library_catalogue())
    ```

With the playbook built as `Playbook.from_yaml("cluster_and_expand.yaml", library_catalogue())`, `find_playbook_issues(playbook, {})` reports:

```text
[config] step 'cluster', setting 'n_hour': there is no setting called 'n_hour'
```

`find_playbook_issues(playbook, inputs)` returns a `list[PlaybookIssue]`, which is empty when nothing is wrong.
`raise_for_playbook_issues` raises `PlaybookHasIssuesError` instead, with the same list as its `issues` attribute.
`Playbook.find_issues` and `Playbook.raise_for_issues` do the same as methods.
`Playbook.run` checks the playbook against its inputs first, and raises `PlaybookHasIssuesError` before any step runs.

| Field | Value | Example |
| --- | --- | --- |
| `kind` | The check that failed. | `"config"` |
| `message` | What is wrong, in words. | `"there is no setting called 'n_hour'"` |
| `step_path` | The step, as ids from the outermost playbook inwards. It is empty for the playbook as a whole. | `("plan", "expansion_myopic")` |
| `input_path` | The input value at fault, or `None`. | `("expansion_mode",)` |
| `setting_path` | Where in the step's settings the problem is, or `None`. | `("optimize_config", "horizon")` |

| `kind` | Reported when |
| --- | --- |
| `structure` | Two steps share an `id`, two inherited inputs clash, or a playbook contains itself. |
| `reference` | An expression reads an input that does not exist, or a nested playbook is given an input it does not declare. |
| `inputs` | An input value is unknown, missing, of the wrong type, or not one of its options. |
| `dims` | A step needs a dimension that neither `initial_data` lists nor an earlier step adds, or that an earlier step removed. |
| `config` | Settings do not fit what a block accepts. |
| `environment` | Two blocks describe the same environment differently. |

Without inputs, `find_playbook_issues(playbook)` runs only the `structure` and `reference` checks, which apply whatever the inputs are.
With inputs, it works out which steps run with them and checks those steps.
The settings of a step that does not run are not checked.
When `find_playbook_issues` finds a `structure` or a `reference` issue, it returns before the checks that need inputs.
For a playbook that contains itself, it returns only the issues about that.

The `dims` check folds the dimensions each step requires, adds, and removes, starting from `initial_data`.
A nested playbook is one step to the playbook around it: it requires the dimensions its own `initial_data` lists, and its own steps are checked against those.
A dimension that `initial_data` lists but the starting data does not populate is found only when the block runs.

A JSON schema cannot state a rule that a block states in code.
`cluster_time` needs exactly one of `n_hours` and `segments`, so where `cluster_time` cannot be imported, the rule is enforced only when the block runs.

## Shipped playbooks

`playbook-library` ships these playbooks, which `playbook_library.playbooks.library_playbooks()` returns as documents, by the name in each document:

| Name | File | Inputs | What it runs |
| --- | --- | --- | --- |
| `expand` | [`expand.yaml`](https://github.com/manta-plan/manta/blob/main/playbook-library/src/playbook_library/playbooks/expand.yaml) | `expansion_mode`: `overnight`, `myopic`, or `perfect`, with `overnight` as the default. | One capacity expansion block, picked by `expansion_mode`. It has no time aggregation step, so it suits a small model only. |
| `cluster-expand-dispatch` | [`cluster_expand_dispatch.yaml`](https://github.com/manta-plan/manta/blob/main/playbook-library/src/playbook_library/playbooks/cluster_expand_dispatch.yaml) | `expansion_mode`: `overnight` or `myopic`, with `overnight` as the default. | Merges every three hours of the time series into one, then optimises capacities. With `overnight`, a rolling horizon dispatch follows, in windows of 168 hours that overlap by 24. |

The dispatch fixes each capacity that the revision it receives has as an optimisation result, which the expansion step before it wrote.
Where the revision has no such result, the dispatch runs against the model's own capacities.

!!! info "See also"

    - [Playbook schema](schema.md) lists every definition of the JSON schema of a playbook document.
    - [playbook](api.md) is the Python API, generated from the docstrings.
    - [Blocks, playbooks and the catalogue](../../explanation/blocks-and-playbooks.md) explains why a playbook is checked before it runs.

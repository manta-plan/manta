<!--
SPDX-FileCopyrightText: Manta contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Playbook syntax

A playbook is blocks chained together into something you can run, written as a YAML document.
A block is one unit of work in an energy model workflow, such as aggregating the time series or optimising capacities.
This page lists every key of a playbook document, and how `playbook` checks a playbook before it runs.
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

In step `cluster`, `cluster_time` aggregates the time series to a resolution of three hours, and `overnight_capacity_expansion` then optimises capacities on the aggregated time series.

## Documents and playbooks

Each example on this page defines one playbook twice, and the two tabs give the same `Playbook`.
The YAML tab contains the document as you write it in a file.
In the Python tab, the same document is built from the classes in `playbook.playbooks` and `playbook.playbooks.syntax`.
The document is then passed to `playbook_from_doc`, with the catalogue of the blocks that `playbook-library` ships.
Because `if` and `with` are Python keywords, their names in Python are `if_` and `with_`.

| Function | Reads | Returns |
| --- | --- | --- |
| `Playbook.from_yaml(path, catalogue)` | A YAML file. The path of a nested playbook is relative to the file that contains its step. | A `Playbook`. |
| `load_playbook(path, loader, catalogue)` | The playbook that a `PlaybookLoader` finds under `path`, and every playbook nested in it. | A `Playbook`. |
| `parse_doc(raw)` | A mapping loaded from YAML or JSON. | A `PlaybookDoc`. |
| `playbook_from_doc(doc, loader, catalogue)` | A `PlaybookDoc`. | A `Playbook`. |
| `Playbook.to_doc()` | A `Playbook`. | A `PlaybookDoc`, with nested playbooks written out in place. |

`playbook_from_doc` imports each block by its name where it can, and otherwise looks it up in the description of every block (the `catalogue`).
For a block it finds neither way, `playbook_from_doc` raises `PlaybookLoadError`:

```text
step 'cluster': No block registered under 'clusterr_time'. Available blocks: ['cluster_time', 'myopic_capacity_expansion', 'overnight_capacity_expansion', 'perfect_capacity_expansion', 'rolling_horizon_dispatch']
```

The message lists every block name that is known in the running process.

For a key that the format does not have, `parse_doc` raises `PlaybookLoadError`.
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

Below its licence header, each shipped playbook has a `# yaml-language-server: $schema=` comment with the path to `playbook/src/playbook/playbooks/playbook.schema.json`.
With that comment, an editor that runs the YAML language server completes and checks the keys.
For every definition in that file, see the [playbook schema](schema.md).

## `name`

`name` is the name of the playbook, as text, and is required.
`library_playbooks` returns each shipped playbook under the `name` in its document, not under its file name.

## `initial_data`

`initial_data` has one key, `dims`, which lists the dimensions of the starting data, such as `snapshot` or `period`.
When a document has no `initial_data`, `dims` is empty.
`find_playbook_issues` checks each step against these dimensions (see the [`dims` check](#checking-a-playbook)).

!!! note

    `initial_data` is what the playbook author states about the starting data record.
    The `dims` check needs to know whether a dimension is populated in the record, but the manifest of the record only shows that the dimension is recorded.
    We aim to drop `initial_data` once the backend can read the data record itself.

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

The issue gives the missing dimension, and the dimensions the data has before `expansion` runs.

## `inputs`

An input is a value that a user sets for one run.
`inputs` is a mapping from the name of each input to its declaration.
A name starts with a letter or an underscore, and contains only letters, digits, and underscores.

Each declaration has a `type`, and optionally a `description`, `required`, and a `default`.

| `type` | Value | Other keys |
| --- | --- | --- |
| `string` | Text. | |
| `number` | An integer or a float. `true` and `false` are not numbers. | |
| `boolean` | `true` or `false`. | |
| `choice` | One of `options`. | `options`, a list of one or more texts or numbers. A `default` other than `null` must be one of them. |

`required` is `true` or `false`, and is `false` when the declaration leaves it out.
Together with `default`, it sets the value of an input that a run leaves out or gives as `null`:

| `required` | `default` | Left out of the run | `null` in the run |
| --- | --- | --- | --- |
| `true` | None, or `null`. | `playbook` reports an `inputs` issue. | `playbook` reports an `inputs` issue. |
| `false` | A value other than `null`. | The input takes the default. | `playbook` reports an `inputs` issue. |
| `false` | None, or `null`. | The input is `null`. | The input is `null`. |

For a declaration with `required: true` and a `default` other than `null`, `parse_doc` raises `PlaybookLoadError`:

```text
invalid playbook: 1 validation error for PlaybookDoc
inputs.n_hours.number
  Value error, the input is required and has `default` 3. Remove `default`, or set `required: false`. [type=value_error, input_value={'type': 'number', 'required': True, 'default': 3}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.13/v/value_error
```

The location `inputs.n_hours.number` is the declaration of the `number` input `n_hours`.

This playbook has two inputs: the number of hours that `cluster_time` aggregates into one, and the length of each rolling horizon dispatch window:

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

Before any step runs, `playbook` resolves the inputs.
Each of these is an `inputs` issue:

- a name that the playbook does not declare
- a required input without a value
- `null` for an input with a default
- a value of the wrong type
- a choice outside `options`

For the same playbook with the inputs `{"n_hours": "3"}`, `find_playbook_issues` reports:

```text
[inputs] playbook, input 'n_hours': '3' is not a number
```

The value `"3"` is text, so it does not fit `type: number`.
With the inputs `{"n_hours": None}`, `find_playbook_issues` reports:

```text
[inputs] playbook, input 'n_hours': cannot be null. Give it a value, or leave it out to use the default 3
```

`n_hours` has a default, so a run that leaves it out gets `3`.

## `steps`

`steps` is a list of at least one step.
A step is one block, or one nested playbook, in a playbook.
Each step has exactly one of these keys:

| Key | What the step runs |
| --- | --- |
| [`block`](#block) | One block, by its registered name. |
| [`playbook`](#playbook) | Another playbook, as a group of its steps. |

Steps run in list order.
A revision is one version of the model data in a datarecord store.
Each step receives the revision of the last step above it that ran.
The first step receives the revision that the run starts from.
Each block writes its result as a new revision in the same store.
A step cannot receive the revision of any other step.

For a step without `block` or `playbook`, `parse_doc` raises `PlaybookLoadError`:

```text
invalid playbook: 1 validation error for PlaybookDoc
steps.0
  A step has neither `block` nor `playbook`. Add one of them. [type=step_kind, input_value={'id': 'cluster', 'with': {}}, input_type=dict]
```

The location `steps.0` is the first step in the list.

### `id`

`id` is the required name of the step, and follows the same rule as the name of an input.
Within one playbook, each step must have its own `id`.
Two steps with the same `id` are a `structure` issue with the message `duplicate step id`.

In an issue, a step is written as its path of ids from the outermost playbook inwards, such as `plan/expansion_myopic`.

### `block`

`block` is the registered name of the block that the step runs, such as `cluster_time`.
The [`with`](#with) of the step sets the settings of the block that a run cannot change.

### `playbook`

`playbook` is the name of another playbook, which runs in this step as a group of its own steps.
The loader looks the playbook up by this name.
With `Playbook.from_yaml`, the name is a file path relative to the file that contains the step.
`playbook` can also be a whole playbook document, written out in place.

On a `playbook` step, [`with`](#with) sets the inputs of the nested playbook.
An input in `with` that the nested playbook does not declare is a `reference` issue.

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

Through `inputs: inherit`, `expand_and_dispatch` has the input `expansion_mode`, and the `if` of its own `dispatch` step refers to it.

With `with: {expansion_mode: myopic}` in place of `inputs: inherit`, the nested playbook always runs `expansion_myopic`, and the outer playbook has no inputs.
The `if` of `dispatch` then refers to an input that does not exist:

```text
[reference] step 'dispatch': reads inputs.expansion_mode, but there is no input 'expansion_mode' (inputs: [])
```

The list of inputs in the message is empty, because the outer playbook declares none.

An inherited input with the same name as an input of the outer playbook is a `structure` issue:

```text
[structure] step 'plan', input 'expansion_mode': inherits input 'expansion_mode', which the playbook already has
```

The issue gives the step that inherits the input, and the name that both inputs share.

For a playbook that nests itself, directly or through another playbook, `load_playbook` raises `PlaybookLoadError` with the chain of files.
When step `m` of `a.yaml` nests `b.yaml`, and step `n` of `b.yaml` nests `a.yaml`, `load_playbook` raises:

```text
step 'n': circular playbook reference: /path/to/a.yaml -> /path/to/b.yaml -> /path/to/a.yaml
```

The chain starts and ends at `a.yaml`.
For a `Playbook` built in Python that contains itself, `find_playbook_issues` reports a `structure` issue instead.

### `with`

On a `block` step, `with` is a mapping of the settings of the block.
On a `playbook` step, `with` is a mapping of the [inputs of the nested playbook](#playbook).
On both kinds of step, `parse_doc` refuses a single expression in place of the mapping.

Each value in `with` is written out in place, or is an [expression](#expressions), at any depth of the mapping.
In [the inputs example](#inputs), the expression for `n_hours` is at the top of the mapping, and the one for `horizon` is inside `optimize_config`.
A setting in `with` is fixed by the author of the playbook, as a value or through an expression.
A run can give every other setting of the block, which [`apply_settings`](#settings-of-a-run) merges into `with`.

Where the block can be imported, `find_playbook_issues` checks `with` against the settings model of the block.
Where the block cannot be imported, `find_playbook_issues` checks `with` against the JSON schema of the block in the catalogue.
That check finds wrong types, missing settings, and unknown settings.
A setting that does not fit is a `config` issue, and the issue contains the path to the setting.

A JSON schema cannot state a rule that a block states in code.
`cluster_time` needs exactly one of `n_hours` and `segments`, so where `cluster_time` cannot be imported, the block enforces this rule only when it runs.

### `if`

`if` is an [expression](#expressions).
When it is false, the step does not run, and the next step receives the revision that the skipped step would have received.
The [`expand` example](#playbook) has an `if` on each step, so a run with `{"expansion_mode": "overnight"}` runs only `expansion_overnight`.

An `if` can refer only to inputs, so `playbook` works out which steps run from the inputs alone, before any step starts.
For why, see [Conditions look only at inputs](../../explanation/blocks-and-playbooks.md#conditions-look-only-at-inputs).

## Expressions

An expression is a whole string of the form `${{ ... }}`.
It refers to a value by a dotted name that starts at `inputs`, such as `${{ inputs.horizon }}`.
`if` and any value in `with` can be an expression.

| Part | Written as |
| --- | --- |
| A comparison | `==`, `!=`, `<`, `<=`, `>`, and `>=`. |
| A combination | `&&`, `||`, and `!`, with brackets. |
| A literal | `'text'`, a number, `true`, `false`, and `null`. A `'` inside text is written `''`. |

The value of an expression has the type of its result, so `${{ inputs.horizon }}` is a number.
An expression that cannot be evaluated with the input values, such as one that orders a number against text, is an `inputs` issue.
`find_playbook_issues` returns the issue, and `execute_playbook` raises `PlaybookHasIssuesError` with it.
For step `cluster` with `if: ${{ inputs.n_hours > 'a' }}`, and `n_hours` at `3`, the issue is:

```text
[inputs] step 'cluster': 3 > 'a' cannot be evaluated. `>` compares two numbers or two strings.
```

The issue gives the step whose expression `playbook` could not evaluate, and the values it compared.

For text that contains `${{` but is not one whole expression, `parse_doc` raises `PlaybookLoadError`:

```text
invalid playbook: 1 validation error for PlaybookDoc
steps.0.block.with
  Value error, 'h_${{ inputs.n_hours }}' mixes an expression with other text. Write one whole `${{ ... }}` expression, or a value that contains none. [type=value_error, input_value={'n_hours': 'h_${{ inputs.n_hours }}'}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.13/v/value_error
```

The location `steps.0.block.with` is the `with` of the first step.

An expression that refers to an input the playbook does not have is a `reference` issue:

```text
[reference] step 'cluster': reads inputs.n_hour, but there is no input 'n_hour' (inputs: ['horizon', 'n_hours'])
```

The message lists the inputs that the playbook has.

## Settings of a run

`apply_settings(playbook, settings)` returns a copy of `playbook` with the settings of one run merged into the `with` of its steps.
`settings` is a mapping from step id to the settings of that step.
`apply_settings` merges nested mappings key by key, so a run can add a setting inside a mapping that `with` already has.
For a `playbook` step, the entry contains the settings of the nested playbook, by its own step ids.
`apply_settings` changes neither `playbook` nor `settings`.

These settings give the solver of step `dispatch` in [the inputs example](#inputs), saved as `cluster_and_dispatch.yaml`:

```yaml title="settings.yaml"
dispatch:
  optimize_config:
    solver_name: highs
```

```python
import yaml
from playbook.playbooks import Playbook, apply_settings
from playbook_library import library_catalogue

playbook = Playbook.from_yaml("cluster_and_dispatch.yaml", library_catalogue())

with open("settings.yaml") as file:
    settings = yaml.safe_load(file)
applied = apply_settings(playbook, settings)
print(applied.steps[1].with_)
```

```text
{'optimize_config': {'horizon': '${{ inputs.horizon }}', 'overlap': 24, 'solver_name': 'highs'}}
```

`solver_name` sits beside the two settings that `with` fixes, and the expression for `horizon` is left for the run to evaluate.

`apply_settings` raises `PlaybookHasIssuesError`, with one `config` issue for each of these:

- a step id that the playbook does not have
- settings of a step that are not a mapping
- a setting that `with` sets
- a value that contains `${{`

For the settings `{"dispatch": {"optimize_config": {"overlap": 48}}}`, the issue is:

```text
[config] step 'dispatch', setting 'optimize_config.overlap': the playbook sets this to 24, so a run cannot set it. Leave it out of the settings
```

The issue gives the path to `overlap` within the `with` of `dispatch`, where the playbook fixes it at `24`.

## Checking a playbook

`find_playbook_issues` checks a playbook against the inputs of one run.
It returns every problem it finds as a `PlaybookIssue`, which contains the step, input, or setting that the problem is about:

```python
from playbook.playbooks import find_playbook_issues, playbook_from_doc
from playbook_library import library_catalogue
from playbook_library.playbooks import library_playbooks

playbook = playbook_from_doc(library_playbooks()["expand"].doc, catalogue=library_catalogue())
for issue in find_playbook_issues(playbook, {"expansion_mode": "greenfield"}):
    print(issue)
```

```text
[inputs] playbook, input 'expansion_mode': 'greenfield' is not one of ['overnight', 'myopic', 'perfect']
```

The loop prints one issue, because `greenfield` is not one of the options of `expansion_mode`.

`find_playbook_issues` finds a misspelt setting in the same way.
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

The issue points at the setting `n_hour` in step `cluster`.

`find_playbook_issues(playbook, inputs)` returns a `list[PlaybookIssue]`.
When it finds no problem, the list is empty.
`raise_for_playbook_issues` raises `PlaybookHasIssuesError` instead, with the same list as its `issues` attribute.
The methods `Playbook.find_issues` and `Playbook.raise_for_issues` call these two functions.
`Playbook.run` checks the playbook against its inputs first, and raises `PlaybookHasIssuesError` before any step runs.

A `PlaybookIssue` has these fields:

| Field | Value | Example |
| --- | --- | --- |
| `kind` | The check that failed. | `"config"` |
| `message` | What is wrong, in words. | `"there is no setting called 'n_hour'"` |
| `step_path` | The step, as ids from the outermost playbook inwards. It is empty for the playbook as a whole. | `("plan", "expansion_myopic")` |
| `input_path` | The input at fault, or `None`. | `("expansion_mode",)` |
| `setting_path` | Where in the settings of the step the problem is, or `None`. It is empty for the settings of a step as a whole. | `("optimize_config", "horizon")` |

The `kind` of an issue is one of these checks:

| `kind` | Reported when |
| --- | --- |
| `structure` | Two steps share an `id`, an inherited input has the name of another input, or a playbook contains itself. |
| `reference` | An expression refers to an input that does not exist, or a nested playbook is given an input it does not declare. |
| `inputs` | An input value is unknown, missing, `null` where it cannot be, of the wrong type, or not one of its options, or an expression cannot be evaluated with the input values. |
| `dims` | A step needs a dimension that neither `initial_data` lists nor an earlier step adds, or that an earlier step removed. |
| `config` | The settings of a step do not fit what its block accepts, or `apply_settings` cannot apply a setting that a run gives. |
| `environment` | Two blocks describe the same environment differently. |

Without inputs, `find_playbook_issues(playbook)` runs only the `structure` and `reference` checks, because they do not depend on the inputs.
With inputs, it first works out which steps run and checks only those, so the settings of a step that does not run stay unchecked.
When `find_playbook_issues` finds a `structure` or a `reference` issue, it returns before the checks that need inputs.
For a playbook that contains itself, it returns only the issues about that nesting.

The `dims` check starts from the dimensions in `initial_data`, and goes through the steps in the order they run.
Each step requires some dimensions, and can add or remove others for the steps after it.
A nested playbook is one step to the playbook around it.
It requires the dimensions that its own `initial_data` lists, and its own steps are checked against those.
If `initial_data` lists a dimension that the starting data does not populate, the problem is found only when the block runs.

## Shipped playbooks

`playbook-library` ships two playbooks.
`playbook_library.playbooks.library_playbooks()` returns them as `LibraryPlaybook` objects, keyed by the `name` in each document.
A `LibraryPlaybook` has the document in `doc`, and the default settings of a run in `default_settings`, by step id.
The default settings of a playbook are in `configs/` beside it, in a file with the same name as the playbook file.
For a playbook without such a file, `default_settings` is empty.

| Name | File | Inputs | What it runs |
| --- | --- | --- | --- |
| `expand` | [`expand.yaml`](https://github.com/manta-plan/manta/blob/main/playbook-library/src/playbook_library/playbooks/expand.yaml) | `expansion_mode`: `overnight`, `myopic`, or `perfect`, with `overnight` as the default. | Optimises capacities with one capacity expansion block, chosen by `expansion_mode`. It has no time aggregation step, so it is for small models only. |
| `cluster-expand-dispatch` | [`cluster_expand_dispatch.yaml`](https://github.com/manta-plan/manta/blob/main/playbook-library/src/playbook_library/playbooks/cluster_expand_dispatch.yaml) | `expansion_mode`: `overnight` or `myopic`, with `overnight` as the default. `solver_name`: `highs`, the only option and the default. | Aggregates the time series, then optimises capacities. With `overnight`, a rolling horizon dispatch follows. |

The `with` of each optimisation step in `cluster-expand-dispatch` sets `optimize_config.solver_name` to the `solver_name` input.
Its default settings, in [`configs/cluster_expand_dispatch.yaml`](https://github.com/manta-plan/manta/blob/main/playbook-library/src/playbook_library/playbooks/configs/cluster_expand_dispatch.yaml), are:

```yaml
cluster:
  n_hours: 3

dispatch:
  optimize_config:
    horizon: 168
    overlap: 24
```

With these settings, `cluster_time` aggregates the time series to a resolution of three hours.
The rolling horizon dispatch then runs in windows of 168 hours that overlap by 24 hours.

The expansion step before the dispatch writes an optimised value for each capacity it optimises.
`rolling_horizon_dispatch` fixes each capacity that has such a value in the revision it receives.
For a capacity without an optimised value, the dispatch uses the capacity in the model.

!!! info "See also"

    - [Playbook schema](schema.md): every definition of the JSON schema of a playbook document.
    - [playbook](api.md): the Python API, generated from the docstrings.
    - [Blocks, playbooks and the catalogue](../../explanation/blocks-and-playbooks.md): why a playbook is checked before it runs.

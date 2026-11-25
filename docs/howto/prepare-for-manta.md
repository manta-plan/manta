---
tags:
  - Modelling tool developers
description: Describe your model data as a schema and split your workflow into blocks, ready for Manta.
---

<!--
SPDX-FileCopyrightText: Manta contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Prepare a modelling framework or workflow for Manta

This guide shows how to get a modelling framework, or a workflow built on one, ready to run in Manta.
It is for people who maintain an energy modelling framework, or who run studies with one today.
Every step is a change in your own repository, so you do not need to install Manta to follow it.
You need to know your framework's data model and the steps of your workflow.

!!! warning "What Manta accepts today"

    Manta currently imports [PyPSA](https://pypsa.org) models only, and the blocks it includes use PyPSA.
    To prepare a PyPSA model, see [Prepare a PyPSA model for Manta](prepare-pypsa-model.md).
    A new block or a new modelling framework currently needs a change to Manta's repository.
    For the route we plan instead, see [Block libraries outside this repository](../explanation/planned-changes.md#block-libraries-outside-this-repository).
    The steps in this guide make that change smaller, and they do not add your framework to Manta.

## Map your workflow to the parts of Manta

Each part of a workflow has a counterpart in Manta, and each section of this guide prepares one of them.

| In your workflow today                               | In Manta                                                                   |
| ---------------------------------------------------- | -------------------------------------------------------------------------- |
| Input and result files in your framework's format    | Tables in a data record, which follow a declared schema                    |
| A script or a rule for each step                     | A block, which gets one version of the model and returns the next          |
| A run script, or the rule graph of a workflow manager | A playbook, which is blocks chained together into something you can run    |
| One configuration file for the whole workflow        | A settings model for each block, which Manta checks before the run         |
| One environment for every step                       | An environment for each block, which Manta runs in a container of its own  |

## Describe your model data as a schema

Manta keeps a project's model, scenarios, and results as layers of tables in one store (a [data record](../user-guide/concepts.md)).
The [`datarecord`](https://energy-models.github.io/datarecord/) package reads and writes that store, and every table in it follows a schema.
A schema has three kinds of declaration.

| Declaration | What it declares                                                                      | Example                                    |
| ----------- | ------------------------------------------------------------------------------------- | ------------------------------------------ |
| Dimension   | An axis that data varies over                                                         | `node`, `technology`, `timestep`           |
| Property    | One value for each label of a dimension                                               | The `carrier` of each technology           |
| Attribute   | Values that vary over one or more dimensions, with a data type, a unit, and a default | `demand` in MW over `node` and `timestep`  |

To prepare, list every input and every result of your framework, and write each one as a dimension, a property, or an attribute.
For each attribute, write down the dimensions it varies over, its data type, its unit, and its default.
If your framework sets a unit or a default in its code, move it into the schema.
Someone who reads the data then does not need that code to understand it.

This schema declares three dimensions, one property, and two attributes:

```python
from datarecord.schema import AttributeSpec, Dimension, PropertySpec, Schema

dimensions = {
    "technology": Dimension(description="A plant or a store"),
    "node": Dimension(description="A place where supply meets demand"),
    "timestep": Dimension(dtype="datetime"),
}
properties = {"technology": {"carrier": PropertySpec(dtype="str")}}
attributes = {
    "capacity_max": AttributeSpec(
        dtype="float", dims={"technology", "node"}, unit="MW", default=float("inf")
    ),
    "demand": AttributeSpec(dtype="float", dims={"node", "timestep"}, unit="MW"),
}
schema = Schema(dimensions=dimensions, properties=properties, attributes=attributes)
print(sorted(schema.attributes["demand"].dims))
```

```text
['node', 'timestep']
```

`Schema` accepts the declarations, and `demand` varies over `node` and `timestep`.
If an attribute names a dimension that the schema does not declare, `Schema` raises a `ValidationError`.
For every field of a declaration, see the [schema reference of `datarecord`](https://energy-models.github.io/datarecord/reference/schema/).

!!! note "A common schema"

    Manta currently uses the schema that `datarecord` derives from PyPSA's components.
    We aim to represent models from several modelling frameworks in a common schema.
    A schema of your own framework shows which of its dimensions and attributes need a counterpart in that common schema.

## Convert your model to tables and back

A block gets one saved version of the data record (a revision) and builds the framework's model from it.
The block then writes its result as a new revision.
The blocks included in Manta do both with two functions, `to_network` and `write_network`, in [`pypsa_helpers.py`](https://github.com/manta-plan/manta/blob/main/playbook-library/src/playbook_library/pypsa_helpers.py).
No block opens a model file itself.

To prepare, write the same pair of functions for your framework:

- One function writes your framework's model, with its results, to tables that follow your schema.
- One function builds your framework's model from those tables.

Keep both functions in one module, and make every step of your workflow read and write its model through them.
Write the results as well as the inputs, because a later block starts from them.
The rolling horizon dispatch block, for example, reads the capacities that the capacity expansion block optimised.

To check the pair, write a model to tables, build it again, and solve both models.
If the two objective values differ, your schema is missing an attribute or a default.

## Split your workflow into blocks

A block is one unit of work in an energy model workflow, and a playbook is blocks chained together into something you can run.
For the blocks and playbooks included in Manta, see [Playbooks and blocks](../user-guide/playbooks.md).

Manta runs each block in a container of its own.
A block gets one revision and its settings, and it returns one new revision.
Nothing else passes from one block to the next.
A block cannot read a file or an object in memory that an earlier block left behind.

To split your workflow, cut it where one modelling task ends and its result is a complete model.
The `cluster-expand-dispatch` playbook has three such cuts: after it aggregates the time series, after it optimises capacities, and after the rolling horizon dispatch.

Some steps need a change before they fit:

- If a step reads an intermediate file that an earlier step wrote, move that data into the model that the earlier step returns.
- If your workflow builds the model from raw data, keep those steps out of the blocks. A playbook currently starts from a model that is already in the data record.
- If a step downloads data, move the download to the steps that build the model.
- If your workflow decides from the data whether a step runs, make that decision a setting. Manta works out which blocks run [from the settings alone](../explanation/blocks-and-playbooks.md#conditions-look-only-at-settings), before the run starts.
- If your workflow repeats a step until a result converges, keep the loop inside one block. A playbook runs each of its steps at most once, in order.

The shortest block included in Manta shows a step after such a split:

```python title="playbook-library/src/playbook_library/time_cluster.py"
--8<-- "playbook-library/src/playbook_library/time_cluster.py"
```

`ClusterTime` builds a PyPSA network from the revision it gets, aggregates the network's time series, and writes the result as a new revision.
Its three class attributes set its environment, its settings model, and the dimension it requires.

To check a step, run it alone, from a saved model and its settings.
Manta runs [one block](https://github.com/manta-plan/manta/blob/main/playbook/README.md#running-one-block) in the same way.

## Declare the settings of each block

Each block has a settings model, which lists every setting of the block with its type and its default.
Before any block runs, Manta checks a playbook's settings against these models and lists every problem it finds.

To prepare, write one settings model for each step:

- List only the settings that the step reads. If your workflow has one configuration file for all its steps, split it by step.
- Give each setting a type and a default, and state the values it accepts.
- If a rule joins two settings, write it as a check in the model. `ClusterTimeConfig` in the block above refuses settings unless exactly one of `segments` and `n_hours` is set.
- If a step reads a value from an environment variable, make it a setting.

Manta's settings models are [pydantic](https://docs.pydantic.dev) models, so a pydantic model in your own code needs the least change later.

## State the dimensions each block requires

Each block declares the dimensions it requires, the dimensions it adds, and the dimensions it removes.
Manta follows these declarations along a playbook.
It refuses the playbook before the run if a block requires a dimension that the model lacks at that step.
`ClusterTime` requires `snapshot`, and the myopic capacity expansion block requires `snapshot` and `period`.

To prepare, write down for each step which dimensions of your schema it requires, adds, and removes.
For example, a step that only works on a model with investment periods requires the dimension that contains those periods.

## Give each block an environment

Each block names the environment it runs in, and Manta runs the block in a container built from that environment.
No other part of Manta installs a block's dependencies.

To prepare, make each step run from a pinned environment:

- Pin the dependencies of each step in a lock file. Steps that need the same packages can share one environment, as the blocks included in Manta share the `pypsa` environment.
- Check that each step runs in a clean container, from the lock file alone.
- Test each step with an open-source solver. The blocks included in Manta currently solve with [HiGHS](https://highs.dev), and Manta manages no solver licences yet.

!!! note "Memory and run time"

    Manta does not read the resource requirements of a block yet.
    We aim for a block to declare the memory it needs.
    Measure the peak memory and the run time of each step on a model of known size, so that you already have those numbers.

## Check the result

Your framework and workflow are prepared when all four checks pass:

1. `Schema` accepts your declarations.
2. A model that you write to tables and build again solves to the same objective value.
3. Each step runs alone, in a clean container, from a saved model and its settings.
4. The steps, run in order, give the same result as your workflow gave before you split it.

To write a block for Manta, follow [Blocks and playbooks](../installation/blocks-and-playbooks.md), then read the [`playbook` reference](../reference/playbook/api.md).

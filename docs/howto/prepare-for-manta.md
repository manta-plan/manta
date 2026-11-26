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
It requires you to understand your framework's data model and how you orchestrate analysis workflows; it doesn't require you to have installed Manta.

!!! warning "Modelling frameworks compatible with Manta today"

    Currently, Manta can only import [PyPSA](https://pypsa.org) models, and can only run Blocks using PyPSA.
    To prepare a PyPSA model for use in Manta, see [Prepare a PyPSA model for Manta](prepare-pypsa-model.md).

    Our goal is to support as many modelling frameworks as the community is willing and able to contribute,
    mostly via [Block libraries outside this repository](../explanation/planned-changes.md#block-libraries-outside-this-repository).
    We hope the steps in this guide will support the community to elp us achieve our goal.

## Map your workflow to the parts of Manta

Currently, your modelling workflow might consist of a single script or interactive notebook (e.g. Jupyter), a collection of scripts you manage yourself, or a reproducible workflow that is managed by an external dependency, e.g., [snakemake](https://snakemake.readthedocs.io).
However involved your current modelling workflow is, each part of it has (or will soon have!) a counterpart in Manta.
This guide is separated into the following workflow steps:

| In your workflow today                                | In Manta                                                                   |
| ----------------------------------------------------- | -------------------------------------------------------------------------- |
| Input and result files in your framework's format     | Tables in a data record, which follow a declared schema                    |
| A script for each step                                | A block, which gets one version of the model and returns the next          |
| A run script, or the rule graph of a workflow manager | A playbook, which is blocks chained together into something you can run    |
| One configuration file for the whole workflow         | Settings for each block, which Manta checks before the run                 |
| A single set of dependencies, or one per script       | An environment for each block, which Manta runs in a container of its own  |

## Describe your model data as a schema

Manta keeps a project's model, scenarios, and results as layers of tables in one store (a [data record](../user-guide/concepts.md)).
The [`datarecord`](https://energy-models.github.io/datarecord/) package reads and writes that store, and every table in it follows a schema.
A schema has three kinds of declaration.

| Declaration | What it declares                                                                      | Example                                    |
| ----------- | ------------------------------------------------------------------------------------- | ------------------------------------------ |
| Dimension   | An axis that data varies over                                                         | `node`, `technology`, `timestep`           |
| Property    | One value for each label of a dimension                                               | The `geometry` of each node                |
| Attribute   | Values that vary over one or more dimensions, with a data type, a unit, and a default | `demand` in MW over `node` and `timestep`  |

To prepare, list every input and every result of your framework, and write each one as a dimension, a property, or an attribute.
For each attribute, write down the maximum set of dimensions it can vary over, its data type, its unit, and its default.
If your framework sets a unit or a default in its code, move it into the schema.
Someone can then read the data without needing to review your framework's source code to understand it.

This schema declares three dimensions, one property, and two attributes:

```python
from datarecord.schema import AttributeSpec, Dimension, PropertySpec, Schema

dimensions = {
    "technology": Dimension(description="A plant or a store"),
    "node": Dimension(description="A place where supply meets demand"),
    "timestep": Dimension(dtype="datetime"),
}
properties = {"node": {"geometry": PropertySpec(dtype="str", "description"="A WKT string defining a shape")}}
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

If you have defined a valid `Schema`, `datarecord` will accept the declarations.
If an attribute names a dimension that the schema does not declare, `Schema` raises a `ValidationError`.
For every field of a declaration, see the [schema reference of `datarecord`](https://energy-models.github.io/datarecord/reference/schema/).

!!! note "A common schema"

    Manta currently uses the schema that `datarecord` derives from PyPSA's components.
    This means, you would need to align to the PyPSA schema to be able to have your model read into Manta currently.
    We plan to support data records that follow a common, framework-agnostic schema.
    Describing you model data already as a `datarecord`-compatible schema will make converting to a common schema easier later.

## Convert your model to data records and back

A block reads a data record and builds a framework's model from it.
Once the block run has completed, it then writes its result as a new revision.
The blocks included in Manta convert from data record to a PyPSA model with a `to_network` helper function, and from a model back to a data record revision with a `write_network` helper function (see [`pypsa_helpers.py`](https://github.com/manta-plan/manta/blob/main/playbook-library/src/playbook_library/pypsa_helpers.py)).

To prepare to have blocks running using your framework, you will need to write the same pair of functions:

- One function writes your framework's model, with its results, to a data record that follow your schema.
- One function builds your framework's model from that data record.

Keep both functions in one module, and make every step of your workflow read and write its model through them.
To check your conversion functions, write a model to a data record, build it again, and solve both models.
If the two objective values differ, your schema is missing an attribute or a default.

!!! note "Adopting `datarecord` for your model data"

    `datarecord` is an independent package that you may want to consider adopting whether or not you are preparing to use your framework in Manta.
    It offers time-, memory-, and disk-efficient data storage and access, with a `git`-like revision history that allows you to track your data changes.
    It is being developed within the energy modelling community, so the key features you need are likely catered for!

## Split your workflow into blocks

A block is one unit of work in an energy model workflow, and a playbook is blocks chained together into something you can run.
For the blocks and playbooks included in Manta, see [Playbooks and blocks](../user-guide/playbooks.md).

Manta runs each block in a container of its own.
A block gets one data record and its settings, and it returns a data record.
To understand what to include in a single block, it is important to understand that the data records passed between them build up in layers, e.g.:

- the first block receives a data record with only input data and adds a property (e.g. a time dimension cluster mapping),
- the next uses that property to aggregate a dimension and then solves the model and add results,
- the next takes some of those results (e.g. optimal capacities), fixes them in the math and then solves the model again; this time without aggregating a dimension.

Each time, only the new data being generated should be stored as a data record layer.
Later blocks can access the entire history of those layers.
In the above example, the final block still has access to the input data even though the preceding block only stored results.

Given this access to the full history of revisions, nothing else needs to pass from one block to the next.
It also means that a block's entire function is to add data to the data record.

You may need to change some of your steps before they fit:

- If a step reads an intermediate file that an earlier step wrote, have the earlier step write that into the model itself.
  This may require a custom data container in your modelling framework to keep all data in one place.
- If your workflow builds the model from raw data, keep those steps out of the blocks.
  A playbook currently starts from a fully built model, with no new, raw data processing steps expected.
  This includes data downloads.
- If your workflow decides from the data whether a step should run, add that decision as a setting in your step's configuration.
  Manta works out which blocks run [from the block configuration alone](../explanation/blocks-and-playbooks.md#conditions-look-only-at-settings), before the run starts.
- If your workflow repeats a step until a result converges, keep the loop inside one block.
  A playbook runs each of its steps at most once, in order.

!!! note "More options are on their way"

    We plan to integrate block loops (to convergence or between blocks that pass data between them), as well as block parallelisation.
    This will all be configurable at the playbook level.

The shortest block included in Manta shows a step after such a split:

```python title="playbook-library/src/playbook_library/time_cluster.py"
--8<-- "playbook-library/src/playbook_library/time_cluster.py"
```

`ClusterTime` builds a PyPSA network from the revision it gets, aggregates the network's time series, and writes the result as a new revision.
Its three class attributes set its environment, its configuration, and the dimension it requires.

To check a step, [run just that one block](https://github.com/manta-plan/manta/blob/main/playbook/README.md#running-one-block) from a data record that represents the output of a prior block (or the input to the playbook, if the first block) and pass the required configuration.

## Declare the configuration of each block

Each block has configuration, in which every setting is defined alongside its type and default value.
Before any block runs, Manta checks a playbook's configuration against these and lists every problem it finds.

To prepare, write one configuration for each block as [pydantic](https://docs.pydantic.dev) models:

- List only the settings that the block reads. If your workflow has one configuration file for all its steps, split it by step.
- Give each setting a type and a default, and state the values it accepts.
- If a rule joins two settings, write it as a check in the model.
  `ClusterTimeConfig` in the block above refuses a configuration unless exactly one of `segments` and `n_hours` is set.
- If a step reads a value from an environment variable, make it a setting.

## State the dimensions each block requires

Each block declares the dimensions it requires, the dimensions it adds, and the dimensions it removes.
Manta follows these declarations along a playbook.
It refuses the playbook before the run if a block requires a dimension that the model lacks at that step.
`ClusterTime` requires `snapshot`, and the myopic capacity expansion block requires `snapshot` and `period`.

To prepare, write down for each step which dimensions of your schema it requires, adds, and removes.
For example, a block that only works on a model with investment periods requires the dimension that contains those periods.

## Give each block an environment

Each block specifies the environment it runs in.
Manta will then run the block in a container built from that environment.
This isolation ensures that blocks with conflicting dependencies can be run in the same playbook and enables reproducibility: you can rerun a block later in the same working environment.

To prepare, make each block run from a pinned environment:

- Pin the dependencies of each block in a lock file.
  Blocks that need the same packages can share one environment, as the blocks included in Manta share the `pypsa` environment.
- Check that each block runs in a clean container, from the lock file alone.
- Test each block with an open-source solver since Manta doesn't manage solver licences yet.
  The blocks included in Manta currently solve with [HiGHS](https://highs.dev).

!!! note "Memory and run time"

    Manta does not read the resource requirements of a block yet.
    We aim for a block to declare the memory it needs.
    Measure the peak memory and the run time of each step on a model of known size, so that you already have those numbers.

## Check the result

Your framework and workflow are prepared when all four checks pass:

1. `Schema` accepts your declarations.
2. A model that you write to a data record and build again solves to the same objective value.
3. Each block runs alone, in a clean container, from a saved model and its settings.
4. The blocks, run in a playbook, give the same result as your workflow gave before you split it.

To write a block for Manta, follow [Blocks and playbooks](../installation/blocks-and-playbooks.md), then read the [`playbook` reference](../reference/playbook/api.md).

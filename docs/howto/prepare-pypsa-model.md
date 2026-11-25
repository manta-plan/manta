---
tags:
  - App users
  - Modelling tool developers
description: Store a PyPSA network as a data record that Manta can open.
---

<!--
SPDX-FileCopyrightText: Manta contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Prepare a PyPSA model for Manta

This guide shows how to store a PyPSA network as a [data record](../user-guide/concepts.md), so that you can run Manta's playbooks on it.
It is for modellers who have a PyPSA network, as a file or from a workflow such as PyPSA-Eur.
You need a Python environment with PyPSA, [HiGHS](https://highs.dev), and the [`datarecord`](https://energy-models.github.io/datarecord/) package with its `pypsa` extra.
Use the same version of `datarecord` as Manta, which is set in [`playbook-library/pixi.toml`](https://github.com/manta-plan/manta/blob/main/playbook-library/pixi.toml).
A data record written with another version may not open in Manta.
You do not need to install Manta.

!!! warning "Adding your data record to Manta"

    You currently cannot upload a model in the web app, so an administrator has to add your data record.
    See the [table of stages](../user-guide/index.md#what-the-web-app-supports-today) for what the web app supports today.
    At the end of this guide you have a folder to send to your Manta administrator.

## Make every component name unique

In a data record, two components of different types cannot have the same name.
For example, a load and a generator cannot both be called `Manchester Wind`, and a load and a line cannot both be called `10`.
Buses and carriers are the exception, so a bus can have the same name as a load.

To find clashing names, convert the network:

```python
import pypsa
from datarecord import Workspace
from datarecord.tools.pypsa import PyPSA

n = pypsa.examples.ac_dc_meshed()
n.add("Load", "Manchester Wind", bus="Manchester")
ws = Workspace()
PyPSA.to_datarecord(n, ws.con)
```

```text
datarecord.tools.base.UnsupportedRecordError: record cannot build a pypsa model; missing: labels claimed by more than one category ['Manchester Wind'] (https://energy-models.github.io/datarecord/reference/format/#labels)
```

The example network already has a generator called `Manchester Wind`, so `PyPSA.to_datarecord` raises an error that lists every clashing name.

To fix a clash, rename the components of one type, both in the component table and in each of its time series:

```python
names = {"Manchester Wind": "load-Manchester Wind"}
n.loads.rename(index=names, inplace=True)
for series in n.loads_t.values():
    series.rename(columns=names, inplace=True)
record = PyPSA.to_datarecord(n, ws.con)
```

`PyPSA.to_datarecord` now accepts the network.
If your workflow gives loads and lines the same numbers, as PyPSA-Earth does, add a prefix to every load with `names = {name: f"load-{name}" for name in n.loads.index}`.

## Write the network to a data record

A data record is a folder with one layer for each saved version of the model (a revision).
To start a data record, save the network as its first revision, which has no parent.
Save the network before you solve it, so that the first revision contains only inputs.

```python
import pypsa
from datarecord import Workspace
from datarecord.tools.pypsa import PyPSA

n = pypsa.examples.ac_dc_meshed()
ws = Workspace()
store = ws.store("ac-dc-meshed")
record = PyPSA.to_datarecord(n, ws.con)
base = store.commit(record, parent=None, meta={"manta.kind": "scenario"})
print(base.manifest.meta)
```

```text
{'manta.kind': 'scenario'}
```

`store.commit` writes the revision to `ac-dc-meshed/layers/` and returns it, with `manta.kind` in its metadata.
Manta reads `manta.kind` to find out what a revision contains: `scenario` for inputs, or `result` for the results of a run.
It does not open a data record unless the first revision is a `scenario`.

## Name the base revision

Manta starts every run from the revision called `base`.
It finds that name in `store.json`, in the folder of the data record.
To name the revision, write that file:

```python
import json
from pathlib import Path

content = {
    "label": "AC-DC meshed example",
    "description": "A small example that solves in under a second.",
    "references": {
        "base": {
            "revision": str(base.id),
            "label": "Base case",
            "description": "PyPSA's ac_dc_meshed example",
        }
    },
}
Path("ac-dc-meshed/store.json").write_text(json.dumps(content, indent=2) + "\n")
print(sorted(path.name for path in Path("ac-dc-meshed").iterdir()))
```

```text
['layers', 'store.json']
```

The folder `ac-dc-meshed` now contains the revision under `layers/` and its name in `store.json`.
The first `label` and `description` describe the data record, and the ones under `base` describe the base scenario.
You can leave out either `description`, but Manta needs all the other keys.

## Check the result

A block in Manta builds a PyPSA network from the revision and solves it with HiGHS.
To check your data record, do the same, and solve your original network for comparison:

```python
from uuid import UUID

references = json.loads(Path("ac-dc-meshed/store.json").read_text())["references"]
revision = Workspace().store("ac-dc-meshed").revision(UUID(references["base"]["revision"]))
back = PyPSA.build(revision.record)
n.optimize(solver_name="highs")
back.optimize(solver_name="highs")
print(round(n.objective), round(back.objective))
```

```text
-3474256 -3474256
```

Both networks give the same objective value, so the data record contains everything the optimisation needs.
When the two values match, your model is ready.
Send the folder to your Manta administrator.

If you do not get two matching values:

- If both networks are infeasible, a run in Manta also fails. A block stops the run when the solver does not find an optimal solution. If the cause is demand that the network cannot meet, add load-shedding generators with `n.optimize.add_load_shedding()`, then write the data record again.
- If the two values differ, check whether any global constraint in your network has a `bus`. `datarecord` currently does not save it ([datarecord#162](https://github.com/energy-models/datarecord/issues/162)), so the constraint applies to the whole network once you build it from the data record. Manta's blocks build the network in the same way, so results in Manta differ from your own results too.
- If your network is too large to solve on your computer, compare the two networks at a lower time resolution. For example, solve `n.cluster.temporal.downsample(6)` and `back.cluster.temporal.downsample(6)`.

!!! info "See also"

    - For the blocks that can run on your model, see [Playbooks and blocks](../user-guide/playbooks.md).
    - To do the same for another modelling framework, see [Convert your model to tables and back](prepare-for-manta.md#convert-your-model-to-tables-and-back).

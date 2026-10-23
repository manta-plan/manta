<!--
SPDX-FileCopyrightText: datarecord contributors

SPDX-License-Identifier: CC-BY-4.0
-->

# Usage

How to use the package. [Design](../design/index.md) is what it is and why;
[API Reference](../api/index.md) is the generated signatures.

## Installation

```bash
pip install datarecord           # core
pip install datarecord[pypsa]    # with the PyPSA tool
```

Or with conda/mamba, from conda-forge:

```bash
conda install -c conda-forge datarecord
```

## Workspaces and stores

A `Workspace` holds the DuckDB database and reaches files; a `Store` is one
location — its [schema](../design/schema.md#one-schema-per-record), its
revisions, its layers — on a workspace several stores share
([design](../design/layers.md#the-store)).

```python
from datarecord import Workspace

ws = Workspace()  # ":memory:" by default
store = ws.store("/data/my-record")  # absolute; never empty
record = ws.at("out/")  # a standalone directory
```

`ws.con` is the calling thread's DuckDB cursor, so one workspace serves every
thread; a frame belongs to the thread that built it.

## The pages

| page                           | what it covers                                |
| ------------------------------ | --------------------------------------------- |
| [Reading a record](reading.md) | the `Record` protocol, `properties`, `flags`  |
| [The schema](schema.md)        | declaring dims, properties and attributes     |
| [Layers](layers.md)            | revisions, branching, materialising           |
| [Editing](editing.md)          | `WorkingRecord`: `set`, `add`, `edits`        |
| [Writing](writing.md)          | `store.root`, `rev.child`, `ws.write`         |
| [Tools](tools.md)              | consuming a record from a modelling framework |

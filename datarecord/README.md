<!--
SPDX-FileCopyrightText: datarecord contributors

SPDX-License-Identifier: CC-BY-4.0
-->

# datarecord

[![docs](https://img.shields.io/badge/docs-energy--models.github.io-blue?style=flat-square&logo=materialformkdocs&logoColor=white)](https://energy-models.github.io/datarecord/)
[![CI](https://img.shields.io/github/actions/workflow/status/energy-models/datarecord/ci.yml?style=flat-square&branch=main)](https://github.com/energy-models/datarecord/actions/workflows/ci.yml)
[![conda-forge](https://img.shields.io/conda/vn/conda-forge/datarecord?logoColor=white&logo=conda-forge&style=flat-square)](https://prefix.dev/channels/conda-forge/packages/datarecord)
[![pypi-version](https://img.shields.io/pypi/v/datarecord.svg?logo=pypi&logoColor=white&style=flat-square)](https://pypi.org/project/datarecord)
[![python-version](https://img.shields.io/pypi/pyversions/datarecord?logoColor=white&logo=python&style=flat-square)](https://pypi.org/project/datarecord)

Dimensioned attribute data with a declared schema.

A record holds **entities** (labels unique record-wide, classified by **properties** such as their type), **groups** of entities over further dims — a `connection` over `(entity, bus)` is the one every record with connections has — **attribute values** over both, and the **axes** those values vary along. A schema declares what may exist; the data says what does.

Records stack: a layer is a partial record on top of a parent, resolved last-writer-wins, so a scenario variant costs the rows it changes rather than a copy of everything. On disk a record is a plain parquet directory that a tool knowing nothing about this package can read.

`datarecord` depends only on `duckdb`, `narwhals` and `pydantic`. It names no modelling framework — a framework consumes a record, a workflow engine produces one, and neither needs to know how the other works.

## Documentation

Full documentation is at **<https://energy-models.github.io/datarecord/>**:

- [Usage](https://energy-models.github.io/datarecord/usage/) — reading, editing, layering and writing a record
- [Design](https://energy-models.github.io/datarecord/design/) — what a record is and why, the authoritative design
- [API Reference](https://energy-models.github.io/datarecord/api/) — every public symbol

## Installation

```bash
pip install datarecord           # core
pip install datarecord[pypsa]    # with the PyPSA tool
pip install datarecord[remote]   # with records on S3
```

## A taste

```python
from datarecord import Workspace

ws = Workspace()
record = ws.at("s3://bucket/my-record/")

record.properties["entity"].collect()  # each entity's stored properties
record.attributes["p_max_pu"].collect()  # long value rows, one per value
record.flags(entity_type="Generator")  # which axes each attribute uses
```

Every frame is a `narwhals.LazyFrame` — a plan, not data. Nothing is read until you `.collect()`.

Records stack, and a `WorkingRecord` accumulates edits that become one layer when written as a child:

```python
from datarecord import WorkingRecord

w = WorkingRecord(revision.record)
w.set("p_nom", 150.0, entity=["wind1", "wind2"])
child = revision.child(w.edits)
```

See [Usage](https://energy-models.github.io/datarecord/usage/) for the rest.

## Development

This project is managed by [pixi](https://pixi.sh):

<!-- --8<-- [start:docs-install-dev] -->

```bash
git clone https://github.com/energy-models/datarecord
cd datarecord

pixi run test    # the test suite
pixi run lint    # ruff, prettier, taplo, typos, zizmor, reuse, mypy
```

<!-- --8<-- [end:docs-install-dev] -->

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the workflow and conventions, and [`AGENTS.md`](AGENTS.md) for how AI-assisted contributions must be marked.

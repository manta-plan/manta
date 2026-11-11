<!--
SPDX-FileCopyrightText: datarecord contributors

SPDX-License-Identifier: CC-BY-4.0
-->

# Reading a record

## The `Record` protocol

Everything a consumer codes against. It is read-only, and structural — a plain directory, a hundred-layer overlay, a record with pending edits and a framework's own object all satisfy it, and a consumer cannot tell which it holds ([design](../design/record.md)).

```python
record.schema  # what may exist: the axes, the properties, the attributes
record.dims["entity"]  # axis labels, keyed by dim
record.properties["entity"]  # stored property values, keyed by dim or group
record.groups["connection"]  # group rows, keyed by group — one frame each
record.attributes["p_max_pu"]  # long input frames, keyed by attribute
record.outputs["p"]  # long result frames, keyed by attribute
record.flags(entity_type="Generator")  # which axes each attribute actually uses
```

Every frame is a `narwhals.LazyFrame` — a plan, not data. Nothing is read until you `.collect()`, and listing the keys reads nothing at all ([design](../design/record.md#frames)).

```python
entities = record.properties["entity"]
gens = entities.filter(nw.col("entity_type") == "Generator").collect().to_pandas()
```

## Labels and properties

`dims[dim]` is the axis's key columns only — the labels, and a nested dim's parent keys — in axis order.

`properties[subject]` is a dim's or a group's key with every property declared for it, **as stored**: a NULL is a value no layer wrote.

One category's labels are `properties[dim]` filtered on a categorizing property — an `Enum` property of a `partial` dim. Which properties they carry is `Schema.properties_for(dim, **categories)`, and an unset one's default, `default_by` per category included, is `Schema.default_for(name, **categories)` ([design](../design/record.md#properties-and-categories)).

## Wide and long

`dims`, `properties` and `groups` are **wide** — one row per label or tuple. `attributes` and `outputs` are **long** — one row per value:

```text
<coordinate> ... | attribute | breakpoint | value
```

`attributes` holds **every** attribute, whatever its `dims` — `p_nom` over `entity` alone is long rows just like `p_max_pu`. The coordinates are the attribute's own — `entity` for `p_nom`, one `connection` struct column for a connection attribute like `efficiency`, and no entity column at all for one addressed by another axis alone ([design](../design/format.md#the-long-schema)).

A NULL dim column means "all values of that dim", not that the attribute lacks the axis: a constant `p_max_pu` is one row with `timestep = NULL`, a varying one is a row per timestep ([design](../design/record.md#the-broadcast-rule)). `entity` broadcasts like any dim; on a categorized dim a NULL reaches only the labels whose categories carry the attribute, so one `p_max_pu` row with `entity = NULL` reaches every generator and no bus. A group column broadcasts the same way, a NULL `connection` meaning every connection. `breakpoint` carries the abscissa of a piecewise-linear value.

`attributes` shows stored rows only: a coordinate no row covers takes the attribute's default, which `Schema.default_for(name, **categories)` answers per category.

No property is a column of an attribute row — `attributes["p_max_pu"]` holds every entity's rows together. To scope to one category, join `properties["entity"]`, filtered on the category, on `entity`.

## `flags`

`flags()` answers which axes each attribute's rows actually use, across the record in one query, so a consumer can plan its reads without opening a file. `flags(**categories)` answers for one category of one dim, counting only rows reaching a matching label and only attributes those labels carry:

```python
flags = record.flags(entity_type="Generator")
set(flags)  # which attributes generators have at all
"timestep" in flags["p_max_pu"].varies  # some row sets it
"timestep" in flags["p_max_pu"].broadcast  # some row leaves it NULL
flags["marginal_cost"].breakpoints  # some row carries a curve
```

The two sets are **not** complements: a dim in both means the labels disagree — some carry a per-timestep series, others a single constant row — which is the instruction to use both containers, not an ambiguity ([design](../design/record.md#flags)).

## Reading a directory

A parquet directory is a record. Nothing about layers is involved:

```python
from datarecord import Workspace

ws = Workspace()
record = ws.at("s3://bucket/my-record/")
record.attributes["p_nom"].collect()
```

The layout is the whole format ([design](../design/format.md)):

```text
record/
├── manifest.json            # the schema, and the record's id
├── dims/<dim>.parquet       # one axis per declared dim: labels and their properties
├── groups/<group>.parquet   # which tuples of the group exist, and their properties
├── inputs/<attr>.parquet    # one input attribute per file, whatever its dims
└── outputs/<attr>.parquet   # one result attribute per file
```

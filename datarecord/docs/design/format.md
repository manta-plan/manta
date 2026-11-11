<!--
SPDX-FileCopyrightText: datarecord contributors

SPDX-License-Identifier: CC-BY-4.0
-->

# The record format

A record's **on-disk form** is a parquet directory: [a write](writing.md) produces it, `Workspace.at(uri)` reads it, and a foreign tool can consume it knowing nothing about this package.
A record that is never written has no directory, and answers [the protocol](record.md) all the same.

```text
record/
├── manifest.json                   # the schema, and the record's id
├── dims/<dim>.parquet              # one axis table per declared dim: labels and properties
├── groups/<group>.parquet          # which tuples of the group exist, and their properties
├── inputs/<attr>.parquet           # one input attribute per file
└── outputs/<attr>.parquet          # one result attribute per file
```

Every file under `dims/` and `groups/` is named for what it holds, singular: `dims/scenario.parquet` for the `scenario` axis, as `inputs/p_nom.parquet` is for `p_nom`.
A dim's file is its name and nothing else — no pluralisation, which would be English grammar applied to a declared identifier and would spell a dim named `bus` as `buss.parquet`.

## The entity axis

`dims/entity.parquet` is what an entity's identity **is**: which entities the layer names, what describes each, and which are tombstoned.

```text
entity | <entity key dims> | deleted | <property> ...
```

It is **an axis file like any other**, with nothing about it particular to `entity`: a `Record` hands it over as `dims["entity"]`, [the writer](writing.md) writes it, and every other `dims/<dim>.parquet` has the same shape.

- **Membership.** An entity exists because it has a row here.
- **Its tombstone.** Deleting an entity is a `deleted` row here, and the fold reads its tombstones from the file it folds membership from: membership from one source and deletions from another would resolve a deletion the fold never saw.
- **Its properties**, one column each — `entity_type`, `carrier`, `sign` in PyPSA's schema — NULL on a row whose [categories](schema.md#categories-an-enum-property-of-a-partial-dim) do not carry it.

**One layout, categories or none.** A record whose entities have categories and one whose entities have none differ by a column: there is no per-category member file. Per-type files existed because every type had a different column set; the schema now says which properties each category carries (`properties_for`), so a category's frame is a filter on its property and a projection to those columns — recoverable from one file, where per-category files would state each entity's category twice, once in a column and once in a filename. Parquet stores an all-NULL column chunk for almost nothing and DuckDB reads only what it projects. Only a per-category `dtype` would need per-category files, and [one name has one spec](schema.md#properties).

## Where a value lives

Decided by the section a name is [declared in](schema.md#properties), not by how many coordinates address it:

| declared as           | lands in                                              |
| --------------------- | ----------------------------------------------------- |
| property of a dim     | `dims/<dim>.parquet` — a column of the axis file      |
| property of a group   | `groups/<group>.parquet` — a column of the group file |
| attribute, any `dims` | `inputs/<attr>.parquet` — long rows                   |
| result, any `dims`    | `outputs/<attr>.parquet` — long rows                  |

`inputs/p_nom.parquet` is `entity | attribute | breakpoint | value`, one row per entity, and widening `p_nom` over `scenario` adds a column to the same file — NULL in every row written before, which is what [the broadcast rule](record.md#the-broadcast-rule) needs to read them unchanged. A scenario `weight` over `scenario` alone is long rows too: an attribute with one coordinate is still data.

An axis or group file then carries only its key, its `within` keys, its tombstones and its subject's properties — no data. A framework's constant frame per category is the category's properties joined with the coordinate-only rows of its attributes; the [tool](tools.md) builds it.

A [group](schema.md#groups)'s rows are in `groups/<group>.parquet`, keyed by that group's tuple and carrying their own tombstones — `groups/connection.parquet` for the `connection` group over `(entity, bus)`.
**The file is keyed by one struct column named for the group**, `connection STRUCT(entity, bus) | role | deleted`, `role` being a property of `connection`, exactly as `dims/<dim>.parquet` is keyed by the column named for the dim: the column an attribute row carries the group as is the one the group's own file is keyed by, so no read or write converts between two shapes.
A record with no such file has no rows of that group.

**One file per group, never split by category.** A group's rows are keyed by its coordinates and `entity_type` is not one of them: splitting put `connection` rows for a `Link` and a `Line` in different files despite identical keys, forcing a union on every read and privileging `entity` among the coordinates. A `corridor` between two buses has no type to split on at all, and a `contract` between two entities has two — one per coordinate, neither of them the row's — so the split never generalised beyond the case it was written for.

A functional group's [`into`](schema.md#into-a-group-that-classifies) label is a plain column of the group's file beside the key, so `groups/bus_country.parquet` is `bus_country STRUCT(bus) | country`. No column on the classified axis: `dims/bus.parquet` does not gain a `country`, the relation being the group's own file. That costs a join where a column read would have done, and buys a uniform rule — `into` decides nothing about storage, so nothing in the layout branches on it.

## The long schema

Every `inputs/` and `outputs/` file carries its attribute's own coordinates, then the columns every row has:

```text
<coordinate> ... | attribute | breakpoint | value
```

The coordinates are what the attribute's [`dims`](schema.md#attributespec) declare, groups first, with a [group](schema.md#groups) carried as **one struct column named for it**, a field per key coordinate — so `inputs/efficiency.parquet` over the `connection` group carries `connection STRUCT(entity, bus)`, and `inputs/p_max_pu.parquet` over `entity` and `snapshot` carries `entity | snapshot` and no `bus`.
The writer rejects a group column that is not a struct of exactly the group's key: DuckDB casts a struct by field name, so a missing field would turn NULL and an extra one be dropped, silently re-keying every row.

**Per attribute rather than schema-wide.** One attribute is one file, so one column set per file; a fixed prefix of `entity | bus` would put an all-NULL `entity` on a record-level weighting, claiming an entity the value has none of, and would privilege one group's spelling of `bus` over every other group's coordinates.

That the shapes differ costs nothing, because `UNION ALL BY NAME` supplies NULL for a column a file does not carry — which is also what lets a file written before a dim was declared still read back correctly ([resolving a relation](read-path.md#resolving-a-relation)).
The fold's _key_ is uniform even though the files are not: it is [`partial_dims`](schema.md#partial-the-granularity-of-an-override) plus `attribute`, one fixed tuple over every attribute, and a coordinate an attribute does not carry reads as NULL there.

One attribute per file, so `value` carries that attribute's dtype.
There is **no category column**: `entity` is unique across every category ([below](#entity-is-unique-across-types)), so `inputs/p_max_pu.parquet` holds every type's `p_max_pu` keyed by entity alone, and a reader wanting one type's rows joins the entity axis.

## `entity` is unique across types

A label identifies one member of its dim across the whole record — an `entity` one entity, whatever its categories.
A `Bus` and a `Generator` both called `north` are a collision, not two entities.

That is what removes `entity_type` from every attribute key.
An `inputs/` row addresses `(entity, …, attribute)`, a group in place of `entity` where the attribute is over one, and the category it belongs to is recoverable but not part of the address.
The alternative — carrying the category in the key — makes it an _entity's_ identity in one place and a _row's_ in another, and every join then has to agree about which.

**The axis carries the categories.** `entity_type` is a column of `dims/entity.parquet`, carried on its resolved row, never of the attribute rows — so `entity -> entity_type` is one read of one file, and a consumer wanting one type's `p_max_pu` joins the resolved attribute frame to the resolved entity axis on `entity`.
That join is against a relation the read path already builds.

Two things follow, and they are the reason to want this.
An attribute row is addressed the way an entity is, so `set("p_nom", 150.0, entity="wind1")` needs no category: the entity determines it ([set](working-record.md#set)).
And the inputs key carries no category, so the fold's key is `(*partial dims and groups, attribute)` — one less column to compare NULL-safely in every join in [the read path](read-path.md).

**Structural, not checked.** One axis row per label is the uniqueness: an entity's categories are columns of its one row, so there is no second table for a name to recur in, and `add` of a label already there restates its row ([add / remove](working-record.md#add-remove)).

A modelling framework that scopes names per type must therefore reconcile before it writes.
Its [tool's `verify`](tools.md) is where that is reported, rather than something the record layer mangles a name to paper over: a record's `entity` is the framework's own name, and a record that renamed them would hand back entities a framework cannot find.

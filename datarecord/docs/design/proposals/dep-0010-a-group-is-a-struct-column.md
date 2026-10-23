<!--
SPDX-FileCopyrightText: datarecord contributors

SPDX-License-Identifier: CC-BY-4.0
-->

# DEP 10: a group is one struct column

| DEP     | 10                                                                          |
| ------- | --------------------------------------------------------------------------- |
| Title   | a group is one struct column                                                |
| Author  | Jonas Hörsch                                                                |
| Status  | Implemented 2026-10-12, [amendment](#amendment-a-group-is-a-dim) 2026-10-13 |
| Created | 2026-10-12                                                                  |
| Version | Unreleased                                                                  |

Landed in the [steps below](#landing) on [the schema](../schema.md#groups), [the record](../record.md#the-broadcast-rule), [the format](../format.md#the-long-schema), [the read path](../read-path.md#owner-map), [the working record](../working-record.md#set) and [consuming a record](../tools.md#results-on-connections); this page is kept as the argument for the change rather than as the current description, and those pages are authoritative where the two disagree.
[What the implementation found](#what-the-implementation-found) records where it departs from or adds to the argument below.

An attribute over a [group](../schema.md#groups) carries the group as **one column, named for the group, of a `STRUCT` dtype over the group's key** — `connection STRUCT(entity, bus)` — rather than the group's coordinates spread out as columns of their own.

That gives back broadcasting to every dim a group draws on, and makes the [owner map](../read-path.md#owner-map) key one column per membership, so a group shows up there as itself.

## What starts it

[Addressing](../schema.md#addressing-dims-x) expands a group in `dims` to its coordinates, so `inputs/efficiency.parquet` is `entity | bus | timestep | …` and the fold key is the flat union of every group's coordinate names ([`partial_dims`](../schema.md#partial-the-granularity-of-an-override)).
A column in the fold key is either broadcast or membership, never both, and a group coordinate [never broadcasts](../record.md#the-broadcast-rule).
So `Schema.broadcast_dims` drops every coordinate any group is keyed by, **schema-wide**:

```python
sparse = {c for g in self.groups.values() for c in g.key}
```

The cost lands on attributes that have nothing to do with the group.
Declaring `connection` over `(entity, bus)` means no attribute anywhere may hold a value once for every bus: a per-bus `marginal_price` over `{bus, timestep}` reads a NULL `bus` as "no bus", not "every bus".
Declaring `bus_country` over `bus` into `country` — a classification, which addresses no attribute row at all — does the same.
The broadcast rule is right that _a connection's_ `bus` has no axis to expand against; it is wrong that _the dim_ `bus` therefore has none.
The two are one column today only because the group was flattened into the dim's name.

The owner map pays the same flattening in legibility.
Its key is `entity | bus | from | to | <partial dims>`, and which of those columns together name a connection, a corridor or nothing is recoverable only from the schema.
A group's tombstones are a multi-column anti-join over coordinates that other groups and plain dims share names with.

## The construct

**An attribute row carries a group as one struct column named for the group**, with one field per [key](../schema.md#into-a-group-that-classifies) coordinate, in `over` order:

```text
inputs/efficiency.parquet   connection STRUCT(entity, bus) | timestep | attribute | breakpoint | value
inputs/flow.parquet         corridor STRUCT("from", "to")  | timestep | attribute | breakpoint | value
inputs/marginal_price       bus | timestep | attribute | breakpoint | value
```

`coordinates_of("efficiency")` is `("connection", "timestep")`: [addressing](../schema.md#addressing-dims-x) still resolves a name in `dims` to the dim of that name first and to the group otherwise, but a group resolves to itself rather than expanding.

**The membership keys are `entity` and one column per group**, and every declared dim but `entity` and the type axis broadcasts.
`broadcast_dims` loses its `sparse` exclusion; `bus` broadcasts like `scenario`.
The fold key stays [one fixed tuple](../schema.md#partial-the-granularity-of-an-override), its columns now `entity | connection | corridor | <partial value dims>`.

**A group column does not broadcast**, for the reason the broadcast rule already gives: it addresses a sparse subset only the group's table knows.
It is compared NULL-safely as one value, which DuckDB hash-joins on directly — checked on 1.5.5, `k IS NOT DISTINCT FROM k` over a `STRUCT` key plans a `HASH_JOIN`, and a NULL field compares equal to a NULL field.
So [resolving a relation](../read-path.md#resolving-a-relation) joins `o.connection IS NOT DISTINCT FROM u.connection` where it joined `entity` and `bus` separately, and the address columns still derive from the schema.

**A group does not share a dim's name.** A group is carried as a column named for it, so `country` into `country` would make two columns one name; the functional group is `bus_country`, and only the entity-type group, which has no file or column of its own, may share its dim's name.

**A group file is keyed by its struct column**: `groups/connection.parquet` is `connection STRUCT(entity, bus) | role`, folded [like any axis](../read-path.md#one-fold-for-every-axis) keyed by that one column, exactly as `dims/<dim>.parquet` is keyed by the column named for the dim — so a row and its group meet on one column with nothing packed between them.

## The owner map

```text
# inputs
entity        -- never NULL where the attribute addresses an entity
connection    STRUCT(entity, bus)
corridor      STRUCT("from", "to")
<partial value dims>
attribute
layer_uuid
varies        STRUCT(<broadcast dim>: BOOLEAN, ...)   -- now with a `bus` field
broadcast     STRUCT(<broadcast dim>: BOOLEAN, ...)
breakpoints   BOOLEAN
```

**Only the groups a long input row can carry are keyed.** A group column belongs in the map where some attribute in `attributes` names the group beside another coordinate, so that it is long rows in `inputs/` — `efficiency` over `{connection, timestep}`.
Every other group would be a column NULL on every row of the map, widening the key every read pays for to identify nothing:

- the entity-type group, whose rows are the entity axis and which no attribute names beside `entity`;
- a group addressed only alone, whose attributes are [columns of its own file](../format.md#where-a-value-lives) — `role` on `connection`, were it the only one;
- a group only results name, `outputs/` [never overlaying](../read-path.md#outputs);
- a group nothing names.

So the map's membership columns are `entity` and `Schema.group_columns`, derived like `partial_dims` rather than declared.
Adding an attribute stays [compatible](../schema.md#versioning) though it may add a group to the key: a map folded before has no such column, which is correct — no row there names the group — so a reader takes a missing group column as NULL, as it takes a missing [flag field](../read-path.md#one-fold-for-every-axis) as unset.

Each membership is one column, so reading the map needs no schema to say which columns belong together.
A group's tombstones are a single-column NULL-safe anti-join, the same shape as the entity axis's; the [no-cascade rule](../read-path.md#owner-map) is unchanged.
The flag structs gain a field for each dim that now broadcasts, so `flags` reports a constant-over-buses `marginal_price` as broadcast over `bus` rather than not at all.

## What changes for a caller

`Record.attributes["efficiency"]` hands back a `connection` struct column; a consumer wanting flat columns takes `nw.col("connection").struct.field("bus")`, or unnests.
The [PyPSA tool](../tools.md) does that once, where it reads and builds connections.

`WorkingRecord.set` keeps [coordinate keywords](../working-record.md#set): `bus="north"` addresses one connection and the stage packs `{entity, bus}`.
A long frame handed to `set` may carry either the struct column or its coordinates flat; the coordinates are packed on the way in, so the frame a tool already builds keeps working.

## What it costs

- **An on-disk format change.** Every `inputs/` and `outputs/` file over a group is rewritten, and materialised owner maps are rebuilt. The project is pre-1.0 and holds no compatibility promise; no reader for the flat form survives.
- **Struct support at the boundary.** narwhals' `struct.field` works on DuckDB, polars and pyarrow-backed frames; a numpy-backed pandas frame has no struct dtype, so a pandas consumer unnests on the DuckDB side first.
- **A filter by entity on a connection attribute** becomes `connection.entity = 'g1'`. That costs nothing measurable: DuckDB 1.5.5 pushes a struct-field filter into the parquet scan and skips row groups on the field's statistics as it does for a top-level column — over 2M rows in 20 row groups, `conn.entity = …` and `entity = …` both read one row group (2.0 ms and 1.8 ms), and a field value outside every range skips all of them.

## One behaviour that must not move

Today a connection attribute row carries a top-level `entity`, so [the fold](../read-path.md#owner-map) drops it when the entity is tombstoned even though the connection tuple survives.
Under the struct it has no top-level `entity`, so the entity tombstone matches every entity a row names instead — `entity`, and each entity inside the group's struct.
Removing an entity still drops its connections' values and leaves the tuples, which is the no-cascade rule as it stands: the tuples are a membership of their own, the values belong to the entity.

## A rule it adds

An attribute naming a group and a dim one of its key coordinates is named for — `dims={"connection", "bus"}` — is rejected: the row would hold the bus twice, free to disagree.
It is unexpressible today only because the two land on one column; the struct makes it expressible, so the schema says so instead.
It is the same "keyed twice over" rule [`into`](../schema.md#into-a-group-that-classifies) already states.

## Landing

1. `Schema`: `coordinates_of` resolves a group to itself; `broadcast_dims` drops `sparse`; `membership_keys` gains the group columns; the rule above.
2. The fold and the read path: owner-map key and the group tombstone anti-join on the struct column; the resolve join on it.
3. Staging: pack coordinate keywords and flat frame columns into the struct.
4. The PyPSA tool packs on `to_datarecord` and unpacks on `build`.
5. [Schema](../schema.md#groups), [record](../record.md#the-broadcast-rule), [format](../format.md#the-long-schema) and [read-path](../read-path.md#owner-map) pages rewritten; this page marked landed.

## What the implementation found

- **Per-bus patching needs `bus` in `partial`.** `bus` is no membership key any more, so a layer patching a per-bus `marginal_price` one bus at a time declares it [`partial`](../schema.md#partial-the-granularity-of-an-override) like any value dim; a connection's bus is patched per row regardless, inside `connection`.
- **A value staged without `bus=` matches no connection.** It is stored keyed `{entity, NULL}`, and a NULL field compares equal only to a NULL field. The "every connection of this entity" reading the pages gave was never implemented; it is left [open](../open-questions.md).
- **The entity tombstone reaches the entity inside the struct.** The fold matches it on every entity a row names — `entity`, and each key coordinate over `entity` of a keyed group — so removing an entity drops its connections' values as before, the tuples standing until removed in turn. A first cut had `remove` tombstone every tuple naming the entity instead, which left a re-added entity without its parent's connections.
- **A layer's own tombstones apply only to its parents.** So the staged collapse drops its own rows itself: `remove_group` also drops the rows it staged on the tuple, as `remove` does on the entity.
- **A long frame handed to `set` carries the struct only.** Accepting its coordinates flat as well cost a second packing path and a both-forms rejection for no caller that needed it: the PyPSA tool packs once, where it builds its frames.
- **An empty frame must still type the group column as the struct.** A source emitting no rows for an attribute hands over a typed empty relation, or the writer rejects a column that is not a struct of the group's key.
- **Shadowing went.** A group sharing a dim's name was resolved to the dim, which every place that tells a group column from a dim had to repeat. Once a group is a column named for itself, the collision is two columns under one name, so the schema rejects it; only the entity-type group, which never becomes a column, keeps its dim's name.
- **A flat group file cost a conversion wherever a row met it.** The fold's group tombstones, the staged collapse, `remove_group` and `add` each packed the file's coordinates into the struct. Keying `groups/<group>.parquet` by its struct column, as an axis file is keyed by its dim, removed every one; packing survives only where a caller hands flat values in — `set`'s coordinate keywords, `remove_group`'s tuples, `add`'s wide frame — and in the PyPSA tool, whose network is flat.
- **PyPSA's `bus` was an attribute and a coordinate at once.** The tool declared the port stem `bus` as an attribute over `connection`, which in a flat file was the same column as the coordinate. Under the struct it would be a second column beside the key, so the tool declares no such attribute: a port's bus is the connection tuple, and a component with no connection row lacks it whatever default PyPSA registers.

## Amendment: a group is a dim

Status: **Implemented** · Drafted 2026-10-13 · Implemented 2026-10-13

As for the proposal above, the [schema](../schema.md#groups), [record](../record.md#the-broadcast-rule), [read-path](../read-path.md#owner-map) and [working-record](../working-record.md#set) pages are authoritative; [what the implementation found](#what-the-amendment-found) records where it departs.

Once a group is one column, the reasons it stayed a membership key, apart from the dims, are gone.
**A group is a dim whose axis is the resolved group**: `groups/<group>.parquet`, keyed by the column named for the group, as `dims/<dim>.parquet` is.
It broadcasts, enters the owner map only where `partial` names it, and is owned whole otherwise — the rules `snapshot` follows, unchanged.

### A group value is a whole tuple or NULL

A struct is either complete or NULL as a whole; `{entity: dc, bus: NULL}` is no value.
A NULL struct means every tuple of the group, by [the broadcast rule](../record.md#the-broadcast-rule), expanded against the resolved group as a NULL dim is against its axis.
A partly NULL struct is refused wherever a row comes in — `set`'s keywords and frames, `add_group`, and the writer — since it would name a tuple no group row matches.
This replaces "a group column does not broadcast" [above](#the-construct), whose reason was that only the group's table knows its tuples; the fold has that table already (`Coords.groups`).

### The owner map

The membership key is `entity` alone, and a group is keyed exactly where a dim is: in `partial_dims` if `partial` names it, absent otherwise.

```text
# inputs
entity        -- NULL on a row over a group, which names its entities inside it
<partial dims, groups among them>
attribute
layer_uuid
varies        STRUCT(<broadcast coordinate>: BOOLEAN, ...)   -- a field per group too
broadcast     STRUCT(<broadcast coordinate>: BOOLEAN, ...)
breakpoints   BOOLEAN
```

[Only the groups a long input row can carry are keyed](#the-owner-map) goes, and `Schema.group_columns` with it: which coordinates key the map is `partial`'s to say, for a group as for a dim.

**Not `partial`, a layer writes the attribute's whole extent along the group.**
A connection attribute carries no top-level `entity`, so its key is `(attribute)`, and a layer touching `{steel_dri, h2_north}` owns every connection's value — the granularity an attribute over `{snapshot}` alone, a weighting, has today.
Staging carries the rest of the extent, as it does for a non-`partial` dim (`_complete_owned_whole`); a layer written directly has to hold it.
Pulling the struct's entity fields out into the key would narrow that to one entity's connections, at the price of the map reaching into struct fields; not worth it, since `partial` gives the finer grain where a tool wants it.

**`partial`, a layer patches one tuple.**
The group is in the key, a NULL struct expands against the resolved group in the fold, and a group tombstone anti-joins the parent on it, as a partial dim's does on its axis.
The PyPSA tool declares `connection` partial: `Link.efficiency` may vary over `snapshot`, and restating every link's series to patch one is the cost `partial` exists to avoid.

### What it costs

- **`flags(ctype)` cannot scope a non-`partial` group attribute.** Its map rows name no entity, so no type claims them — the position an axis-only attribute is in today, and the [record-level flags question](../open-questions.md) widens from a corner to every such attribute. With `connection` partial, PyPSA's are unaffected.
- **An owner-map format change**, materialised maps rebuilt; pre-1.0, no reader for the old key survives.
- **The default grain coarsens.** A schema that relied on per-connection ownership without saying so now says `partial={"connection"}`.

### What it saves

The struct change left `src/` about 340 lines larger than the flat layout it replaced, most of it in packing, validation and the PyPSA tool's conversion, which this does not touch.
What goes is the group's separate path through the key:

| goes                                                                                                             | comes                                                                  |
| ---------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| `group_columns`, and the derivation of which groups are keyed                                                    | `broadcast_dims` naming groups, the entity-type group excepted         |
| group columns as a second key family in `membership_keys`, `long_columns`, `fold_inputs`' padding and projection | `expand_dims` taking a group's relation where it takes an axis         |
| the group-tombstone membership in `fold_inputs`, separate from the partial dims'                                 | a partial coordinate's tombstone reading `source.group(g)` for a group |
| the docs' account of which groups are keyed and why                                                              | the whole-or-NULL check at the three entry points                      |

It was estimated at 40–80 lines net out of `src/`.
**Measured, it saved none: `src/` grew by 19 lines net** (119 added, 100 removed).
The derivation of keyed groups and `membership_keys` went as planned, and three things the estimate did not foresee added back as much — [the read-time entity filter, the attribute-scoped expansion](#what-the-amendment-found) and the whole-or-NULL check against data rather than dtypes.
The "which groups are keyed" sections of the design pages went.
The gain is one rule where there were two: everything said of a dim — broadcast, `partial`, owned whole, flags — is said of a group, with the group's file as its axis.

### Landing

1. `Schema`: groups among the broadcast coordinates; `membership_keys` is `entity`; `partial` may name a group; `group_columns` goes.
2. The fold: `expand_dims` over a group's relation; a partial group's tombstone; the flags gain a field per group.
3. The whole-or-NULL check in staging and the writer; `set` stages a NULL struct where no coordinate is given.
4. The PyPSA tool declares `connection` partial.
5. [Schema](../schema.md#groups), [record](../record.md#the-broadcast-rule), [read-path](../read-path.md#owner-map) and [working-record](../working-record.md#set) pages; the open question widened.

### What the amendment found

- **A NULL is expanded only for the attributes over its coordinate.** The fold key is one tuple over every attribute, so an attribute not over `connection` holds NULL there for want of the column; expanding every NULL multiplied its rows by the group's size. `expand_dims` now broadcasts a NULL only on rows whose attribute's coordinates include it, for a plain dim as for a group.
- **Removing an entity needs a filter at read.** With `connection` outside `partial`, a connection attribute's map row names no entity, so the fold's entity anti-join cannot reach it. The read drops a row naming, in an unkeyed group's entity field, an entity the resolved axis no longer holds (since [deletion cascades through tombstones](dep-0011-deletion-cascades-through-tombstones.md), against the group's dead tuples: [a label outside the key](../read-path.md#a-label-outside-the-key)) — so removing an entity still drops its connections' values.
- **A NULL struct crosses entity types.** It expands to every tuple of the group, and `connection` spans every type, so a constant meant for links reaches buses' connections too. Left [open](../open-questions.md).
- **`group_columns` stayed, with a smaller meaning**: every group but the entity-type group, the coordinates `broadcast_dims` appends. What went is the derivation of which groups are keyed.
- **`set`'s keywords stage no NULL struct**, unlike landing step 3 planned. A missing key coordinate is still refused rather than staged as NULL, as [`set`](../working-record.md#set) already did; a NULL struct comes in through a long frame.
- **It grew `src/` by 19 lines net** rather than shrinking it by 40–80: the read-time filter, the attribute-scoped expansion and the whole-or-NULL check, which reads data where the struct check read only dtypes, cost what the removed derivation saved ([what it saves](#what-it-saves)).

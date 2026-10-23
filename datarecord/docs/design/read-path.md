<!--
SPDX-FileCopyrightText: datarecord contributors

SPDX-License-Identifier: CC-BY-4.0
-->

# The DuckDB read path

## Owner map

The owner map answers, for a node, which layer owns each key.
**One map: `inputs`.** It is the only relation whose winning _key_ and winning row's _values_ live in different files — an attribute's ownership spans every `inputs/<attr>.parquet`, so the map names the owning layer per key and a read then goes to that layer's file for the value.
Every axis — a [dim](schema.md#partial-the-granularity-of-an-override)'s coordinates, the entity axis among them, and a [group](schema.md#groups) — is a single keyed file whose winning row _is_ the whole row, so none needs a map; each folds to a [resolved relation](#one-fold-for-every-axis) read inline.

The inputs map's columns, keys first:

```text
# inputs
<partial dims>          -- the fold key: exactly the partial dims and groups
  <owned_per coordinates> -- e.g. entity, scenario; a partial group as one STRUCT: connection STRUCT(entity, bus)
attribute
layer_uuid              -- the owning layer
varies      STRUCT(<coordinate>: BOOLEAN, ...)   -- a field per broadcast dim and group
broadcast   STRUCT(<coordinate>: BOOLEAN, ...)
breakpoints BOOLEAN
```

It maps each key to the owning `layer_uuid`, with deletions already applied.
It carries no `value`, no varying dim's value, and no `breakpoint`, so it stays small regardless of the series data or the size of a curve.

The **inputs key is schema-derived**, not spelled: it is [`partial_dims`](schema.md#partial-the-granularity-of-an-override) plus `attribute`.
`partial_dims` is exactly the broadcast coordinates — dims and groups alike — a layer may patch per value (`partial`); no dim is in it by name, `entity` included.
A coordinate an attribute's own file does not carry reads as NULL, which is what keeps the key one fixed tuple across attributes whose columns differ.
A group is one column, so which columns name a connection is legible from the map itself, with no schema to say which belong together.

**A group outside `partial` is not in the key**, as a dim outside it is not: a layer touching one connection's value owns the attribute's whole extent along the group.
An attribute over such a group and no other `partial` coordinate has the key `(attribute)` alone, the grain of a record-level weighting.

No category is on `inputs`: an attribute row is addressed by `entity` alone ([entity is unique across types](format.md#entity-is-unique-across-types)), and the resolved entity axis is what says which categories an entity has.
That axis is what every category-scoped question goes through — [per-category `flags`](record.md#flags) join it, as does a consumer wanting one type's frame — and it carries each [categorizing property](schema.md#categories-an-enum-property-of-a-partial-dim) as a column, functionally determined by the label rather than keyed alongside it, so a re-categorized label is one row with a new value.

The map is built by folding along the root→node path: parent map minus deletions and overrides, union the layer's own keys.
A node whose caches are [materialised](layers.md#materialised-node-caches) persists it (and the resolved axes beside it), so a read needs only the ancestry **back to the nearest materialised node** — the key scalability property.
Every key column's tombstones reach this map in the fold: `fold_inputs` anti-joins the parent against the deleted rows of each partial dim and group — read from the same file that axis or group folds from — so a key whose entity, connection tuple or dim coordinate was deleted is absent from the resolved map rather than filtered at read.
A group's tombstones are one NULL-safe anti-join on its struct column, the group file's own key — the same shape as a dim's.
A layer's tombstones apply to its parents' keys, not to its own rows.
A dim's anti-join matches its top-level column only. A label inside a struct is reached through its tuple: [removing a label](layers.md#deletion) tombstones the live tuples naming it in the same layer, and each group honours its _own_ tombstones.
A row leaving a key column NULL is not addressed by it, and its NULL-safe anti-join never takes it; only a row naming a dead entity, tuple or label is dropped.

**On a categorized dim a NULL reaches the labels carrying the attribute.** Where the fold expands a NULL against the axis, an attribute some trait narrows on that dim joins a carriers relation — `(label, attribute)`, built through [`attributes_for`](schema.md#traits) once per category combination the resolved axis holds — so `set("p_max_pu", 0.9)` reaches every generator and never a bus; a label with a NULL category carries none of the narrowed attributes. An attribute no trait narrows expands over every label, as before. A materialised ancestor's map is seeded already expanded, so its NULL rows do not reach labels a descendant adds or re-categorizes ([open](open-questions.md)).

## One fold for every axis

A dim's coordinates, the entity axis, and a group are one construct: a keyed relation a layer patches per key — a group's key being its one struct column, as a dim's is the column named for it.
They fold by one path — last-writer-wins per key, [`deleted` honoured](layers.md#deletion), its other columns carried on the winning row (`entity_type` on the entity axis, `role` and `into` on a group) — producing one **resolved relation** with no `deleted` column and no `layer_uuid`.

The resolved relation is returned **in first-introduced member order** — root first, then file order within a layer — and a node's caches persist it _in that order_, so a reader recovers member order from the resolved file's own row number.
There is no persisted `order_key` column: member order is the file's row order.
A consumer wanting positional ports numbers an entity's connections by this order, so a patch layer adding a connection appends rather than renumbering — the [positional-keying failure](record.md#connections) that order exists to prevent.
Across a materialised parent it still holds: the resolved seed is read in its own row order and a descendant's new rows number after it.

Every property is a column of its subject's file, so the resolved axis or group is the whole of what a per-category read needs: `properties[dim]` filtered on categorizing columns and projected to `properties_for`, with no second file to gate against.

The fold runs live over an unmaterialised tail, cached in the workspace's database as [shared tables](#a-cursor-per-thread); since [layers are write-once](layers.md#a-layers-data-is-write-once), such a cache never needs invalidating.

The [flags](record.md#flags) are folded in alongside the ownership group-by, so they cost nothing beyond it.
They are computed **per key**, so per entity: whether _this_ entity's `p_max_pu` sets `timestep` is a different question from whether any does.

The structs have a field per **broadcast** coordinate: every declared dim, `entity` included, and every group.
A group broadcasts and has its field, as does a dim a group draws on, so a constant-over-buses `marginal_price` reports `bus` as broadcast.

Two **structs** rather than a `varies_<dim>` column per dim, because which dims exist is [declared](schema.md#dimensions) and a flat layout would make the map's _column set_ depend on the schema.
[Versioning](schema.md#versioning) calls adding a dim compatible; that has to hold for a map already persisted at a [materialised node](layers.md#materialised-node-caches), not only for the layers.
With a struct the difference is a missing _field_, which `UNION ALL BY NAME` fills with NULL exactly as it would a missing column, and the new dim reads as unset — which it is, since no row mentions it.
The map's columns are then fixed, and only the fields move.

`breakpoints` stays outside both structs, being no dim ([wide and long rows](record.md#wide-and-long-rows)).
That also means the dim namespace lives entirely inside `varies`/`broadcast`, so a dim named `breakpoints` would collide with nothing.

`Record.flags()` unions them over the record, and `flags(**categories)` over the labels of those categories, restricted to what they carry — [the granularity a consumer works at](record.md#flags), where what the union means is argued.

## Resolving a relation

A resolved relation joins the owning layers' files to the `inputs` map, keeping only owned rows:

```sql
SELECT u.timestep,
       COALESCE(u.scenario, o.__owned_scenario) AS scenario,   -- one per owned_per coordinate, entity likewise
       u.attribute, u.breakpoint, u.value
FROM ( -- one arm per distinct layer the map names for this attribute
  SELECT ?::UUID AS layer_uuid, * FROM read_parquet(<layer>/inputs/<attr>.parquet)
  UNION ALL BY NAME
  ...
) u
JOIN ( -- the map keyed as its owning layer stored each key
  SELECT * EXCLUDE (scenario), scenario AS __owned_scenario,
         UNNEST(list_concat(
           CASE WHEN COALESCE(varies.scenario, false)   THEN [scenario] END,
           CASE WHEN COALESCE(broadcast.scenario, true) THEN [NULL] END
         )) AS scenario
  FROM inputs
) o
  ON o.attribute  = u.attribute
 AND o.layer_uuid = u.layer_uuid
 AND o.scenario   IS NOT DISTINCT FROM u.scenario  -- owned-per coordinates: as stored, NULL included
```

The projected coordinates are the **attribute's own**, not a fixed prefix: `connection` for a connection attribute, `corridor` for one over a corridor, `entity` for a per-entity one, none of them for a record-level weighting ([the long schema](format.md#the-long-schema)).
The join's arms follow from the same place — the key columns the attribute's file carries — so the query shape is derived from the schema rather than spelling `entity` and `connection` as literals, which is what lets a second group resolve through the identical code.
A coordinate outside the key, `timestep` here or a group outside `partial`, is in no arm and passes straight through.

The map already names the winning layer per key, so resolution reads only the owning layers' files.
There is no per-read `MAX`/group-by, and the only tombstone filter is for what the map cannot see — see [below](#a-label-outside-the-key).

Each owned-per coordinate's arm is **NULL-aware**: a stored NULL means "all values", and the map may own it for only some of them, so the row joins every entry naming its layer and takes that value in the output.
The arm cannot be the obvious condition: `u.scenario IS NULL OR u.scenario IS NOT DISTINCT FROM o.scenario` is no hash key, so DuckDB joins on the other columns and filters the dim afterwards, which costs the square of the dim's length per key.
So the map is keyed the way its owning layer stored each key, which its [flags](#owner-map) record: a map row keeps its value where the layer's row set the dim (`varies`) and holds NULL where the row left it NULL (`broadcast`), with the owned value carried beside it.
A layer row then finds its owned keys by its stored values, NULLs included, on NULL-safe equality — one hash join, scanning the layers and the map once each; the keyed map holds one row per owned key, two for a key its layer wrote both ways.
A map row NULL in the dim itself, broadcast over an empty axis, has `varies` false, so only its NULL form exists and it matches once.
A flag field missing from a map folded before the dim was declared counts as `broadcast` here, unlike in the flags a consumer reads: the layers' rows hold NULL there.

A **`partial` group column** like `connection` joins NULL-aware exactly as `scenario` does, [broadcasting](record.md#the-broadcast-rule) over the resolved group; DuckDB hash-joins `IS NOT DISTINCT FROM` on a `STRUCT` key directly.
A dim the group draws on, `bus` beside it on a per-bus attribute, is a broadcast dim of its own and joins NULL-aware where it is `partial`.

`breakpoint` is projected but not joined on, being no part of the key: a curve is owned whole ([wide and long rows](record.md#wide-and-long-rows)), so every breakpoint of a key comes from the winning layer.

Non-key dims pass through unchanged, because within one key-dim combination the rows come from one layer.

An attribute no layer wrote is absent from the map; its relation is empty, and the consumer applies [the schema's `default`](schema.md#attributespec).

### A label outside the key

Every coordinate in the key is [tombstone-pruned in the fold](#owner-map), so a row whose entity, partial connection tuple or partial dim label was deleted is already gone from the map.
A dim or group outside `partial` is not in the key, so the fold cannot see its labels: with `connection` owned whole, a connection attribute's map row is `(attribute)` alone, and owns every tuple's value.
The read drops those rows instead, anti-joining each such coordinate against its **dead labels** — those whose winning row in the fold is a tombstone, a group's being its dead tuples — so a removed tuple's values go whichever way the group is keyed.
The fold keeps them beside the resolved axes and groups, and a [materialised node](layers.md#materialised-node-caches) caches them, since its resolved relations hold no tombstones and a read above it would otherwise not see a label removed below.
The set is usually empty, and the join against it cheap.

## One record over one fold

There is one `Record`, and it is the narwhals interface over a [`Resolver`](#owner-map). A plain parquet directory is not a second implementation of it: `Workspace.at(uri)` folds over a single [`DirectorySource`](format.md), and over one source the fold degenerates to a scan of it — there is one layer, so every key is owned by it and the anti-join has nothing to evict.

So a directory takes the same properties as a tree node, rather than its own column of exceptions:

- **`flags`** are computed in the ownership `GROUP BY`, one scan rather than the second one a separate aggregate would cost. They need a real aggregate either way: parquet's footer statistics are per row group, not per category, so a file mixing one type's series rows with another's constant says nothing about either.
- **Member order** is `order_key`, which over one source is `(0, file order)` — file order, arrived at by the general rule.
- **`schema.partial`** is the granularity of a patch, and one layer patches nothing, so it is inert rather than absent.

Being a node in a layer tree is not what the fold requires; being a layer _layout_ is, and that is what a record directory is. A directory copied out of any tree, with no revision file, reads identically.

## A cursor per thread

A DuckDB connection is not safe to use from two threads at once. DuckDB's answer is a cursor per thread, so the workspace's `con` is **the calling thread's cursor** on its one database, made on first use in that thread by a `threading.local` subclass — which reruns its `__init__` in each new thread, so there is no existence check and no lock, and a thread's cursor is dropped with the thread. A dict keyed by thread id would reuse ids; a `ContextVar` is copied into a task runner's workers, which would share the parent's cursor.

Tables are shared between cursors — the `revisions` cache, the staging tables, the folded caches. A `DuckDBPyRelation` is not: it is bound to the cursor that built it. So the line runs around relations alone:

- **Nothing but a relation holds a cursor.** A store, a revision, a `Resolver` and a layer source hold their workspace and look up `workspace.con` per call, so every relation they build lands on the calling thread's cursor, and a `Record` is usable from any thread. What they cache besides is plain data any thread computes the same.
- **A relation, a narwhals frame over one, and a `WorkingRecord` belong to the thread that built them.** One reaching another thread's write path is rejected as [a relation from another connection](#a-relation-from-another-connection-is-rejected) is.

**What a fold caches is shared, not held.** The frozen prefix's folded axes and groups are tables, `dims_<dim>_<id>` and `group_<name>_<id>`, beside the `owner_map_<kind>_<id>` [owner map](#owner-map); a last `coords_<id>` table lists them and is created after them, so a reader finding it finds them all. A dim or group name is hashed into the table name, being a caller's string. `<id>` is the node whose frozen layers were folded: a revision's id, the base's for a `WorkingRecord`, the [id its manifest carries](schema.md#one-schema-per-record) for a standalone directory. The schema is not in the key, so a fold made before the manifest widened is read as it is under the wider one. A [compatible widening](schema.md#versioning) changes no column a table already has and only adds; the one addition a table can lack is the new dim's field in the [flag structs](#owner-map), and each reader of a flag takes a missing field as unset, decided from the struct's type when the query is built rather than per row. Nor are they cast to the declared types as a materialised map is: each holds what the same fold would return uncached.

A fold one thread builds serves every thread. Two threads missing at once both fold and both create, and DuckDB fails the second with a write-write conflict rather than a name clash; the miss path catches that and reads the winner's table. The duplicate fold is wasted, not wrong.

### A relation from another connection is rejected

Copying a relation onto the target connection would collect it on its own — a full materialisation the caller never asked for, which fails anyway if that connection has been closed. So `as_relation`, the boundary every frame handed to a write or an edit crosses, binds it to the target cursor first, which costs no read and fails for a relation from another connection or another thread's cursor, and re-raises that as a `ValueError` naming the fix: build the frame on `record.con` in this thread, or hand over a non-DuckDB frame to land.

## Outputs

`outputs/<attr>.parquet` does not overlay.
An output relation reads the node's own layer only: if that layer has no `outputs/`, the record has no results, and an ancestor's are not inherited.

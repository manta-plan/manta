<!--
SPDX-FileCopyrightText: datarecord contributors

SPDX-License-Identifier: CC-BY-4.0
-->

# DEP 1: dims, mappings, groups and traits

| DEP     | 1                                 |
| ------- | --------------------------------- |
| Title   | dims, mappings, groups and traits |
| Author  | Jonas Hörsch                      |
| Status  | Implemented 2026-08-16            |
| Created | 2026-08-15                        |
| Version | v0.1.0a1                          |

**This page is the argument, not the design.** What shipped is described by [the schema](../schema.md) — [groups](../schema.md#groups), [traits](../schema.md#traits) — together with [the record format](../format.md) and [the read path](../read-path.md), and those pages are authoritative where the two disagree.
The `on` mapping this page landed has since been [absorbed into groups as `into`](dep-0002-groups.md), so its half of the argument describes a construct that no longer exists.

It is kept because the reasoning is not reproduced there: why `keys` was deleted rather than replaced, why `bus` stopped being structural, and what the [worked example](#a-pypsa-network-in-full) exposed about vocabulary collisions.
Two things it raises stayed open and moved to [open questions](../open-questions.md): [whether existence may depend on a dim](#may-existence-depend-on-a-dim), and whether `flags(ctype)` needs a record-level counterpart.

Read below for why; read the design pages for what.

Two departures from the sketch below are worth naming, since the text still reads as though neither happened.
`shape()` was **not** implemented — `flags(ctype)` stands alone, and the gap it leaves is the open question above.
And `set` grew no `bus=` parameter: every coordinate but `entity` goes through `**dims`, which is what lets a two-coordinate group be addressed at all.

## What starts it

An attribute that belongs to no component type has nowhere to live.

Snapshot weightings are the case. A weighting is a number per snapshot — it varies over the time axis and over nothing else, and it is not a property of any generator, bus or line.
Today [`Schema.attributes`](../schema.md#attributespec) is `component type -> attribute -> spec`, so there is no key such a thing could be filed under.
It is carried instead as an extra column on the axis frame, undeclared: `dims/snapshots.parquet` gains an `objective` column, and the PyPSA tool's import half recognises it by name.

That works and it is invisible. The column has no `dtype`, no `default`, no `unit`, no `description`; it appears in no [`flags`](../record.md#flags); it does not resolve across layers; a reader that is not this tool cannot know it is an attribute at all.
The same holds for the scenario weightings the fold already carries alongside the `scenario` axis.

The narrow fix is a place to declare axis payload columns.
The wider observation is that `name` is not different in kind from `snapshot`: it is an axis, attribute values are addressed by it, and the reason it looks structural is that the schema is nested under it.
Once that is seen, several other things in the design turn out to be the same mechanism written three ways.

## The four mechanisms

|               | what it declares                                      | where it lives                                                                    |
| ------------- | ----------------------------------------------------- | --------------------------------------------------------------------------------- |
| **dimension** | an axis of labels                                     | `dims/<dim>.parquet` — labels and order, plus any attribute addressed by it alone |
| **mapping**   | each label of the dim I am `on` has one label of mine | a `Dimension` subclass; own axis file, plus a column on the classified dim's file |
| **group**     | which tuples over several dims exist                  | own table; subsumes connections                                                   |
| **trait**     | which entities an attribute applies to                | a subscription on the component type                                              |

`within` is unchanged and stays a fifth thing, distinct from mapping — see [mappings are not `within`](#mappings-are-not-within).

The unifying claim is that **`AttributeSpec.dims` becomes the only addressing mechanism**.
An attribute is addressed by the coordinates it declares; whether one of those is an entity axis, a group, a mapped classification or a plain axis changes where the labels come from, not how the attribute is declared or stored.

## `entity` — the component axis

`name` becomes a declared dim, called `entity`.
It gets an axis file like any other dim, and that file is what a component's identity is:

```text
dims/entity.parquet     entity | component_type | deleted
```

Four things move there, each of which is currently derived or enforced elsewhere:

**Uniqueness becomes structural.** One row per `entity` in one file, so the collision [name uniqueness](../format.md#entity-is-unique-across-types) rejects at two call sites cannot be represented.

**`entity -> component_type` is a column read.** Today it is "the file a name's row is in", so building the components map means globbing every type's file and injecting the type per arm.
The [owner map](../read-path.md#owner-map) already treats `component_type` as carried-not-keyed, functionally determined by the key — which is the shape of a payload column. This puts it where that shape says it belongs.

**Tombstones get one home.** Deleting a component is deleting its `entity` row, rather than a `deleted` flag globbed across per-type files.

**Order is generated, not stored.**
`order_key` is a column of [the owner map](../read-path.md#owner-map), never of a layer's parquet: the fold computes it as `max(parent) + row_number() OVER (ORDER BY _row)` per layer, from that file's own row order, and it persists only where a node's maps are [materialised](../layers.md#materialised-node-caches).
Assigned **before** the union, because `row_number()` over what `UNION ALL` emits has no defined order to recover.
Nothing sorts eagerly — a consumer wanting order applies `ORDER BY order_key`.

So `dims/entity.parquet` carries no order column, exactly as an axis file carries none: **file order is the input, `order_key` is the derived answer.**
That is one rule for every table that folds, rather than a components-and-connections special case — and it is why the entity axis needs no more on disk than an ordinary dim's, despite being the one axis whose order is a fold product rather than a single file's.

The test for the rest is **does this table gain rows across layers?**
A [group](#groups) does, and its map keeps `order_key` for the load-bearing reason the read path records: a framework reconstructing positional ports numbers them by this order, and a reshuffle silently moves an existing connection's attributes to a different port.
An ordinary dim does not — an axis is [not partial](../schema.md#partial-the-granularity-of-an-override), so a layer restating it restates it whole and file order survives untouched.

What remains in `dims/components/<Type>.parquet` is then only [what varies over nothing](../format.md#where-a-value-lives) — the non-varying attribute values, partitioned by type.
The partition is justified by the one thing that genuinely is per type: the attribute vocabulary, since every type has a different column set.

An attribute with no `entity` in its `dims` needs no owner and no special case:

```python
"objective_weighting": AttributeSpec(dtype="DOUBLE", dims={"snapshot"})
```

That is the thing that started this, expressible — and [the file-split rule](#where-a-value-lives) puts it on `dims/snapshot.parquet`, which is where the undeclared column sits today.

## Attributes are top-level

`Schema.attributes` inverts: flat, one spec per attribute, and component types subscribe.

The current nesting says an attribute _belongs to_ a component type. Once `entity` is one dim among several that is false in both directions — `objective_weighting` has no type, and `p_max_pu` is carried by Generator, Link and StorageUnit as three identical specs.

The storage already disagrees with the declaration: `inputs/p_max_pu.parquet` holds every type's rows in one file, keyed by name alone, with one `value` dtype.
So the nesting is expressive where the storage is not — two types may declare the same attribute with **different dtypes**, and one column has to serve both.
Nothing rejects that today; it is a silent wrong read waiting for a record that does it.

Flat declaration makes it unrepresentable, which is the stronger form of the same guarantee.
The declaration then matches the file layout one-to-one: one attribute, one spec, one file, one dtype.

```python
attributes = {
    "p_max_pu": AttributeSpec(
        dtype="DOUBLE", dims={"entity", "snapshot", "scenario"}, default=1.0
    ),
    "p_nom": AttributeSpec(dtype="DOUBLE", dims={"entity"}, default=0.0),
    "efficiency": AttributeSpec(
        dtype="DOUBLE", dims={"connection", "snapshot"}, default=1.0
    ),
    "objective_weighting": AttributeSpec(
        dtype="DOUBLE", dims={"snapshot"}, default=1.0
    ),
}
```

`AttributeSpec.bus` is deleted: a connection attribute is one whose `dims` name the `connection` group.

### Where a value lives

[Today](../format.md#where-a-value-lives) the split is `bool(spec.dims)`: varying over nothing puts an attribute in `dims/components/<Type>.parquet` as a column, anything else in `inputs/<attr>.parquet` as long rows.
That test breaks the moment `entity` is a dim — `capacity` gains `dims={"entity"}`, `bool` says varying, and every non-varying attribute silently moves file.

The rule that replaces it: **an attribute naming exactly one addressing coordinate and nothing else is a column on that thing's own table.**

| `dims`                       | lands in                                                              |
| ---------------------------- | --------------------------------------------------------------------- |
| `{"entity"}`                 | `dims/components/<Type>.parquet` — one column per attribute, per type |
| `{"connection"}`             | the `connection` group's table                                        |
| `{"corridor"}`               | `dims/corridor.parquet`                                               |
| `{"scenario"}`               | `dims/scenario.parquet` — the axis file                               |
| `{"entity", "snapshot"}`     | `inputs/<attr>.parquet`                                               |
| `{"connection", "snapshot"}` | `inputs/<attr>.parquet`                                               |

So `varying` is not "has dims" but **"has dims beyond its address"**, and one rule now covers what were three unrelated stories: a component's constant columns, a connection's `role`, and an axis's payload.

That last one is what the [opening problem](#what-starts-it) actually was.
`scenario_weighting` with `dims={"scenario"}` is not a special "record-level attribute" needing a new home — it is the axis-file case of the same rule, and the weighting column the fold already carries beside `dims/scenario.parquet` becomes a _declared_ one with a `dtype`, a `default` and a `description`.

**No separate payload declaration.** A group's table columns, an axis file's payload columns and a component table's constant columns are all just attributes whose `dims` name exactly that one thing.
Declaring them a second time on the `Group` or the `Dimension` would be two ways to say it, disagreeing eventually.

`role` follows from this rather than needing an exception: it becomes `AttributeSpec(dtype="VARCHAR", dims={"connection"})`.
[Today](../record.md#connections) it is described as describing the connection and identifying nothing, and it stays exactly that — a non-key column of the group's table — but it gains a declared type, a description, and a place in [`shape()`](#flags-is-not-enough), none of which it has now.

## Traits

A trait is a named bundle of attributes; a component type subscribes to traits and may add its own.

```python
traits = {
    "investable": {
        "capital_cost",
        "overnight_cost",
        "discount_rate",
        "fom_cost",
        "build_year",
        "lifetime",
    },
    "dispatchable": {
        "p_min_pu",
        "p_max_pu",
        "p_set",
        "marginal_cost",
        "marginal_cost_quadratic",
    },
    "committable": {
        "committable",
        "min_up_time",
        "min_down_time",
        "start_up_cost",
        "shut_down_cost",
        ...,
    },
}
component_types = {
    "Generator": ComponentType(
        traits={"investable", "dispatchable", "committable"},
        attributes={"efficiency", "sign", ...},
    ),
}
```

`Schema.attributes_for(ctype)` — the union of subscribed traits plus own attributes — is what [`flags`](../record.md#flags) and the [`add` routing](../working-record.md) read, so everything downstream is unchanged.

Two reasons this is a trait rather than a bare subscription list:

- **Deduplication is real.** The boundaries below are measured from PyPSA's registry, not invented.
- **lpspec dispatches on them.** An equation declares which traits it applies to, so a trait is a queryable schema fact rather than a way to shorten the manifest. That is what makes the vocabulary worth declaring: it is authored, not derived.

A trait is **declared, not inferred**. PyPSA has no trait registry to read, so the mapping from its registry to traits is authored and maintained. That is a cost, and it is the price of the vocabulary being useful to something other than this schema.

Conflicts — two traits declaring the same attribute with different specs — are a validation error, not last-wins.

## Groups

A group declares **which tuples over several dims exist**: a sparse subset of a dim product, with its own order.
Its table's non-key columns are not declared here — they are the attributes whose `dims` name exactly this group ([where a value lives](#where-a-value-lives)).

```python
groups = {
    "connection": Group(over={"entity": "entity", "bus": "bus"}),
    "corridor": Group(over={"from": "entity", "to": "entity"}),
}
```

`over` maps **coordinate name -> dim**, not a bare set of dims, for two reasons.
A group over two coordinates drawn from the _same_ dim needs two column names — a corridor between two entities is `(from, to)`, and a set could not spell it.
And an attribute over a group carries the group's _coordinate_ names as columns, never the group's own name:

```text
inputs/flow.parquet       from | to | snapshot | attribute | breakpoint | value
inputs/efficiency.parquet entity | bus | snapshot | attribute | breakpoint | value
```

The group name appears only in the schema. A reader goes attribute → group → coordinates, never the reverse, so two groups may share a coordinate set without ambiguity: the attribute names which group constrains it.

**`bus` stops being structural.** It is one coordinate of one group, and another group's coordinates are not called `bus` at all — so keeping it in `STRUCTURAL_TYPES`, in the long schema's fixed prefix or in the fold's key literals would privilege one group's spelling over the mechanism.
The fixed prefix becomes `entity | attribute | breakpoint | value`, and every coordinate including `bus` arrives through the derived part.

`entity` is the one dim the format still knows by name, and not merely because it is an axis: it is **the axis the component types partition**. `dims/entity.parquet` carries `component_type`, which decides an attribute vocabulary, and `dims/components/<Type>.parquet` is keyed by it. Nothing else in the schema does that.

**A group in `dims` expands to its coordinates.** `dims={"connection", "snapshot"}` means the attribute's effective columns are `entity | bus | snapshot`, the group contributing both of its own.
So the fold's key does not vary per attribute: [`input_dims`](../schema.md#partial-the-granularity-of-an-override) stays one fixed tuple over every attribute, now the union of plain dims and group _coordinate_ names rather than dim names alone.
An attribute not addressed by a coordinate writes NULL there, exactly as one not varying over a dim does today.

Coordinate names rather than dim names is what makes `corridor` work: `from` and `to` both draw on `entity`, so a key built from dims would collapse them into one column.

**Connections become a group.** `dims/connections/<Type>.parquet` is `Group(over={"entity", "bus"})`, with `role` an ordinary attribute over it — which is what it already is, keyed `(name, bus, *connection dims)` with its own tombstones.

**Broadcast, for a group coordinate, enumerates the group** rather than the product of its dims.
That is the rule today's `bus` gets by being excluded from expansion, stated as a rule rather than an exception: a NULL `bus` on a connection attribute means "every connection of this entity", which is the group's rows, not the whole bus axis.

This closes [whether `within` should subsume `bus`](../open-questions.md) as _no — groups do it_.
The blocker recorded there is that `bus` inverts the NULL rule. That premise does not survive: expansion is already governed by whether a dim is in the fold's key set, and [`input_dims`](../schema.md#partial-the-granularity-of-an-override) is already `dims ∩ partial` — a filter over declared dims, not every declared dim. A non-partial dim like `timestep` is never expanded either, and an attribute whose `dims` omit `scenario` writes a NULL there that means "inapplicable", not "all scenarios".
So the behaviour that "makes a dim a dim" is not uniform today, and `bus` is not an exception to it.

## The protocol

[`Record`](../record.md) names `connections` as a member of its own, keyed by component type.
Once connections are one group among several that is wrong twice — a second group has nowhere to go, and `connections` privileges one instance of a general mechanism.

```python
@runtime_checkable
class Record(Protocol):
    @property
    def schema(self) -> Schema: ...

    @property
    def dims(self) -> Frames: ...  # axis frames, keyed by dim — mappings included
    @property
    def components(self) -> Frames: ...  # non-varying values, keyed by component type
    @property
    def groups(self) -> Frames: ...  # group tables, keyed by group name
    @property
    def attributes(self) -> Frames: ...
    @property
    def outputs(self) -> Frames: ...

    def flags(self, ctype: str) -> dict[str, Flags]: ...
    def shape(self) -> dict[str, Shape]: ...  # record-wide, keyed by attribute
```

`connections` becomes `groups["connection"]`, and `record.groups` is keyed by group name rather than by component type — a group is not partitioned per type, since [`entity` carries the type](#entity-the-component-axis) and a group row references entities rather than belonging to one type's file.
`dims` gains the entity axis and every mapping, both being ordinary dims.

### `flags` is not enough

`flags(ctype)` takes a component type, which two of the new kinds of attribute do not have: `objective_weighting` is addressed by `snapshot` alone, and `flow` by a group's coordinates.
Neither has a ctype to ask about, so neither can be reached through it.

Rather than widen `flags`, add a second method beside it, keyed by attribute and scoped to the whole record:

```python
@dataclass(frozen=True)
class Shape:
    dims: frozenset[str]  # coordinates some row of this attribute sets
    broadcast: frozenset[str]  # coordinates some row leaves NULL
    breakpoints: bool
    types: frozenset[
        str
    ]  # component types with rows, empty for a record-level attribute
```

`shape()` answers _what exists_ — which attributes have rows at all, which coordinates they use, which types they touch — for every attribute in one call.
`flags(ctype)` keeps its meaning as the per-type question a framework assembling containers asks; `shape()` is the record-level one, and `types` is what lets a consumer get from one to the other without opening a file.

**It is cheap because the owner map already computes it.**
The `varies`/`broadcast` structs are built in the same `aggregate` as ownership, from a `_raw_<dim>` column carried alongside each expanded dim, so a struct field per coordinate costs nothing beyond the group-by that is already running.
`types` is the same aggregation over the components map's `component_type`, which that map already carries as a column.
So `shape()` for a `LayeredRecord` is a projection of the folded map — no attribute file is opened, which is the property [`flags`](../record.md#flags) was introduced for and the reason to put this beside it rather than inside it.

A `DirectoryRecord` pays a `GROUP BY` scan over `inputs/`, as it already does for `flags` — [the same asymmetry](../read-path.md#one-record-over-one-fold), not a new one.

**Open:** whether `flags(ctype)` survives at all, or becomes `shape()` filtered by `types`.
The two would then differ only in scoping, and one method answering both is smaller — but `flags` is per type _by construction_ (its union stops at the type boundary deliberately), and a filtered `shape()` would have to reproduce that. Not settled here.

## Mappings

A mapping is a `Dimension` subclass declaring that **each label of the dim it is `on` has exactly one label of its own**.

```yaml
dimensions:
  bus:
    dtype: VARCHAR
  state:
    dtype: VARCHAR
    on: bus # each bus is in one state
  country:
    dtype: VARCHAR
    on: state # each state is in one country
```

Declared on the coarse dim, phrased as "country is a mapping on state". The **column** still lives on the classified dim's file, since that is the side where it is single-valued:

```text
dims/country.parquet    country | co2_budget | ...      the axis: labels, order, attributes over it
dims/state.parquet      state   | country | ...         the same, plus the mapping column
dims/bus.parquet        bus     | state   | v_nom | ...
```

A mapping has its **own axis file** rather than being only a column. That is what gives it order ([axis order](../record.md#axis-order) is a file's row order) and a place for per-country data — a CO2 budget is a property of the country, and with no file it would have nowhere to go.
Those columns are declared like any other: `co2_budget` is an attribute with `dims={"country"}`, which [the file-split rule](#where-a-value-lives) puts on `dims/country.parquet`.

Being a `Dimension` subclass, a mapping **is a dim**: `Schema.dims` includes both, one namespace, name collisions across the two declaration sections are an error. An attribute may be addressed by it, and then carries a literal `country` column.

**Chains are not denormalised.** `dims/bus.parquet` carries `state`, not `state | country`. Two files asserting bus→country would let a layer restating `dims/state.parquet` leave every bus's `country` column stale with nothing to detect it. A denormalised column is generated on read or by a helper, never stored.

**The record does not resolve across levels.** An attribute over `country` is handed back as stored, keyed by country. Projecting it down to buses is a join through the mapping column, and that is the consumer's work — helpers may come later. The fold learns no new operation.

Mappings are **not partial**: a mapping is its axis file's own content, so a layer touching it restates it whole.

Single-valued **by construction** — it is a column, so a row has one value. A many-to-many classification is a group, not a mapping. That is the line between the two mechanisms.

### Mappings are not `within`

Both are dim→dim, both acyclic, both put a column on another dim's file. They mean opposite things, and the doc must present them together rather than let a reader infer the difference from two similar signatures.

- **`within`** names my _parents_: my label set is **scoped per parent**, so `t1` in period 2015 and `t1` in period 2020 are different points, and the axis key is `(period, timestep)`.
- **`on`** names the dim I _classify_: one flat label set, each label of that dim picking one of mine. `country` is not scoped by `bus`; it is a partition of buses.

Nesting versus classification. `within` cannot express `country`, and a mapping cannot express `timestep`.

## `keys` goes

`Dimension.keys` declared that an entity exists _per value_ of a dim — a generator present in scenario `high` and absent from `low` — which put the dim in the entity table's key and scoped its tombstones. It is [now deleted](../schema.md#existence-does-not-vary-along-a-dim); what follows is why.

It cannot survive this proposal, and not merely because it is hard to grasp.
`KeyKind` is the closed set `{"component", "connection"}`, and `Schema._keyed(kind)` derives `component_dims` and `connection_dims` by asking every dim which of those two tables it keys.
Once connections are a [group](#groups), `"connection"` names a structural category that no longer exists — so the field references a table the proposal deletes.
This is an immediate failure at step 5 of the [sketch](#implementation-sketch), not something deferrable.

**Nothing replaces it here.** A field declaring per-dim existence was drafted for this proposal and removed again, because the semantics it needs are not settled — see [may existence depend on a dim](#may-existence-depend-on-a-dim) below.
So in this proposal an entity exists or it does not, a group row exists or it does not, and neither varies along another axis.
`dims/entity.parquet` carries `deleted` and a group's table carries its own; both are unconditional.

That is a **narrowing** of what the format can express today, and it is deliberate: it is better to drop a mechanism whose meaning is unresolved than to carry it into a redesign under a new name.
Anything relying on scenario-scoped existence needs the open question answered first.

What is decided independently: a **mapping never scopes existence**, whatever the answer. Membership cannot vary along a classification of another axis — whether a generator exists in Germany is already determined by its bus and that bus's country, so there is no freedom for it to vary independently. Same reasoning excludes mappings from `partial`.

## A PyPSA network in full

The point of the example. Attribute names, dtypes, defaults and trait boundaries below are read from PyPSA's own component registry rather than invented; the trait _names_ are authored.

```jsonc
{
  "version": 2,

  "dimensions": {
    // no `keys`: whether existence may vary along a dim is deliberately
    // unanswered here — see "may existence depend on a dim"
    "entity": { "dtype": "VARCHAR", "description": "A component." },
    "snapshot": { "dtype": "TIMESTAMP", "description": "A point in the operational time series." },
    "period": { "dtype": "BIGINT", "unit": "year", "description": "An investment period." },
    "scenario": { "dtype": "VARCHAR" },
    "bus": { "dtype": "VARCHAR", "description": "A node of the network." },

    // a mapping: each bus is in one country; the column lives on dims/bus.parquet
    "country": { "dtype": "VARCHAR", "on": "bus" },
  },

  "groups": {
    // subsumes dims/connections/: a component attaches to a bus.
    // No payload block — `role` is an attribute over this group, below
    "connection": {
      "over": { "entity": "entity", "bus": "bus" },
    },
  },

  "traits": {
    // measured: shared by Generator, Line, Link, Store, StorageUnit, Transformer
    // `capacity*` is renamed from PyPSA's p_nom/s_nom/e_nom, which lets the
    // capacity itself sit in the trait rather than only its costs — see below
    "investable": [
      "capital_cost",
      "overnight_cost",
      "discount_rate",
      "fom_cost",
      "build_year",
      "lifetime",
      "capacity",
      "capacity_extendable",
      "capacity_min",
      "capacity_max",
      "capacity_set",
      "capacity_mod",
    ],
    // measured: shared by Generator, Link, StorageUnit
    "dispatchable": ["p_min_pu", "p_max_pu", "p_set"],
    // measured: shared by Generator, Link
    "committable": [
      "committable",
      "min_up_time",
      "min_down_time",
      "up_time_before",
      "down_time_before",
      "start_up_cost",
      "shut_down_cost",
      "stand_by_cost",
      "ramp_limit_up",
      "ramp_limit_down",
      "ramp_limit_start_up",
      "ramp_limit_shut_down",
    ],
    // measured: shared by Line, Transformer
    "passive_branch": ["r", "b", "g", "s_max_pu", "num_parallel", "v_ang_min", "v_ang_max"],
  },

  "component_types": {
    "Bus": { "traits": [], "attributes": ["v_nom", "v_mag_pu_set", "v_mag_pu_min", "v_mag_pu_max", "carrier", "unit", "location"] },
    "Carrier": { "traits": [], "attributes": ["co2_emissions", "color", "nice_name", "max_growth", "max_relative_growth"] },
    "Generator": {
      "traits": ["investable", "dispatchable", "committable"],
      "attributes": ["efficiency", "sign", "carrier", "active", "control", "q_set", "e_sum_min", "e_sum_max", "weight", "marginal_cost", "marginal_cost_quadratic"],
    },
    "Line": { "traits": ["investable", "passive_branch"], "attributes": ["length", "terrain_factor", "carrier", "active", "x"] },
    "Link": { "traits": ["investable", "dispatchable", "committable"], "attributes": ["efficiency", "length", "terrain_factor", "carrier", "active", "marginal_cost", "marginal_cost_quadratic"] },
    "Store": { "traits": ["investable"], "attributes": ["e_cyclic", "e_initial", "standing_loss", "marginal_cost", "marginal_cost_storage", "carrier", "active"] },
    "StorageUnit": {
      "traits": ["investable", "dispatchable"],
      "attributes": [
        "max_hours",
        "efficiency_store",
        "efficiency_dispatch",
        "standing_loss",
        "cyclic_state_of_charge",
        "state_of_charge_initial",
        "inflow",
        "marginal_cost",
        "marginal_cost_storage",
        "carrier",
        "active",
      ],
    },
    "Load": { "traits": [], "attributes": ["p_set", "q_set", "sign", "carrier", "active"] },
  },

  // One rule places every one of these: an attribute naming exactly one
  // addressing coordinate is a column on that thing's table; anything more
  // is long rows in inputs/. See "where a value lives".
  "attributes": {
    // dims = {entity} -> a column in dims/components/<Type>.parquet
    "capacity": { "dtype": "DOUBLE", "dims": ["entity"], "default": 0.0, "unit": "MW" },
    "capacity_extendable": { "dtype": "BOOLEAN", "dims": ["entity"], "default": false },
    "capacity_max": { "dtype": "DOUBLE", "dims": ["entity"], "default": "__inf__" },
    "capital_cost": { "dtype": "DOUBLE", "dims": ["entity"], "default": 0.0, "unit": "EUR/MW" },
    "carrier": { "dtype": "VARCHAR", "dims": ["entity"], "default": "" },
    "v_nom": { "dtype": "DOUBLE", "dims": ["entity"], "default": 1.0, "unit": "kV" },

    // beyond its address -> inputs/<attr>.parquet, as long rows
    "p_max_pu": { "dtype": "DOUBLE", "dims": ["entity", "snapshot", "scenario"], "default": 1.0 },
    "marginal_cost": { "dtype": "DOUBLE", "dims": ["entity", "snapshot", "scenario"], "default": 0.0, "breakpoints": true, "unit": "EUR/MWh" },
    "efficiency": { "dtype": "DOUBLE", "dims": ["connection", "snapshot"], "default": 1.0 },

    // dims = {connection} -> a column on the group's own table. Replaces the
    // `payload` block, and gives `role` a dtype it never had
    "role": { "dtype": "VARCHAR", "dims": ["connection"], "description": "Which end of the component this attachment is." },

    // dims = {snapshot} -> a column on dims/snapshot.parquet, the axis file.
    // The thing that started this: declared, typed, and no longer a column
    // the PyPSA tool recognises by name
    "objective_weighting": { "dtype": "DOUBLE", "dims": ["snapshot"], "default": 1.0 },
    "generator_weighting": { "dtype": "DOUBLE", "dims": ["snapshot"], "default": 1.0 },
    "store_weighting": { "dtype": "DOUBLE", "dims": ["snapshot"], "default": 1.0 },

    // dims = {scenario} -> dims/scenario.parquet, beside the axis labels
    "scenario_weighting": { "dtype": "DOUBLE", "dims": ["scenario"], "default": 1.0 },

    // dims = {country} -> dims/country.parquet, a mapping's own axis file
    "co2_budget": { "dtype": "DOUBLE", "dims": ["country"], "unit": "t" },
  },

  "partial": ["scenario"],
  "meta": { "format": "pypsa-parquet" },
}
```

### What the example exposes

Reading it back is the test, and three things show up that the prose above does not settle.
Both name questions are ones the **storage already asks and the nested schema hides**: one attribute is one file, `inputs/<attr>.parquet`, holding every type's rows keyed by name alone with a single `value` dtype.
So flattening does not introduce them. It makes them representable.

**One name per concept.** PyPSA spells the same quantity `p_nom` (Generator, Link, StorageUnit), `s_nom` (Line, Transformer) and `e_nom` (Store).
Nested under a component type those are three unrelated attributes; flat, they are one concept under three names, and `investable` could otherwise hold only the _costs_ of investing rather than the thing invested in.

The example renames them to `capacity`, which is what lets `capacity` and its bounds sit in the trait alongside `capital_cost`. That is the outcome to want — an equation in lpspec asking for "the capacity of anything investable" gets one name — and it implies: **the record's vocabulary is not PyPSA's**, and the tool renames on the way in and out.

**Renaming happens tool-side, and traits declare no roles.** The [schema a tool carries](../tools.md) already maps a framework's attribute names to a record's, per component type, so `p_nom -> capacity` for a Generator and `s_nom -> capacity` for a Line is what that mechanism is for.
A trait naming a _role_ an attribute fills would put the same mapping in the record's schema instead, which is one more indirection for something the tool seam already answers — and it would mean an equation dispatching on `capacity` has to resolve a role before it can read a column.

**Collisions become representable rather than silent.** `Bus.x` is a coordinate, `Line.x` is reactance; `Bus.type` and `Line.type` are unrelated standard-type references.
These are **already collisions today**: both types' `x` rows go to one `inputs/x.parquet` with one `value` dtype, so the nested schema declares two specs over storage that can only honour one.
Two declared dtypes and one column is a silent wrong read, and nothing rejects it.

Flattening cannot represent the disagreement, which is why the collision surfaces at declaration time instead.

**The record does not resolve them.** One attribute name means one thing record-wide; two concepts wanting the same name is a limitation the record states rather than a problem it solves.
A tool reconciles on its own side — prefixing (`line_x`), renaming to something meaningful (`reactance`), or refusing the network in `verify` — which is [the same seam](../tools.md) that renames `p_nom` to `capacity` above, and the same one that already reports a framework scoping names per type against a record scoping them record-wide.

No qualified names, no per-type namespaces: both would put the component type back into an attribute's address, which is exactly what [name uniqueness](../format.md#entity-is-unique-across-types) removed and what makes one file per attribute possible.
The example accordingly removes `type` from every type and `x`/`y` from `Bus` rather than inventing a mechanism.

**Per-port attributes.** `Link.efficiency2`, `bus0`/`bus1` collapse to a stem addressed by the `connection` group, which the example shows for `efficiency` but not for the `bus0`/`bus1` columns themselves — those become group _rows_, not attributes, and the example does not show the group table.

Outputs are deliberately left out of this proposal.

## Implementation sketch

Rough, and deliberately so — the design is not finished, and the ordering below is what would make each step testable rather than a commitment.

**Docs first, code after.** Every step is a schema change and [`version`](../schema.md#versioning) bumps once for the whole thing; all of it is incompatible, so there is no migration path and a record is rewritten rather than upgraded.

Two breaks in `mutable.py` are worth naming before they are met, because neither announces itself:

- **`AttributeSpec.varying` inverts at step 4.** `add` routes columns by `declared[c].varying`, which is `bool(spec.dims)`. Once `capacity` declares `dims={"entity"}` that is true, so every non-varying attribute would route to `inputs/` instead of its component table. [The file-split rule](#where-a-value-lives) is the fix, but the routing site has to move with it.
- **`_overlay`'s broadcast set shifts without being edited.** It computes `broadcast` as the declared dims _minus_ the input key, which today is exactly the non-partial dims (`snapshot`, `period`) — the axes an attribute is not owned per.
  The key spells `name` and `bus` as literals, so renaming the entity axis to `entity` while `schema.dims` gains it puts **`entity` in `broadcast`**, where a staged row with a NULL entity anti-joins every base row regardless of entity — one edit wiping another component's values from an overlay read.
  `bus` is unaffected, being a literal in the key already.
  The fix is to derive the key's address coordinates rather than spell them, after which `broadcast` means what it did; the hazard is only that nothing fails loudly first. `_long_columns` has the same literals-beside-`schema.dims` shape but breaks loudly, by emitting a column twice.

  A group coordinate must land in the **key**, never in `broadcast` — a NULL `bus` means "every connection of this entity", which [enumerates the group's rows](#groups) rather than comparing NULL-safely along an axis. That is the one place where "`bus` is just a coordinate" does not mean "`bus` behaves like `scenario`", and it is where this proposal's broadcast rule meets the code.

1. **Flat attributes + traits.** `Schema.attributes` inverts, `attributes_for(ctype)` becomes the accessor, and every read site moves to it. No format change — the files are unchanged, only the manifest. This is the largest blast radius in the Python and the smallest in the data, which makes it the right first step.

2. **Singular parquet names.** `dims/<dim>.parquet`, dropping the `f"{d}s"` concat in `directory.py` and `layered/write.py`. Trivial, and it removes a latent bug: a dim named `bus` currently yields `dims/buss.parquet`.

3. **Mappings.** `Dimension` subclass with `on`, its own axis file, the column on the classified dim's file. Additive: no existing record has one, and the fold treats a mapping exactly as a dim. Cheapest real feature here.

4. **`entity` as a dim.** `dims/entity.parquet` with `component_type` and tombstones — no order column, [order being derived](#entity-the-component-axis); `dims/components/<Type>.parquet` demoted to non-varying values. Rebuilds the components map from an axis rather than a type glob, which is where the fold work actually is.

5. **Groups, connections as the instance — including `keys`.** `fixed=("name","bus")` in `layered/resolve.py` becomes schema-derived; the `varies`/`broadcast` structs key on coordinates rather than dims. Deletes `AttributeSpec.bus` and the `bus` special case.
   [`keys` goes in the same step](#keys-goes), not after it: `connection_dims` is derived by scanning every dim for `"connection"` in its `keys`, so the moment connections stop being an entity table that scan has no referent. `KeyKind`, `_keyed`, `component_dims` and `connection_dims` all disappear with it, and nothing replaces them until [the open question](#may-existence-depend-on-a-dim) is answered.

Dropping `keys` narrows what a record can express, so step 5 is where scenario-scoped _membership_ stops being representable until [the open question](#may-existence-depend-on-a-dim) is settled — scenario-varying _values_ are untouched, as is every per-scenario overlay.
That makes 5 the one step with a functional regression rather than a pure refactor, and it should not land without the answer.

Its tests go with it, in the same step rather than ahead of it — the behaviour is shipped and working until the code implementing it is removed:

- `tests/test_scenario.py::test_per_scenario_tombstone` — the only passing test of scenario-scoped existence. The rest of that file covers values and layer resolution, and survives.
- `tests/test_connections.py::test_narrower_connection_key_than_component_key` — already `xfail(strict=True)`, and exactly [the case](#may-existence-depend-on-a-dim) the open question now records.
- the `keys` plumbing in `tests/fixtures.py`, which most call sites pass as `keys={}` and do not exercise.

6. **[The protocol](#the-protocol).** `connections` becomes `groups`, `shape()` joins `flags`. Lands with 5, since `groups` has nothing to be keyed by until groups exist — but it is the change every consumer sees, so it is worth calling out separately from the fold work that forces it.

7. **[`WorkingRecord`](../working-record.md) reaches the new attribute kinds.** `set(attr, value)` with `names=None` resolves targets through the types declaring the attribute, so a record-level attribute — no `entity` in its `dims` — resolves to no types, no names, and stages nothing at all rather than failing. And `bus=` is a single scalar parameter, which addresses the `connection` group but cannot spell a two-coordinate group like `corridor`. Both need a path that does not go through a component type. The compensation is that `_require_unique` and the name→type scan over every type's frame collapse to one read of `dims/entity.parquet`.

The long schema's columns become schema-derived at step 4 and stay that way. `union_by_name` is what makes files readable across shapes, so the fixed column order in [the long schema](../format.md#the-long-schema) matters less than its phrasing suggests — but `STRUCTURAL_TYPES` fixing `name` and `bus` does have to go.

Not in any step, and needed before step 1 ships against a real network: **the PyPSA tool's trait table**. Traits are authored, so someone writes the registry-to-trait mapping and the `p_nom -> capacity` renames for every exported type, and maintains them as PyPSA's registry moves. The [example](#a-pypsa-network-in-full) sketches four traits; a real one covers every type the tool exports.

## What this closes and opens

Closes, in [open questions](../open-questions.md):

- **`within` subsumes `bus`** — no; groups do it, and the recorded blocker rests on a premise (NULL uniformly means broadcast) that does not hold today.

Decided here, rather than left open:

- **Vocabulary reconciliation is tool-side.** Renaming `p_nom`/`s_nom`/`e_nom` to `capacity` happens in [the tool's schema](../tools.md); traits declare no roles.
- **Genuine collisions are a limitation, not a mechanism.** One attribute name means one thing record-wide; `Bus.x` versus `Line.x` is a tool's problem to work around by prefixing or renaming.

Opens:

- **[May existence depend on a dim](#may-existence-depend-on-a-dim)** — the replacement for `keys`, deliberately unanswered. Subsumes the connection-tombstone question [open questions](../open-questions.md) records, and belongs in that page rather than here once this proposal lands.
- **Whether [`flags(ctype)`](#flags-is-not-enough) survives alongside `shape()`**, or becomes it filtered by `types`.

Outputs are out of scope here and need settling separately.

## May existence depend on a dim

The question `keys` [answered badly](#keys-goes), restated from scratch: **may an entity's or a group row's existence vary along another dim?**

A stochastic network is the case that wants it — a generator built in scenario `high` and absent from `low`, so `dims/entity.parquet` is keyed `(entity, scenario)` and a tombstone names one scenario.
Today's `keys` says yes and puts the dim in the entity table's key. This proposal drops that and does not replace it, because two things have to be settled first.

**The tables can disagree, and no projection recovers the difference.**
Suppose the entity table's existence varies over `scenario` and the `connection` group's does not — a component may be absent in `low`, but where it attaches is the same in every scenario:

```text
dims/entity.parquet      wind1 | Generator | scenario=high | deleted=false
                         wind1 | Generator | scenario=low  | deleted=true    ← gone in low only
dims/connection.parquet  wind1 | north     | role=bus                        ← no scenario column
```

`wind1` survives in `high`, so its attachment must survive too; it is deleted in `low`, so the attachment must not.
There is one row and no scenario column to write the difference into. Both answers are wrong:

- **drop it** — `wind1` exists in `high` attached to nothing;
- **keep it** — a connection referencing a component absent in `low`.

The conservative reading — project the tombstone down to the shared dims, so the row goes — is what the fold implements today, pinned by an `xfail` in `tests/test_connections.py`.
[Open questions](../open-questions.md) records why it cannot do better: the connections fold would need to know which scenarios `wind1` survives in, and it only sees connection rows.

**A validator could forbid the mismatch**, requiring every group's existence dims to be at least as fine as the entity table's. That makes the case unrepresentable rather than resolved, and it is a real option — but it is a decision, not a default, and it constrains what a framework may declare.

So the questions are:

1. Is per-dim existence needed at all, or does an `active`-style attribute cover it? PyPSA has both — `active` as a boolean attribute, and scenario-scoped membership — which suggests the two are not the same thing, but does not say which the record should carry.
2. If needed, may tables disagree, or is uniformity enforced?
3. If they may disagree, what does the coarser table's row mean — and can the fold compute it at all?

Answering **1** with "no" deletes the whole area, which is the outcome to check first.

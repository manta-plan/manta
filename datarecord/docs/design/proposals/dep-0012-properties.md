<!--
SPDX-FileCopyrightText: datarecord contributors

SPDX-License-Identifier: CC-BY-4.0
-->

# DEP 12: properties — metadata declared apart from data

| DEP      | 12                                                                                                           |
| -------- | ------------------------------------------------------------------------------------------------------------ |
| Title    | properties — metadata declared apart from data                                                               |
| Author   | Jonas Hörsch                                                                                                 |
| Status   | Implemented 2026-10-13 (steps 1 and 2)                                                                       |
| Requires | [DEP 10](dep-0010-a-group-is-a-struct-column.md), [DEP 11](dep-0011-deletion-cascades-through-tombstones.md) |
| Created  | 2026-10-12                                                                                                   |
| Version  | Unreleased                                                                                                   |
| Replaces | [DEP 6](dep-0006-a-member-file-holds-values.md)                                                              |

Two changes that are one. **Properties** — what classifies or describes one label of a dim, its metadata — get their own section of the manifest, apart from **attributes**, the data. And the entity-type axis stops being a dim with a group over `entity`: it becomes an ordinary `Enum` property of `entity`, whose values — **categories** — per-category defaults and trait scoping key on. With it goes every special case of `entity` and `entity_type` in core: `entity` becomes a dim like any other, listed in `partial`, and the name `entity_type` is data a schema happens to declare.

It builds on [a group is one struct column](dep-0010-a-group-is-a-struct-column.md) — a group is a dim, referenced in rows by one struct column — and on [deletion cascading through tombstones](dep-0011-deletion-cascades-through-tombstones.md).

It lands in two steps. **Step 1** — properties, categories, and `entity` as an ordinary dim — is being built. **Step 2** — the section, not the shape, deciding where a value lives — is the rest of the design below, sequenced after. A per-category read, [`members`](#optional-members), is deferred. An [optional stage](#optional-stage-categories-in-attribute-rows), storing a category in an attribute row, is to be decided.

## What starts it

**Where a value is read depends on how many coordinates address it, not on what it is.** `p_nom` and `carrier` are both declared under `attributes` with `dims: [entity]`, so both land on the entity axis — and `record.attributes` hands over neither, since it [holds long frames only](../record.md); a caller finds them on `record.dims["entity"]` or `record.entity_types["Generator"]`. Yet `p_nom` is data a model optimises against, and `carrier` a label describing the generator. The rule placing them — [exactly one addressing coordinate](../format.md#where-a-value-lives) — groups the two by an accident of shape.

The same rule makes a compatible schema change move a file. Widening `p_nom` to `dims: [entity, scenario]` is [compatible](../schema.md#versioning) because NULL broadcasts, but it moves `p_nom` from a column of the entity axis to `inputs/p_nom.parquet`, so the rows a layer wrote before are in a file the new schema no longer reads it from.

**The entity-type axis is a special case at every layer.** It is a dim, plus a group over `entity` `into` it, whose rows are [the entity axis file rather than a `groups/` file](../format.md#where-a-value-lives) — the one exception to a file per group. Its name is reserved as an attribute name. Whether it is declared decides the [layout of the entity axis](../format.md#the-entity-axis): per-type member files under `dims/entity_type/` in one case, columns of `dims/entity.parquet` in the other. Traits may be scoped by it. Its `Enum` dtype is what makes it a vocabulary, while a `String`-typed declaration of it is an [open question](dep-0006-a-member-file-holds-values.md#what-it-opens-rather-than-settles).

**`entity` is a special case too.** It is in the fold key whatever `partial` says, a NULL in it never broadcasts, its tombstones alone cascade into a group's fields, and the read API answers per entity type (`entity_types`, `entity_type(ctype)`, `flags(ctype)`). None of that is said in the schema; all of it is code naming `"entity"`.

**And the schema cannot say what a framework's registry says.** PyPSA defaults differ per component for one name:

| name       | default per type                                                     |
| ---------- | -------------------------------------------------------------------- |
| `sign`     | `1` for Generator, Store, StorageUnit; `-1` for Load, ShuntImpedance |
| `carrier`  | `"AC"` for Bus; `""` otherwise                                       |
| `type`     | `"primary_energy"` for GlobalConstraint; `""` otherwise              |
| `p_min_pu` | `-1` for StorageUnit; `0` otherwise                                  |
| `p_set`    | `0` for Load; `NaN` otherwise                                        |

`AttributeSpec.default` is one value, so today a tool either picks one and writes the others out as data, or loses them. None of the 142 input names differs in **dtype** between types — only in default.

## The construct

### Properties and attributes

```yaml
dimensions:
  entity: { dtype: String }
  bus: { dtype: String }
  snapshot: { dtype: { Datetime: us } }
  scenario: { dtype: String }

groups:
  connection:
    over: { entity: entity, bus: bus }

properties:
  entity:
    entity_type:
      dtype: { Enum: [Bus, Generator, Load, Link, Store, StorageUnit] }
    carrier:
      dtype: String
      default: ""
      default_by:
        entity_type: { Bus: AC }
    sign:
      dtype: Float64
      default: 1
      default_by:
        entity_type: { Load: -1 }
  bus:
    x: { dtype: Float64, unit: "°" }
    y: { dtype: Float64, unit: "°" }

attributes:
  p_nom:
    dtype: Float64
    dims: [entity]
    default: 0
  p_nom_extendable:
    dtype: Boolean
    dims: [entity]
    default: false
  p_max_pu:
    dtype: Float64
    dims: [entity, snapshot]
    default: 1
  p_min_pu:
    dtype: Float64
    dims: [entity, snapshot]
    default: 0
    default_by:
      entity_type: { StorageUnit: -1 }
  efficiency:
    dtype: Float64
    dims: [connection]
  weight:
    dtype: Float64
    dims: [scenario]
    default: 1

traits:
  generator:
    attributes: [p_max_pu, p_nom_extendable]
    on: { entity_type: [Generator] }
    switch: p_nom_extendable

partial: [entity, scenario, connection]
```

**A property is one value per label of one dim, its subject**, and is declared under that subject's key — there is no `dims` on a property, and it never varies along another axis. It identifies, classifies or describes the label: a type, a carrier, a sign convention, a coordinate on a map.

**An attribute is data**: what a model reads as part of its problem and what a scenario or a layer would vary. It keeps `dims`, which may name a single coordinate — `p_nom` over `entity`, a scenario `weight` over `scenario` — without that making it a property.

Which a name is, is the author's declaration, not derived. The test is the one above, and a tool reads it from its registry where it can.

**One name, one spec, across every section.** A name declared as a property and as an attribute, or as a property of two subjects, is rejected — [`flags`](../record.md#flags) would have two answers for it. So is a property sharing a dim's or a group's name, which would collide with that coordinate's column. This is the [flat-attributes argument](../schema.md#attributespec) extended to the new section.

### An `Enum` property of a `partial` dim categorizes its subject

**Any `Enum`-typed property of a dim listed in `partial` may be named by `Trait.on` and `default_by`.** Its values are that dim's **categories** along it. There is no flag declaring the role, and no limit of one per dim: `entity_type` categorizes `entity`, and an `Enum`-typed `carrier` would too, as would a `bus_type` on `bus`. Naming any other property — a `String`, or one of a dim outside `partial` — is refused.

The two conditions are what a category needs:

- **`Enum`**, so the categories a trait or a default names are checkable against a declared vocabulary. This settles the [`String`-typed axis question](dep-0006-a-member-file-holds-values.md#what-it-opens-rather-than-settles): a set of categories is an `Enum`, or nothing can key on it.
- **The dim in `partial`**, because only there is a dim owned and checked per label. Outside it, a layer setting one entity's value would own every entity's, and a label could not be refused against an axis the fold does not key.

That replaces the whole entity-type construct: no `entity_type` dim, no group over `entity` into it, no exception to a file per group, and no reserved name — `entity_type` is a column of `dims/entity.parquet` because every property of `entity` is. A schema whose entities have no categories declares no `Enum` property of `entity`, and nothing else about it differs. The schema attaches no meaning to the name `entity_type`; it is what PyPSA and every existing record call it.

**Category** is the word for such a property's values throughout, because **label** already names an axis value — what `add(dim, labels)` and `remove(dim, labels)` take. `Schema.categorizing(dim)` lists the properties of `dim` a trait or default may key on; which attributes a label carries is `attributes_for(dim, **categories)` — the label's value of each categorizing property — and its default `default_for(name, **categories)`.

**A category may change.** `set("entity_type", "Load", entity="g1")` is a patch of one property like any other. The values `g1` holds for attributes a Load does not carry stay stored — `record.attributes` shows what was written — but fall outside every per-category read and every broadcast, which are evaluated against its current categories.

### `default_by` — a default per category

`default` stays the fallback. `default_by` maps a categorizing property to per-category overrides:

```yaml
default: 0
default_by:
  entity_type: { StorageUnit: -1 }
```

A value read unset — a NULL property column, or no `inputs/` row reaching the label — reads the first `default_by` key, in declaration order, whose map lists the label's category; else `default`.

- **On properties and attributes alike.** `p_min_pu` and `p_set` need it as much as `sign` does, and a default is never stored, so it costs no file layout.
- **Each key reachable from the value's address.** A key must categorize a dim the value reaches: `entity` directly, or through `connection`'s `entity` field for a value over the group. A category outside the property's `Enum` is refused.
- **Only the default varies.** `dtype`, `unit` and `description` are the spec's own and never per category, which is what keeps one name one column and one `inputs/` file.

Step 1 declares and validates `default_by` and answers it through `Schema.default_for`; applying it on read is step 2.

### Traits are scoped by a category

`Trait.on` keeps its shape — `on: {entity_type: [Generator, Link]}` — and names a categorizing property where it named an entity-type axis; one property per trait, as built. [A trait narrows; it does not grant](../schema.md#traits) holds unchanged, whichever property each trait keys on: an attribute no trait claims is carried by every label, and a claimed one by every label some claiming trait matches. A trait on `entity_type: [Generator]` and one on `carrier: [wind]`, both claiming `p_max_pu`, give it to every generator and every wind entity. Every trait in the PyPSA tool reads as before.

A switch is addressed by exactly the dim its trait's property categorizes, and a trait with a switch must have an `on`.

**`switch` is not subsumed.** A category is a property — one value per label, never varying along another axis — while a switch may: `p_nom_extendable` per `investment_period` is a trait an entity carries in some periods and not others. Lifting the [trait-switches restriction](dep-0003-trait-switches.md#what-it-opens) to the categorized dim exactly is step 2: `switch` would then name a property of the subject or an attribute addressed by it and further dims. Which categories _may_ carry a value stays a schema answer; which labels _do_ in a given period stays a question about data.

### A NULL reaches the labels carrying the attribute

`entity` broadcasts like any dim: a row leaving it NULL means every entity. On a categorized dim, **every** is narrowed by the schema — a NULL expands only to the labels that carry the attribute (`attributes_for`), judged by their categories at read time. `set("p_max_pu", 0.9)` reaches every generator, those added in a later layer included, and never a bus. One filter where the fold expands a NULL, and the old "every entity whose type declares it" without a list of names stored.

### `entity` is an ordinary dim

With the categories a property and the fold key a schema declaration, nothing in core names `entity`:

- **The fold key** is exactly what `partial` lists — dims and groups alike. Every dim and every group broadcasts. A dim a group draws on need not be in `partial`: its dead labels are kept and dropped on read ([deletion](dep-0011-deletion-cascades-through-tombstones.md)).
- **Deletion** is [tombstones cascading](dep-0011-deletion-cascades-through-tombstones.md): `remove(dim, labels)` tombstones the labels and every live tuple of a group with a field over `dim` naming one; the fold anti-joins the tombstones of every `partial` dim and group.
- **The read API** answers per record, not per type: `Record`, `Resolver`, `Fold` and `LayerData` lose `entity_types`, `entity_type(ctype)` and `entity_axis`, and `flags()` takes no type. A per-category frame is `dims[dim]` filtered on a categorizing column.
- **Uniqueness** across types is structural: one axis row per label.

### One file per subject on disk

**On disk**, every property of a dim is a column of `dims/<dim>.parquet`, categories and all, NULL on a row whose category does not carry it. `dims/entity_type/<Type>.parquet` goes, and with it the second entity-axis layout [the member-file proposal](dep-0006-a-member-file-holds-values.md#what-it-costs) introduced: a record with and one without categories have one layout, differing by one column.

Per-type files existed because every type has a different column set. The schema now says which columns each category carries, so a category's frame is a filter on its property and a projection to those columns — recoverable from one file, where per-type files would state each entity's category twice, once in the column and once in the filename. Parquet stores an all-NULL column chunk for almost nothing and DuckDB reads only what it projects. Only a per-category **dtype** would need per-category files, and that is ruled out above.

### Editing is generic over dims

`WorkingRecord` loses its per-type calls (`add(ctype, frame)`, `remove(ctype, names)`, `set(..., entity=…)`) for ones over any dim:

```python
w.add("entity", ["g1", "g2"], entity_type="Generator", carrier="wind")
w.set("carrier", "solar", entity="g2")  # a property: one column of one axis row
w.set("p_max_pu", 0.9)  # every generator, now and later
w.set("efficiency", 0.7, entity="l1", bus="b0")  # a group's fields by keyword
w.set(
    "p_max_pu", 0.8, entity_type="Generator", carrier="wind"
)  # the wind generators there are now
w.remove("entity", ["g1"])  # tombstones g1 and its connections
```

- **`add(dim, labels, **columns)`** writes whole axis rows: a column must be one the axis file has — a property, a single-dim attribute, a parent key of a nested dim. An `Enum` property's value must be one of its categories.
- **`set(attribute, value, **coords)`** addresses every coordinate by keyword, a group's fields included. It writes a property too, a category included, as a patch of one column of the axis row.
- **A property keyword selects labels when `set` is called.** `entity_type="Generator", carrier="wind"` resolves to the labels matching both on the record as staged, and `set` writes one row per label — nothing of the filter is stored. A label added later is not reached; a plain NULL (every label carrying the attribute) and `default_by` are the two ways a value reaches labels not yet added. Storing a category in the row instead is the [optional stage](#optional-stage-categories-in-attribute-rows).
- **`remove(dim, labels)`** writes axis tombstones and cascades to group tuples.

Adding a component with its connections and varying values is now `add`, `add_group` and a `set` per attribute, where the old wide-frame `add` split one frame three ways. Whether a wide-frame convenience comes back, over the generic calls, is open below.

## Step 2: the section decides where a value lives

| declared as           | lands in                                         |
| --------------------- | ------------------------------------------------ |
| property of a dim     | `dims/<dim>.parquet` — a column of the axis file |
| attribute, any `dims` | `inputs/<attr>.parquet` — long rows              |

That replaces [where a value lives](../format.md#where-a-value-lives) as a rule over `len(dims)`. `inputs/p_nom.parquet` is `entity | attribute | breakpoint | value`, one row per entity, and widening `p_nom` over `scenario` adds a column to the same file — NULL in every row written before, which is what [the broadcast rule](../record.md#the-broadcast-rule) needs to read them unchanged. An axis file then carries only its labels, its `within` keys, its tombstones and the subject's properties; no data.

Step 1 keeps single-dim attributes as axis columns, so no file moves yet.

**In the API** each accessor then holds one section:

```python
record.dims["entity"]  # entity — labels only
record.properties["entity"]  # entity | entity_type | carrier | sign | ...
record.attributes["p_nom"]  # entity | attribute | breakpoint | value
record.attributes["p_max_pu"]  # entity | snapshot | attribute | breakpoint | value
```

`properties[dim]` holds stored values, no defaults applied. A framework's static frame — PyPSA's `n.generators` — is that frame filtered on a category, its `default_by` filled, and joined with the entity-only rows of its attributes; the tool keeps calling it `entity_types`. `Schema.attributes_for` splits into `properties_for` and `attributes_for`, both narrowed by the same traits.

Also step 2: **properties of a group** (`connection.role`, today an attribute over `connection`), and **per-category flags** — `flags()` per record loses what PyPSA's `verify` checked per type.

## Optional: `members`

Status: **deferred** — not part of the accepted scope, until a caller needs it. `properties[dim]`, stored values without defaults, and `flags(**categories)` cover what is read today.

```python
record.members(
    "entity", entity_type="Generator"
)  # entity | carrier | sign | ... — its rows, its properties
```

A per-category read — `members` here, the name open — would filter a dim's labels on its categorizing properties and project to the properties those labels carry, with `default_by` applied; no attribute columns. A framework's static frame would be that frame joined with the entity-only rows of its attributes.

## Optional stage: categories in attribute rows

Status: **to be decided** — implications first, independent of step 2.

A row of `inputs/` would carry a categorizing property as a column, narrowing a NULL along its dim: `entity` NULL and `entity_type = Generator` reads "every generator", those added in a later layer included, where a staging-time filter writes the generators there are now.

```text
inputs/p_max_pu.parquet
entity | entity_type | snapshot | attribute | breakpoint | value
NULL   | Generator   | NULL     | p_max_pu  | NULL       | 0.9    every generator, now and later
g7     | NULL        | NULL     | p_max_pu  | NULL       | 0.5    one label
```

It is the step-1 broadcast filter — a NULL reaching only the labels carrying the attribute — with a category chosen by the row as well as by the schema.

What it would mean:

- **The format.** Every attribute reaching a categorized dim gains its categorizing properties as columns of its long rows — `long_columns_for` grows by one per property reached. Adding one to a schema is compatible: old rows read NULL, which filters nothing.
- **Reach follows the category.** The filter is evaluated at read time against each label's current category, so a label re-categorized by `set` moves into or out of the row's reach — what "every wind generator" means. A non-`Enum` property cannot be stored as a filter, as it cannot key a trait.
- **The fold.** The filter applies where a NULL is expanded, against the resolved axis, before the owner map is keyed, so the owner key keeps its shape and the column never reaches a reader. A row naming its label explicitly has the column NULL; a non-NULL category on an explicit label is redundant at best and is refused.
- **Overlap within one layer.** Today a staged row is replaced by its key. A category row and an explicit row, or two category rows on different properties, have different keys and reach the same label. That needs a specificity rule — explicit label over category row over plain NULL — and two rows of equal specificity reaching one label refused at staging.
- **Overlap across layers** is unchanged: last writer wins per expanded key, so a later layer's category row overrides an earlier layer's explicit value for every label it reaches, exactly as a later plain NULL does.
- **Flags.** `broadcast` says a row left a dim NULL; a category row is a narrowed broadcast. Either it counts as broadcast (the narrowing invisible to `flags`) or `flags` gains a third state.
- **Groups.** A value over `connection` reaches `entity` through a field; its category column names the category of that field. A group drawing twice on one categorized dim — a corridor `(from, to)` — would need a column per field, and is refused until wanted.
- **Against `default_by`.** Two per-category mechanisms: the schema's default and a layer's category row. Data wins where it reaches; the default fills the rest. The difference is who declares it — a schema author once, or any layer.
- **The read and the write.** `record.attributes` stays per label, the category expanded away; `write_layer` checks the column's values are categories carrying the attribute; `set(..., entity_type=…)` writes the column instead of resolving labels.

What would decide it: a case where layer data, not the schema, must reach every label of one category, those not yet added included, for an attribute other categories carry too. Until one appears, staging-time filters cover the rest.

## What this buys

**The entity-type special cases go.** The dim, the group into it, the group-file exception, the reserved name, the two entity-axis layouts, and every literal `"entity"` in core — all of them were there to make one dim and one of its properties special.

**Categories need no new construct.** An `Enum` property of a `partial` dim is one; any dim may have several, and a `bus_type` scopes traits and defaults over buses exactly as `entity_type` does over entities.

**A registry's per-type defaults round-trip.** `sign`, `carrier`, `p_min_pu` and `p_set` are declared as PyPSA defines them instead of written out as data or lost.

**Step 2: each section answers where its values are read**, `p_nom` included — the confusion this starts from — and widening an attribute's `dims` is compatible in fact.

## What it costs

**The read API answers less, for now.** No per-type flags until step 2, no per-type frame and no applied defaults; PyPSA filters the entity axis itself, and its `verify` counts an attribute one type owns as owned by every type.

**`partial` must list what used to be implicit.** A schema keying traits or defaults on `entity`'s categories must put `entity` in `partial`; a schema omitting it is refused rather than silently keyed.

**A category is schema vocabulary.** Making `carrier` categorizing means an `Enum`, so adding a carrier is a schema change.

**Re-categorized labels keep stale values.** A label whose category changes keeps what it held for attributes it no longer carries; they are out of every per-category read's reach, but stored.

**Entity-only data reads through the fold, not the axis** (step 2). `p_nom` was a column resolved with the entity row; it becomes long rows keyed by the [fold key](../schema.md#partial-the-granularity-of-an-override) like any attribute — a static frame of forty columns is forty attribute reads and a pivot where it was one file.

**The choice is the author's, and can be wrong.** Nothing derives whether `x` on a bus is metadata or data; a schema declaring it either way is valid. Moving a name between sections moves its file and is an [incompatible change](../schema.md#versioning).

**A per-type value addressed by the type alone loses its home.** An `icon` per entity type lived on `dims/entity_type.parquet`; with no `entity_type` dim there is no file keyed by category. Nothing in the tools declares one; if a case appears, it is a property of a dim declared for the purpose.

**Every manifest is rewritten**, and every record re-exported: the entity-type dim and group become one property, and `entity` joins `partial`. [Breaking changes are free](https://github.com/energy-models/datarecord/blob/main/AGENTS.md).

## What it opens

**Whether a functional group over one coordinate is a property.** `country` over `[bus]` `into` `country` is one label per bus — metadata, of a dtype ranging over a dim. The old entity-type axis was exactly that, and this proposal turns it into a property; `into` might go the same way, or [the chain argument](../schema.md#within-is-not-into) might keep it a group.

**Whether wide-frame editing comes back** — one call adding a component with its properties, connections and values, built on `add`, `add_group` and `set`, as the inverse of what `to_datarecord` produces.

**Whether a broadcast survives materialisation.** A materialised ancestor's owner map stores a NULL row already expanded to the labels that existed then, and seeds a child's fold without re-expanding. So `set("p_max_pu", 0.9)` reaches a generator added — or re-categorized — in a child only while the ancestor is unmaterialised; plain NULLs behave the same today. One level down, a `WorkingRecord` folds its committed prefix once, so a label staged or re-categorized there is not reached by a parent's NULL even while the parent is unmaterialised. To be gone into once this proposal is built.

**Whether groups edit like dims.** A group is a dim, yet is edited through `add_group`/`remove_group` with a struct frame where `set` takes its fields by keyword; `add(name, keys, **columns)` over a group would close that.

## Status

Steps 1 and 2 are built on `feat/properties-structs`, and the design pages, usage pages and changelog follow them. Two departures from the text above:

- **No `partial` rule for groups.** A dim a group draws on need not be in `partial`; its dead labels already cover deletion. The only `partial` requirement is a categorized dim's.
- **A `default_by` is applied by its reader.** `record.properties` and `record.attributes` show stored rows, and a reader fills a per-category default through `Schema.default_for`, as the PyPSA tool does.

Neither [`members`](#optional-members) nor the optional stage is built.

## How to know it worked

**No `entity` or `entity_type` in `src/datarecord` outside `tools/`, docstrings and tests.** The names are only data — a dim and a property a schema happens to declare.

**A record with and one without categories differ on disk by one column.** Same files, `dims/entity.parquet` with or without `entity_type`, no `dims/entity_type/` in either.

**A category on `bus` works like one on `entity`.** A trait `on: {bus_type: [DC]}` narrows attributes over `bus`, and `default_by: {bus_type: …}` validates.

**Two categorizing properties of one dim combine.** Traits on `entity_type: [Generator]` and `carrier: [wind]` claiming one attribute give it to both sets of labels.

**`set("p_max_pu", 0.9)` reaches every generator, a later-added one included, and no bus.**

**A trait keyed on a `String` property, or on a property of a dim outside `partial`, is refused.**

**PyPSA round-trips `sign` and `p_min_pu` with nothing written** (step 2). An `add` of a Load and a StorageUnit setting neither reads back `sign == -1` and `p_min_pu == -1`.

**`p_nom` is in `record.attributes`** (step 2), `inputs/p_nom.parquet` holds one row per entity, and widening it over `scenario` reads an old layer's values back in every scenario.

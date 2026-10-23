<!--
SPDX-FileCopyrightText: datarecord contributors

SPDX-License-Identifier: CC-BY-4.0
-->

# DEP 2: groups — one construct for classification and sparsity

| DEP     | 2                                                      |
| ------- | ------------------------------------------------------ |
| Title   | groups — one construct for classification and sparsity |
| Author  | Jonas Hörsch                                           |
| Status  | Implemented 2026-09-01                                 |
| Created | 2026-08-27                                             |
| Version | v0.1.0a1                                               |

Landed in [the schema](../schema.md#groups) and [the record format](../format.md#where-a-value-lives); this page is kept as the argument for the change rather than as the current description.

Supersedes the split between [groups](../schema.md#groups) and [`on`](dep-0001-dims-groups-traits.md#mappings) that [dims, mappings, groups and traits](dep-0001-dims-groups-traits.md) landed.
Those two are one mechanism with one field's difference, and the field is worth having where the two models are not.

## What starts it

The schema declares two things that are both "which tuples over dims exist".

A `Group` says it directly — `over={"entity": "entity", "bus": "bus"}`, a sparse subset of a product.
A mapping says it sideways — `Dimension(on={"bus"})` for `country`, which is the same statement narrowed to the case where each `bus` appears once.
They are stored differently, addressed differently, aggregated differently, and validated by different code, on the strength of a distinction that is one uniqueness constraint.

The cost shows up when a consumer writes math. Aggregating along a mapping is dim aggregation (`GROUP BY country`); aggregating along a group needs to say which coordinate survives. Two spellings for one operation, and a modeller has to know which kind of thing they are holding before they can write the sum. No framework we looked at splits them: GAMS declares both as a set over a tuple of sets, Calliope reaches for a lookup array either way, PyPSA carries a bus column — so the split is ours rather than the domain's.

The narrow observation is that `on` is a group whose codomain happens to be a declared axis.
The wider one is that the axis is the _only_ thing it adds, and that a field naming it collapses the two models without losing what either declares.

## The construct

One section, `groups`, absorbing `Dimension.on`:

```yaml
dimensions:
  entity: { dtype: string }
  bus: { dtype: string }
  country: { dtype: string }
  timestep: { dtype: date }

groups:
  country:
    over: [bus]
    into: country
  connection:
    over: [entity, bus]
  corridor:
    over: { from: bus, to: bus }
```

`over` declares the coordinates. `into` names the dim a group is functional into, and is what makes it a mapping in the narrow sense: **each tuple of `over` carries exactly one label of `into`**.

- **`into` present** — single-valued. The group `country` partitions buses into the dim `country`, sharing its name; `dims/country.parquet` exists and the dim is addressable, while the group is the relation and declares a uniqueness constraint on `over`.
- **`into` absent** — a sparse tuple set and nothing more. `connection` has no label set of its own, is not a dim, and never appears as a column.

`over` accepts a list where coordinate names equal dim names, and a dict where they do not — `corridor`, a transmission path between two nodes, needs `{from, to}` over one `bus` dim, which a list cannot spell.
The list form is sugar for the dict form with identical keys and values.

`group` stays the word, and is true of the functional case too — `country` groups buses, in the direction `into` names.
It is overloaded in the surrounding tooling, though — `GROUP BY`, PyPSA's `group_constraints`, Calliope's `group` — so prose about [aggregation](#aggregation) has to say which is meant.

### Why `into` is the right field

It is the declaration that was missing rather than a label on an existing distinction.

A group cannot say "single-valued"; it can only happen to be, which leaves a duplicate row a data error the schema has no name for.
`into` names it, so the constraint is declared and checkable, and the two cases stop being two models: `groups/country.parquet` with `into` and `groups/connection.parquet` without differ in what the schema promises about their rows, not in what kind of object they are.

**No existing system declares it, and that is the argument for `into` rather than against it.**
GAMS gets the one-construct half right — `map(b,c)` and `conn(e,b)` are both a set over a tuple of sets, and `Alias` gives two coordinates over one set distinct names, which is what `over`'s dict form does locally instead of globally.
But GAMS has no way to say `map` is functional: single-valuedness is a convention the modeller maintains, and breaking it yields a wrong answer with no error, because a duplicated `b` silently double-counts in every `sum(b$map(b,c), ...)`.
Calliope is the same, one step further along — `select_from_lookup_arrays` presumes a functional lookup and its `where` gating cannot express the presumption.

A schema whose purpose is to make the shape of data checkable should not inherit that gap. `into` is the declaration neither has, and closing it is a choice this proposal makes rather than a precedent it follows.

### `into` must name a declared dim

Not a name the group invents.

That is what keeps the axis file, and the axis file is the whole of what a functional group has over a bare tuple set: `dims/country.parquet` gives `country` its [order](../record.md#axis-order) and somewhere for a per-country CO2 budget to live.
A group whose `into` named nothing would be a tuple set with a labelled column — expressible, and it loses the axis, which is [the argument the superseded page makes](dep-0001-dims-groups-traits.md#mappings) and which survives this refactor unchanged.

**A group may share its name with a dim**, and the [existing prohibition](../schema.md#groups) on the two colliding is dropped rather than narrowed.

For a group with `into` the sharing is the natural spelling: the dim is the axis of labels, the group is the relation between it and `over`, and they are reached by different syntax — [`dims: [country]`](#addressing-dims-x) finds the dim, [`by=country`](#aggregation) finds the group. Keeping the prohibition would cost a name (`country_map`) invented only to satisfy it.

Nothing then justifies the prohibition in the `into`-less case either. [Addressing](#addressing-dims-x) resolves the dim namespace first, so a dim and a group both called `connection` is not ambiguous — `dims: [connection]` is the dim — and one rule covers every collision instead of a rule plus a guard.

What it gives up is a schema error. A shadowed `into`-less group loses its only spelling in `dims`, and no longer says so at load time; a shadowed functional group loses a spelling it had no use for.
That asymmetry is the argument for keeping the prohibition, and it is not worth a second rule: the collision has to be authored deliberately, both entries are visible in one file, and a lint naming the shadowed group is a better answer than a prohibition that also rejects the harmless case.

### `into` over several coordinates

`over: [bus, scenario]` with `into: country` — a bus whose country varies per scenario — is allowed.

Nothing about `into` assumes one coordinate. The constraint it declares is already per-tuple — each tuple of `over` carries exactly one label of `into` — so over two coordinates it is a uniqueness constraint on `(bus, scenario)`, and [`by=`](#aggregation) still keeps `into` and collapses all of `over`.

It costs nothing in storage because [every group is a file](#where-the-rows-live): `groups/country.parquet` is `bus | scenario | country`, keyed like any other group.
The restriction would only be needed if a single-coordinate functional group were stored as a column on its coordinate's axis file — a column asserting bus→country has nowhere to live once the key is `(bus, scenario)` — and that form is not kept.

## Addressing: `dims: [X]`

An attribute names a group in its `dims` exactly as it names a dim, and one rule resolves both:

**`X` is the dim `X` if one is declared, and otherwise the group `X` expanded to its `over` coordinates.**

```yaml
efficiency: # no dim `connection`  -> the group, expanded
  dims: [connection, timestep] #   entity | bus | timestep
co2_budget: # `country` is a dim   -> the dim
  dims: [country] #   country
```

A group with no dim of its name has no other spelling — `connection` is not addressable as anything else — so expanding it is the only way to declare an attribute over it, and the expansion is what keeps [the fold's key](../schema.md#partial-the-granularity-of-an-override) one fixed tuple.

A group sharing a dim's name is shadowed here, which for a functional group is what should happen: a value that is genuinely per-country is `dims: [country]`, the dim, which is what [the axis file](#into-must-name-a-declared-dim) exists for, and expanding instead would give `dims: [bus]` written so the reader has to look up the group's `over` to see it.

So `dims` names dims, plus groups that no dim shadows as sugar for their coordinates — and `into` is not consulted, because it decides nothing here.
Where it does decide something is [aggregation](#aggregation): `over=` and `by=` resolve on the group, and `by=country` keeps country while collapsing buses. There is no spelling of `dims` that means "the buses of a country".

## Attributes on a relation between two entities

A group's coordinates may both draw on `entity`, so a relation between two components carries attributes like anything else.

A power purchase agreement is the case: a contract between a generator and an offtaker, with a volume and a strike price that are properties of neither party alone.

```yaml
groups:
  contract:
    over: { seller: entity, buyer: entity }

attributes:
  contracted_volume:
    dtype: float64
    dims: [contract, timestep] # seller | buyer | timestep
  strike_price:
    dtype: float64
    dims: [contract] # seller | buyer
```

The declaration is [already possible](../schema.md#groups) and this proposal does not introduce it — `over`'s dict form is what lets two coordinates draw on one dim, and [addressing](#addressing-dims-x) expands `contract` to `seller | buyer` as it always did.
What changes is that the shape stops being second-class:

- **It has a file of its own.** `groups/contract.parquet`, keyed `(seller, buyer)`. The [`<Type>` split](#where-the-rows-live) had no type to split on here — a contract is not a component and has no `entity_type` — so it never described this case at all, which is what shows the split was wrong rather than merely awkward.
- **It has an aggregation spelling.** `over=contract[buyer]` gives a generator's total contracted volume across offtakers, `over=contract[seller]` an offtaker's total procurement, and neither had a way to be written before.
- **It may be declared functional.** `over: [entity], into: parent` with `parent` a dim of entities is a hierarchy — each component under one other — which the [uniqueness constraint](#why-into-is-the-right-field) checks and `by=parent` aggregates up. `Dimension.on` could not express a mapping from entities to entities at all, so this case is new rather than merely better served.

Nothing about `entity` is privileged in any of this. `corridor` between two buses, a contract between two components, a relation between a bus and a country are one declaration, and the record neither knows nor needs to know which coordinates happen to name components.

## Where the rows live

`groups/<name>.parquet`, one file per group, always — one rule for [the format page](../format.md#where-a-value-lives) to state, with no case left for the declaration to imply.

```text
groups/country.parquet      bus | country
groups/connection.parquet   entity | bus | role
groups/corridor.parquet     from | to
groups/contract.parquet     seller | buyer | strike_price
```

Two departures from what shipped, both deliberate.

**No `<Type>` split.** `dims/<group>/<Type>.parquet` is gone.
A group's rows are keyed by its coordinates, and `entity_type` is not one of them — the split puts `connection` rows for a `Link` and a `Line` in different files despite identical keys, forcing a union on every read and privileging `entity` among the coordinates.
`corridor` has no type to split on at all, and [`contract`](#attributes-on-a-relation-between-two-entities) has two — one per coordinate, neither of them the row's — so the split never generalised beyond the case it was written for.
`Schema.group_columns` leads with `entity_type` today and stops doing so.

**No column on the classified axis.** `dims/bus.parquet` does not gain a `country` column; `groups/country.parquet` carries `(bus, country)`.

The column form is what forces the [no-denormalisation argument](dep-0001-dims-groups-traits.md#mappings) — `bus → state → country` as one hop per file, because two files asserting bus→country would let a layer restating states leave every bus's country stale.
A file per group gives that property for free: the chain is a join over two files either way, and a layer restating a group restates exactly one file.
The cost is that reading a bus's country is a join rather than a column read, which is cheap and buys a uniform rule — `into` no longer decides storage, so nothing about the file layout branches on it.

## Aggregation

The operation both cases wanted, spelled once.

For a consumer's math language, `over=<group>[coords]` collapses the bracketed coordinates and keeps the rest:

```text
sum(x, over=connection[entity])      # collapse entity, keep bus
sum(x, over=corridor[from])          # keep to
sum(x, over=contract[buyer])         # keep seller: volume sold per generator
sum(x, over=country[bus])            # collapse bus, keep country
```

`over=` always names what goes, never what stays — the sense it already carries where it takes a plain dim.

lowering to a group-by over a join:

```sql
SELECT bus, timestep, SUM(...) FROM connection JOIN p USING (entity)
GROUP BY bus, timestep
```

**`by=<group>` is the other direction, and takes a second keyword because it means the opposite thing.**

```text
sum(x, by=country)                   # keep country, collapse the rest
```

`by=` names what survives, and is what `GROUP BY country` says.
Overloading `over=` for it — a bare `over=country` reading as "keep country" — would give one keyword two senses, and the bare form would be the one that names a coordinate the expression never mentions while collapsing one it does.

`by=` is available only where `into` is declared, because only then is there a survivor to name: `by=g` keeps `g`'s `into` dim and collapses all of `over`.
That is the whole of what `into` buys a consumer beyond the uniqueness constraint, and it is a licence rather than a hint — the aggregation is well-defined because the dependency is declared, not because the record guessed which way a modeller meant to sum.

The two coincide on a single-coordinate functional group, where `by=country` and `over=country[bus]` are one query written two ways, which is no worse than `GROUP BY` and "sum over" both being idiomatic English for it.

**The bracket is mandatory on every `over=` naming a multi-coordinate group**, including where it could be inferred.
A functional group needs it whenever a coordinate must survive that `by=` would collapse: `over=country[bus]` on `over: [bus, scenario]` keeps `(scenario, country)`, a per-scenario country total that `by=country` cannot spell.
Inference from the enclosing scope fails under nesting: `sum(sum(x, over=connection), over=siting)` over `(bus, site)` would have the inner sum collapse both of its coordinates, because neither is bound outside it, destroying the `bus` the outer sum needs — silently, with the right shape and the wrong number.
Stating the collapse set makes a sub-expression mean the same thing wherever it appears, and resolution one inside-out pass with the constraint's index set as a check rather than an input.

`over=` is then the same statement along a functional group and along a bare tuple set, which is the point: a modeller collapses a coordinate without first knowing which kind of thing they hold.
`into` adds `by=` on top of that rather than changing it, so the two constructs stay one where it matters and differ only where a declared dependency makes a second operation possible.

## Implementation sketch

**`into` is sugar, resolved once at parse.** A group declaring it normalises to the coordinates it implies, and everything downstream sees one kind of group:

```python
Group(over=["bus"], into="country")     # what the author writes
Group(over=["bus", "country"], ...)     # what `coordinates` returns
```

So `group_coordinates`, `group_columns`, the [file layout](#where-the-rows-live), the fold's key and [`dims:` expansion](#addressing-dims-x) read `coordinates` and never branch on `into`.
`groups/country.parquet` carrying `bus | country` is not a rule about functional groups — it is the same rule that gives `connection` its `entity | bus`, applied to coordinates that happen to come from sugar.

`into` is retained on the model rather than discarded, because three things still need it:

- **the uniqueness constraint** — the key is `coordinates` minus `into`, which is what makes the group functional and is checkable on write;
- **[`by=`](#aggregation)** — a consumer needs to know which coordinate survives;
- **round-tripping the manifest** — writing back `over: [bus, country]` where the author wrote `into:` would silently rewrite their schema.

Each is a leaf: no traversal, no read path and no layer resolution consults `into`.

**`into` must name a declared dim, checked beside the existing `over`-names-declared-dims validator.** The field is retained, so the check reads it directly and does not care whether the coordinates have been flattened yet.

It is worth erroring rather than tolerating, because the failure is otherwise silent: a dim shadows a group of its name, so an `into` naming a dim nobody declared leaves `dims: [country]` quietly expanding to `bus | country` instead of naming the axis it was meant to.
The [collision check](#into-must-name-a-declared-dim) in the same validator goes, being what this proposal drops.

## What does not change

- **A coordinate never broadcasts.** A NULL `bus` on a connection attribute is [the group's rows](../record.md#the-broadcast-rule), not the bus axis — there is no axis to expand against.
- **A group in `dims` expands to its coordinates** where it is not itself a dim ([addressing](#addressing-dims-x)), so the fold's key stays one fixed tuple.
- **The record does not resolve across levels.** An attribute over `country` comes back keyed by country; projecting to buses is the consumer's join.
- **`within` is untouched** and stays distinct: it scopes a label per parent, where `into` partitions one axis by another.
- **Traits are untouched.**
- Names live in one namespace, now [resolved rather than policed](#into-must-name-a-declared-dim): a dim wins, a group is what is left.

## What it costs

**A rename across the tree.** `Dimension.on` and `Dimension.mapping` go, `Schema.mappings_on` with them, and `WorkingRecord`'s `kind=` and the `CONNECTION` constant in `mutable.py` stop naming one group specially.
`group_coordinates`, `group_columns` and `groups_of` keep both their names and their bodies, since [desugaring](#implementation-sketch) hands them coordinates like any other group's.
Breaking changes are free here, so this is work rather than risk.
Keeping `groups` as the word is what holds the rename to the parts that change meaning.

**A format migration.** `dims/<group>/<Type>.parquet` → `groups/<name>.parquet`, and a `country` column on an axis file → its own file. No reader keeps both layouts.

**A join where there was a column.** Bus → country is a file read and a join. Uniform, and slower than the column it replaces.

## What it opens

**Whether a shadowed group warrants a warning.** Dropping the collision prohibition makes an `into`-less group that shares a dim's name unreachable in `dims` without saying so. A lint at load naming the shadowed group would recover what the prohibition caught, without also rejecting the functional case it was never about.

**Whether a group's rows are validated against its coordinate dims' labels.** GAMS domain-checks a relation at compile time and treats it as the primary error the construct exists to catch; nothing here does, before or after this change.

**Whether a consumer needs more than the dependency.** `into` declares a functional dependency, which is a record-level fact and checkable as one; [`by=`](#aggregation) is a consumer's operation that the dependency licenses.
Keeping those separate is what stops the record from storing hints for someone else's `sum` — the record says what is true of the data, and the math language decides what that makes possible.
Whether every consumer-side aggregation factors that cleanly is untested against a second consumer.

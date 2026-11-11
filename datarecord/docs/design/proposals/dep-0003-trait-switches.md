<!--
SPDX-FileCopyrightText: datarecord contributors

SPDX-License-Identifier: CC-BY-4.0
-->

# DEP 3: trait switches — a trait a component opts into

| DEP     | 3                                              |
| ------- | ---------------------------------------------- |
| Title   | trait switches — a trait a component opts into |
| Author  | Jonas Hörsch                                   |
| Status  | Draft                                          |
| Created | 2026-08-27                                     |

Stacked on [groups](dep-0002-groups.md), which it does not depend on but shares a direction with: what a record can say about a component should be declared rather than encoded in a type name.

## What starts it

A trait is scoped by entity type and by nothing else, so a distinction that is not about the type has nowhere to go — whether finer than a type, or orthogonal to types in a record that declares none.

`committable` is the case. In PyPSA a generator may be unit-committed, which decides whether `start_up_cost`, `min_up_time` and `ramp_limit_start_up` mean anything for it — and it is a property of the individual generator, not of `Generator`. Today the schema can only say that every generator carries them, so a record holds the attributes on all 3000 generators to describe the fifty that are committable, and a consumer that wants the distinction reads a boolean attribute the schema never connected to the bundle.

The same shape recurs wherever a framework has an opt-in behaviour: `cyclic_state_of_charge` on a storage unit, `e_cyclic` on a store, transmission losses on a link, an extendable-versus-fixed capacity split.

It is the minority of traits. `investable` and `dispatchable` are properties of a _type_ — every generator is dispatchable — and the type scope is the right and only scope for them. What is missing is a way to say the other thing, not a replacement for what `on` says.

[Only an entity-type axis may scope a trait](../schema.md#traits), and that rule is right: a trait scoped to `country` would make an attribute's vocabulary depend on what a bus maps to, a per-entity lookup every caller of `attributes_for` treats as answerable from the schema alone. The rule bans scoping a trait on _data_.

But a switch is not data of that kind. It is a declared attribute of the component itself, with a known dtype and a default, and the vocabulary it selects is fixed by the schema — which of two known answers applies is per entity, and both answers are on the page before any row is read.

## The construct

**A trait narrows two ways, and both are optional.** `on` says which entity types carry it and reaches every type when absent; `switch` names an attribute deciding it per component, and gates nothing when absent.
Neither is the primary mechanism the other qualifies — a trait may use either, both or [neither](#the-four-combinations), and `on` reaching everywhere is [what it already means](../schema.md#traits) rather than anything this proposal adds.

The new half is `switch`, an attribute of the trait's own that turns it on:

```yaml
traits:
  committable:
    attributes: [start_up_cost, shut_down_cost, min_up_time, ramp_limit_start_up]
    on: { entity_type: [Generator, Link] }
    switch: committable # joins `attributes` on its own

attributes:
  committable:
    dtype: bool
    dims: [entity]
    default: false
```

`switch` names an attribute the schema declares, `dims: [entity]` exactly — the switch is per component, which is the whole of what it adds over `on`.

**The switch joins the trait's `attributes` on its own**, added during [normalisation](#implementation-sketch) rather than listed by the author.
Naming it twice would be two ways to say one thing: a trait whose `switch` is not among its attributes is not a coherent declaration, so the schema completes it instead of rejecting it.
A consumer asking what `committable` bundles gets the switch along with the rest, which is what makes the trait queryable as one object.

**`switch` is optional, and most traits want none.** A behaviour every component of a type has is not a switch — every generator is dispatchable, so `dispatchable` stays exactly as it is:

```yaml
dispatchable:
  attributes: [p_min_pu, p_max_pu, p_set]
  on: { entity_type: [Generator, Link] }
```

No switch column, no per-component narrowing, nothing new to read. A switch earns its place only where a framework has a genuine opt-in — where the answer differs between two components of one type — and adding one where it does not is a column of `true` that says nothing.

### The four combinations

| `on` | `switch` | reaches                                |
| ---- | -------- | -------------------------------------- |
| —    | —        | every component, of every type         |
| yes  | —        | every component of the listed types    |
| —    | yes      | the components whose switch is true    |
| yes  | yes      | those of the listed types, switch true |

The third row is the one worth naming: **a switched trait needs no entity-type axis at all.** A record declaring no types can still say that some components are committable and others are not, which the type scope could never express — and a schema with types may still gate a trait without listing any, where the opt-in is genuinely orthogonal to what kind of thing a component is.

The two never interact. `committable` `on` `{Generator, Link}` reaches no `Store` whatever its switch column says, and reaches a generator only where its `committable` is true — `on` first, then `switch`, with no case where one changes what the other means.

### The switch is an ordinary attribute

Not a new kind of declaration. It has a `dtype`, a `default`, a `unit` if it wants one, it is written and read like anything else addressed by `entity`, and it lives where [an attribute over `entity` alone](../format.md#where-a-value-lives) already lives.

That it also names a trait changes nothing about it, which is what keeps the mechanism cheap: no new file, no new column kind, no new resolution rule, and a record whose consumer does not care about traits sees a boolean it can read.

**Its default decides the unset case**, and `false` is the one to declare. A component that never mentions the switch is not committable, which is what a reader expects and what keeps the bundle off every component that predates the trait.

**A switch is not narrowed by its own trait.** Being [in the bundle](#the-construct) it would otherwise be, and the attribute deciding a trait cannot be gated by the trait it decides — nothing could ever turn it on.

So the switch is in `attributes` for discovery and out of the narrowing: `committable` the attribute is carried by every type `committable` the trait is `on`, whatever any component's value.
It is the one attribute a trait bundles without restricting, which is what being the switch means.

### Which dtypes

`bool` is the case that motivates this and the one to allow first.

An `Enum` switch selecting among several traits is the obvious generalisation — `capacity_mode` of `fixed`/`extendable`/`committable`, with three traits each naming the same attribute and a different label — and it is deferred rather than rejected: it needs a way to say _which label_ turns a trait on, which is a second field (`switch_value`), and no case in the tools demands it yet.

A `bool` switch is that generalisation with the label fixed at `true`, so admitting it later widens rather than reshapes.

## What it changes for `attributes_for`

`Schema.attributes_for(ctype)` answers from the schema alone, and it must keep doing so.

A switched trait's attributes are **carried by the type** — `attributes_for("Generator")` includes `start_up_cost` — because the question it answers is which attributes a generator _may_ have, which is what [`flags`](../record.md#flags) and the [`add` routing](../working-record.md#add-remove) need. A schema-level answer cannot depend on a row, and it does not have to: the switch narrows which components carry a _value_, not which the type admits.

A trait gated only by a switch is therefore invisible to `attributes_for`, which is the right answer for the same reason: its attributes reach every type, and which components hold a value is a question about data.
A schema with no entity-type axis already has `attributes_for` [returning everything addressed by `entity`](../schema.md#traits) whatever it is asked, and a switch does not change that.

So the switch is a **validation and query mechanism, not a change to the vocabulary**:

- **A value set on a component whose switch is false is an error on write.** That is the check the mechanism exists for, and it is the one thing today's schema cannot express — it turns "these 3000 generators all have a `min_up_time` column, mostly NULL" into "fifty of them may, and setting the fifty-first is a mistake".
- **A consumer may ask which components a trait reaches.** `record.entities_with("committable")` is a filter on the switch column, which is the queryable half of what makes a trait worth declaring, now at component granularity rather than type.

Whether `attributes_for` grows a per-entity counterpart is left open below.

## Implementation sketch

**The switch is folded into `attributes` at parse**, so nothing downstream has to remember it is special:

```python
Trait(attributes={"start_up_cost", ...}, switch="committable")   # what the author writes
Trait(attributes={"start_up_cost", ..., "committable"}, ...)     # what `attributes` returns
```

`switch` is retained on the model, for the same reason [`into`](dep-0002-groups.md#implementation-sketch) is: two things still need it, and both are leaves.

- **`attributes_for`** excludes the switch from its own trait's narrowing — one membership test, where a trait's bundle is already being resolved.
- **The write-time check** reads it to find the column gating a value.

Validation is the [existing trait validator](../schema.md#traits), which already rejects a bundled attribute the schema does not declare; `switch` is checked the same way, plus that its `dims` are exactly `{"entity"}`.
Folding it into `attributes` before that check runs means the declared-attribute half needs no second call site.

## What it costs

**A second narrowing axis to explain.** A trait now cuts by type and by component, and a reader has to hold both. The saving grace is that they compose in one direction — `on` first, then `switch` — with no case where they interact.

**A validation that reads data.** Rejecting a value whose switch is false means the writer consults the switch column, which no `AttributeSpec` check does today. It is a join against `dims/entity.parquet` on write, in a path that already reads that file to check the entity exists.

**One more way to spell a boolean.** A record may carry `committable` as a plain attribute and ignore the trait, and both spellings will exist in the wild. The trait is the one that connects it to a bundle; nothing forces its use.

## What it opens

**An `Enum` switch and `switch_value`**, deferred above.

**Whether `attributes_for` needs a per-entity counterpart.** The schema-level answer stays type-scoped, and a caller wanting "what does _this_ generator carry" has to read the switch column itself. That is the same shape as the [open question](../open-questions.md) about a record-level `flags`, and probably wants the same answer.

**Whether a switch may be addressed by more than `entity`.** `dims: [entity, scenario]` would be a component committable in one scenario and not another, which is coherent and is the [existence-does-not-vary](../schema.md#existence-does-not-vary-along-a-dim) argument in a milder form — the component exists either way, only its vocabulary moves. Rejected here for the same reason that page gives, that what a tombstone or a coarser row means is unsettled, and worth revisiting only with a case.

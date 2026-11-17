<!--
SPDX-FileCopyrightText: datarecord contributors

SPDX-License-Identifier: CC-BY-4.0
-->

# DEP 6: a member file holds values, and nothing else

| DEP           | 6                                              |
| ------------- | ---------------------------------------------- |
| Title         | a member file holds values, and nothing else   |
| Author        | Jonas Hörsch                                   |
| Status        | Superseded 2026-10-13 (implemented 2026-09-04) |
| Created       | 2026-09-02                                     |
| Version       | v0.1.0a1                                       |
| Superseded-By | [DEP 12](dep-0012-properties.md)               |

> **Superseded** by [properties](dep-0012-properties.md#one-file-per-subject-on-disk):
> the entity-type axis is now an `Enum` property of `entity`, and a record with
> and one without categories share one entity-axis layout with no member files.
> The authoritative account is [the entity axis](../format.md#the-entity-axis),
> [where a value lives](../format.md#where-a-value-lives) and
> [categories](../schema.md#categories-an-enum-property-of-a-partial-dim); this
> page is kept as the argument that led to the intermediate layout. It keys on `entity_type_dim is None` (no group over
> `entity` alone), leaving a `String`-typed **declared** axis on today's per-type
> layout — the [open question](#what-it-opens-rather-than-settles) below was
> resolved that way. `entity_type(ctype)` **raises** where no type axis is
> declared rather than answering `None`. Cache invalidation on schema change is
> still not settled: a materialised cache written under the old layout is a
> rebuild, [as noted below](#the-column-leaves-the-entity-axis-too).

Two claims about `dims/entity_type/<Type>.parquet`, which are one claim: that file holds a type's attribute values, and everything about a component's _existence_ belongs to the [entity axis](../format.md#the-entity-axis).

Today it holds more. A record whose schema declares no entity-type axis still writes one member file per type — types that are not declared, not validated and not constrainable, yet decide which file a value is in, so a reader must know them to reach it. And every member file carries `deleted`, which the fold reads as a tombstone alongside the axis's own, so a removal is written twice to say one thing.

This proposal puts those values on `dims/entity.parquet` where the schema declares no entity-type axis, and takes `deleted` off the member file in every record. What is left in a member file is `entity` and one column per attribute.

The related concern — `entity_type` asserted rather than derived in the read path — is already settled: the [entity axis folds like any dim](../read-path.md#one-fold-for-every-axis) rather than through an owner map, so `entity_types()` reads the resolved axis directly and there is no map column set to make conditional. What remains is the member file itself.

## What starts it

[The schema](../schema.md#properties) is explicit that the axis is optional, and that omitting it makes the labels data:

> The entity-type axis's enum categories, so a schema declaring it as a plain `String` has none: the labels are then data rather than declarations, and `attributes_for` accepts any of them.

`tests/test_untyped.py` exercises that: a schema with two attributes over `entity` and no classifying group, components added under `thing` and `other`, and both round-trip. So far so good.

The problem is where their values land. `p_nom` is `dims={"entity"}` and non-varying, and the format gives that exactly one home — [`dims/entity_type/<Type>.parquet`](../format.md#where-a-value-lives). It cannot be a column of `dims/entity.parquet`, because `attributes_on("entity")` returns `()` by explicit early return; it cannot be an `inputs/` row, because it does not vary. So a label the schema never declared becomes a filename:

```
dims/entity.parquet             entity, entity_type, deleted
dims/entity_type/thing.parquet  entity, p_nom
dims/entity_type/other.parquet  entity, p_nom
```

**`entity_type` there is a column no declaration accounts for.** Every other column of an axis file answers to something: its key comes from `axis_key`, its attribute columns from `attributes_on`, `deleted` is structural. This one is admitted by a special case in `_validate_frame` and typed as a plain `String` by a fallback in `_axis_columns`, because there is no `Dimension` to read a dtype from. It is the one column in the format whose presence is not derivable from the schema.

## Why it cannot simply be dropped

The obvious move — no declared axis, no `entity_type` column — does not close, because the label carries the type wherever a per-type question is asked:

| reader                        | what it does with it                          |
| ----------------------------- | --------------------------------------------- |
| `NodeCache.entity_types()`    | `distinct_values(entity_axis, "entity_type")` |
| `NodeCache.entity_type_frame` | scopes to one type, then reads its file       |
| `NodeCache.attributes_of`     | scopes the flags to one type                  |

The label lives on the [resolved entity axis](../read-path.md#one-fold-for-every-axis), carried on the winning row like `weight` on `dims/scenario.parquet` — not in an owner map, since the entity axis folds like every other dim. So gating only the member file, and leaving `entity_type` on the axis filled with NULLs, leaves `entity_types()` yielding `{None}` rather than `{thing, other}`.

Deriving the label from the filenames instead works, but costs a `LayerSource.entity_types()` listing member files and a per-layer `LIST` on the read path — which is what [the entity axis exists to avoid](../format.md#the-entity-axis). Trading a stored string for a directory listing per layer per fold is the wrong direction.

So the label is load-bearing _given the current layout_. The layout is what this proposal changes.

## The construct

**Where a schema declares no entity-type axis, a non-varying attribute over `entity` is a column of `dims/entity.parquet`.** No `dims/entity_type/` directory, no per-type files, and `entity_type` is then genuinely absent — nothing classifies, so there is nothing to classify into.

```
dims/entity.parquet   entity, deleted, p_nom, ...
```

Which is what the entity axis already is for every other purpose: the file keyed by `entity` that carries what is true of a component. `attributes_on`'s early return — "Never `entity`, whose sole-coordinate attributes are the _component_ frame's columns" — becomes conditional on a type axis existing, which is the one line of schema that decides the whole layout.

### The column leaves the entity axis too

The layout change is not enough on its own: the resolved entity axis carries `entity_type` on its winning row, so **that** is where the column has to become conditional. The axis frame a source supplies is `(entity, entity_type, deleted)`; where the schema declares no type axis it is `(entity, deleted, *attrs)` instead — no `entity_type`, the attribute columns in its place.

The readers follow from the column's absence:

- **`entity_types()`** returns the empty set — `distinct_values` is not called on the axis, rather than called on a column of NULLs.
- **`entity_type_frame(ctype)`** has no type to be asked for. `Record.entity_types` iterates an empty mapping, so nothing reaches it; a direct call is a caller error, and should say so rather than filter on a missing column.
- **`attributes_of(ctype)`** scopes the flags by type, which is meaningless without types. Its semi-join to `of_type` becomes the whole axis — every component, which is what "no types" means for a per-type question.

**The materialised axis is the consequence to be deliberate about.** `resolved/dims/entity.parquet` is written from the folded axis, so the cache of a record with no declared type axis stops carrying `entity_type` — and a cache written before the change has it. [Materialised node caches](../layers.md#materialised-node-caches) are derived data that can be rebuilt, so this is a rebuild rather than a migration; but a stale cache read against the new column set is the failure mode to check for, and it argues for the cache carrying a schema version or being invalidated on schema change. This proposal does not settle that.

### `deleted` belongs to the axis alone

A member file carries `deleted` today, and the fold reads it from there as well as from the entity axis. That is the same duplication the axis exists to remove: [membership is the axis's](../format.md#the-entity-axis) — "a component exists because it has a row here, not because some type's file mentions it" — and a tombstone is a statement about membership.

It shows up as a coupling in the staging area. `remove` has to write twice, once to the axis and once to the type's member table, because a removal that left no member row would read as a member the layer never mentioned. Two writes to say one thing, kept in step by hand.

So this proposal also takes `deleted` off the member file: a member file holds `entity` and that type's columns, nothing else. `remove` then writes one row, on the axis, and the fold reads tombstones from one place.

The two changes belong together because they are the same claim about that file — a member file holds _values_, and everything about a component's existence is the axis's. Separately each looks like a detail; together they leave the member file with no column that is not an attribute.

### What a schema declaring the axis does, unchanged

A schema declaring the axis keeps today's layout exactly: `dims/entity_type/<Type>.parquet` per type, `entity_type` on the entity axis, typed by the declared `Dimension`. This proposal adds no case there; it removes one from the side where nothing declares the axis.

### Every source and every producer

The layout is one thing; what each implementation of it must do is another, and the change is only coherent if all of them agree. There are four `LayerSource`s and two record-side producers.

| implementation                   | `axis("entity")` under this proposal              | `entity_type(name)`              |
| -------------------------------- | ------------------------------------------------- | -------------------------------- |
| `_FileLayer` (shared)            | `dims/entity.parquet`, now with attribute columns | `None` — no such directory       |
| `ParquetLayer`                   | inherited                                         | inherited                        |
| `ResolvedLayer`                  | `layers/<id>/dims/entity.parquet` — **see below** | inherited, from `layers/<id>/`   |
| `DirectorySource`                | inherited                                         | inherited                        |
| `StagedSource` / `WorkingRecord` | `_ENTITY_AXIS` table, now with attribute columns  | `None` — no member tables staged |
| `PyPSA` (tool)                   | `dims["entity"]`, its member frames merged in     | `entity_types` empty             |

Three of the four sources need no code change at all: `_FileLayer` reads whatever columns the file has, and `ParquetLayer` and `DirectorySource` inherit it. `entity_type(name)` answering `None` follows from the directory being absent, which `try_read_parquet` already handles. That is the test of whether the layout is right — a file-backed source should not have to know which configuration it is reading.

**The `PyPSA` tool** currently supplies `entity_types` per type and, since the entity axis became a supplied member, `dims["entity"]` from `_entity_axis_frame`. Under this proposal an untyped export merges the member columns into that frame and stops supplying `entity_types` — but PyPSA always has types (`n.components`), so it is unaffected in practice. It matters as a statement about the protocol rather than about this tool: a producer with no types has one axis frame to fill and no `entity_types` mapping, which is exactly what the `Record` protocol should let it say.

### The prerequisite: `axis` means one thing on every source

`ResolvedLayer` overrides `axis` and `axes` to read `resolved/dims/` — the _folded_ answer, standing for everything above this node — so `axis(dim)` means something different on it than on every other source, where it means "this layer's own rows". Moving a component's attribute columns onto the entity axis brings them into the reach of a source read that expects layer-local rows, so the override has to go first.

That untangling is [`one-interface-source-and-fold`](dep-0008-one-interface-source-and-fold.md)'s subject in full: the `ResolvedLayer` masquerade — a persisted fold typed as a source — is the root, and once the base is a `Resolver` and the head a plain `ParquetLayer`, `axis` is layer-local on every source with no exception. This proposal depends on that split; it adds no new argument to it.

## What this buys

**Every column of the format answers to a declaration.** `entity_type` stops being the exception admitted by a special case, because it appears only where a group declares the axis — which is also when it has a dtype. The `_validate_frame` special case and the `_axis_columns` `String` fallback both go, and so does the `nw.String()` fallback that types a column no `Dimension` describes.

**The entity axis's shape follows the schema.** Where a schema declares no type axis, the folded entity axis stops carrying `entity_type` — on disk in a materialised cache too — rather than carrying it filled with NULLs. The three per-type readers then all resolve to "there are no types" rather than to "the type is NULL".

**A record whose schema declares no type axis has one member file, not N.** Today `add("thing", …)` and `add("other", …)` write two files that no declaration distinguishes, and a reader must enumerate them to find a component. One axis file is the honest shape of "these components have no kinds".

**`Record.entity_types` stops lying.** It currently returns `{thing, other}` where the schema declares no entity-type axis — reporting filenames as a vocabulary. Empty is the true answer, and `entity_types` being empty is already what `schema.entity_types` says.

## What it costs

**A second layout for one construct.** The entity axis carries attribute columns in one configuration and not the other, which is a branch in `_axis_columns`, in `_validate_frame`'s `known` set, and in whatever `add` uses to route a wide frame. Against that: the branch replaces the `entity_type`-column special case rather than adding to it, and it is keyed on one schema property.

**A prerequisite in `ResolvedLayer`.** Its `axis`/`axes` must become layer-local first, with the folded read moved to the seed path (above). That is a small change and a defect fix in its own right, but it lands before this proposal rather than with it, and it touches `resolve_dims` - the one place the fold reads axes across sources.

**`attributes_on("entity")` changes meaning.** Its early return is load-bearing in more places than the writer — worth auditing every caller before moving it, since "never `entity`" is currently an invariant a reader may lean on.

**Migration.** A record written under the old layout has `dims/entity_type/thing.parquet` and an `entity_type` column; one written under the new has neither. Pre-1.0 and [breaking changes are free](https://github.com/energy-models/datarecord/blob/main/AGENTS.md), so this is a re-export rather than a compatibility path — but it is a re-export of every existing record whose schema declares no type axis, not a no-op.

## What it opens rather than settles

**Whether a declared axis with no `Enum` is the same case.** `schema.entity_types` is empty for a `String`-typed entity-type dim too — the labels are data there as well, yet a group declares the axis, so the type is a real dim with a dtype. This proposal keys on `entity_type_dim is None`, not on whether the labels are enumerable, and the two differ for exactly that schema. Which side it belongs on is a question about what declaring the axis _means_, and this page does not answer it.

**Whether `attributes_for` should narrow at all without types.** It currently returns every entity-addressed attribute for any label. If there are no types, "which attributes does type X carry" has no meaning, and the method's contract could say so rather than accepting any string.

## How to know it worked

**`tests/test_untyped.py` changes shape, and that is the deliverable.** `test_a_component_round_trips_without_a_type` and `test_an_unknown_label_is_accepted` both assert on `record.entity_types` returning labels; under this proposal they assert it is empty and read the values off `dims["entity"]` instead. The round trip is the same round trip — a value written and read back — through one file rather than two.

**A written untyped layer has no `dims/entity_type/` at all.** The clearest single assertion: the directory does not exist, where today it holds one file per label an `add` happened to use.

**The `_validate_frame` special case is gone.** Asserting that an `entity_type` column on the entity axis of a record with no declared type axis is now _rejected_ is what says the exception was removed rather than relocated.

**`sources.py` is untouched, `ResolvedLayer` aside.** The strongest signal that the layout is right rather than merely different: if `_FileLayer`, `ParquetLayer` and `DirectorySource` need no edit, then a file-backed source genuinely does not have to know which configuration it reads. A diff that adds a branch to any of them means the layout is being carried by the readers instead of by the format.

**A resolved record with no declared types reads the same as an unresolved one.** Materialise a node of such a record and read a component's value through both; they must agree. This is the assertion the `ResolvedLayer` prerequisite above exists to protect, so it belongs in the suite before either change rather than after.

**The resolved entity axis has no `entity_type` column where the schema declares no type axis** — asserted on the relation's columns, and on the materialised `resolved/dims/entity.parquet` for a node that was materialised. Today both carry it, filled with NULLs, which is the state that makes `entity_types()` answer `{None}`; a test that only checks `entity_types() == set()` would pass with the column still there and still NULL.

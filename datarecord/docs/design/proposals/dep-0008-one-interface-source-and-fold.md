<!--
SPDX-FileCopyrightText: datarecord contributors

SPDX-License-Identifier: CC-BY-4.0
-->

# DEP 8: one interface, two objects — a source is its own rows, a fold is the resolution

| DEP     | 8                                                                               |
| ------- | ------------------------------------------------------------------------------- |
| Title   | one interface, two objects — a source is its own rows, a fold is the resolution |
| Author  | Jonas Hörsch                                                                    |
| Status  | Implemented 2026-09-04                                                          |
| Created | 2026-09-02                                                                      |
| Version | v0.1.0a1                                                                        |

> All three commits below landed on `refactor/staging-as-a-layer` (`cd2ce92`,
> `006c159`, `7f244a9`). The authoritative account is [the read
> path](../read-path.md#one-record-over-one-fold), [the Record
> protocol](../record.md) — including [`LayerData`](../record.md#layerdata) —
> [writing](../writing.md) and [the module layout](../module-layout.md); this
> page is kept as the argument that led there, and those pages are authoritative
> where the two disagree. `NodeCache` landed as `Resolver`, `ResolvedLayer` is
> deleted, the base is a `Fold` (`datarecord/layered/fold.py`) discovered from
> the sources, and `write_record` takes a `LayerData`. The untyped-enumerator
> `∅`-not-`{None}` half is the subject of its now-landed successor,
> [`a-member-file-holds-values`](dep-0006-a-member-file-holds-values.md). The "Commit N as
> landed" notes below record where the implementation departed from this sketch.

One claim: **`axis(dim)` should mean the same thing wherever it is written — "the rows of the thing I am holding".** You pick "one layer's contribution" versus "the resolved answer to here" by _which object you hold_, not by a `resolved_` prefix on a method nor by a mode flag. A [`LayerSource`](../read-path.md#owner-map) answers for its own layer; a fold answers for everything folded into it; both answer under the same names.

The codebase is already most of the way there and inconsistent about the last step. [`WorkingRecord`](../working-record.md) does it the clean way — the fold and the staged-layer's-own-rows are _two objects_ (`WorkingRecord` the [`Record`](../record.md) over a `NodeCache`, `StagedSource` the source). `ResolvedLayer` does it the muddy way — _one object_ that is a fold (a persisted `NodeCache`) but is typed as a source and put in the fold's own input list, so it answers for its own layer through some methods and for the fold-to-here through others.

This is the prerequisite [`a-member-file-holds-values`](dep-0006-a-member-file-holds-values.md) names, taken at its root rather than at the symptom. That page proposes adding `resolved_axis`/`resolved_axes` beside `map_uri` — a third folded-answer method under a distinct name, papering the dual role. The root cause is that a fold-result (`ResolvedLayer`, a persisted `NodeCache`) is masquerading as a fold-input (a `LayerSource`); untangle _that_ and no new method name is needed.

## What starts it

Three abstractions, each with a one-line contract the code states explicitly:

- **`LayerSource`** — "One layer's own rows, however they are stored" (the `sources.py` protocol docstring). `axis` "means 'this layer's own rows'". Every implementation obeys it: `ParquetLayer`, `DirectorySource`, `StagedSource`.
- **`NodeCache`** — "A record's resolved view: owner map, dims, schema, and the relations over them" (`resolve.py`). It holds a `sources` list and _folds_ it: the `inputs` owner map, `dims` (the entity axis and groups among them), and every `relation`/`entity_type_frame`/`group_frame` are computed from those sources.
- **`Record`/`RecordLike`** — "the narwhals interface over one fold" ([`record.md`](../record.md)). A `Record` wraps exactly one `NodeCache` and presents its fold as narwhals frames.

So `NodeCache` _is_ the fold, and a `Record` is its public face. The line between "own rows" (`LayerSource`) and "the fold" (`NodeCache`) is clean until one object straddles it.

### `ResolvedLayer` _is_ a `NodeCache`, persisted

This is the fact the rest of the page turns on. `Revision.materialise()` folds a node's sources and writes the result to `resolved/` — `_fold_kind` for the `inputs` owner map, `resolve_coords` for the axes (the entity axis and groups among them) ([`materialise`](../layers.md#materialised-node-caches)). That is _exactly_ what a `NodeCache` computes in memory; materialising is persisting a `NodeCache`'s output. `ResolvedLayer` is the handle that reads it back, and `NodeCache` seeds from it to skip the re-fold:

```python
NodeCache._fold_map: seed = read(
    head.map_uri(kind)
)  # a ResolvedLayer's stored owner map
NodeCache.resolve_dims: seed = head.resolved_axes()  # a ResolvedLayer's stored dims
```

So `ResolvedLayer` and `NodeCache` are **the same thing — the fold to a node — in two tenses**: `NodeCache` computed live, `ResolvedLayer` computed earlier and read from `resolved/`. A `NodeCache` reads a `ResolvedLayer` as its own prior incarnation, which is the whole point of `sources_to_read` stopping at a materialised ancestor: its `ResolvedLayer` already carries what re-folding from the root would recompute.

The defect is that this persisted fold is typed as a **`LayerSource`** and put in the `sources` list — a list of _own-layer_ things. **A fold-result is masquerading as a fold-input.** Everything below follows from untangling that one type error.

### The masquerade shows as a dual role

Because the persisted fold sits in the `sources` list, the head is asked two different questions by two different consumers of the _same list_ — the fold-input question and the fold-result question it should never have had to answer at once:

| consumer                  | holds the head as | wants                               | reads                 |
| ------------------------- | ----------------- | ----------------------------------- | --------------------- |
| `resolve_dims` seed       | fold seed         | resolved axes to here               | `resolved/dims/`      |
| `_fold_map` seed          | fold seed         | resolved `inputs` map to here       | `resolved/owner_map/` |
| `source_for` → `relation` | a source          | the head layer's _own_ winning rows | `layers/<id>/`        |

`source_for(layer_uuid)` returns the head `ResolvedLayer` for a key the head owns, then reads its member with `source.attribute(...)` — the _own-rows_ accessor. The seed paths read the _folded_ answer. One object, both roles, and the only thing keeping them apart is that the folded answer hides under `map_uri` (and, in `a-member-file-holds-values`'s sketch, would hide under `resolved_axis`).

`relation` already shows the intended shape by accident: for a layer the map names but the truncated source list does not hold, `source_for` fabricates `ParquetLayer(layer_uuid, con)` — a plain own-rows source. It _wants a source_, and where the list does not give it one it builds one. The head is the case where the list gives it a source that is secretly also a fold.

### `WorkingRecord` is the model, and has the latent version of the same seam

`WorkingRecord` keeps the two views as two objects:

- The **resolved view** (base + staged) is `WorkingRecord` itself, a `Record`, built as `base_cache.with_source(StagedSource(self, ...))` and answered by the inherited fold.
- The **own-layer view** (staged rows alone, for commit) is `StagedSource` the source, and `staged_only()` → `_Written`, built from the `_staged_*` helpers.

That is the shape this proposal generalises. But the seam is present here too, quieter: `staged_only()` returns a `_Written`, a _third_ type, rather than handing over the `StagedSource` that already _is_ the staged layer's rows. `_Written` and `StagedSource` are two spellings of "the staged layer's own rows" — one shaped for the writer, one for the fold — because `write_record`'s input is spelled as neither the source interface nor the interface a fold answers, but wants what both can give. The write-path half below closes that by naming the interface the two share. Left alone, `_Written` is the next `ResolvedLayer` waiting to happen.

## The construct

**A fold and a source answer the same interface; the object decides the meaning.** Concretely, four moves: a `Fold` object holding the fold machinery, a `Resolver` that is `LayerData` routing into its `Fold`, a base discovered from the sources rather than stored, and the write path taking `LayerData`.

### The fold machinery is a `Fold` object

Everything the fold _produces_ and the reads gated by it move into one object, the counterpart to `Coords` (today's `Dims`, renamed — it holds axes _and_ groups plus the broadcast/match algebra, which "dims" undersold):

```python
class Fold:
    """A node's resolved view: the folded axes and owner map, and the reads over them."""

    schema: Schema
    coords: (
        Coords  # the folded axes and groups (entity among them) + expand/match helpers
    )
    owner_map: (
        DuckDBPyRelation  # folded (input_key, layer_uuid, varies/broadcast/breakpoints)
    )

    # pure-map reads
    def attributes(
        self,
    ) -> list[str]: ...  # distinct `attribute` (was `attribute_names`)
    def owners(
        self, attribute: str
    ) -> DuckDBPyRelation: ...  # map rows for one attribute

    # map x axis read — here because a Fold has both halves
    def flags(
        self, entity_type: str | None = None
    ) -> dict[str, Flags]: ...  # was `attributes_of`

    @classmethod
    def read(
        cls, revision_id, con
    ) -> Fold | None: ...  # from resolved/, folds nothing; None if unmaterialised
    @classmethod
    def compute(
        cls, sources, con, schema, *, base: Fold | None
    ) -> Fold: ...  # fold sources over the base
```

`flags` takes `entity_type=None` — whole-record when `None`, a type when named. The type-scoping (semi-join the map to that type's entities) needs the entity axis, which a `Fold` has via `coords.axes["entity"]`; so `flags` belongs on `Fold`, the one object holding both the map and the axes, rather than on a map-only `OwnerMap` that would have to be handed an entities relation from outside. `owners(attribute)` is the map-only read `relation` joins against; `attributes()` is the map-only enumerator. `flags_from_rows` stays a module function `flags` calls — it is schema logic, not map logic.

`Fold.read` and `Fold.compute` are the two tenses: a materialised node's `resolved/` read back, versus a fold computed over sources. The same object shape either way, which is what makes a computed fold able to start from a read one as its base.

### `NodeCache` becomes `Resolver`, `LayerData` routing into its `Fold`

The rename says what the class is: it _resolves_ a node's layers into the answer a `Record` presents. "Cache" named an implementation detail (the frozen-prefix materialisation) as if it were the identity; "resolver" names the job.

```python
class Resolver:
    revision_id: UUID
    sources: list[LayerSource]    # the whole (frozen-truncated) ancestry as sources; no `base` field
    con: DuckDBPyConnection
    schema: Schema                # a plain field (see below), resolved by the caller

    @cached_property              # stable-gated as `coords` is today
    def fold(self) -> Fold: ...   # base = deepest materialised source; compute the rest over it

    # LayerData surface — routes into `fold`
    def axes(self): ...           # set(fold.coords.axes)
    def axis(self, dim): ...      # fold.coords.axes.get(dim)
    def attributes(self, kind): ...    # fold.attributes() for inputs; own-layer listing for outputs
    def attribute(self, name, kind): ...   # relation(name)/outputs(name), via fold.owners + source_for
    def entity_types(self) / entity_type(self, ct): ...   # was entity_types / entity_type_frame
    def groups(self) / group(self, g): ...                # was (from schema) / group_frame

    # routing reads that need the fold's members by name
    def owners(self, attribute): ...   # fold.owners(attribute)
    def flags(self, entity_type=None): ...   # fold.flags(entity_type)  (was attributes_of)

    # extras a single fold-product cannot answer
    def source_for(self, layer_uuid) -> LayerSource: ...   # dispatch a winning key to its layer
    def with_source(self, source) -> Resolver: ...         # append one more layer (staging)
    @property
    def frozen(self) -> bool: ...   # all(s.frozen for s in sources)   (was `stable`)
```

`inputs` (the raw map relation) and `entity_axis` stay as thin routing properties — `fold.owner_map` and `axis("entity")` — because white-box tests and `mutable.py` read them by those names; they are `owners` and `axis("entity")` without the argument.

`Resolver.frozen` (the `LayerData` member) is today's `NodeCache.stable`: `all(s.frozen for s in sources)`, whether the whole source list is write-once. Distinct from `frozen_prefix`, which counts how far the leading run is frozen to decide the in-memory cache boundary.

**`schema` becomes a plain field** (deferred to its own commit): today it is a property returning `declared` if set else `read_schema(con)`, threaded through `with_source`. Every fold reads the schema, both construction sites already hold it (the tree node reads the root schema, `Record.over` has the manifest), and the resolver is lazy, so the fallback buys nothing. Moving `read_schema(con)` to the one tree-node construction site makes `schema` a plain field, deletes `declared` and the property, and lets `with_source` pass `self.schema` already resolved.

### The base is a `Fold`, discovered from the sources, not stored

The base is not a stored field. `sources` is the whole ancestry (frozen-truncated for the in-memory cache, unrelated to materialisation) as plain `LayerSource`s, and the fold discovers its base from among them:

```python
def materialised(self, con) -> Fold | None: ...  # on LayerSource


# ParquetLayer: Fold.read(self.revision_id, con)   — a resolved/ dir, or None
# DirectorySource / StagedSource: None
```

`Resolver.fold` walks `sources` from the deepest, asks each `source.materialised(con)`, and the first hit is the base: everything at or below it is skipped, everything above folds on top via `Fold.compute(above, con, schema, base=hit)`. No materialised ancestor → `base=None`, fold the whole list.

This is why `frozen` and `materialised` are two questions, not one. **`frozen`** = "these rows cannot change under a reader" — a source-type flag (`False` only for `StagedSource`) gating the _in-memory, connection-scoped_ fold cache (`frozen_prefix`/`_frozen_table`). **`materialised`** = "this node has a `resolved/` directory on disk" — a filesystem fact, set only by an explicit `.materialise()`, gating the _fold-shortening base_. Every materialised node is frozen; almost no frozen node is materialised. So the base comes from the deepest _materialised_ source, which the walk finds by testing `source.materialised(con)`, never from "the last frozen source".

`ResolvedLayer` is deleted. Its fold-role becomes the base `Fold.read(...)` a source offers via `materialised(con)`; its own-rows role, where `source_for` reaches a winning layer's rows, becomes a plain `ParquetLayer`. `source_for` resolves an owner id to a source and never to the base. The fold-result stops being an entry in the fold-input list.

### Sequenced commits

This lands as three tested-green commits:

1. **Read-path split** ✅ **done** — kill the masquerade: `source.materialised(con) -> Fold | None`, `Resolver.fold` takes its base from the deepest materialised source, `sources` is plain `ParquetLayer`s, `ResolvedLayer` deleted, `NodeCache -> Resolver` rename (and `.stable` -> `.frozen`). This is the piece `a-member-file-holds-values` is blocked on.
2. **`Fold` object** ✅ **done** — extract `coords` + `owner_map` and the reads (`owners`, `flags(entity_type=None)`, `attributes`, per-type/group frames) into `Fold`; `Resolver` routes into it. Orthogonal to (1); a clean second diff.
3. **`LayerData` + write path** ✅ **done** — define `LayerData`, make `Resolver` and `LayerSource` both satisfy it (source gains `entity_types`/`groups`/`attributes` enumerators), rename the fold-named readers to the shared vocabulary, `write_record` takes a `LayerData`, `_Written`/`staged_only()` deleted, both commit callers pass the object they hold.

> [!NOTE]
> **Commit 1 as landed** (departures from the sketch above, and facts for commits 2–3):
>
> - **`Fold` lives in its own module `datarecord/layered/fold.py`**, not in `resolve.py`, to break the import cycle a `source.materialised() -> Fold` return would otherwise create (`resolve.py` imports `sources.py`; a source returning a `Fold` from `resolve.py` would close the loop). In commit 1 it is a minimal seed struct — `axes`/`groups`/`entity_types` dicts + `owner_map`, and `Fold.read` — depending only on `duck`. Commit 2 moves the reads (`owners`/`flags`/`attributes`) onto it and folds the four dicts into `coords: Coords`.
> - **`_base_and_above(sources, con)`** in `resolve.py` is the split helper: it scans `sources[:-1]` deepest-first for the first `materialised(con)` and returns `(base_fold, sources_above)`. **The last source is never the base** — a node resolves from its own layer, never its own cache — which is also what stops `materialise` (which writes `owner_map` before `dims`) from reading its own half-written cache back as a base.
> - The base seeds the fold as **depth 0** of each `fold_axis`/`fold_inputs` call (its resolved, tombstone-free relation prepended), so a layer above still wins per key and its tombstones still evict a base key — behaviourally identical to the old `ResolvedLayer`-as-first-source seed. This touches `resolve_dims`, `resolve_groups`, `_fold_map`, `entity_type_frame`, and `_materialise_dims`.
> - The invariant guard `test_resolved_reads_same_as_unresolved` (in `test_overlay.py`) landed **first**, green before and after: it folds one node through the base and one from the root (via an `_Unmaterialised` `ParquetLayer` subclass forcing `materialised() -> None`) and asserts they agree on the owner map, entity axis, and every attribute relation.
>
> **Commit 2 as landed** (the `Fold` object):
>
> - **`Fold` grew into the real object in `fold.py`**: `schema` + `axes`/`groups`/`entity_types` dicts + `owner_map`, plus the map reads `attributes()` (was `attribute_names`), `owners(attribute)`, and `flags(entity_type=None)` (was `attributes_of`, now whole-record when `None`). `flags_from_rows` moved to `fold.py` beside its only caller.
> - **`Fold.compute` is a resolve.py concern, not a `Fold` classmethod.** The folding that builds a live `Fold` needs `Coords`' broadcast algebra and the DuckDB expression machinery, both in `resolve.py`; relocating them into the light `fold.py` would invert the layering. So `Resolver.fold` assembles a live `Fold` from `dims` (the folded `Coords`) and `_map("inputs")` (the folded owner map) — both of which keep their own frozen-scoped connection cache, so `fold` re-wraps rather than re-folds and no cache moved. `Fold.read` (the base tense) stays a `Fold` classmethod.
> - The live `Fold` carries `entity_types={}`: it is never another fold's base, and its reads never touch the per-type frames (those go through `Resolver.entity_type_frame`, which folds per call). `Coords` is unchanged — `Dims` renamed, holding axes+groups+the broadcast algebra.
> - **`materialised(con, schema)`** gained the schema argument, since `Fold.read` needs it to cast the read-back map; every implementation and `_base_and_above` thread it through.
>
> **Commit 3 as landed** (`LayerData` + the write path):
>
> - **`LayerData` lives in `record.py`** beside `RecordLike`, the neutral protocol module both the write path and `mutable.py` already import. Its enumerators return `Iterable[str]`, not `set[str]` — a `Resolver.attributes` orders its keys (a `Record` over it needs a stable order) while a source's are a `set`, and `Iterable` is the covariant type both satisfy without either re-wrapping.
> - **Every source carries a `schema` reference, so a `LayerSource` _is_ a `LayerData`.** The reference is passed in at construction — `sources_to_read`, `source_for`, `Record.over`/`Record.at` and `WorkingRecord` all thread the one schema they already hold down into each `ParquetLayer`/`DirectorySource`/`StagedSource` — never re-read from disk. This is the "`schema` becomes a plain field" step the commit-2 note deferred: `Resolver.schema` stops being a lazy `declared or read_schema(con)` property and becomes a required field resolved by the caller, and the same reference sits on every source in the fold. A file layer's schema is never _read_ by anything (the writer only ever gets a `StagedSource` or `Resolver`), but carrying it is what lets `commit` hand `self.resolver.sources[-1]` straight to `write_record` with no cast.
> - **A `LayerSource`'s new enumerators take no `schema` argument** and do not filter by declaration — `entity_types`/`groups`/`attributes` are plain directory listings, as `axes()` already is. The `∅`-not-`{None}` schema-governance the proposal makes an acceptance test of is a property of the objects `write_record` actually receives (`StagedSource`, `Resolver`), whose staged/folded state is already declaration-scoped.
> - **`Resolver` keeps `relation`/`outputs` as private `_relation`/`_outputs`** behind the shared `attribute(name, kind)`, and returns a non-`None` relation (an empty one where no layer wrote the attribute) — a valid narrowing of `LayerData.attribute`'s `| None`. **`group_frame` and `entity_type` differ**: `entity_type_frame` renamed to `entity_type` (the shared name, no collision), but `group_frame` stayed, being the `Record`-presentational read (member order, empty→`None`) that `Record._group_frame` alone uses; the shared `group(name)` is the raw fold `Resolver` already had.
> - **`isinstance(x, LayerData)` decides the adapter**, and `@runtime_checkable` checks only member _names_. A `RecordLike` producer (`_NetworkSource`) has `dims`/`entity_types` where `LayerData` wants `axes`/`axis`/`entity_type`/`frozen`, so it correctly fails the check and routes through **`_RecordLikeAsLayerData`** in `write.py` — a thin adapter reading its `Frames` mappings through the enumerate-and-read pairs (`as_relation` for the one non-DuckDB backend boundary). `write_record` takes `LayerData | RecordLike`.
> - **`commit` hands the fold's last source straight over**: `self.resolver.sources[-1]` (the `StagedSource`) for `NewChild`, `self.resolver` for `Directory`, both already a `LayerData` with no cast needed. `_Written`, `staged_only()`, and the `_staged_axes`/`_staged_entities`/`_staged_attributes` `Frames` builders are deleted; `_staged_groups` stays for `StagedSource.groups()`'s key set.
> - **`write.py` is raw-relation throughout**: `_validate_frame`/`_write_frame`/`_require_unique` take `DuckDBPyRelation`, `nw.concat`/`.unique`/`.group_by` became `union_all_by_name` + a self-join count, and `as_relation` is reached only inside the `RecordLike` adapter.

### The interface `Resolver` and a layer share

A `Resolver` and a `LayerSource` answer the _same questions_ — "the keys of kind X" and "the rows for one key of kind X" — one over a fold, one over a single layer. That is a shared read protocol; call it `LayerData`. Each is that protocol plus its own extras.

| the shared question    | `LayerData` member      | a layer answers (own rows)                                        | a `Resolver` answers (folded)              |
| ---------------------- | ----------------------- | ----------------------------------------------------------------- | ------------------------------------------ |
| the schema in force    | `schema`                | — the writer supplies it                                          | `schema`                                   |
| which axes exist       | `axes()`                | `axes()` ✓                                                        | keys of `coords.axes`                      |
| one axis's rows        | `axis(dim)`             | `axis(dim)` ✓                                                     | `coords.axes[dim]`                         |
| which types exist      | `entity_types()`        | _new: list member files; `∅` if the schema declares no type axis_ | `entity_types()` ✓                         |
| one type's rows        | `entity_type(name)`     | `entity_type(name)` ✓                                             | `entity_type_frame` → renamed              |
| which groups exist     | `groups()`              | _new: list group files; only what the schema declares_            | _from schema_ → made explicit              |
| one group's rows       | `group(name)`           | `group(name)` ✓                                                   | `group_frame` → renamed                    |
| which attributes exist | `attributes(kind)`      | _new: list attr files_                                            | `attribute_names`/`output_names` → renamed |
| one attribute's rows   | `attribute(name, kind)` | `attribute(name, kind)` ✓                                         | `relation`/`outputs` → renamed             |

`schema` heads the table but governs it: which of the pairs below it are populated depends on what the schema declares — see [`schema` governs which pairs are live](#schema-governs-which-pairs-are-live-it-is-not-a-peer-of-them).

So `LayerData` is: `schema`, `frozen`, `axes`/`axis`, `entity_types`/`entity_type`, `groups`/`group`, `attributes`/`attribute` — the enumerate-and-read pairs (each an `enumerate() -> set[str]` and a `read(key) -> Rel | None`) plus the two members that mean the same over a layer and a fold. `all_attributes` stays source-only (see [`all_attributes` is source-only](#all_attributes-is-source-only-for-now)). A `LayerSource` gains the three enumerators it lacks (`entity_types`, `groups`, `attributes` — directory listing for a `_FileLayer` as `axes()` already is, the staging tables for `StagedSource`); a `Resolver` renames its fold-named readers (`entity_type_frame` → `entity_type`, `relation` → `attribute`, and the `coords.axes` keys become `axes()`) so the two answer under one vocabulary.

`frozen` is on `LayerData`; `all_attributes(kind)` is not (source-only, [below](#all_attributes-is-source-only-for-now)). `frozen` is a real property of a fold, not a convention-constant: a `Resolver` can hold a `StagedSource` (this is what `WorkingRecord` is), so it is over a mix of frozen and unfrozen sources, and its `frozen` is `all(s.frozen for s in sources)` — whether its whole source list is write-once. (Distinct from `frozen_prefix`, which counts how far the leading run is frozen to decide materialisation, not whether all of it is.)

Beyond the shared protocol, each keeps what only it has:

- **`LayerSource` also has** `layer_id` — the per-source key `source_for` dispatches a winning `layer_uuid` back through — and `uri` on the file-backed ones. `layer_id` stays source-only because a fold has no single one: it spans many layers, keyed by `revision_id` and routed by the owner map, so "the last layer's `layer_id`" is not a value `source_for` could dispatch on.
- **`Resolver` also has** the fold machinery a single layer has no answer for, held in its [`Fold` object](#the-fold-machinery-is-a-fold-object): `with_source`, `source_for`, `owners` (over the one owner map), `flags`, `fold`/`coords`/`entity_axis` (the folded state), and `revision_id` in place of a `layer_id`. (`stable` is now `frozen` on the shared protocol; the base is a `Fold` discovered from the sources, not a stored field.)

`Resolver` fulfils `LayerData`; so does `LayerSource`. `write_record` takes a `LayerData` — a single `StagedSource` for the `NewChild` commit, a `Resolver` for the `Directory` commit — and `_Written` is deleted, being the adapter that filled the gap `LayerData` now closes.

The discipline that keeps this from becoming "one protocol for two unlike things": `LayerData` holds _only_ the enumerate-and-read members that mean the same for a layer and a fold. A method only one has — `all_attributes` on a source, `with_source` on a `Resolver` — stays off the shared protocol. The shared names are for the shared idea; the rest are each type saying it is not the other.

### `schema` governs which pairs are live, it is not a peer of them

The table above lists `schema` as one shared member among the enumerate-and-read pairs, but it is not their peer — it is what decides _which of them exist_. [`a-member-file-holds-values`](dep-0006-a-member-file-holds-values.md#what-starts-it) establishes that the [entity-type axis is optional](../schema.md#categories-an-enum-property-of-a-partial-dim): where a schema declares no type axis (`entity_type_dim is None`), there are no member files, no `entity_type` column, and a component's attribute values live on `dims/entity.parquet` directly. So the `entity_types()`/`entity_type(name)` pair is not universal — it is populated exactly when the schema declares the axis, and `groups()` reflects only the groups the schema declares.

`LayerData` therefore reads _through_ `schema`, not alongside it: `schema` is the one member the other pairs are conditional on, and a `LayerData` for an untyped record is a first-class shape, not the typed shape with types nulled out. The new source enumerators inherit `a-member-file-holds-values`'s own acceptance test on this — the failure mode is an enumerator answering `{None}` rather than `∅`:

- `entity_types()` on a source whose schema declares no type axis returns the **empty set**, not `{None}`. `entity_type(name)` is then never a valid question — a direct call is a caller error, mirroring `Resolver.entity_type_frame` on the same record.
- `groups()` returns only the groups the schema declares, and no more.

This is the point where the two proposals are the same work at two altitudes. `a-member-file-holds-values` is the read/write-path consequence of `entity_type` being optional, and it names the `ResolvedLayer` `axis`-means-one-thing fix as its **prerequisite** — which is [the base/source split](#the-base-is-a-fold-discovered-from-the-sources-not-stored) above. The two land together: this note gives `LayerData` the enumerators, and the untyped case is where those enumerators must answer `∅` rather than carry a phantom type.

### `axis` is layer-local on every `LayerSource`, no exception

`ResolvedLayer`'s `axis`/`axes` overrides go; it is deleted, and every source inherits the layer-local `_FileLayer` ones. The folded read moves to the base `Fold` a source offers via `materialised(con)`, which is not a `LayerSource`. The test of correctness is [`a-member-file-holds-values`'s own](dep-0006-a-member-file-holds-values.md#how-to-know-it-worked): `sources.py` needs no branch, because a file-backed source no longer has to know whether it is being read as a layer or as a fold.

### The writer takes a `LayerData`, and `_Written` disappears

`_Written` is not a second shape of `StagedSource` — it is a `RecordLike`, because `write_record(source: RecordLike)` speaks the record dialect and `StagedSource` speaks the source dialect. `_Written` is the _adapter_: `staged_only()` rebuilds the staged layer's rows as per-kind `Frames` so the writer can eat what the fold already reads as a source. It exists only because the writer's input was spelled as neither of the two things that can supply it.

But the writer needs exactly `LayerData`. It uses `schema` and, per kind, enumerates the keys this thing holds and reads each — which is the enumerate-and-read protocol above, no more. (It never touches `flags`, and `outputs` is `attributes(kind="outputs")`.) So `write_record` takes a `LayerData`: the `NewChild` commit hands it the `StagedSource`, the `Directory` commit hands it the `Resolver`, each the object it already is. `_Written` is deleted, not collapsed — it was the adapter for a gap `LayerData` closes.

This is why `LayerData` earns its three new enumerators. The _reader_ never needs them — the fold learns which keys exist from the schema and the owner map, so a `LayerSource` was point-accessor. The _writer_ must enumerate what a layer actually holds, where the schema over-declares. Adding `entity_types`/`groups`/`attributes` to the source is what lets the reader's interface serve the writer too.

The `Directory` case proves the interface rather than excepting it. It writes the _resolved_ record — base and staged flattened — which is not one layer's rows, so it cannot be a `StagedSource`; but "enumerate what I hold, hand each over" is exactly what a fold answers, where "what I hold" means every folded key. That is this proposal's thesis on the write path: [one interface](#the-construct), the object deciding whether it means a layer or a fold.

This is the larger of the two halves and the most safely deferred, since it moves `write_record`'s contract and reconciles names across the fold and the source. It belongs to the same idea: `_Written` is the write-path twin of a `resolved_axis` prefix — a third spelling of a thing the common interface should already carry.

## What this buys

**No object answers `axis` two ways.** The overload that `a-member-file-holds-values` has to route around disappears at the source, so that proposal's prerequisite section reduces to "already true".

**A file-backed source needs no branch.** `_FileLayer`/`ParquetLayer`/`DirectorySource` read whichever columns a file has and never learn which configuration they are in — the strongest single signal the layout is carried by the format, not by the readers.

**One vocabulary for "the rows of this thing".** `axis`, `entity_type`, `attribute`, `group` mean "the rows of the object I hold", whether that object is a single layer or a fold. A reader learns the interface once.

**The `WorkingRecord` and resolved-node mechanisms become one pattern.** Both are "a fold-object over sources, with a distinguished own-rows source for the layer that is also the fold's boundary". Today they rhyme; after, they are the same construct.

**The writer takes `LayerData`, the interface a source and a `Resolver` share.** `write_record`'s input is the enumerate-and-read surface both fulfil, so both commit callers pass the object they already hold and `_Written`, the adapter that existed only because the input was spelled as neither, is deleted.

## What it costs

**It reshapes the `Resolver`'s (`NodeCache`'s) source list.** The head stops being a `LayerSource` that is secretly a fold; the base becomes a `Fold` the deepest materialised source offers via `materialised(con)`, and `source_for` stops returning it. `sources_to_read`, the fold construction (now `Fold.compute`), `resolve_coords`, and `source_for` all move together. This is the change `a-member-file-holds-values` deferred as a prerequisite, taken at its root — the masquerade — rather than papered with a `resolved_` prefix.

**A shared interface across a source and a fold invites `isinstance` where a method belongs.** The discipline that keeps it honest: if the fold-object needs a method a source does not have (a map has no `entity_type`; a source has no `map`), that is the interface telling you they are _not_ the same type — the shared members are the ones that mean "my rows", and the rest stay apart. This proposal is not "one protocol for both"; it is "the same names for the same idea where the idea is shared".

**Teaching the writer to take `LayerData` touches its contract.** `write_record` moves from `RecordLike` to `LayerData`, `LayerSource` gains the three enumerators, and `_Written` and its `staged_only()` builder go. `_Written` has callers in the tests and one in `commit`, and the `Directory` path hands over a `Resolver` under the new contract rather than the record it built. A real change to the write path, not only a read-path cleanup, and the part most safely deferred.

## What it settles

**The base is a `Fold`, discovered from the sources.** It is not a stored field. `Fold.read(revision_id, con)` reads `resolved/` and folds nothing; a source offers it via `materialised(con)`, and `Resolver.fold` takes the deepest materialised source's `Fold` as the base for `Fold.compute`. Same object shape either tense — read or computed — which is what lets a computed fold start from a read one.

**`LayerData` is a `Protocol` both types satisfy structurally, with `layer_id` the sole source-only member.** `LayerSource` is `LayerData` plus `layer_id` (and `uri` on file-backed ones) and `all_attributes` (source-only); `Resolver` is `LayerData` plus the fold machinery and `revision_id`. `frozen` is on `LayerData`, not source-only (above). Neither type inherits from `LayerData` — each `satisfies` it by shape, as `LayerSource` implementations already satisfy that protocol.

**The untyped case keys on `entity_type_dim is None`, enum or not.** An enumerator answers `∅` exactly when the schema declares no entity-type axis — not when `schema.entity_types` is empty, which is also true for a declared `String`-typed axis whose labels are data. A declared-but-non-enum axis is still a declared axis: its member files exist and `entity_types()` lists them. `a-member-file-holds-values` [leaves whether those two cases should ever converge open](dep-0006-a-member-file-holds-values.md#what-it-opens-rather-than-settles); this note does not, keying only on declaration.

## What it opens rather than settles

**How far the name reconciliation reaches.** The write-path half already reconciles the _rows_ interface a fold and a source share (`entity_type_frame`/`entity_type`, `relation`/`attribute`, `dims`/`axes` become one vocabulary the writer reads). Left open is whether `Record`'s _public narwhals_ surface joins it — `Record.dims` returns `Frames`, not the relation a source's `axis` does, so it is a presentation over the same idea rather than the idea itself. Whether the resolved-and-own pair should share the outward name too, or only the internal rows interface does, is the larger claim this page does not force.

### `all_attributes` is source-only, for now

`all_attributes(kind)` — a source's `<kind>/*.parquet` unioned by name, unfolded, values intact — stays a `LayerSource` member and off `LayerData`. It reads like the fold's owner map's raw input, and the temptation is to give a `Resolver` a folded `all_attributes` so the pair `attributes`/`all_attributes` is complete on both. Two facts hold it back:

- **No fold-side caller.** Both callers read it on a _source_: `fold_inputs` on each source to build the map, and the `outputs` bulk read on the last layer (`sources[-1].all_attributes("outputs")`). Nothing asks a `Resolver` for its own `all_attributes`, so a fold-side one would be a method with no reader.
- **The per-layer aggregate that _looks_ separable is not layer-local.** A layer's contribution to the owner map (aggregate `all_attributes` to `(input_key, layer_uuid, varies/broadcast/breakpoints)`) needs `expand_dims` against the _resolved_ axes to fan a broadcast NULL out to every value on its axis — a record-wide fact a single layer's files cannot supply. So the clean fault line is `all_attributes` (raw rows, coords-free, source) | expand+aggregate+recurse (coords, fold), not one row higher where a `source.owner_map(coords)` would sit.

Whether a later `Store`-shaped refactor makes a `Resolver.owner_map(kind)` and an `all_attributes` folded read worth having — so the two are the same enumerate-and-read pair on both types — is reopened then, not settled here.

## How to know it worked

**`ResolvedLayer` is gone; the base is a `Fold`.** The single assertion the resolved-node half is downstream of: the persisted fold is a `Fold.read(...)` the live fold starts from, not a source in its input list. `def axis` in `sources.py` is found only on `_FileLayer`, and nothing folded-answer-shaped is typed as a source.

**A resolved record reads the same as an unresolved one.** Materialise a node, read a component's value through the resolved node and through the same node read from its own layers unmaterialised; they agree. This is the invariant the whole split protects, and it belongs in the suite _before_ the change, not after — it is what says the base carries the fold correctly once `axis` stops doing so.

**`Resolver.sources` holds only `LayerSource`s, and the base is a `Fold`.** The masquerade is over exactly when no `ResolvedLayer` appears in a `sources` list — every entry is a plain `ParquetLayer`, and the fold-to-here the head stood for is the `Fold` the deepest materialised source offers. `source_for` then always hands back an own-rows source, never the base. Assertable on the source types and on what `source_for` returns.

**`sources.py` is untouched but for deletion.** As in `a-member-file-holds-values`: if the file-backed sources need no _added_ branch, the layout is carried by the format. A diff that adds a conditional to `_FileLayer` means the fold is leaking into the source again.

**A source's new enumerators answer `∅`, not `{None}`, for an untyped record.** `entity_types()` on a `LayerSource` whose schema declares no type axis returns the empty set, and `groups()` only the declared groups — the same `∅`-not-`{None}` check `a-member-file-holds-values` makes on the owner map. A test that materialises an untyped node and asserts `entity_types() == set()` on both the base `Fold` and a `ParquetLayer` of the head is what says `schema` governs the pairs rather than the pairs carrying a phantom type.

**`_Written` is gone and `write_record` took the `StagedSource` directly** — once that half lands. The `NewChild` commit passes the staged source to the writer, the `Directory` commit passes the resolved record, and both satisfy one input contract. Until it lands, `_Written` standing unchanged is the marker that this is the deferred part, not a regression.

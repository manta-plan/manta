<!--
SPDX-FileCopyrightText: datarecord contributors

SPDX-License-Identifier: CC-BY-4.0
-->

# The `Record` protocol

The definition sketched in [what a data record is](index.md#what-a-data-record-is), in full. This is the contract a consumer codes against; [the record format](format.md) is how it is stored.
It is read-only: writing is [`store.root(source)`, `rev.child(source)` or `ws.write(source, uri)`](writing.md).

Two names, one shape. **`RecordLike`** is the protocol below — what a signature annotates against, and what a framework object satisfies structurally without depending on this package. **`Record`** is the class this package provides: the narwhals interface over [one fold](read-path.md#one-record-over-one-fold), which is what `Revision.record` and `Workspace.at(uri)` both give you. The concrete thing gets the short name because it is what a caller constructs and holds.

```python
@runtime_checkable
class RecordLike(Protocol):
    """Dimensioned attribute data with a declared schema."""

    @property
    def schema(self) -> Schema: ...  # dims, properties, attributes, partial

    @property
    def dims(self) -> Frames: ...  # axis key columns, keyed by dim
    @property
    def properties(self) -> Frames: ...  # stored property values, keyed by subject
    @property
    def groups(self) -> Frames: ...  # each group's rows, keyed by group
    @property
    def attributes(self) -> Frames: ...  # long input frames, keyed by attribute

    @property
    def outputs(self) -> Frames: ...  # long result frames, keyed by attribute

    def flags(self, **categories: str | Sequence[str]) -> dict[str, Flags]: ...
```

Each accessor holds one section of [the schema](schema.md): `dims` the labels, `properties` the metadata of those labels, `attributes` the data. Where a value is read follows from what it is declared as, never from how many coordinates address it.

## `LayerData`

`RecordLike` is what a caller reads; [the writer](writing.md) writes a different, narrower protocol — **`LayerData`**, "the rows of one thing, enumerated and read":

```python
@runtime_checkable
class LayerData(Protocol):
    @property
    def schema(self) -> Schema: ...
    @property
    def frozen(self) -> bool: ...

    def axes(self) -> Iterable[str]: ...
    def axis(self, dim: str) -> DuckDBPyRelation | None: ...
    def groups(self) -> Iterable[str]: ...
    def group(self, name: str) -> DuckDBPyRelation | None: ...
    def attributes(self, kind: Kind = "inputs") -> Iterable[str]: ...
    def attribute(
        self, name: str, kind: Kind = "inputs"
    ) -> DuckDBPyRelation | None: ...
```

Each pair is an enumerator — the keys of that kind — and a read for one key.
The enumerators return `Iterable[str]` rather than `set[str]` so a `Resolver`, whose keys carry a stable order a `Record` over it relies on, can return a `list` where a source returns a `set`; the meaning is the same set of keys either way.

An `axis` is the rows of its file: the labels, their `within` keys, their tombstones and the dim's properties. A `group` is its tuples, its `into` label and the group's properties.

One object, two meanings: a [`LayerSource`](read-path.md#owner-map) answers `axis`/`group`/`attribute` for its own layer's rows; a `Resolver` answers the same names for everything folded into it.
The writer cannot tell which it holds and does not need to — a staged layer's own rows (`w.edits`) and a resolved whole record are both a `LayerData`, so a [`WorkingRecord`](working-record.md#edits) hands over either without a third shape adapting one to the other.

`schema` governs which of the other pairs are populated, rather than standing beside them as a peer: `groups`/`group` answer only for the groups it declares.
An enumerator answers the **empty set**, never a phantom key, where the schema declares nothing of that kind.

Rows are raw `DuckDBPyRelation`s, not narwhals frames — the write path stays one engine throughout.
A framework object satisfying `RecordLike` instead (narwhals `Frames`, as [`Tool.to_datarecord`](tools.md) returns) is not itself a `LayerData`; the writer wraps it in a thin adapter that reads its `Frames` mappings through the same enumerate-and-read pairs, so a tool stays narwhals-facing without the writer growing a second code path.

## Wide and long rows

`schema` is [the declaration](schema.md): which axes exist, which properties describe their labels, which attributes each label may carry, and over which axes each may vary.
The rest is data, and comes in two shapes.

`dims`, `properties` and `groups` are **wide** — one row per label or tuple:

```text
dims["entity"]                     entity                              key columns only
properties["entity"]               entity | entity_type | carrier | ... stored values
groups["connection"]               connection STRUCT(entity, bus) | role | ...
```

`dims[dim]` is the axis's key — the label and its `within` parents — in [axis order](#axis-order), and nothing else. Properties and categories are covered [below](#properties-and-categories).

`groups` is keyed by the group alone, one frame each: `groups/connection.parquet` holds every attachment whatever the categories of its entities ([where the rows live](format.md#where-a-value-lives)).
A group's own frame is keyed by the one struct column named for it, as an axis's is by the column named for the dim, its `into` label and its properties beside it.

`attributes` and `outputs` are **long** — one row per value, keyed by the attribute's name:

```text
attributes["p_nom"]        entity | attribute | breakpoint | value
attributes["p_max_pu"]     entity | <one column per coordinate> | attribute | breakpoint | value
attributes["efficiency"]   connection STRUCT(entity, bus) | <...> | attribute | breakpoint | value
```

`attributes` holds **every** attribute, whatever its `dims`: `p_nom` over `entity` alone is long rows like `p_max_pu`, so widening it over `scenario` adds a column to the same frame rather than moving it.
A row names what the value belongs to, the coordinate it sits at, and the value there.

**The columns are the attribute's own**, not a fixed set every file carries: an attribute's coordinates are what its [`dims`](schema.md#attributespec) declare, with a [group](schema.md#groups) carried as one struct column named for it.
So `efficiency` over the `connection` group carries `connection`, `flow` over a `corridor` carries `corridor`, and `objective_weighting` over `snapshot` alone carries no entity column at all — an all-NULL `entity` would be a column claiming an entity the value has none of.
A consumer wanting a group's coordinates flat takes `nw.col("connection").struct.field("bus")`, or unnests; a numpy-backed pandas frame has no struct dtype, so a pandas consumer unnests on the DuckDB side first.
`union_by_name` is what lets the fold union files of differing shape, supplying NULL for a coordinate a given file does not carry.

**No property is a column of an attribute row**: `attributes["p_max_pu"]` holds every entity's `p_max_pu` together, whatever its category, since an `entity` identifies one label on its own.
A consumer wanting one category's rows joins `properties["entity"]`, filtered on the category, on `entity`.

**`breakpoint`** is NULL for the ordinary case. It carries the abscissa of a piecewise-linear value: a curve is one row per breakpoint, `value` the ordinate at each. Convexity is never checked or recorded — that is a framework's judgement.

`properties` and `attributes` answer **stored values only**; no default is applied, so a NULL property is one no layer wrote, and a coordinate no row covers is absent. A default, a property's or an attribute's, is the consumer's to apply, through `Schema.default_for`.

## Properties and categories

A [property](schema.md#properties) is one value per label of its subject — a dim or a group — and is stored as a column of that subject's file.

**`properties[subject]`** is the subject's key with every property declared for it, as stored: a record-wide view, NULL wherever no layer wrote a value. It is keyed by each subject declaring properties.

An `Enum` property of a dim in [`partial`](schema.md#partial-the-granularity-of-an-override) [categorizes](schema.md#categories-an-enum-property-of-a-partial-dim) that dim. One category's labels are `properties[dim]` filtered on it; which properties they carry is `Schema.properties_for`, and a property's [default](schema.md#default_by-a-default-per-category) — `default_by` per category, else `default` — is `Schema.default_for`. A framework's static frame, PyPSA's `n.generators`, is that frame, defaulted, joined with the entity-only rows of its attributes. A per-category read applying the defaults itself is deferred until a caller needs it.

Which properties and attributes a label carries is decided by its categories at read time, against the [traits](schema.md#traits). A label whose category changes keeps what it held for attributes it no longer carries — `attributes` shows what was written — but those values fall outside every per-category read and every broadcast.

## Connections

Some attributes belong not to an entity but to one of its connections to a bus.

A connection is one row of the **`connection` [group](schema.md#groups)** — `Group(over={"entity": "entity", "bus": "bus"})` — rather than a structural category of its own.
`groups["connection"]` lists the attachments themselves, one row per `(entity, bus)`, whatever their entities' categories; `role` — which end of the entity it is — describes the connection and identifies nothing, so it is a property a tool declares on the group ([PyPSA does](tools.md)) rather than a column the format fixes.

A connection is identified by **the bus it attaches to**, never by position.
An attribute is a connection attribute because its `dims` name the group, so a per-connection value is otherwise an ordinary long row: `efficiency` may vary by timestep and scenario like any other attribute, and decodes by the same rules with no special case.

**A connection attribute is keyed by the connection, not the entity.** Its row carries no top-level `entity`; the entity's tombstone reaches it by the entity inside the struct, in [the fold](read-path.md#owner-map) where the group is `partial` and at read where it is not.
Removing an entity also [tombstones its connections](working-record.md#add-remove), so their values go with them.

A record declaring no such group has no connections, and one declaring it with no rows answers `groups["connection"]` empty.
Nothing about the mechanism is particular to buses — `corridor` over `(from, to)` is the same machinery, which is why `bus` is a field name here rather than a word the read path knows.

## The broadcast rule

A row's `value` applies to every combination of its NULL dim columns, enumerated from the axis frames in `dims`.
A NULL dim means "all values of that dim", not that the attribute lacks the axis: a constant `p_max_pu` is one row with `timestep = NULL`, a varying one is a row per timestep.

**Every declared dim broadcasts**, `entity` included, and **the dims a group draws on** too: a connection's `bus` is a field of the `connection` column, not the dim `bus`, so a per-bus `marginal_price` with `bus = NULL` holds one value for every bus.

**On a categorized dim, "every" is narrowed by the schema.** A NULL reaches only the labels whose categories carry the attribute, judged at read time: `set("p_max_pu", 0.9)` is one row with `entity = NULL`, reaching every generator — one added in a later layer included — and never a bus. A label with a NULL category carries only what no trait narrows.

**A [group](schema.md#groups)'s column broadcasts too**, its axis the resolved group: a NULL `connection` means every connection, expanded against `groups/connection.parquet` as a NULL `timestep` is against `dims/timestep.parquet`.
A group value is therefore a whole tuple or NULL. A struct with some fields NULL, `{entity: dc, bus: NULL}`, names a tuple no group row matches, so it is refused wherever a row comes in rather than stored.

Rows never overlap, so at most one covers any coordinate.
A coordinate no row covers — including an attribute with no rows at all — takes that attribute's default from [the schema](schema.md#attributespec): its `default_by` entry for the label's category where one lists it, else `default`.

Broadcast form is preserved: a value held once is answered once, so a consumer can reconstruct the constant-versus-varying split from the shape it gets back.

## Axis order

An axis's order is the row order of its frame in `dims`.

Labels and a group's rows are in the order they were first introduced across layers ([the owner map](read-path.md#owner-map)).
Order is never a stored column: a file's row order is the input, and the fold derives first-introduced order from it.

## `Frames`

```python
Frames = Mapping[str, nw.LazyFrame]
```

narwhals is the boundary type because it is a _protocol over dataframes_ rather than a dataframe: a record may hand back a DuckDB relation, a polars plan or a pandas frame and the consumer's code is the same.

`LazyFrames` is the lazily-building implementation, used where constructing a frame is itself I/O: `read_parquet` reads the parquet footer to bind the schema, so it opens the file.
Locally that is a page-cache hit; against a remote record it is a round trip per attribute, so a consumer wanting three of forty attributes pays three rather than forty, and listing the keys pays none.

Laziness here saves I/O, not memory: an unmaterialised relation is a query plan, so holding every attribute's frame at once costs little.
The expense is `collect`, which is the consumer's call either way.

## `Flags`

Which axes an attribute's rows actually use — so a consumer can plan its reads without opening a file.

```python
@dataclass(frozen=True)
class Flags:
    varies: frozenset[str]  # dims some row of this attribute sets
    broadcast: frozenset[str]  # dims some row leaves NULL, i.e. "all values"
    breakpoints: bool  # any row carries a breakpoint
```

`flags()` answers for the whole record in one query, keyed by attribute.
Only attributes with rows are present, so `set(record.flags())` also answers which attributes the record has at all.

**`flags(**categories)`** answers for one category: the keywords are categorizing properties of one dim, each one category or a list ([categories](#properties-and-categories)).
Only rows reaching a matching label count — on the dim's own column, or through a group's single field over it — and only attributes those labels carry are present.
Keywords categorizing several dims, or a group reaching the dim through two fields, are refused: there is no one label a row would count towards.

The sets name dims, so a consumer asks about a **named** axis: `"timestep" in flags["p_max_pu"].varies`.
`breakpoints` is a boolean rather than a set because a breakpoint is not a dim ([wide and long rows](#wide-and-long-rows)) — it is an abscissa within one row's value, not an axis the value is indexed by.

**The two sets are not complements.** An attribute may have per-timestep rows for one entity and a single NULL-timestep row for another, so `timestep` lands in both.
That is an instruction to use both containers: `timestep in broadcast` selects the NULL-timestep rows into a constant frame, `timestep in varies` selects the rest into a series frame.
Per label they would be complements; the aggregation over many labels is what makes the pair carry information.
That is also why a framework asks per category: a Generator's per-timestep rows and a Link's single row, unioned, describe neither.

**`varies | broadcast`** is the test for whether an attribute touches a dim at all.
Both sets empty for a dim means the attribute has no values along it, so the consumer builds no container there.

**Both sets are scoped to what the attribute is addressed by.** A dim outside its [`dims`](schema.md#attributespec) is in neither, never in `broadcast`.
The two are easy to conflate because whatever the flags are aggregated from — the [owner map](read-path.md#owner-map), a scan of `inputs/`, a staging table — is one relation over every attribute, so a dim one attribute uses reads NULL for the rows of one that does not; but that NULL means "no such axis", not "every value of it".
Reporting it as broadcast would answer the question above wrongly for every attribute in the record: a consumer would build a constant container along an axis the attribute has no values on.

`entity` is a dim like the others here: `p_nom` set per entity reports `entity` in `varies`, and a single `entity = NULL` row puts it in `broadcast`. An attribute with no rows at all is [absent from the mapping](#flags) entirely.

`flags` says nothing about properties, which are columns of their subject's file and read from `properties`.

## The protocol names no engine

The protocol names no engine — `nw.LazyFrame` is all a consumer sees, so a pure-Python, polars or Ibis-backed record would satisfy it without change.

The implementations provided are DuckDB-backed, both of them, and the resolution engine is not abstracted behind an interface.
The [owner-map fold](read-path.md#owner-map) is relational algebra of real complexity, and an engine abstraction with one implementation behind it is a cost paid for a second that does not exist.
Adding one later means writing a second `Record`, which the protocol already permits.

<!--
SPDX-FileCopyrightText: datarecord contributors

SPDX-License-Identifier: CC-BY-4.0
-->

# `WorkingRecord`

[`Record`](record.md) is read-only, and [the writers](writing.md) write a whole record from a source that already knows everything it will contain.
Neither covers editing: adding labels, removing them, setting an attribute or a property.

```python
class WorkingRecord:
    """A `Record` that accepts edits, and hands them over as a layer."""

    def __init__(self, base: Record) -> None: ...

    def set(
        self,
        attribute: str,  # an attribute, a result, or a property
        value: Any,  # scalar | sequence | mapping | series | frame | nw.Expr
        *,
        kind: Literal["inputs", "outputs"] = "inputs",
        **coords: Any,  # coordinates, a group's fields, categorizing properties
    ) -> None: ...

    def add(self, dim: str, labels: Sequence[Any], **columns: Any) -> None: ...
    def remove(self, dim: str, labels: Sequence[Any]) -> None: ...

    def add_group(self, group: str, frame: IntoFrame) -> None: ...
    def remove_group(self, group: str, keys: Sequence[tuple[Any, ...]]) -> None: ...

    @property
    def edits(self) -> LayerData: ...  # the staged layer alone
    def rollback(self) -> None: ...
```

Built over a base `Record`, `WorkingRecord(revision.record)`, it stages on the base's connection, `record.con`.

A **class, not a protocol**.
`Record` is a protocol because several things satisfy it — two backings, a framework object presenting itself as one, the two readings a write takes — and structural typing is what lets a consumer satisfy it without depending on this package.
There is one way to edit a record, so a second name for it would be an interface over its only implementation.
Where [the staged rows live](#staging) is this class's own business, which is why the name says what it is rather than how.

It **satisfies** `Record`, which is the load-bearing decision: a mutable record reads as a record, and what it reads is the data _with its pending edits applied_.
So an edit can be read back, or the record handed to something that only knows `Record`, without writing it.
Structurally, not by inheritance — the read members are implemented here over [base-plus-staged](#reading-with-pending-edits).

Two properties follow from accumulate-then-write, and both are the point:

- An edit costs a row in a staging table, not a rewrite.
  A hundred edits to one attribute are a hundred rows, collapsed once when written.
- Nothing touches the record until [`edits`](#edits) is written as a child.
  A caller that fails halfway leaves no layer; one that changes its mind calls `rollback()`.

## The shape of an edit

Each edit maps onto exactly one part of the format:

| edit                     | writes                                                 | key it targets                      |
| ------------------------ | ------------------------------------------------------ | ----------------------------------- |
| set an attribute         | `inputs/<attr>.parquet` rows                           | the attribute's coordinates         |
| set a property           | one column of existing `dims/<dim>.parquet` rows       | the dim's axis key                  |
| set a group's property   | one column of existing `groups/<group>.parquet` rows   | the group's struct                  |
| add labels               | whole `dims/<dim>.parquet` rows                        | the dim's axis key                  |
| remove labels            | `deleted = true` axis rows, and the tuples naming them | the dim's axis key, the group's key |
| add_group / remove_group | `groups/<group>.parquet` rows and tombstones           | the group's own key coordinates     |

Nothing names `entity` or a category: `add` and `remove` take any dim, and which coordinates an attribute's row carries is its [`dims`](schema.md#attributespec).
Nor is there a `connect`/`disconnect` pair beside `add_group` — `connection` is one group among however many the schema declares, and a call naming it would be the record layer holding one framework's vocabulary.

The crucial property: **an edit is expressed in the format's own terms.** Setting `p_nom` on twenty entities _is_ twenty `inputs/p_nom.parquet` rows, which is what a patch layer would hold anyway.
So a staged edit is already the row it will be written as, and writing `edits` is a concatenation rather than a translation.

## `set`

```python
w.set("p_nom", 150.0, entity=["wind1", "wind2"])  # broadcast
w.set("p_nom", [150.0, 80.0], entity=["wind1", "wind2"])  # per label
w.set("p_nom", {"wind1": 150.0, "wind2": 80.0})  # per label, keyed
w.set("p_max_pu", frame, entity=["wind1"])  # long frame
w.set("p_max_pu", series.rename_axis("snapshot"), entity=["wind1"])  # a series
w.set("p_max_pu", 0.9)  # every label carrying it, now and later
w.set("p_max_pu", 0.8, entity_type="Generator", carrier="wind")  # selected now
w.set("efficiency", 0.9, entity="dc", bus="north")  # a connection
w.set("p_nom", 200.0, entity="wind1", scenario="high")  # scoped
w.set("p_nom", nw.col("value") * 1.1, entity=["wind1"])  # derived
w.set("carrier", "solar", entity="g2")  # a property
w.set("p", solved, kind="outputs")  # a result
```

**Every coordinate is a keyword**, a [group](schema.md#groups)'s fields included: `entity=`, `snapshot=`, `bus="north"` for one connection, `from=`/`to=` for one corridor.
None has a parameter of its own, because which coordinates exist is declared rather than fixed.
A keyword holds one label, fixing that coordinate, or a list of labels the value is staged at each of.

A coordinate no keyword names is NULL, which by [the broadcast rule](record.md#the-broadcast-rule) is every label of it — narrowed, on a categorized dim, to the labels whose categories carry the attribute.
So `set("p_max_pu", 0.9)` is one row reaching every generator, one added in a later layer included, and never a bus.

A group's fields are packed into the group's [struct column](schema.md#groups), so `entity="dc", bus="north"` stages `connection = {entity: dc, bus: north}`.
A group value is [a whole tuple or NULL](record.md#the-broadcast-rule), so every field must be given or none: omitting `bus` alone is refused, since `{entity: dc, bus: NULL}` names no tuple, and naming no field stages the NULL struct, every tuple.
A field is named by its own name: a contract `(from, to)` over `entity` is addressed as `from="plant", to="mill"`, and `entity=` beside it is refused, since it would have to guess which party it names.

**A categorizing property as a keyword selects labels when `set` is called.** `entity_type="Generator", carrier="wind"` resolves to the labels matching every keyword on the record as staged, and `set` writes one row per label; nothing of the filter is stored.
A label added later is not reached — a plain NULL and [`default_by`](schema.md#default_by-a-default-per-category) are the two ways a value reaches labels not yet added.
The property's dim must be one the attribute reaches through exactly one coordinate, and the keyword is refused beside that coordinate's own.

**`set` writes a property too**, a category included, when `attribute` names one: a patch of one column of the axis rows of its subject, the other columns kept. Its value is a mapping or series from label to value, a scalar with a `dim=` keyword naming the labels, or a scalar for every label the axis has. A group's property takes a scalar, its fields as keywords selecting the tuples. A property is never a result and never derived, so `kind="outputs"` and an `nw.Expr` are refused for one.
Changing a category is such a patch: `set("entity_type", "Load", entity="g1")`. What `g1` holds for attributes a Load does not carry stays stored but falls outside every per-category read.

`kind` names the destination in the format's own terms — [the shape of an edit](#the-shape-of-an-edit) is a mapping from edit to destination, and this makes that destination the parameter it was always implicitly carrying.
`"outputs"` stages into `outputs/` instead of `inputs/`, which is how a tool [hands results back](#results-through-kindoutputs) to a record before it is written.

`value` takes six forms, because assigning one value to many labels and assigning a different value to each are equally ordinary and neither should require building a frame:

| `value`   | meaning                            | keywords                                                                     |
| --------- | ---------------------------------- | ---------------------------------------------------------------------------- |
| scalar    | staged at every listed combination | an omitted coordinate broadcasts                                             |
| sequence  | aligned positionally               | exactly one list keyword, same length                                        |
| mapping   | keys are labels of one coordinate  | the one coordinate no keyword names                                          |
| series    | index is labels of one coordinate  | the index's own name, else the one coordinate no keyword names               |
| frame     | supplies its own keys              | single labels completing it                                                  |
| `nw.Expr` | a function of the current value    | selects what to [derive from](#an-nwexpr-value-derived-from-the-current-one) |

A mapping's keys or a series' index are ambiguous: they may hold labels of any of the attribute's coordinates, an axis label being a string like any other.
**The caller says which** by naming the series' index after a coordinate, or by naming every other coordinate as a keyword; where neither settles it, the call is refused.
Never inferred from the labels themselves: testing them against the axis would make one call mean different things in two records — a scenario labelled `wind1` would silently capture a series meant per entity — and a partial overlap would pick a reading without saying so.

A frame over a group carries it **as the struct column**, `connection STRUCT(entity, bus)`.
One carrying a field flat, `entity` or `bus`, is rejected with the struct to pass instead, and so is a struct whose fields are not exactly the group's key, which a cast would silently re-key.
A struct with some fields NULL is rejected too; a NULL struct broadcasts over every tuple.

The first four normalise to a long frame before staging, so there is one staging path.
A length mismatch between a sequence and its keyword is an error at the call, not a silently truncated edit.

Every form is checked against [the labels the record resolves](#validation), the frame form included: "supplies its own keys" decides where the labels come from, not whether they have to exist.

## An `nw.Expr` value — derived from the current one

```python
w.set("p_nom", nw.col("value") * 1.1)  # scale up every p_nom
w.set("p_max_pu", nw.col("value").clip(upper=0.9), entity=["wind1"])
```

A sixth `value` form rather than a second method.
Nothing else a caller passes is an `nw.Expr`, so the dispatch is unambiguous — unlike the series-versus-mapping tie, which [`set`](#set) has the caller settle rather than guessing at.

What it does differently is read before it stages:

- What it derives from is the resolved value **including earlier pending edits** ([reading with pending edits](#reading-with-pending-edits)), so two such calls compose.
- Where the other forms stage without touching parent data, this one must resolve the keys it targets first.
  On a layered record that is a fold, so a broad derived edit is the one edit whose cost scales with the ancestry rather than with the rows written.
- What is staged is the _result_, not the expression.
  So a written layer holds ordinary rows, and nothing in the format records that a value was derived — replaying an edit sequence is not a thing the record supports.

The expression is evaluated by narwhals against the resolved long frame, so it names `value` rather than the attribute: the frame is long, and one attribute per call means the column is always `value`.

**A named target must resolve to a row.**
If the caller names a coordinate, every one of those targets must produce a row to derive from, or the call raises.
The caller asked for those rows to take a new value and there is nothing to compute one from, which is a failed change rather than a no-op — the same class of error as [naming a label no layer declares](#validation).

With no keyword the instruction is "whatever resolves", so an empty result is an answer rather than a failure.
That asymmetry is the whole of the rule: a broad derived edit where only some labels carry the attribute is ordinary, while a targeted one that hits nothing is a typo.

## Results through `kind="outputs"`

A tool solves against a record and hands back what it computed:

```python
w = WorkingRecord(record)
w.set("p_max_pu", 0.8, entity=["wind1"])
model = PyPSA.build(w)  # solve the edited record
model.optimize()
for attr, frame in PyPSA.results(model, w.con).items():
    w.set(attr, frame, kind="outputs")
rev.child(w.edits)  # one layer, inputs and results together
```

In memory only: the results live in the staging area beside the input edits and become part of the same layer when `edits` is written, so a solve produces one new record rather than a record plus a separate results record.
Nothing on disk is mutated, and [write-once](layers.md#a-layers-data-is-write-once) stands unchanged.

Two things differ from an input edit, both following from [outputs](read-path.md#outputs):

- **The name is checked against `results`, not `attributes`.**
  A result attribute is [declared](schema.md#results) in its own vocabulary, so an unknown name is an error exactly as it is for an input — what differs is which mapping answers.
  A tool reads its result vocabulary off the same registry it reads its inputs from, so declaring them costs it no list of its own: PyPSA's `status` field marks them, and the [tool](tools.md) forwards what it finds.
  The dim vocabulary is checked for both, and a result's coordinates are its own rather than every declared dim.
- **No label check.**
  An input value for a label no layer declares is [rejected](#validation), because it would resolve to nothing.
  A result may legitimately name a label the record never declared: PyPSA's `SubNetwork` exists only after a solve, so rejecting it would refuse a real result.
- **No extent completion when staged.**
  Results are complete as produced rather than [a partial override of a parent's](schema.md#partial-the-granularity-of-an-override), so there is nothing to carry forward from the base.

Keeping results coherent with the inputs they were computed from is the caller's business.
Editing an input after attaching results leaves results describing a record that no longer exists, and nothing here silently discards them — a record that dropped them on the next `set` would be guessing at which of the two the caller meant to keep.

## `add` / `remove`

```python
w.add("bus", ["north", "south"])
w.add("entity", ["g1", "g2"], entity_type="Generator", carrier="wind")
w.remove("entity", ["old_coal"])
```

`add(dim, labels, **columns)` stages whole axis rows: `columns` are the other columns of `dims/<dim>.parquet` — the dim's properties and a nested dim's parent keys — each a scalar for every label or a sequence aligned to `labels`.
A column no keyword names is NULL on these rows, since `add` restates a label's row whole.
An `Enum` property's value must be one of its categories.
An attribute keyword is refused with a pointer to `set`: an attribute's values are long rows whatever its `dims`, never a column of the axis.
A column the schema does not declare is **rejected**: a [staging table is shaped like the file it becomes](#staging), so there is no dtype to give such a column. A tool that grows a column declares it first, which [schema versioning](schema.md#versioning) accepts as a widening.

It is **not** a sequence of `set` calls.
A label exists by virtue of its axis row, and [validation](#validation) rejects a value for a label no layer declares; adding a bus with no properties is an edit, with nothing to `set`.
Uniqueness is structural: one axis row per label, so an `add` of a label the record already resolves restates its row rather than creating a second.

Adding a component with its connections and varying values is `add`, then [`add_group`](#add_group-remove_group), then a `set` per attribute.

`remove(dim, labels)` stages one tombstone per label, and no dim scope: a label [exists or it does not](schema.md#existence-does-not-vary-along-a-dim).
It need not enumerate what it deletes: [the fold](layers.md#deletion) drops every value keyed by the label where `dim` is `partial`, a group attribute's by the label inside its struct ([the owner map](read-path.md#owner-map)).
It also tombstones every tuple, of any group, with a field over `dim` naming one of `labels`, read from the record as it resolves with pending edits, so the [writer](layers.md#deletion) never meets a dangling tuple. Only for a dim keyed by its label alone: a nested dim's label names no point without its parents, which a tuple does not carry.
An `add` of the same label revives the label alone: its tuples are re-added through [`add_group`](#add_group-remove_group).

## `add_group` / `remove_group`

```python
w.add_group("connection", frame)  # a `connection` struct column, `role` beside it
w.remove_group("connection", [("dc", "north")])
```

The one staging path every declared [group](schema.md#groups) writes through.

`frame` is shaped like the group's file: one struct column named for the group (`connection STRUCT(entity, bus)`, `corridor STRUCT("from", "to")`), its `into` label where it declares one, and the group's properties, such as PyPSA's `role`.
A field as a column of its own is rejected with the struct to pass instead, as [`set`](#set) rejects it.
`keys` is a tuple per row in the group's [key](schema.md#into-a-group-that-classifies) order, packed into the struct for the caller.

A group's attributes are not columns of its file but long rows, set through [`set`](#set) with the group's fields as keywords.

## Edits

A `WorkingRecord` does not write. What it holds are two things the [writers](writing.md) take:

```python
w = WorkingRecord(rev.record)
w.set("p_nom", 100.0, entity=["gen1"])
edited = rev.child(w.edits)  # the delta, as a child layer
ws.write(w, "out/")  # base plus edits, flattened
w.rollback()
```

- **`w.edits`** — the staged layer alone, the [`LayerData`](record.md#layerdata) it already is. Written as a child of the revision `w` was built over, it is **only the edits** — that is what a patch layer is, and the fold resolves the rest from the parent. The layer lands in the **child**, never in the node branched from, so it is `child`'s return value that reads the edits back.
- **`w`** itself — what is staged _plus what the record already reads_, the whole resolved record. Written as a standalone directory, there being no parent to resolve against.

The writer cannot tell which it was handed, which is the point: "enumerate what I hold, hand each over" is one contract whether "what I hold" is a single layer or a whole fold.

Each part of a write now has one owner. Which rows to write is the caller's choice of `w.edits` or `w`. Which parent is named by the caller, who built `w` from it. Clearing the staging area is `rollback()`, called or not: a `WorkingRecord` still holding its edits after a write reads exactly what it did before.

One mistake is caught. `other.child(w.edits)`, with `w` built over a different revision, would write a delta computed against the wrong parent — an axis edit carries its base's sibling columns — and read back wrong, so `child` compares the edits' base revision with its own id and raises on a mismatch. Edits over a directory have no revision as their base and so are a child of none. One mistake is not caught: `rev.child(w)` writes the whole resolved record as a child layer rather than the delta. It reads back correctly, just larger, and a resolved record being a valid layer source too, `edits` is the name that has to carry it.

An edited axis follows [`partial`](schema.md#partial-the-granularity-of-an-override), exactly as an attribute's rows do.
A `partial` axis is patched label by label: the layer holds the labels the edit touched, and the fold resolves the rest from the parent, last-writer-wins per [axis key](record.md#axis-order).
An axis **outside** `partial` is owned whole once touched, so the layer restates every label with its properties — one rule for what non-partial means, rather than an axis-shaped exception to it.
The fold would resolve the narrower form correctly, since it keys per label and an omitted one keeps its parent's row; what ownership buys is that a layer's axis file says what the axis _is_ there, rather than being readable only against its parent.
A standalone write of `w` writes the resolved axis whole either way, and an axis nothing touched is written by neither.

Restating on edit is what an axis outside `partial` costs, and it is [the cheaper side of that trade](schema.md#partial-the-granularity-of-an-override) — which is the reason not to reach for `partial` when an axis merely gains a property.

Neither carries the **base's** results across.
An edit changes the inputs a result was computed from, so a parent's `outputs/` says nothing about the child — results belong to the node that was solved, and a node with different inputs is a different node.

What a write does carry is results **staged into this record** through [`set(..., kind="outputs")`](#results-through-kindoutputs).
Those were computed against these pending inputs, so they describe exactly the layer being written, and both readings write them: a child written from `edits` holds the edits and the results computed from them together.

An edit **replaces the rows it names** rather than appending beside them: it deletes the rows at the coordinate it writes and inserts the new ones, so a staging table holds one row per coordinate and no fold is needed to read it.
The key it replaces on is the coordinate — the same one a read would have collapsed — so the delete removes exactly what a last-writer-wins fold would have discarded.
An axis or group property is the exception in mechanism, not in effect: a row's columns are independently editable, so a property `set` patches its one column in place (`UPDATE`) rather than replacing the row, which is what keeps a sibling property a different `set` wrote.

Per **coordinate**, not per ownership key: the ownership key excludes the dims an attribute is [not owned per](schema.md#partial-the-granularity-of-an-override), so replacing on it would drop a whole staged series to one row — two edits at different snapshots are two coordinates, not two writes to the same place.
The same distinction governs [the read overlay](#reading-with-pending-edits) and the restate below, and it is the one thing easy to get wrong here.

Three interactions need stating, because each is where replacing by coordinate alone is not the whole story:

- **`remove` after `set`** on the same label: the tombstone wins, since a deleted label has no values.
  A tombstone reaches another file's rows, so it stays an anti-join at read and write rather than a replace — the attribute rows are keyed by coordinate, the tombstone by label.
  A layer's tombstones apply only to its parents in [the fold](read-path.md#owner-map), so the staged collapse drops its own rows itself: a row naming a removed label, and a row whose group column names a tuple staged deleted, by `remove_group` or by `remove`'s cascade.
- **`add` after `remove`** of the same label: the label exists again.
  The axis replaces on its key, so the `add` row displaces the tombstone by construction.
  So do the parent's values for it, which only the displaced tombstone reached; its tuples stay removed.
- **`set` on a label this record also added**: correct as-is, the attribute living in `inputs/` and a property patching the staged row.

The [non-`partial` rule](schema.md#partial-the-granularity-of-an-override) is the subtle one.
Overwriting one value along a non-partial axis means the layer must carry that label's _whole_ extent along it, so such a `set` reads the resolved series for that key and stages the untouched coordinates alongside the edit.
That is the one read of parent data an edit makes, and it happens as the rows are staged rather than at write: the staging table then already holds what the layer will hold, so a write of `edits` has no completion step of its own.

The scope is the key the edit named, never the attribute: a label no edit mentioned keeps its rows in the parent, and a layer carrying them would claim an extent it was never given.
**A group outside `partial` is owned whole the same way.** A `set` on one connection's `efficiency` stages every other connection's resolved value beside it, and the scope is the attribute: a connection attribute's key names no label of a `partial` dim, so the key the edit named is `(attribute)` alone.
A staged row that leaves the axis NULL is the exception, since [the broadcast rule](record.md#the-broadcast-rule) already makes it cover every label — there is nothing left to carry, and a carried row beside it would overlap.
Carried rows go in only where no edit already holds the coordinate, so a later `set` on a carried coordinate replaces the fill rather than tying with it — the anti-join that keeps a fill off an occupied coordinate is the whole of what orders the two.

## Validation

[The writer](writing.md) validates structurally, so writing `edits` inherits that.
What editing adds is edit-level, caught when the edit is **staged**, not at write — a caller should learn about a typo'd attribute at the line that typed it, not fifty edits later:

- an undeclared attribute, result, property or keyword, or a keyword the attribute does not vary over;
- a label of a `partial` dim the record does not resolve, `add` them first;
- a label whose categories do not carry the attribute ([traits](schema.md#traits)), judged by its current categories; a label with no category passes;
- a value an `Enum` property does not list, in `add` or `set`;
- an `add` missing a nested dim's parent key, or naming an attribute.

The label read these need is the one a property keyword already performs, so checking categories costs nothing beyond it. Two coordinates over one categorized dim — a contract's `from` and `to` — name no one label whose categories decide, so neither is checked against them.

## Staging

Staged rows live in DuckDB tables on the record's own connection:

```sql
CREATE TABLE staged_inputs_<attr>_<id>   (<that attribute's long columns>);
CREATE TABLE staged_outputs_<attr>_<id>  (<that attribute's long columns>);
CREATE TABLE staged_axis_<dim>_<id>      (<the axis key>, <the dim's properties>, deleted BOOLEAN);
CREATE TABLE staged_<group>_<id>         (<group struct>, <into>, <the group's properties>, deleted BOOLEAN);
```

**Every table is shaped like the file it becomes**, which is the rule the rest of this section is consequences of. So there is no table whose columns are a union over things the format keeps apart, and a column the schema does not declare has nowhere to go — [`add`](#add-remove) rejects one rather than widening a table to fit it, there being no declared dtype to give it.

**One table per staged attribute**, because that is the file it becomes: its columns are [the attribute's own coordinates](format.md#the-long-schema) and `value` has the attribute's declared type.
A shared table would have to widen `value` to text and carry every declared dim, which costs twice: the value needs casting back on the way out, and a NULL in a dim column becomes ambiguous between "this attribute has no such axis" and [the broadcast rule](record.md#the-broadcast-rule)'s "every value of it".
Per attribute both questions are answered by the table's shape, so neither is asked.

A result the schema never declares has no declared type to take; the table records the one its frame arrived with, settled once at creation rather than guessed per read.

**One table per staged axis and per declared [group](schema.md#groups)**, mirroring [the maps the fold builds](read-path.md#owner-map): its key, its properties and a tombstone column, so `add` writes one row per label and `remove` one tombstone. Both replace on the key, so re-adding or removing a label displaces its earlier row rather than stacking beside it, while a property `set` patches one column in place.
`entity` is staged as any other dim, `staged_axis_entity_<id>`, and reaches [the fold](read-path.md) as `axis("entity")` with no special case.

These tables are the **only** place a staged row exists: [the reads](#reading-with-pending-edits) read them rather than holding a copy.

DuckDB rather than in-memory objects, for three reasons that all matter: the reads are already a fold, so staging elsewhere would mean marshalling every edit into a relation on every read; a large edit is a bulk insert rather than ten thousand Python objects; and a write of `edits` hands each table to the writer as the file it already is, no collapse in between.

Tables in the workspace's database, like the folded caches, so on `:memory:` they vanish with the workspace and never appear on disk.
A record whose edits must survive a process boundary should be written as a child.

An edit **replaces** what it names rather than appending, so a table holds one row per key and reading it is a scan — no ordering column, and edit order is just which edit ran last.

## Reading with pending edits

The inherited `Record` members must reflect the edits; otherwise `set` then read gives the old value, which no caller would expect.

A set of pending edits **is** a layer — an unwritten one.
So the reads compose the same way: the staged rows are the last layer, resolved over whatever the record was reading before.

```text
resolved = fold(parent layers..., staged rows)
```

This is exactly one more fold step over the same [owner-map machinery](read-path.md#owner-map), with the staging tables standing in for a layer directory — over a layered base or a plain directory alike, a directory being a layer laid out like any other.
It costs what one more layer costs, **per read**: a written layer is folded once and cached forever, and the staged one cannot be, being the only layer that can still change.
So the fold is materialised up to the last layer that cannot change under the reader, and the staged step on top of it stays a relation — which is also why an edit needs no invalidation, there being nothing cached to invalidate.

`flags` follows for free, computed in the fold's own ownership `GROUP BY` as it is for any layer: a staged row setting a dim adds it to `varies`, one leaving it NULL adds it to `broadcast`, and a staged curve sets `breakpoints`.
It says nothing about a property, which is a column of its subject's axis or group file and read from `properties` or `members`, staged edits included.

An axis overlays per column rather than per row: a staged label's edited columns win, and a label the edit did not name keeps the base's whole row.
So two `set` calls for two properties of one label compose instead of the later one blanking the earlier's column.

<!--
SPDX-FileCopyrightText: datarecord contributors

SPDX-License-Identifier: CC-BY-4.0
-->

# Open questions

- **May an entity's existence depend on a dim?** `Dimension.keys` said yes — a generator present in scenario `high` and absent from `low` — and is [now deleted](schema.md#existence-does-not-vary-along-a-dim), with nothing in its place. An entity exists or it does not.

  What it cost to keep was a second question with no good answer: what an entity tombstone means for a connection keyed by fewer dims. Deleting an entity in one scenario removed a connection that was not scenario-scoped, even though the entity survived elsewhere, and no projection recovers the difference — the connection row has no scenario column to write it into. The conservative reading was implemented and pinned by an `xfail`.

  What it cost to drop is narrower than it looks. A **value** may still vary along any axis; it is the **thing** that may not. A stochastic network with a different `capital_cost` per scenario is an attribute over `{entity, scenario}`, which [the file split](format.md#where-a-value-lives) already places in `inputs/`. Only membership itself is unrepresentable.

  Reopening it means deciding all three: whether it is needed at all, whether an entity table and a group may disagree about which dims scope them, and what the coarser one's rows mean if they may.

- **Whether `partial` should ever be per attribute.** [The schema](schema.md#partial-the-granularity-of-an-override) puts it on the axis because it is true of every attribute varying over that axis.
  A counter-example would be an attribute whose series a consumer _can_ accept in pieces while others cannot — none known, and permitting it would make the fold's key vary per attribute, which the fixed inputs key assumes it does not.

- **Whether a broadcast survives materialisation.** A materialised ancestor's owner map stores a NULL row already expanded to the labels that existed then, and seeds a child's fold without re-expanding.
  So `set("p_max_pu", 0.9)` reaches a generator added — or re-categorized — in a child only while the ancestor is unmaterialised; plain NULLs behave the same.
  One level down, a `WorkingRecord` folds its committed prefix once, so a label staged or re-categorized there is not reached by a parent's NULL even while the parent is unmaterialised.

- **Whether staged results should be invalidated by a later input edit.** Results attached through [`set(..., kind="outputs")`](working-record.md#results-through-kindoutputs) were computed from the inputs pending at that moment, so editing an input afterwards leaves them describing a record that no longer exists.
  Dropping them on the next input edit was considered and rejected: it silently discards work the caller may have wanted, and a record that guesses which of the two the caller meant to keep is worse than one that keeps both and says so.
  Coherence is the caller's business, and writing `edits` writes whatever is staged.
  If this bites in practice, a `pending`-level warning is the cheap next step rather than a silent truncation.

- **Whether a `WorkingRecord` over an open record stages against a snapshot.** Writing into an open record invalidates its owner-map cache.
  A mutable record would need the same invalidation per edit, or to stage against a snapshot taken at construction.
  The second is simpler and arguably more correct — an edit sequence should not see another writer's changes mid-flight — but it means a record can go stale.

- **Registering a record's relations as named views.** A frontend issuing ad-hoc SQL needs names in a catalog rather than Python objects, which `CREATE VIEW` against a file-backed catalog provides — each view's definition being the resolved overlay, materialising nothing.
  Creating a view binds its schema, so registering N attributes costs N footer reads; and catalog reopen cost is linear in view count, which argues for one catalog per record rather than one shared.

- **What else a `Record` should answer about its labels without handing over a frame.** [`flags`](record.md#flags) sets the shape — cheap derived metadata a consumer plans against without opening a file — but answers only per attribute.
  `entity -> entity_type` is now a column of the resolved axis, [names being unique record-wide](format.md#entity-is-unique-across-types), so it is one frame rather than one per type; "which categories have live labels" and "how many labels a category has" are still frames to collect.
  What is open is the granularity: those are the same kind of question, and a protocol growing one method per question is worse than the frames it replaces.
  Whatever is chosen, it has to be answerable off the fold, which is where a record's membership already lives.

- **What a NULL group struct reaches when two of its fields are categorized.** A NULL `connection` reaches the tuples whose `entity` field names a label [carrying the attribute](read-path.md#owner-map). A group with two fields over categorized dims — a `contract` between two entities — has no single label to ask, and its NULL reaches every tuple; requiring both, or either, would each be a reading the schema does not state.

## Settled

- **Whether [`flags`](record.md#flags) needs a record-level counterpart** — it is one. `flags()` answers per record, every attribute included, and `flags(**categories)` per category, restricted to what those categories carry ([properties](proposals/dep-0012-properties.md#entity-is-an-ordinary-dim)). An attribute over an axis alone or a group outside `partial` is reachable through the first.

- **What a NULL group struct reaches across entity types** — the tuples whose field over the categorized dim names a label carrying the attribute, as a NULL on the dim itself reaches its carrying labels ([the owner map](read-path.md#owner-map)). A constant link `efficiency` no longer lands on generators' connections.

- **What a connection value staged without its `bus` should mean** — nothing; the call is [rejected](working-record.md#set).
  `{entity: dc, bus: NULL}` is [no group value](record.md#the-broadcast-rule), a group value being a whole tuple or NULL, so it is refused wherever a row comes in.
  The alternative, "every connection of this entity", would broadcast over part of a tuple — a group column broadcasts only whole, a NULL struct meaning every tuple.

- **Whether `within` should subsume `bus`** — no; [groups](schema.md#groups) do it.
  The recorded blocker was that `bus` inverts the rule NULL follows for a dim: a NULL declared dim means "all values" and the fold expands it against the axis, while a NULL `bus` is compared NULL-safely and never expanded.
  That premise did not survive. Expansion is governed by whether a coordinate is in the fold's key set, and a non-`partial` dim is never expanded either — so the behaviour that "makes a dim a dim" was never uniform, and `bus` was not an exception to it.
  A group states the rule instead of carrying an exception: a group coordinate addresses a sparse subset with no axis to expand against, which is [the broadcast rule](record.md#the-broadcast-rule) rather than a special case in it.
  Since [a group is one struct column](proposals/dep-0010-a-group-is-a-struct-column.md), a connection's `bus` is a field of `connection` rather than the dim's column, so the dim `bus` broadcasts like any other and the exception is gone from the dim entirely.
  Since [a group is a dim](proposals/dep-0010-a-group-is-a-struct-column.md#amendment-a-group-is-a-dim) it is gone from the group too: a NULL struct expands against the resolved group, as a NULL dim does against its axis.

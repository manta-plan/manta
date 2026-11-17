<!--
SPDX-FileCopyrightText: datarecord contributors

SPDX-License-Identifier: CC-BY-4.0
-->

# DEP 7: staging without `_seq`

| DEP     | 7                      |
| ------- | ---------------------- |
| Title   | staging without `_seq` |
| Author  | Jonas Hörsch           |
| Status  | Implemented 2026-09-02 |
| Created | 2026-09-02             |
| Version | v0.1.0a1               |

Landed in [staging](../working-record.md#staging) and [committing](../working-record.md#edits); this page is kept as the argument for the change rather than as the current description, and those pages are authoritative where the two disagree.

Two departures from the sketch below are worth naming. An axis edit is not delete-then-insert: an axis row's columns are independently editable, so a `set` there **patches its one column in place** (`UPDATE ... FROM`, plus an `INSERT` for a label no row yet holds), which is what keeps a sibling attribute without a completion step — `_complete_axis` was drafted and then dropped for it. And `_axis_layer` stays, reduced to a scan for a `partial` axis and a union with the untouched base labels for one owned whole, rather than going entirely.

The residual risk the argument below flags — `_complete_owned_whole`'s anti-join key and the long-row replace key _agreeing_ rather than being one derivation — was retired as it suggested: both now read `_long_key`, so the fill an anti-join excludes and the row a later `set` replaces are one key by construction, not two that happen to match.

Every staging table carries a `_seq`, and every read folds on it. Make each edit replace the rows it names — delete then insert — and the column goes from all four kinds, along with the four folds that read it. A staging table then _is_ what the layer will write, and reading one is a table scan.

## What starts it

[Staging](../working-record.md#staging) holds the rule this proposal finishes: **every table is shaped like the file it becomes.** No table satisfies it, because every one carries a `_seq` no file has, and three of the four need a fold to mean anything.

`_seq` serves four purposes, and they are not the same problem:

| kind               | what `_seq` does                                    | folded by             |
| ------------------ | --------------------------------------------------- | --------------------- |
| axis               | orders two **partial** rows for one label           | `_collapsed_axis`     |
| entity axis        | orders two whole rows for one name                  | `_collapsed_entities` |
| `inputs`/`outputs` | orders two rows for one coordinate                  | `_collapsed_inputs`   |
| groups             | orders two rows for one `group_key`                 | `_collapsed_group`    |
| —                  | `_CARRIED_SEQ`: marks a row a **fill**, not an edit | (see below)           |

The last is a different thing wearing the same column, and it is the one that decides whether `_seq` can go entirely.

## The construct

**An edit replaces the rows it names.** Delete the keys, insert the new rows:

```sql
DELETE FROM <table> WHERE <key> IN (SELECT <key> FROM _rows);
INSERT INTO <table> BY NAME SELECT * FROM _rows;
```

`_rows` is the arrow relation `_values_relation` builds, registered by replacement scan — the same crossing every insert here already makes, and the same `DELETE`-by-scan `_release_from_other_types` uses. Nothing becomes Python objects per row, which rules out `INSERT … VALUES`.

The key is per kind, and in each case it is the one the fold already partitions on: the label for an axis, `entity` for the entity axis, the coordinate set for a long file, `group_key` for a group. So the delete removes exactly what `_latest_per` would have discarded.

### Axis rows must also become complete

Delete-then-insert alone is not enough for an axis, because there the _rows_ are partial, not merely duplicated. One `set` stages a row carrying that attribute's column and NULL for its siblings; replacing the row would clear them.

So a `set` on an axis attribute stages **the complete row for each label it touches**: the previously staged row where one exists, otherwise the base's, with this edit's column replaced. Where a label has no base row, the staged columns are the whole of it, as today.

The base read is already there — `_stage_axis`'s scalar arm reads `self._base.dims.axes.get(dim)` to know which labels exist. The mapping arm would start, as a point lookup against a folded relation the `NodeCache` already holds.

That is what retires `_collapsed_axis`'s `max_by(a, _seq) FILTER (WHERE a IS NOT NULL)` — the `FILTER` stops a sibling's NULL from winning, and the `max_by` makes two `set`s commute. With rows complete, both are what the table already holds.

Downstream of it, `_axis_frame`'s outer join and per-column `coalesce` go — they exist to fill an untouched label that would otherwise read as cleared — and `_axis_layer`'s semi-join for a [`partial`](../schema.md#partial-the-granularity-of-an-override) dim goes with them: with only touched labels present and rows complete, **the table's rows are the touch record.**

### `_CARRIED_SEQ`'s job is already done by an anti-join

`_complete_owned_whole` copies base rows into a long staging table so the layer carries an extent it now [owns whole](../schema.md#partial-the-granularity-of-an-override). Those rows are fills, and a real edit on the same coordinate must beat one regardless of arrival order — which is what `_CARRIED_SEQ = 0`, below every edit's, expresses.

It never fires. The method's third anti-join drops any coordinate the table already holds, and its key set is the one `_collapsed_inputs` partitions on, so a fill and an edit cannot coexist on one coordinate. Checked against the fixture's three attribute shapes — no `owned_whole` dims, one, and one with breakpoints — the anti-join's `[*scope, *present, "breakpoint"]` and the partition's `input_key ∪ dims ∪ {breakpoint}`, both intersected with the file's columns, are the same set every time.

So the priority class is redundant: the anti-join keeps fills out of occupied coordinates, and under this proposal a later `set` on a filled coordinate deletes the fill before inserting. Two mechanisms, one of which was already sufficient.

**Worth being exact about the residual risk.** The two key sets _agree_ rather than being _derived from one place_ — `_complete_owned_whole` builds `[*scope, *present, "breakpoint"]` and `_collapsed_inputs` builds its own. They match today for every shape the suite exercises, and a schema where they diverge would already be a bug (a fill surviving beside an edit, resolved only by `_CARRIED_SEQ`). Landing this should make them one derivation rather than two that agree, which is a small refactor and the honest way to retire the guard.

### The entity axis joins, and the two collapse modes go with it

`dims/entity.parquet` has a single-label key and its columns are [one indivisible fact](../format.md#the-entity-axis) — a name exists, is of this type, is alive or dead. Delete-then-insert on `entity` gives `remove` then `add` under another type one row by construction, where `_collapsed_entities` folds whole-row to get the same answer today.

That retires the last place staging folds differently depending on what it is folding. `_collapsed_axis` folds per column and `_collapsed_entities` per row, and the difference is real: an axis row's columns are independently editable, a membership row's are not. Under this proposal neither folds, so the distinction stops being a branch and becomes what it always was — a fact about the data.

It does change `remove`, from "append a tombstone" to "replace the row with a tombstone". The semantics are the same because membership is one fact per name, but staging is no longer append-only.

## The alternative to re-evaluate

**`INSERT … SELECT … ON CONFLICT (<key>) DO UPDATE SET`** is the same idea in one statement, and DuckDB supports it on the arrow-relation form, so the column-wise insert path survives either way.

Two reasons it is not the proposal:

- **It needs a primary key on the staging table.** Tables are created from a relation by `_shape(...).create(name)`, which carries no constraint, so this would mean DDL after create — a second step back for exactly the tables that rule was introduced to make uniform.
- **`DO UPDATE SET` needs its column list built per call**, where delete-then-insert is the same two statements whatever the edit names.

Neither is fatal, and a true upsert is one statement rather than two. **Re-evaluate once the shape here is settled** — if the delete-then-insert version lands cleanly, the question is only whether `_shape` can carry a key without giving up being the single source of a table's shape.

## What this buys

**Four folds go**, and with them `_latest_per` itself: `_collapsed_axis`, `_collapsed_entities`, `_collapsed_inputs`, `_collapsed_group` become the tables they read. The tombstone anti-join in `_collapsed_inputs` stays — a component tombstone reaching another attribute's rows is a cross-table fact, not an ordering one.

**Reads become table scans.** `_axis_layer` runs per axis on every commit and every staged read; today each call is an aggregate, an outer join, a per-column `coalesce` and possibly a semi-join. The work moves to one base lookup per `set`, paid once.

**The staging rule holds all the way.** "Shaped like the file it becomes" currently means columns; after this it means rows too, and a staged table can be handed to `write_record` without a fold in between. `StagedSource` becomes projection-free — its members return tables.

## What it costs

**A `set` reads the base, for axes.** The mapping arm gains a point lookup. Against it: the scalar arm already does this, and the relation is one the `NodeCache` holds.

**Append-only goes.** Staging becomes read-modify-write, so an edit is no longer a pure append. That is what makes a row complete and a key unique — but a reader who assumes "staged rows accumulate" will be wrong.

**Two statements per edit where there was one.** Both are scans over the same registered relation, and edits are not the hot path; the reads are.

**A carried row's protection becomes structural rather than belt-and-braces.** Today the anti-join and `_CARRIED_SEQ` both keep a fill from beating an edit. After, only the anti-join does — see the residual risk above.

## How to know it worked

**`_seq` is absent from every staging table.** The single assertion the whole proposal is downstream of: a `_shape` still declaring it means something still orders rows.

**Two `set` calls on one axis still commute**, which is what the `FILTER` bought. Existing coverage should pass unchanged — if `set("icon", …)` then `set("budget", …)` on one label loses the icon, the row was not complete.

**A `partial` dim's layer carries the touched labels and no others.** `test_a_partial_axis_stays_a_patch` pins this from the outside; it says the semi-join was subsumed rather than dropped.

**A `remove` then `add` under another type is one row** — `test_a_freed_name_may_be_reclaimed_by_another_type`, now by construction.

**A whole-owned extent still carries its untouched coordinates after two edits.** `_complete_owned_whole`'s idempotence is what this leans on hardest, so the case to pin is a second `set` on the same attribute at a different coordinate: the first edit's fills must survive, and the second's must replace the fill on its own coordinate.

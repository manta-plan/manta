# datarecord changes

Manta carries a vendored fork of [energy-models/datarecord](https://github.com/energy-models/datarecord)
in `datarecord/`. This file records how the fork diverges from upstream, so the two can be
reconciled later.

- **Current divergence** is the summary of where the fork differs from upstream right now.
  Keep it current: an entry that is reverted comes out of it.
- **Log** is append-only, newest last. Every change to `datarecord/` gets an entry, and so
  does every revert. Reverts are logged, not deleted.

## Upstream baseline

| | |
|---|---|
| Repository | https://github.com/energy-models/datarecord |
| Commit | `521fef238ad3aabcd6d561c3c221344fc5efc84c` (2026-10-14, "chore: number proposals (#69)") |
| Vendored | 2026-10-23 |
| Method | Verbatim copy of the GitHub tarball for that commit. No `.git`, nothing excluded. Upstream's `.gitignore` ignores `.claude/`, but upstream tracks the `.claude/CLAUDE.md` symlink (to `AGENTS.md`), so it has to be added with `git add -f`. |

To diff the fork against its baseline:

```bash
gh api repos/energy-models/datarecord/tarball/521fef238ad3aabcd6d561c3c221344fc5efc84c > /tmp/dr.tar.gz
mkdir /tmp/dr && tar -xzf /tmp/dr.tar.gz -C /tmp/dr --strip-components=1
diff -r /tmp/dr datarecord
```

## Current divergence

None. `datarecord/` is identical to the baseline.

## Known issues at baseline

These are upstream problems, not divergence. They're recorded here because fixing any of
them in the fork creates divergence that's worth sending upstream.

### Incompatible with DuckDB 2.0

`pyproject.toml` declares `duckdb>=1.5.4` with no upper bound, so a fresh install resolves
DuckDB 2.0.0. Under 2.0.0 the suite has 84 failures and 111 errors. With every other
dependency held at the `pixi.lock` versions, the counts are the same, so DuckDB alone causes
all of them. At the `pixi.lock` versions (DuckDB 1.5.5) the suite passes: 447 passed,
9 skipped.

There are four causes, each confirmed against DuckDB 1.5.5 and 2.0.0 directly. The first two
hide the third: with only those two fixed, the suite still has 19 failures and 7 errors.

1. `DuckDBPyConnection.values(...)` drops the aliases on its expressions and names the
   columns `col0, col1, ...`. Call sites: `duck.py` (`DuckTypes.empty_relation`) and
   `layered/categories.py` (`_per_combination`). Symptoms: "missing long-schema columns",
   "`add(...)` was given columns the schema does not declare", and binder errors such as
   `Values list "t" does not have a column named "entity_type"`.
2. `DuckDBPyRelation.fetchone()` was removed ("Use rel.limit(1).fetchall() instead"). Call
   sites: `mutable.py:1030`, `mutable.py:1860`, `layered/resolve.py:1028`,
   `layered/write.py:308`, `layered/write.py:314`, and in tests `test_connections.py:281`
   and `test_owner_map.py:368`. `fetchone()` on a connection, as in `store.py:408`, still
   works.
3. An ordered relation no longer binds the aliases of the relations joined into it. A
   qualified `col("s", name)` projected after `.order(...)` fails with
   `Referenced table "s" not found`. Call sites: `tools/pypsa.py`, in `_left_join_values` and
   in `Index.left_join` as used by `_series_frame`. This breaks `PyPSA.build`.
4. `EXPLAIN` spells operators in title case (`Hash Join`, `Nested Loop Join`) where 1.5
   wrote `HASH_JOIN`, `NESTED_LOOP_JOIN`. Only
   `test_owner_map.py::test_the_fold_broadcasts_by_hash_join` depends on the spelling. Under
   2.0 its positive check fails, and its negative check (no nested-loop join) would pass
   whatever the plan.

## Log

### 2026-10-23: vendored upstream at `521fef2`

Copied upstream at the baseline commit into `datarecord/`. No changes.

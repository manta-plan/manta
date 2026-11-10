# How the record server exposes a record over SQL

As of 2026-10-30 (records and catalogs updated the same day). A proposal, open to change: nothing outside this repo
depends on these names yet.

The record server opens a datarecord store and serves it over DuckDB's Quack
protocol. The browser's DuckDB-Wasm attaches it as `r` and reads it with
plain SQL, either in the browser (`FROM r.attributes.p_nom`) or on the server
(`quack_query_by_name('r', 'FROM attributes.p_nom')`). This note describes
the names a client sees: which catalogs, schemas and views there are, and
which parts come from datarecord and which are ours.

## In short

```
<catalog>.<schema>.<view>

catalog   the record and scenario: <record>__<scenario>,
          e.g. bel_pre_aggregated_perfect__patch
schema    dims | properties | attributes   datarecord's relations, as is
          manta                            ours: app views over those three
```

| Schema | Comes from | Holds |
|---|---|---|
| `dims` | datarecord: `record.dims` | one view per dimension: its labels |
| `properties` | datarecord: `record.properties` | one view per dimension with properties: its labels and their properties |
| `attributes` | datarecord: `record.attributes` | one view per attribute with rows, layers already folded |
| `manta` | ours (`app/manta_views.py`, `app/scenarios.py`) | what the app assumes about a record (locations, branches, …) and the store's scenarios |

**What's datarecord's:** the three groups of relations and their contents.
Each view is `CREATE VIEW <schema>."<name>" AS <relation.sql_query()>`, so
it holds datarecord's own resolved SQL. Nothing is copied or rewritten, and
the parquet files are read lazily on query.

**What's ours:** turning each group into a DuckDB schema and choosing its
name, the `manta` schema, and the scenario catalogs. Datarecord defines no
SQL schema names. We used its API names (`record.dims`, …) because they were
the obvious match. Separate schemas also keep same-named relations apart:
`dims.entity` and `properties.entity` are both "entity".

## The datarecord schemas

For `BEL-pre-aggregated-perfect` (the 30 October records), revision `inputs`:

| Schema | Views | Example | Columns |
|---|---|---|---|
| `dims` | 11 | `dims.bus` | `bus` |
| | | `dims.connection` | `connection` (STRUCT{entity, bus}) |
| `properties` | 7 | `properties.bus` | `bus, carrier, type, x, y, unit, location, shape_onshore, shape_offshore, country` |
| | | `properties.entity` | `entity, ctype, carrier, sign, type` |
| | | `properties.connection` | `connection, role` |
| `attributes` | 63 | `attributes.capital_cost` | `entity, attribute, breakpoint, value` |
| | | `attributes.p_max_pu` | `snapshot, scenario, entity, attribute, breakpoint, value` |

- An attribute's view has its declared dims, then `attribute`, `breakpoint`
  and `value`. A row without a snapshot holds for every snapshot.
- Attributes without rows have no view: datarecord leaves them out of
  `record.attributes`.
- One_of dims (`ctype`, `role`) are views in `dims` like any other, although
  the store has no `dims/` files for them (DEP 24).

## The `manta` schema

Plain SQL over the three schemas above. It doesn't call datarecord, so it
would work over any database holding those views.

| Name | Kind | Columns | What for |
|---|---|---|---|
| `bus_location` | view | `bus, carrier, location, x, y, virtual` | every bus at its location; `EU` (PyPSA-Eur's copper plate) is virtual |
| `locations` | view | `location, x, y, buses, carriers` | real locations: what the map draws as points |
| `location_zones` | view | `level, location, zone` | zones from `busmap_*` attributes, if any |
| `branches` | view | `entity, ctype, carrier, bus0, bus1, location0, location1, scope` | input → output pairs of lines and links, from `properties.connection` roles; `scope` is `within`, `between` or `virtual` |
| `attached` | view | `entity, ctype, carrier, bus, location, virtual` | generators, loads, stores and storage units at their bus |
| `regions` | view | `entity, component, bus, location, wkt` | Shape polygons, if the record has them |
| `attribute_summary` | table | `attribute, dim, label, bus, constant, series_rows` | per attribute and subject (entity, bus, …): its constant value and how many series rows. Built at start, so one query fills an item's attribute list |
| `ctype_attributes` | view | `ctype, attribute, entities` | which attributes each ctype stores; elsewhere, an absent value means the manifest default |
| `revisions` | table | `name, id, parent, kind, label, description, catalog` | the store's named revisions (from `<store>.json`), as scenarios or run results |
| `scenario_changes` | table | `scenario, attribute, dim, label, bus, before, after, series_rows, ratio` | per scenario, each value its own layer changes against its parent |

`revisions` and `scenario_changes` are about the whole store; every catalog of
the store holds the same copy.

Some of this relies on PyPSA-Eur conventions rather than on anything
datarecord records:

- A bus's location is its `location` property.
- `EU` is a virtual location.
- A zone level is a `busmap_*` attribute.
- A revision's kind (scenario or run result) is guessed from its layer: a
  revision is a run result when most of the attributes it writes are new to
  its parent. `<store>.labels.json` can override the guess.

## Records and scenario catalogs

The server serves every store under one root (`RECORDS_ROOT`: a local folder,
or `s3://manta-records` through datarecord's remote stores); each store is a
record. Every revision of kind `scenario` of every record is attached as its
own in-memory catalog, `<record>__<scenario>` (lowercased, other characters as
`_`), with the same four schemas:

```sql
FROM r.bel_pre_aggregated_perfect__inputs.attributes.capital_cost  -- Base case
FROM r.bel_pre_aggregated_perfect__patch.attributes.capital_cost   -- Wind and solar stress test
```

- There is no record in the default catalog: a query always names one.
- Run results (`results`, `patch_results`) get no catalog for now. They're
  meant for a later Inspect page.
- `manta.revisions.catalog` names each scenario's catalog (NULL for a run
  result).
- **A record opens on first use** (a project asking for it), after the
  server has locked down. datarecord's SQL reads Python objects by name
  (`FROM u`), which DuckDB only resolves while external access is on, so the
  lockdown leaves it on and switches off the HTTP file systems instead.
- A client attached before a record opened doesn't see its catalogs as
  `r.<catalog>`: Quack's client reads the catalog list when it attaches. The
  app runs every query on the server (`quack_query_by_name`), which sees
  them; the explorer re-attaches.
- The client picks a scenario by naming its catalog. The server stays shared
  and stateless: no `USE` or `SET` per client, which the read-only guard
  refuses anyway.
- A view binds unqualified names in its own catalog, so the `manta` views
  work unchanged in every catalog. A table built with `CREATE TABLE … AS`
  doesn't, so `attribute_summary` qualifies its sources with the catalog.
- datarecord's view SQL refers to objects it registers in the default
  catalog (`dims_…`, `owner_map_…`). DuckDB still finds them from a view in
  another catalog. The relation objects must stay alive while the views do,
  so the server keeps them.

## What can change, and what it costs

All names are ours to change: they're not stored anywhere, and only this
repo uses them (the app, the explorer page, the tests). A rename touches:

- the server: `KINDS` in `app/record.py`, the SQL in `app/manta_views.py` and
  `app/scenarios.py`, and `tests/`;
- the app: `src/lib/recordServer/queries.ts` (names go through
  `serverName()`/`localName()`, but the schema names are written in the SQL);
- the explorer: `SCHEMAS` in `static/index.html`;
- the README.

Two rules should hold whatever the names:

1. Same-named relations of different groups must not clash
   (`dims.entity`, `properties.entity`).
2. Every scenario catalog has the same schemas and views, so a query works
   in any of them, of any record, by changing only the catalog.

## Questions for datarecord

1. **Schema names:** keep `dims`, `properties` and `attributes`, matching
   `record.dims`, `record.properties` and `record.attributes`? Would you rather
   datarecord define them, for example a `record.to_duckdb(con, catalog=…)`
   that creates the views, so other clients name things the same way?
2. **`dims` and `properties`:** a dimension with properties appears in both.
   Should `properties` replace `dims` for those, or is it worth keeping both?
3. **`manta`:** rename it (`app`, `views`, …)? Does any of it belong in
   datarecord instead? `attribute_summary` and `scenario_changes` are
   generic; `locations`, `branches` and `attached` are PyPSA-specific.
4. **Revision kind:** could datarecord record whether a revision is a
   scenario or a run result, instead of our guess from the layer contents?
5. **Catalog names:** `<record>__<scenario>` comes from the store's folder
   name and the names in `<store>.json`. Are these meant to be stable enough
   to appear in queries?
6. **External access:** could datarecord register its intermediate relations
   with `con.register` instead of having DuckDB find Python variables? Then
   the server could switch external access off entirely (with the records
   bucket as the only allowed path) and still open records on demand.

Settling these now is cheapest: once other clients query the server, the
names become harder to change.

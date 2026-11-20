<!--
SPDX-FileCopyrightText: Manta contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Design note: data access for the frontend

How the FE reads the data of a session: constant values and the owner map in place of a full scan, changes between revisions, and settling in SQL.

Part of the datarecord-session plan, draft 9. Start with the [overview](index.md). The codes F, S, R, D and I point to the [appendix](appendix.md).

This note covers three FE needs. [Constant values and the owner map](#2-constant-values-and-the-owner-map) is the component table, the drawers and the location graph: which attributes exist and which constant values they hold. [Changes between revisions](#3-changes-between-revisions) is the scenario panel and the change markers: what a scenario changes against the scenario it was made from. [Settling in the FE](#4-settling-in-the-fe) is how the FE turns raw rows into one value per coordinate.

Today quack-server prepares this data at open. It builds the table `attribute_summary` with one full scan over every attribute, and the view `ctype_attributes` over it. It builds the table `scenario_changes` for all scenarios at open. Nothing settles: the FE queries read raw rows and apply partial rules of their own, or none. [Replacing the manta objects](session.md#5-replacing-the-manta-objects) in the session note lists these objects (groups B and C).

In the target no prepared table exists and no full scan runs beyond DR's fold. The FE reads which attributes exist from the owner map, which holds no values. It reads constant values from the session's `static_<dtype>` views, with a filter on the attributes it shows. Changes are always those of a reference against its base: the reference's current revision is compared with the fork point, the last revision that both share. The FE asks the BE for the change summary of a reference. The BE finds the two revisions and passes the request to the session. The values before and after come from a diff registration of the same two revisions. The FE settles with its own TypeScript function that composes SQL; the session offers no settled view.

## 1. DR notions used in this note

A revision is one layer on top of its parent. A layer stores only the rows it writes. The data model has dimensions (entity, connection, bus, snapshot, ...) and attributes (`p_nom`, `p_max_pu`, ...).

A stored row can leave a dimension empty (NULL). It then stands for every label of that dimension. One `marginal_cost` row without a snapshot holds for all snapshots. One row without an entity holds for all entities. DR's registered views return rows as the layers store them, NULLs included (F20). Such rows are *raw*.

Several raw rows can cover the same coordinate, for example a constant and a series of one generator. DR's broadcast rule says which row holds: a NULL means every label, and the most specific row wins. To apply the rule is to *settle*. Settled rows have exactly one row per coordinate. Raw rows are smaller: one row with a NULL stands for every label.

When DR opens a revision it *folds* the layers. It works out which layer holds the rows in force for each attribute and label. The result is the *owner map*. One *map row* is one attribute plus one label on each of the attribute's dimensions in `partial`. These are the dimensions that a layer may cover in part. For PyPSA they are entity, connection, bus and scenario; the snapshot is never among them. A map row can leave a dimension NULL, which covers every label of it. The owner map assigns each map row to one layer. It holds no values and no row counts.

Each map row carries two flags per dimension, `varies` and `broadcast`. `varies.<d>` is true when some row sets a label on dimension `d`. `broadcast.<d>` is true when some row leaves `d` NULL. So `varies.snapshot` means "has a series", and `broadcast.snapshot` means "has a constant".

The owner map is the registered view `manta.<name>.owner_map`, for a revision and for a WR (F21, R7). Its columns are the dimensions in `partial`, then `attribute`, `layer_uuid`, `varies`, `broadcast` and `breakpoints`. DR's Python call `record.flags(ctype=T)` gives the attributes that reach a component type; it is a `bool_or` over the owner map.

## 2. Constant values and the owner map

Group B is today's `attribute_summary` table and the `ctype_attributes` view over it ([replacing the manta objects](session.md#5-replacing-the-manta-objects)). Both go away. This section shows where their answers come from in the target.

### What the FE needs

| # | FE feature | Question | Scope |
|---|---|---|---|
| N1 | Drawer, column picker | Which attributes does component type T store? | one ctype |
| N2 | Item drawer, entity page | For entity X: which attributes exist, which are series, the constant values | one entity, all attributes |
| N3 | Entity table, component page | The constant values of all entities of a ctype and carrier, every attribute, with a summary per attribute | one ctype, all attributes, all entities |
| N4 | Location graph | The capacity (`p_nom`, `e_nom`, `s_nom`) of the entities at a location | few entities, one attribute |

N3 is the largest need. Today the component page gets everything from one query. That query returns every stored attribute of every entity of a ctype and carrier. The page builds these elements from it:

| Element | Needs |
|---|---|
| Column list, ordered "most stored first" | per attribute: number of entities that store it |
| Visible columns: `PREFERRED_COLUMNS` first, then the rest with a constant | constant values of some attributes |
| Summary per attribute: same, range or mixed; series count; default count | counts, plus min, max and distinct of the constants |
| Cost cards and totals (`p_nom`, `capital_cost`, `marginal_cost`) | constant values of a few fixed attributes |
| Profile marker | "has a series", yes or no |
| Sort and search, in the browser | the loaded values |

### Where the answers come from

Two sources answer every need. The owner map tells which attributes exist, for which labels, and whether each is a constant or a series. The `static_<dtype>` views (below) hold the constant values.

| Need | Source | Change for the FE |
|---|---|---|
| N1 | `flags(ctype=T)` over the owner map, manifest for defaults | none |
| N2 presence | owner map filtered to the entity's map rows | `series_rows` becomes a yes or no |
| N2 values | one targeted read per attribute that the owner map marks as constant | several small queries |
| N3 | owner map for names and counts; `static_<dtype>` for the constants of the visible columns | one query per value type at page open |
| N4 | direct join on the three capacity attributes | none |

The `static_<dtype>` views can also serve N2 and N4, with a filter on the entity.

For N3 the counts need no value read. The stored count, the series count, the default count and the profile marker all come from the owner map.

The owner map has no series row count per map row. The FE shows such a number today: "N points", "N values over time", and the count column of the table drawer. In the target it shows a yes or no instead. Values stay out of the fold.

The `has_rows` probe that today runs on every attribute at open is replaced by `flags()`.

A filter on a dimension in `partial` reaches the Parquet scan through the registered views (R8; [what the DR stack changes](appendix.md#83-what-the-dr-stack-changes)). So `entity = ...` reads only the matching part of a file. For a struct dimension the filter must name a field: `snapshot.period IS NULL`, `connection.entity = ...`. A filter on the whole struct (`snapshot IS NULL`) is correct but reads every row group. Parquet keeps no statistics for a whole struct. DR will not change this.

On a WR a filter on a dimension reaches only part of the scans of the base map. A filtered read of a WR's owner map therefore costs more than one of a revision.

### The `static_<dtype>` views

The session adds the views `manta.<name>.static_<dtype>(entity, bus, attribute, value)` at every registration. They sit directly in the registration's DuckDB schema ([session service](session.md#3-session-service), [names in DuckDB](session.md#4-names-in-duckdb)). They belong to no view pack. Their definition uses no PyPSA-Eur convention. It uses only the owner map and the dimension names `entity`, `connection` and `snapshot` of a PyPSA record.

There is one long view per value type: `float`, `int`, `bool` and `str`. Each view has one row per constant value. One view per type keeps `value` in its native type, without columns full of NULLs.

Each view is a `UNION ALL` with one branch per attribute of its type. The session takes the branches from the owner map at registration: one per attribute over `entity` or `connection` that holds rows. The view covers every such attribute, not a short list. Each branch reads the rows without a snapshot, with the field form `snapshot.period IS NULL`. `bus` is set only for attributes over `connection`, which have one value per entity and bus.

The views are plain SELECT statements without a join chain. DR's PyPSA tool notes that chained joins over lazy relations are quadratic (`tools/pypsa.py:657-702`).

The views are long, not one per ctype, for these reasons:

- A filter on `attribute` removes branches before any read. So the length of the view costs nothing.
- A filter on `entity` reaches the Parquet scan.
- A filter on ctype is a join with `manta.<name>.properties.entity`, written by the caller.
- The FE's table query already consumes this long shape.
- The same view serves N2, N3 and N4.

No query runs without an attribute filter.

On a WR, the `static_<dtype>` views read the WR's views and so follow its edits. An edit never changes the views' shape.

The views follow the shape of the pinned DR, which is the stack tip (D18, D19). Two open DR PRs outside the stack will change that shape (F31):

| DR PR | Change | Effect on the views |
|---|---|---|
| 142 | A connection is keyed by its port: `connection STRUCT(entity, port)`, and `bus` becomes a property of the connection. | The `bus` of a connection row comes from `properties.connection`, or the column becomes `port`. |
| 146 | Global constraints become a dimension `global_constraint`. | The attributes of global constraints need a column `global_constraint` or views of their own. |

The views change when the pin moves to a DR with these PRs, not before.

### The preload list

The preload list names the attributes that the FE reads at page open, as a filter `attribute IN (...)`. It lives with the convention set and is easy to change. The view pack owns only this list, not the views.

The list is derived from the FE's code (`baby-manta`). It was checked against one input store, `composed_2050.store`, with 83.5k generators. Every listed attribute file is under 1 MB there.

| Attribute | Component types | FE feature that needs it up front |
|---|---|---|
| `p_nom`, `s_nom`, `e_nom` | generators, storage units, links; lines, transformers; stores | capacity totals, capacity card, location graph |
| `p_nom_extendable`, `s_nom_extendable`, `e_nom_extendable` | same | "N extendable" count |
| `build_year`, `lifetime` | capacity types | whether an entity counts in a period |
| `capital_cost` | capacity types | cost card |
| `marginal_cost` | generators, links, storage units, stores | cost card (constant rows only) |
| `investment_period`, `constant`, `sense` | global constraints | constraint chart |
| `efficiency` | links (per output bus), generators | first check of a modeller; over `connection`, so its rows carry `bus` |

Value types of the listed attributes: `build_year` is `int`, the `*_extendable` are `bool`, `sense` is `str`, the rest are `float`.

These attributes are not listed. The FE reads them on demand from `attributes.<A>`:

- `p_nom_min`, `p_nom_max`, `s_nom_max`, `e_nom_max`: the FE names them only for column order.
- `p_max_pu`, `p_set`, `s_max_pu`, `e_max_pu`: at page open the FE needs only "has a series", which the owner map gives. Their constants are cheap to read when wanted (see Cost).
- Everything else, including PyPSA-Eur custom attributes (`technology_group`, `asset_status`, ...).
- Results (`p_nom_opt`, `p`, `mu`, ...), which the FE already reads directly.

Attributes over `connection` in DR's PyPSA registry: inputs `efficiency`, `delay`, `cyclic_delay`, `rate`; results `p`, `q`.

### Changes in the FE

Entity table and Entities tab, as the FE works today (`componentPage.ts:109-161`, `InspectComponentPage.tsx:248-262`):

- The column picker shows names and a hint only (`default`, `series`, or none), no values. It offers every attribute the ctype stores, plus attributes with a ctype default from the manifest. Source: owner map and manifest.
- Visible by default: every attribute for which some entity stores a constant. Their cells need values.
- The FE reads all default columns at page open, in one query per value type with a filter on their attributes. This is today's behaviour. It relies on cheap constant reads, which the measurements support.
- The FE computes sort, search, totals and the same, range or mixed figures locally from the loaded rows. No statistics are stored beside a revision. A revision never changes, so loaded rows stay valid.

Other places:

- Parameters panel of a carrier: names and counts come from the owner map. The same, range or mixed figure of an unlisted attribute is computed when its row is opened.
- Item drawer and label drawer: on open, they read the attributes that the owner map lists for that entity or label.
- `ctype_attributes` and the profile "varies" check use the owner map.

### Cost

Measured on `europe-full-resolution` ([results of S2 and S3](appendix.md#81-results-of-s2-and-s3-on-dr-main), [what the DR stack changes](appendix.md#83-what-the-dr-stack-changes)):

- The planned `static` read, the constants of six attributes as one `UNION ALL`, returned 990k rows in 0.36 s on the server. The old `attribute_summary` scan took 24.6 s.
- Each attribute is one file per layer. Most listed attributes have files with constants only. `marginal_cost` returns 200k rows in 0.15 s.
- In a file that mixes constants with series, the PyPSA writer puts the constants in one block at the end. `p_max_pu` (1.2 GB) has its 2,465 constant rows in the last of 9,516 row groups.
- Reading these constants with `snapshot IS NULL` takes 1.5 s, because a filter on the whole struct prunes no row group. With `snapshot.period IS NULL` through the view it takes 0.2 to 0.4 s (PR 148). This is why the `static_<dtype>` views use the field form.

The clustering of constants is a behaviour of the writer, not a guarantee. A WR commit may scatter constants. Scattered constants cost more but stay correct. No writer change is planned (R12 closed).

## 3. Changes between revisions

Today quack-server builds the table `scenario_changes` for all scenarios at open. Per scenario, attribute and subject it holds before, after, changed series rows and the median ratio. It is a FULL JOIN of each attribute in the revision and in its parent, keeping rows whose value differs. A value restated unchanged does not count. In the target the table goes away. A change list belongs to a reference: by default its current revision against the fork point with its base reference ([the baseline](#the-baseline)). The two revisions need not be registered.

### What the FE needs

| # | Feature | Question | Scope |
|---|---|---|---|
| C1 | Scenario panel | per scenario and attribute: number of changed subjects, changed series rows, median ratio | all scenarios, at record open |
| C2 | Change table | label, bus, before, after, ratio | one scenario, one attribute, on click |
| C3 | Change markers in drawers and tables | before value at every changed coordinate | one scenario, on scenario switch |

C2 and C3 ask for the same rows: per changed coordinate, the value before and after. C2 reads one attribute when the user opens its table. C3 reads all changed attributes of the shown scenario at a scenario switch, to mark changed cells in the drawers and tables. So there are two needs: the summary (C1) and the changed values (C2 and C3).

### The baseline

A scenario is a reference: a named pointer that moves with every commit. A revision against its parent is therefore the wrong unit. After three commits, the newest revision's diff against its parent shows only the third commit. Figures per commit cannot be added up. So a diff compares references.

Each reference records its *base*: the reference it was made from. `store.json` holds it ([the `store.json` form](backend-mvp.md#the-storejson-form)). For a scenario it is the scenario it was created from. For a result it is the scenario reference that was solved. The root scenario has none.

The default baseline of a reference R with base B is the *fork point*: the last revision that the histories of R and B share. The default diff has two sides:

- `after` is the current revision of R;
- `before` is the fork point.

The default diff answers "what did this scenario change". It stays the same when B is edited later.

An explicit compare of two references uses the current revisions of both. It answers "how do the two differ today". Later edits of the base then show as differences.

An example with the store of the [example references](backend.md#example): `patch` has the base `inputs`. A user commits three edits to `patch`, and then one edit to `inputs`.

- The fork point of `patch` with `inputs` stays `9ec88f52`, the revision that `patch` was made from.
- The default diff of `patch` shows the changes of all its layers since `9ec88f52`. It does not show the edit of `inputs`.
- An explicit compare of `patch` with `inputs` shows the changes of `patch` and also the edit of `inputs`.

A scenario does not see later edits of its base, because its parent chain is fixed. The plan has no rebase.

### The change summary (C1)

The change summary belongs to a reference, not to a commit. By default it compares the reference's current revision with the fork point with its base reference. Per attribute it holds the number of changed subjects, the changed series rows and the median ratio. The scenario panel shows the summary of each scenario against its default baseline.

1. The FE asks the BE for the changes of a reference: `GET /v1/projects/{id}/session/changes` ([routes and Quack relay](backend.md#5-routes-and-quack-relay)).
2. The BE resolves the baseline to two revision ids. Without an explicit `before`, this is the fork point with the base.
3. The BE calls the session's `POST /summaries` with the two revision ids ([session service](session.md#3-session-service)) and passes the answer through.

Nothing is stored. The scenario panel is part of the record view, so the project's session runs when the panel asks.

The session computes the summary from the two revisions in Python, with DR's own `settle`. It does not use the SQL views of the diff, which are raw and do not apply the broadcast rule.

The summary is not part of the commit `meta`. It is computed at each request, so the scenarios of an imported store need no extra step.

### The changed values (C2, C3): a diff registration

A diff is a third kind of registration, beside `view` and `edit`. The FE asks the BE for it by reference:

```
PUT /v1/projects/{id}/session/registrations/{name}   {"kind": "diff", "store": "<store>", "after": "<reference or revision id>", "before": "<reference or revision id>"}
```

- `after` and `before` each name a reference or a revision id.
- Without `before`, the BE uses the fork point of the `after` reference with its base. It refuses the request if `after` is not a reference with a base.
- With two references, the diff is an explicit compare of their current revisions.
- The BE resolves both sides to revision ids before it calls the session ([routes and Quack relay](backend.md#5-routes-and-quack-relay)).

The session always receives two revision ids:

```
PUT /registrations/{name}   {"kind": "diff", "store": "<store>", "after": "<revision id>", "before": "<revision id>"}
```

Two revisions of one store define a diff, not two registered names. The session opens both revisions itself; neither has to be registered.

For unsaved edits, `after` names a working record instead of a revision, and `before` is its base revision ([working records](session.md#6-working-records)).

The session creates the DuckDB schema `manta.<name>` of a diff itself, next to the registered revisions, and puts the views directly in it ([names in DuckDB](session.md#4-names-in-duckdb)). DR's `register` does not create this DuckDB schema, so the session also drops it. All objects are lazy views, and the registration reads no values.

| View | Columns | Source | Cost |
|---|---|---|---|
| `map_rows` | attribute, the index columns (entity, connection, ...), assigned layer before and after, the `varies` and `broadcast` flags of both sides | a full join of the two owner maps on the index, keeping only rows where the assigned layer differs or one side has no row | no value read |
| `static_<dtype>` | entity, bus, attribute, `before`, `after` | the raw constant rows of both revisions for the candidate map rows, joined on identical labels (NULL equals NULL), keeping rows whose value differs or that exist on one side only | reads the constants of the touched attributes |
| `series_<dtype>` | entity, bus, attribute, snapshot, `before`, `after` | the same join over the series rows | reads both series; on demand only. The FE aggregates over it in SQL (changed rows, median ratio), so only the result travels |

### How the diff finds the changes

The owner map of a revision assigns each map row to the layer whose rows are in force. If both revisions assign a map row to the same layer, both read the same rows there. Only map rows that differ between the two maps can lead to different values. These are the candidate map rows, and the `map_rows` view is this comparison.

- For a revision against one of its ancestors, the candidate map rows are those assigned to a layer between the two. Such a layer is in the history of the later revision and not in the history of the ancestor. The default diff is this case, because the fork point is an ancestor of the reference's current revision.
- For two arbitrary revisions, the full join of the two owner maps covers it. An explicit compare of two references is this case.

The views compute a row diff, not a coordinate diff. The join pairs a row of one revision with the row of the other that sets the same labels. A value restated unchanged drops out. These are the semantics of today's `scenario_changes`.

The views return raw rows, as `register` produces them, and never apply the broadcast rule. The FE settles ([settling in the FE](#4-settling-in-the-fe)). Settling matters here because a map row with a NULL label covers every label of that dimension. Rows that cross each other also add overlap rows: a row with a NULL comes back once per map row it serves (F20). So a correct comparison of values is one of settled rows at coordinates, not of map rows one to one.

A row with an empty `before` (or `after`) means "the other revision has no row with these labels". The value in force there may still come from a broader row. Examples are a constant behind a new series, or a row for all entities. The flags in `map_rows` tell the FE when that can be the case. The FE then settles that coordinate itself.

### Working records

With a working record as `after` and its base as `before`, the diff is the list of unsaved changes. One mechanism thus serves the scenario panel, the change markers and the edit UI.

The owner map of a WR is part of its registered view (F21). Its staged rows carry the WR's own layer id. So "assigned to the WR's layer" selects the unsaved changes. That id is not the id of the committed layer, so nothing may store it.

### Changes in the FE

- The scenario panel (C1) asks the BE for the summary of each scenario against its default baseline. It reads no table in the session.
- The FE registers a diff through the BE when it needs changed values. It names the scenario's reference as `after` and leaves out `before` for the default baseline.
- To compare two scenarios as they are today, the FE names both references.
- It reads a diff's `manta.<name>.static_<dtype>` like a revision's `manta.<name>.static_<dtype>`, with `before` and `after` in place of `value`.
- C2 is a filter on one attribute. C3 is the read of the attributes on screen.
- For series, the FE aggregates over `series_<dtype>` in SQL (changed rows, median ratio).
- Where `before` or `after` is empty and the flags in `map_rows` allow a broader row, the FE settles that coordinate ([settling in the FE](#4-settling-in-the-fe)).

A diff row in `session_registrations` names its two revisions, as the BE resolved them. On restore the BE replays views, then working records, then diffs ([session lifetime](backend.md#3-session-lifetime)).

### Cost

The `map_rows` view reads no values. The `static_<dtype>` view reads only the constants of the touched attributes. The `series_<dtype>` view reads both series, and only on demand.

The join and the filter run in the session, so only differing rows travel. For a scenario that scales a large profile, the FE receives an aggregate, not two copies of the series.

A change summary is computed at each request. Its cost is not measured. Today's quack-server computes the same numbers for all scenarios at every open. If the cost is too high, the session keeps a cache keyed by the two revision ids. The fork point needs no session: the BE finds it from the parent chains that DR reads from the manifests ([fork point](backend-mvp.md#7-the-fork-point)).

## 4. Settling in the FE

### What the FE needs

Many FE queries need one value per coordinate, not raw rows. Neither frontend settles today (F22). Every query filters `entity = X`, which a row for all entities never matches. `loadDemandByLocation` counts an entity twice when it has a constant and a series.

FE queries that need settling (F22): `getSeries`, the entity and label pages, `loadEntityFigures`, `loadEntityDispatch`, `loadComponentResults`, `loadCarrierProfile`, `loadDemandByLocation`, `loadCarrierEmissions`, `loadConstraintPrices`. Today they apply partial rules of their own (`coalesce(series, constant, 1)`), or none.

### Where settling happens

The FE owns one TypeScript function that composes a settle statement as SQL text. It is the port of DR's `settle` (`src/datarecord/settle.py`, 191 lines). Settling is always SQL. TypeScript only composes the statement; no JavaScript code settles rows.

The session offers no settle function and no settled view. Its views (`static_<dtype>`, the diff views) are raw. Raw rows are smaller than settled rows, and settling is mechanical.

Input:

- a source relation (SQL text) and its column list;
- per dimension to settle, a relation of labels (SQL text), for example `SELECT entity FROM manta.r1.dimensions.entity` with the page's filter.

Output: one `WITH` chain with three steps.

1. Add a bit mask of the dimensions that the row names.
2. Per dimension, join once against the labels, keyed by the label and by NULL. A NULL takes each label. A label outside the set drops out.
3. Apply one window filter per coordinate. Keep the row whose mask equals the union of all masks there. Raise where no row does: then two rows cross.

Columns outside the label map (`attribute`, an unsettled dimension) stay as written and take part in the partition. `breakpoint` and `value` do not.

The function takes no flags. DR's own test states that overstated flags change no value.

Not ported: `filter=False` and `twins`. Only DR-internal callers use them.

### Changes in the FE

The statement is an ordinary FE query. The FE decides per query where it runs:

| Case | Where the statement runs |
|---|---|
| The query aggregates or filters to a small result (a series of one entity, a total per carrier) | in the session, wrapped in `quack_query_by_name` |
| The raw form is the small one (constants with broadcast rows for a whole component table) | on the local DuckDB-WASM, over a local table of the rows the FE has already fetched raw |

The queries listed above replace their partial rules with this function.

### Cost

A prototype in Python builds only the SQL text. It is not part of the repository. The composer is about 30 lines. The statement for three dimensions has 1346 characters.

The prototype ran against DR's `settle` on 3500 random cases. The cases cover plain dimensions, a struct dimension, a dimension outside the labels, `breakpoint`, and labels outside the set. The rows were the same in 3043 cases. Both sides raised an error in 457 cases. No case differed.

### Tests

DR ships 20 cases as `datarecord/settle_cases.json` (PR 155, R14). Each case has `columns`, `rows`, `labels`, `filter`, and either `expected` or `error: "crossed"`. The FE runs them with `vitest` and `@duckdb/node-api` (F23). DR's own `settle` and the FE's function thus run the same cases.

## 5. Open points

| Question | Proposal |
|---|---|
| Are read times through Quack fast enough for page open ([constant values](#2-constant-values-and-the-owner-map))? | Measure in spike S3. If too slow, read the preload list at page open, and each further column when it scrolls into view. |
| Does the FE need a series row count per map row ([constant values](#2-constant-values-and-the-owner-map))? | Skipped for now; the FE shows a yes or no until it comes back. |
| Who owns a convention set and its preload list ([constant values](#2-constant-values-and-the-owner-map))? | Open; it must match between the playbooks, the session and the FE. See [replacing the manta objects](session.md#5-replacing-the-manta-objects). |
| Does a playbook result promoted to a scenario get a summary ([changes between revisions](#3-changes-between-revisions))? | Parked. |
| Does the scenario panel show a default diff for results ([changes between revisions](#3-changes-between-revisions))? | Open. The default diff of a result against its base scenario is well defined: the fork point is the scenario revision that was solved. It may not be useful. A comparison of two results (`patch/perfect` against `perfect`) is an explicit compare of current revisions. |
| How does the diff show added and removed labels of a dimension ([changes between revisions](#3-changes-between-revisions))? | Later, from the dimension owners, in the session's SQL. DR built no view of them (optional part of R7). They are reachable only as `manta._fold.<hex>.dimension_owners`. No diff relation is requested from DR. |
| How does `settle_cases.json` reach the FE ([settling in the FE](#4-settling-in-the-fe))? | A copy pinned to the DR version, compared in CI. |
| Does the settle statement run on DuckDB-WASM in the browser ([settling in the FE](#4-settling-in-the-fe))? | Not checked yet. Check in the browser. |
| Should the settle function use flags ([settling in the FE](#4-settling-in-the-fe))? | Later, from the owner map, to skip joins. |

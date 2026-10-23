<!--
SPDX-FileCopyrightText: datarecord contributors

SPDX-License-Identifier: CC-BY-4.0
-->

# Changelog

All notable changes to datarecord are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed

- **Properties**, metadata apart from data: a new `properties` section of
  the schema (`PropertySpec`) declares per dim or group the values describing
  one label, stored as columns of `dims/<dim>.parquet` or
  `groups/<group>.parquet`. An `Enum` property of a `partial` dim
  categorizes it; traits key on categories, and `default_by` gives a default
  per category (`Schema.categorizing`, `attributes_for(dim, **categories)`,
  `properties_for`, `default_for`). This replaces the `entity_type` dim, its
  group over `entity` and the `dims/entity_type/<Type>.parquet` member files.
  `entity` is an ordinary dim: it broadcasts, and must be in `partial` to be
  patched per label or categorized; a NULL on a categorized dim reaches only
  the labels whose categories carry the attribute. Every attribute,
  whatever its `dims`, is stored in `inputs/`. On reading, `dims[dim]` holds
  key columns only, `properties[subject]` the stored property values, and
  `attributes` every attribute; `entity_types` is gone and `flags` takes
  categories (`flags(entity_type="Generator")`). `WorkingRecord` edits any
  dim: `add(dim, labels, **properties)`, `remove(dim, labels)` (cascading to
  group tuples), and `set(name, value, **coords)` writing attributes and
  properties alike, a categorizing property keyword selecting labels at call
  time; `set` loses `indexed_by`. The PyPSA tool declares `entity_type`,
  `carrier`, `sign` and `type` as properties of `entity` and `role` of
  `connection`, with `partial={"entity", "scenario", "connection"}`. Every
  manifest and record is rewritten.
- An attribute over a group carries it as one struct column named for the
  group, a field per key coordinate (`connection STRUCT(entity, bus)`), in
  place of the coordinates flat. This is an on-disk
  format change: `inputs/` and `outputs/` files over a group are rewritten.
  The dims a group draws on now broadcast, so a per-bus value with
  `bus = NULL` holds for every bus, and patching one bus at a time needs
  `bus` in `partial`. `WorkingRecord.set` still takes `bus=`; a long frame
  carries the struct, its coordinates flat being rejected. Naming a group
  beside a dim its key is named for (`dims={"connection", "bus"}`) is
  rejected.
- A group is a broadcast coordinate like a dim, its axis the resolved group:
  a NULL struct means every tuple of the group, and a struct with some
  fields NULL is refused by `set`, `add_group` and the writer. The owner
  map's key is `entity` plus the `partial` dims and groups; `partial` may now
  name a group, and a group outside it is owned whole, so a layer patching
  one connection's value restates every connection's. The PyPSA tool
  declares `partial={"scenario", "connection"}`, keeping per-connection
  ownership. `Schema.membership_keys` is gone, and `Schema.group_columns` is
  every group but the entity-type group. Materialised owner maps are
  rebuilt.
- A group file is keyed by one struct column named for the group, as an
  axis file is by its dim: `groups/connection.parquet` is
  `connection STRUCT(entity, bus) | role | deleted`, an `into` label a plain
  column beside it. This is an on-disk format change. `Record.groups[...]`
  hands back that shape; `add_group` takes the struct column and rejects the
  coordinates flat; `remove_group` still takes a tuple per key. The PyPSA
  tool no longer declares `bus` as an attribute: a port's bus is the
  connection tuple. `Schema.group_coordinates` and `Group.coordinates` are
  gone.
- `WorkingRecord.set(..., entity=...)` fills only a coordinate named
  `entity`. An attribute over a group with no such field, a contract
  `(from, to)`, takes every party as a keyword and refuses `entity=`; it
  used to stage one duplicate row per entity of the type. `add` refuses a
  frame carrying a group's columns without its full key, which used to
  stage a half-keyed row. Likewise `set` on a group attribute without one
  of its key coordinates (`set("efficiency", 0.9, entity=["dc"])`, no
  `bus=`) is refused; it used to store a value no read reached.
- A group may not share a dim's name, the entity-type group excepted: a
  group is carried as a column named for it. Rename a functional group for
  the relation, `bus_country` into `country`.
- A `Workspace` holds the DuckDB connection and a `Store` one location;
  `connect`, `layer_dir`, `DATARECORD_BASE_URI`, `Record.at` and the process
  default connection are gone. A store's revisions live beside its layers as
  `revisions/<id>.json`, so a `Revision` serialises as its location and reads
  its ancestry back in a new process. `ws.con` is the calling thread's cursor,
  and a relation from another connection or thread is rejected at the write
  and edit boundary.
- Writing is `store.root(source)`, `rev.child(source)` and
  `ws.write(source, uri)`; `write_record`, `Revision.create` and the
  source-less `Revision.child()` are gone. A `WorkingRecord` no longer
  commits: `rev.child(w.edits)` writes its edits as a child,
  `ws.write(w, uri)` the flattened record, and `NewChild`, `Directory` and
  `commit` are gone. A tree write writes its revision file last, so a failed write leaves
  no revision and never widens the manifest.
- `Tool.to_datarecord(model, con)` and `Tool.results(model, con)` take the
  connection their frames are planned on, so `PyPSA.results(n, w.con)` sets
  straight onto `w` rather than failing on a relation from DuckDB's default
  connection; `on_connection` is gone.
- `Resolver.group_frame` and `Resolver.entity_type` return an empty relation,
  rather than `None`, where every row written is tombstoned: telling the two
  apart ran the whole fold a second time on every read. `None` still means no
  layer wrote a row.
- A schema declaring a dim, group, group coordinate, attribute or result
  whose name holds `"` or `.`, starts with `_`, or is a column datarecord
  writes itself (`value`, `deleted`, `layer_uuid`, ... ignoring case, and
  `entity_type` for an attribute), or that differs from another declared
  name only in case, is refused at load, naming each offender.
  Such a name used to collide silently: a dim named `deleted` read every
  label as a tombstone. A manifest declaring one no longer loads; rename it.
  Based on #26 by @FBumann.
- The PyPSA tool stores per-port results on connections, like per-port
  inputs: `p0`, `p1`, `p2`, ... and a one-port type's `p` are one result `p`
  over the `connection` group, a row per `(entity, bus)` keeping each port's
  sign, and likewise `q`. `Bus.p` and `Bus.q`, the sum of those rows at a
  bus, are no longer written, and `Link.p`/`Process.p` are `p_internal`. A
  three-port Link's `p2` is now a declared result.
- The PyPSA tool stores a Process's `rate0`, `rate1`, `rate2`, ... as one
  input `rate` over the `connection` group, like `efficiency`, and `build`
  puts each row back in its port's column, static or per snapshot. `rate`
  declares no default, its ports defaulting to `-1` and `1`.

- Removing an entity removes the group tuples naming it: `WorkingRecord.remove`
  tombstones every tuple with a field over `entity` naming it, in the same
  layer, and a value over a group goes with its tuple rather than with the
  entity. An `add` of the name revives the entity alone. A layer adding a
  tuple that names a dead label, or removing a label a tuple still names, is
  refused at write. A value over a dim or group outside `partial` naming a removed label
  is dropped at read, a removed `bus` label's per-bus values included. A
  materialised node caches the dead labels in `resolved/dead/`; one
  materialised before reads as having none.

### Added

- A store or standalone directory on `s3://`, through boto3 behind the
  `datarecord[remote]` extra and configured by the AWS environment alone.
  Revision files are written create-only and the manifest by
  compare-and-swap, so two writers widening one schema never silently lose
  a widening.

### Fixed

- Removing an entity drops the values of every group row naming it, not only
  where it is the group's first entity coordinate: a `contract` over
  `(from, to)` loses its values when either party is removed, and
  `flags(ctype)` counts such a row towards the type of each party.
- Writing a layer whose `manifest.json` write keeps losing, as it does with a
  credential that can write the manifest but not read it, gives up after ten
  attempts with an error naming `s3:GetObject`, rather than looping forever.
- `materialise()` writes `owner_map/inputs.parquet` last, each file through
  a temporary name, so a node never reads as materialised from half its
  cache.
- A fold cached before the manifest widened now reads under the wider schema.
- Reading an attribute over a `partial` dim no longer slows with the square
  of that dim's length.
- Folding the owner map no longer compares every row with every label of a
  `partial` dim's axis; the first read of a record with long series is linear
  again.
- A record whose layers are all written scans its owner map once for the
  layers owning each attribute, rather than once per attribute read.
- A pickled `Revision` unpickles through `Workspace.process()` and reads its
  ancestry back, rather than reading empty, and pickles after `.record` is
  read rather than failing on its DuckDB connection.
- A standalone record's `manifest.json` carries an `id` that `ws.write`
  mints, and which keys its folds in the workspace in place of its URI. A
  record deleted and written again at one URI, or one relative path read
  from another working directory, no longer reads the folds of the record
  before it. `ws.at` resolves a local path as `ws.store` does, and refuses a
  manifest without an id: write such a record again.
- `ws.write` to an existing empty directory raises its `FileExistsError` up
  front, saying a standalone record is written to a URI that does not exist
  yet, rather than passing the check and failing inside the write.
- `PyPSA.to_datarecord` melts a time series whose component name holds a
  `"`, or is `snapshot` or `period`, rather than failing to parse or
  duplicating an id column: a name is no longer pasted into the `UNPIVOT`
  as an SQL identifier.
- `PyPSA.build` keeps the time series of a component named `snapshot`, or
  `period` in a multi-period network, rather than dropping it from
  `dynamic`: the `PIVOT` is on each component's position, so no name
  becomes an SQL identifier there either.
- `PyPSA.to_datarecord` accepts components whose names differ only by case,
  such as `Gen` and `gen`, rather than reporting them as one name: neither
  the melt nor the pivot folds case any more.
- `PyPSA.results` and a network's `outputs` key exactly the results the
  PyPSA schema declares, so setting each one with `kind="outputs"` no longer
  raises `KeyError`: `Bus.control` and `SubNetwork.carrier`, which PyPSA
  also registers as inputs, are no longer emitted as results.
- `PyPSA.build` turns a per-connection input back into PyPSA's port columns:
  `efficiency` on a Link's bus2 connection is `efficiency2` again, static or
  per snapshot, rather than every port's value landing in `efficiency` and
  `efficiency2` reading as its default.

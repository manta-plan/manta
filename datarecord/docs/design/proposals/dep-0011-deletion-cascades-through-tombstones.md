<!--
SPDX-FileCopyrightText: datarecord contributors

SPDX-License-Identifier: CC-BY-4.0
-->

# DEP 11: deletion cascades through tombstones, not through filters

| DEP      | 11                                                        |
| -------- | --------------------------------------------------------- |
| Title    | deletion cascades through tombstones, not through filters |
| Author   | Jonas Hörsch                                              |
| Status   | Implemented 2026-10-13                                    |
| Requires | [DEP 10](dep-0010-a-group-is-a-struct-column.md)          |
| Created  | 2026-10-13                                                |
| Version  | Unreleased                                                |

A label is removed by a tombstone, and only by a tombstone: removing one tombstones every [group](../schema.md#groups) tuple naming it, a layer leaving such a tuple alive is refused, and nothing is inferred on read from a dead label a row refers to.

This supersedes the no-cascade rule [the struct proposal](dep-0010-a-group-is-a-struct-column.md#one-behaviour-that-must-not-move) kept — "the tuples stand, dangling" — for group tuples; values still never cascade further than the rules below say.

## What is wrong today

Removing an entity drops the values that name it, but in four places, each covering part of the problem:

| Where                             | What it drops                                                                                        | Keyed on                                                                              |
| --------------------------------- | ---------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| `fold_inputs`                     | parent owner-map rows hit by this layer's tombstones: `entity`, each keyed group, each `partial` dim | owner-key columns, and the entity fields of keyed groups through `entity_coordinates` |
| `_living` (read)                  | value rows naming a removed entity in a coordinate outside the owner key                             | the resolved entity axis, through `entity_coordinates`                                |
| `WorkingRecord._collapsed_inputs` | staged rows hit by this layer's own entity and tuple tombstones                                      | `_tombstoned` and `entity_coordinates`                                                |
| `resolve_groups`                  | only the group's own tombstones                                                                      | –                                                                                     |

So after `remove("Generator", ["g1"])` the value `x(g1, bus0)` is gone, but the tuple `(g1, bus0)` still stands in `record.groups["connection"]`, naming an entity the record no longer has.
And the deletion paths go through `entity_coordinates` and `Schema.entity_fields`, which hard-code one dim: removing a `bus` label reaches nothing that names it inside a struct.

## The rule

1. **Removing a label writes the cascade.** `WorkingRecord.remove(ctype, names)` tombstones the entities _and_ every group tuple with a field naming one of them, read from the resolved groups. The folded group then honours its own tombstones, and `resolve_groups` needs no filter. The API is unchanged; a dim label tombstoned through a layer written directly carries its own cascade, which rule 2 enforces.
2. **`write_layer` refuses a dangling tuple.** A layer that leaves a tuple alive whose field names a label dead after the layer, or adds a tuple naming one, is refused at write time. A layer written by hand carries its own cascade, or fails loudly.
3. **The fold drops keyed values.** A coordinate in the owner key — `entity`, `partial` dims, `partial` groups — is anti-joined against the layer's tombstones in `fold_inputs`, as now. A re-added label starts fresh. The entity anti-join reaches the top-level `entity` only: a group's entity fields are reached through the group's tuple tombstones rule 1 wrote.
4. **The read drops unkeyed values against dead labels.** For a coordinate outside the owner key, ownership is per attribute, so the fold cannot reach the rows. On read, value rows are anti-joined, per such coordinate, against its _dead labels_: those whose winning row in the fold is a tombstone. For a group that is its dead tuples, one struct column. An equi-join against a set that is usually empty, and skipped when it is.

`partial` stays what it is — the granularity of an override. It is not transitive: a group drawing on a `partial` dim need not be `partial` itself.

## Dead labels survive materialisation

A [materialised node](../layers.md#materialised-node-caches) caches the owner map and the folded axes and groups, not value rows, and its folded relations are tombstone-free.
So rule 4 cannot take its dead labels from the layers above the base alone:

- layer 1 sets `x(g1, bus0)`, with `connection` outside `partial`;
- layer 2 removes `g1`, and so `(g1, bus0)`;
- layer 3 is materialised;
- a read at layer 4 takes `x`'s owner from the cached map, layer 1 per attribute, and reads layer 1's file.

Dead labels from above the base alone do not name `(g1, bus0)`, so `x(g1, bus0)` would come back with nothing re-added.
The fold cannot cut them earlier either: along an unkeyed coordinate the owner map holds one row per attribute, not per label, so there is no row for a dead label to remove, only an exception to carry.
So the cache keeps them, as `dead/<coord>.parquet` beside `dims/` and `groups/`, for each dim and group outside `partial` — a keyed coordinate's dead labels are already cut by the fold — and for each dim a group draws on, which rule 2 checks tuples against below the base too, and rule 4 reads the base's dead labels plus those of the layers above it.
The resolved axes and groups stay tombstone-free for every reader that expects them so; `fold_axis` hands the dead labels back as a by-product of the fold it already does.

A semi-join against the live labels, which the cache already holds, would need no new file, but it runs on every read, where the anti-join against a usually empty set is skipped.

## Re-adding a label revives its unkeyed values

Layer 1 sets `x(g1, bus0)`; layer 2 removes `g1` (and so `(g1, bus0)`); layer 3 re-adds both.
Along a keyed coordinate the fold dropped layer 1's row, so `x` starts fresh.
Along an unkeyed one the owner map still names layer 1 for `x`, and `(g1, bus0)` is no longer dead, so `x(g1, bus0)` comes back — for every unkeyed attribute over the tuple at once.

This is accepted: it is what a coordinate outside `partial` means — values owned per attribute, not per label. A schema wanting re-adds to start fresh declares the group `partial`.

## What it costs

- **`write_layer` depends on the ancestry.** "Dead after the layer" needs the parent's resolved axes and groups, so rule 2 is a fold plus one semi-join per group field over the written layer. Today the writer's checks are layer-local but for name uniqueness.
- **Removing a bus removes its connections.** A PyPSA component whose bus is removed is left with no connection row, which `build` reports as a missing `bus`.
- **The resolved cache grows** by a dead-labels file per dim and group outside `partial`.

## What goes

- `_living`, replaced by rule 4's anti-join against dead labels.
- The entity-field anti-joins through `entity_coordinates` in `fold_inputs` and `_collapsed_inputs`; the top-level `entity` anti-join stays, as rule 3's keyed case.
- Every literal `entity` in the cascade: rules 1–4 are stated over dims and groups.

`entity_coordinates` and `Schema.entity_fields` stay for what is not deletion: `Fold.flags(ctype)` scopes owner-map rows to a type by the entities they name, and `set` resolves an attribute's entity names (`_keyword_entities`).

## To check before building

- That nested dims (`within`) follow rule 1 too: `fold_axis` keys a nested dim by its `axis_key`, `(period, timestep)`, so a parent's tombstone does not reach its children today; removing `period=2030` would tombstone `(2030, t)` for every `t`. Not built: `WorkingRecord` removes no dim label, and rule 2 checks no tuple field over a nested dim.

## As built

- Rule 1 is `WorkingRecord.remove`; a dim label other than an entity is removed only by a layer written directly, which carries its own cascade.
- Rule 2 runs in `write_layer` for a layer writing any axis or group, folding the parent's sources and the staged layer. It checks only what the layer does — the tuples it adds, and the tuples still naming a label it removes — so a tuple an ancestor left dangling blocks no later write.
- Rule 4's anti-join is `_living`; `dead/` holds the coordinates `resolve.mortal` names.

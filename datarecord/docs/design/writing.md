<!--
SPDX-FileCopyrightText: datarecord contributors

SPDX-License-Identifier: CC-BY-4.0
-->

# Writing a whole record

```python
store.root(source) -> Revision  # a new root with this layer
rev.child(source) -> Revision  # a new child of rev with this layer
ws.write(source, uri) -> Record  # a standalone directory, read back
```

Three calls make something, one per place it can go, and each is named for what it returns. `child` lives on the parent rather than as a store call taking a parent, which would name the store twice, and not as `rev.write`, which would read as changing `rev` when layers are [write-once](layers.md#a-layers-data-is-write-once). A call per destination rather than one taking a target, because a tree write needs the location and the tree, a directory write only a connection, and the two return different things.

Each writes `source` as a new layer.
An existing layer directory is an error rather than an overwrite or a merge, so a whole-record write can never half-replace what a record holds.

`outputs/` is written only for a source whose [`outputs` mapping](record.md) is non-empty, so a record with no results produces a layer with no `outputs/` rather than an empty directory.

Keys are looked up one at a time and each file written before the next is built, so a lazily-building source does one read per file written rather than one per key up front.
Locally, frames are staged into a sibling directory and renamed on success, so a frame the fold could not resolve leaves no layer rather than half of one.

Every column the schema declares a type for is cast to it on the way out, so a record's files carry the schema's types and a reader can trust them.
Without that a source may hand over an all-NULL column its dataframe library typed as float, and every reader would re-cast defensively instead.

Validation is structural: a long frame carries [its attribute's own coordinates](format.md#the-long-schema), and an entity frame carries every dim it is keyed by.
Which entity types are valid belongs to [the schema's vocabulary](schema.md), which the record layer does not interpret.

An **input attribute the schema does not declare is rejected**, unlike an entity type: its [`dims`](schema.md#attributespec) are what say which columns its file carries, so an undeclared one has no shape to write it in and would leave a file no reader could derive the columns of.
A **result is exempt** — [`Tool.results`](tools.md) derives which attributes count as results from a framework's own registry, so an unknown name is an error for an input and simply unknowable for a result.

A frame carrying a column its attribute is **not** addressed by is rejected too, rather than narrowed on the way out.
The read path projects an attribute's own coordinates, so such a column would be written and never read — and a source emitting one means something different by the attribute than the schema does, which is worth reporting rather than absorbing.
A result is exempt from both checks: its shape is a framework's business, and a name it shares with an input says nothing about which coordinates the result varies over.

The input is a [`LayerData`](record.md#layerdata): "the rows of one thing, enumerated and read" — the same interface a [`LayerSource`](read-path.md#owner-map) answers for its own layer and a `Resolver` answers for a whole fold, so the writer cannot tell which it was handed and does not need to.
A staged layer's own rows and a resolved record are both a `LayerData`, which is what lets a [`WorkingRecord`](working-record.md#edits) hand over either.

A framework object exposing narwhals frames — [`Record`](record.md) rather than `LayerData` — is not itself one: the writer wraps it in a thin adapter that reads its `Frames` mappings as the enumerate-and-read pairs `LayerData` declares, so a tool stays narwhals-facing and the layered write path stays raw-relation throughout.

## A revision exists only by its file

**The revision file is written last, and its existence is what makes the layer real.** A tree write runs in three steps: the layer, then the [manifest](schema.md#one-schema-per-record), then [`revisions/<id>.json`](layers.md#the-tree-beside-the-layers). Without the revision file no `revision()`, `revisions()` or ancestry reaches the layer.

Locally a failed write leaves nothing, the layer being staged and renamed. Remotely there is no rename, so a failed write can leave part of a layer behind — but unreachable rather than half-read, which makes a remote write atomic in what any reader can see. Removing such leftovers is cleanup, a separate concern.

The manifest check comes after the layer, so a layer whose schema turns out incompatible, or whose write fails, leaves the manifest untouched as well as unreachable: the manifest is never widened for a layer that does not exist.

### The manifest's compare-and-swap

Two writers creating a location's first layers, or widening its schema, at once race on `manifest.json`. So the manifest is written through a [conditional write](layers.md#files-local-and-remote): read with its version — `Absent` where there is none — checked for compatibility, and written only if still at that version. A writer that lost re-reads and checks again, so two writers widening at once end with both widenings, where the later one's schema includes the earlier's, or with the later one's incompatibility reported, never one silently lost. The retry is bounded: a writer that loses ten times, backing off with jitter in between, gives up with an error. That is also what a credential that can write `manifest.json` but not read it meets, since a remote read answered 403 counts as missing and every create-only write then fails.

`materialise()` follows the same rule. `owner_map/inputs.parquet` is what [says a node is materialised](layers.md#materialised-node-caches), so it is written last, after the other maps, the resolved dims and groups. Locally each file is written under a temporary name and renamed, because a parquet file appears at its final path before it is complete and a reader meeting it mid-write fails rather than misses. Two writers materialising one node write the same content, so that race is harmless.

## A standalone directory

A standalone directory has no revision file, so there **the manifest is written last**: `ws.at` requires one, so a directory whose write failed reads as no record rather than part of one. `ws.write` writes to a URI that does not exist yet, refusing one that does — locally the path, even an empty directory, remotely any key under it — as a whole-record write refuses an existing layer: unlike a layer's UUID the caller picks this URI, and a write over an existing record would mix the two under the old manifest. The check and the write are two steps, so two writers racing to one new URI can still mix; a standalone directory has one writer.

Each write mints the record a fresh [id](schema.md#one-schema-per-record), carried in its manifest, so a record deleted and written again at one URI is a new layer to every workspace rather than the old one's cached folds. `ws.write` and `ws.at` resolve a local path as `ws.store` does.

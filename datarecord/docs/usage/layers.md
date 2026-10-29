<!--
SPDX-FileCopyrightText: datarecord contributors

SPDX-License-Identifier: CC-BY-4.0
-->

# Layers

A `Revision` is a node in a tree of layers. Each node adds one layer; what it resolves to is that layer over its ancestors', last-writer-wins ([design](../design/layers.md)).

```python
from datarecord import Workspace

store = Workspace().store("/data/my-record")

root = store.root(source)  # a new node, with `source` as its layer
child = root.child(patch)  # branch off it, with `patch` as its layer
record = child.record  # the resolved overlay, as a `Record`
```

There is no empty revision: a revision exists by writing its layer.

Each revision is a file under `revisions/` beside `layers/`, so a location alone
is enough to find the tree, and a `Revision` serialises as its id, its parent and
its store's location ([design](../design/layers.md#the-tree-beside-the-layers)).

A layer's data is **write-once**, so any node may be a parent and no cache ever needs invalidating ([design](../design/layers.md#a-layers-data-is-write-once)). Branching is several children sharing a parent by pointing at it, not by duplication.

## Materialising

`materialise()` writes a node's owner map and resolved dims under `layers/<id>/resolved/`, so descendants' reads stop there instead of walking to the root. Purely additive — a policy, not a lifecycle step, changing no answer, only how many layers a read touches ([design](../design/layers.md#materialised-node-caches)):

```python
child.materialise()
```

## Navigating

```python
revision = store.revision(uuid)  # load one by id
store.revisions()  # every revision, unordered
revision.ancestry()  # the root→node path
store.layer(uuid)  # one layer read alone
```

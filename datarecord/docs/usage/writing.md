<!--
SPDX-FileCopyrightText: datarecord contributors

SPDX-License-Identifier: CC-BY-4.0
-->

# Writing a whole record

```python
root = store.root(source)  # a new root revision with this layer
child = root.child(source)  # a new child of root with this layer
record = ws.write(source, "out/")  # a standalone directory, read back
```

`source` is anything satisfying `Record` — including a framework object presenting itself as one, which is what puts read and write on a single seam. An existing layer directory is an error rather than an overwrite: frames are staged into a sibling path and renamed on success, so a source that fails validation leaves no layer rather than half of one ([design](../design/writing.md)).

A revision's file is written after its layer and the manifest, so a write that fails leaves no revision behind; a standalone directory's manifest is written last for the same reason ([design](../design/writing.md#a-revision-exists-only-by-its-file)).

Every column the schema declares a type for is cast to it on the way out, so a record's files carry the schema's types and a reader can trust them. Validation is structural — a long frame carries [the format's columns](../design/format.md#the-long-schema), and an entity frame carries every dim it is keyed by.

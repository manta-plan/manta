<!--
SPDX-FileCopyrightText: datarecord contributors

SPDX-License-Identifier: CC-BY-4.0
-->

# API Reference

Generated from the docstrings. The docstrings cite the [Design](../design/index.md)
pages by link rather than restating the argument, so a symbol's "why" is one hop
away; [Usage](../usage/index.md) is the worked prose.

Everything below is importable from the top-level package:

```python
from datarecord import (
    AttributeSpec,
    Dimension,
    Flags,
    Frames,
    LazyFrames,
    Record,
    RecordLike,
    Revision,
    Schema,
    Store,
    WorkingRecord,
    Workspace,
)
```

| page                        | symbols                                                 |
| --------------------------- | ------------------------------------------------------- |
| [Record](record.md)         | `Record`, `RecordLike`, `Frames`, `LazyFrames`, `Flags` |
| [Schema](schema.md)         | `Schema`, `Dimension`, `AttributeSpec`                  |
| [Layered](layered.md)       | `Workspace`, `Store`, `Revision`                        |
| [WorkingRecord](mutable.md) | `WorkingRecord`                                         |
| [Tools](tools.md)           | `Tool`, `Requirements`, the PyPSA tool                  |

<!--
SPDX-FileCopyrightText: datarecord contributors

SPDX-License-Identifier: CC-BY-4.0
-->

# Tools

A **tool** is one modelling framework's view of a record. Tools live under `datarecord/tools/`, are reached by importing them (no registry), and nothing in the core imports one — so importing the record layer pulls in no framework ([design](../design/tools.md), [module layout](../design/module-layout.md)).

```python
from datarecord.tools.pypsa import PyPSA

missing = PyPSA.verify(record)
if missing:
    raise RuntimeError(missing.describe())

n = PyPSA.build(record)  # a pypsa.Network
n.optimize()

record_back = PyPSA.to_datarecord(n, ws.con)  # the inverse; a `Record`
results = PyPSA.results(n, ws.con)  # Frames, in the long schema
```

`to_datarecord` and `results` plan their frames on the connection they are handed — the workspace's that writes them, or the record's they are `set` on — so they reach the write path without a copy; `build` reads `record.con` itself.

`verify` catches what the record layer cannot — an entity type the framework has no registry entry for, a connection `role` it cannot place, a `partial` set that breaks its constant-versus-varying split — and returns a falsy `Requirements` when the record is usable. `build` raises `UnsupportedRecordError` rather than producing a partial model.

## Solving and writing results back

`results` returns the same `Frames` type `Record.outputs` presents, so a solve's output goes straight back:

```python
w = WorkingRecord(rev.record)
w.set("p_max_pu", 0.8, entity=["wind1"])
n = PyPSA.build(w)  # a WorkingRecord is a Record
n.optimize()
for attr, frame in PyPSA.results(n, w.con).items():
    w.set(attr, frame, kind="outputs")
rev.child(w.edits)  # one layer, inputs and results together
```

Two checks are skipped for `kind="outputs"`: the attribute need not be schema-declared, and a result's labels need not resolve — a solve may produce rows for labels it derived rather than read ([design](../design/working-record.md#results-through-kindoutputs)).

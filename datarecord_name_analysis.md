The naming critique is back. I re-ran the one data bug it found and it reproduces, so it’s confirmed. Nothing in the repo was modified.¹
The worst naming problems:
Inputs and results each go by three names. Model inputs are Schema.attributes in the schema, Record.attributes in Python, and inputs/ on disk. Solve results are Schema.results, Record.outputs and outputs/. On top of that, “attribute” is also used for both. In Manta it gets worse: a block’s output record would have its own outputs/ folder.
Store collides with PyPSA’s Store component. Modellers have n.stores open while writing store = ws.store(...).
bus means two different things, and that causes a real bug. A Bus is stored as a row in the entity table, but connections point at a separate bus dimension that has no file of its own. Removing Bus north therefore leaves the generator’s connection to north in place, even though tools.md promises the removal cascades to connections.
entity_type isn’t PyPSA’s word, and it sits right next to a type column. PyPSA’s own n.statistics calls this level component.
dims is overloaded. Two schema fields mean the same thing, some “dims” lists include groups, and Record.dims[d] isn’t the same as the file dims/d.parquet.
Calls that write data read like getters. store.root(src) and rev.child(src) write; ws.at(uri) reads.
The tool layer reuses core names. tools.base.Schema shadows datarecord.Schema, and the PyPSA module already has to import the core one under an alias.
What it proposes:
Data sections: “attribute” becomes the generic term, and inputs / results are the two sections, named the same in the schema, in Python and on disk. That means renaming outputs/ to results/ and Record.outputs to Record.results, and a separate set_result().
Store → Repository.
Verb-style calls: ws.at → ws.open; root / child → write_root / write_child.
entity_type → component.
Fix the bug: drop the separate bus dimension, so connections point at entity rows and removals cascade. The agent didn’t test this fix.
manifest.json → schema.json.
AttributeSpec.dims → coords.
Smaller items: the tool-layer renames (from_model / to_model), making the path helpers private, and the doc drift. For example, the docs’ first example calls record.entity_types, which doesn’t exist.
What it says to keep: Record, RecordLike, WorkingRecord, Revision, Workspace, and the long-form columns attribute | breakpoint | value. Also dims/, groups/, inputs/, deleted, and the struct column named after its group.
Order it recommends:
Make every on-disk format change before Manta persists a single record. Breaking changes are free right now and won’t be later.
Then the cheap Python-only renames.
Leave the cache-layout renames for whenever.
It recommends skipping partial, owner_map and materialise (jargon only schema authors see), and the roughly 350-hit “axis vs dim” sweep through the docs.
Manta side: don’t reuse the name DataRecord. A serialised Revision ({id, parent, store}) is already the handle a block needs.
My take: (3) is a correctness fix, so it’s worth doing no matter what happens with the renames. And (1) is the rename with the biggest payoff; I’d do it before anything gets written to disk. The rest is decent but negotiable.
¹ I ran its bus.py at a fresh path (its own run had left the output directory behind). After w.remove("entity", ["north"]), the connections are still [{'connection': {'entity': 'g', 'bus': 'north'}, 'role': 'attached'}], and "bus" in w.dims is False. The agent’s scripts are in /tmp/drnaming/scripts/.

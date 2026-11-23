<!--
SPDX-FileCopyrightText: Manta contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Design note: storage access and commit

How an edit becomes a revision: the commit flow, the claim, the two scoped S3 tokens with their policies, and the changeset format. Read with the S3 access control plan for runs (F25).

Part of the datarecord-session plan, draft 9. Start with the [overview](index.md). The codes F, S, R, D and I point to the [appendix](appendix.md).

This note covers the write path of the session. The [commit flow](#1-commit-flow) describes the commit exchange between FE, BE, the session and S3. [The two tokens](#2-the-two-tokens) describes the two S3 tokens and the requirements on the object store. The [changeset format](#3-changeset-format) describes the changeset that the FE sends.

In short: the session has no write access of its own. For each commit the BE claims a new revision with DR and mints a short-lived STS token that can write into that one layer. The BE then sends the claim, the token and the changeset to the session. The session applies the changeset to a WR on the parent and commits with the token. It returns the manifest, and the BE compares the manifest with its claim. The BE then moves the reference by a conditional write of `store.json`. The session reads with a second token for the project's folder. Both tokens are grants of the same form as the storage grants of runs (F25).

## 1. Commit flow

### The flow

```
FE --changeset--> BE                                    S                        S3
                  1. check ownership,
                     read store.json + ETag, reference  <------------------------ store.json
                     at the expected revision, else 409
                  2. Store.claim(parent, meta)  ------------------------------> layers/<id>/claim.json
                  3. mint write token for layers/<id>/
                  4. POST /commits {claim, token, changeset} -->
                                                        5. WR(parent), apply ops
                                                           (restatement, F13)
                                                        6. Claim.commit(wr, credentials=token)
                                                           ---> layers/<id>/dimensions, attributes, manifest.json
                  <-- {manifest} -------------------------
                  7. compare id, parent, meta of the manifest with the claim
                  8. read store.json + ETag  <---------------------------------- store.json
                     check reference and kind, else 409
                     PUT store.json, If-Match: ETag  ----------------------------> store.json
                     on 412 read again (five tries, then 503)
FE <--revision---
```

1. The BE checks that the user owns the project. The FE's request names the reference to move and the revision that the FE expects there. The BE reads `store.json` with its ETag. If the reference does not point to the expected revision, the BE answers 409 before it claims.
2. The BE calls `Store.claim(parent, meta)` with `parent = Revision(id=expected, store=store)`. Building that `Revision` reads nothing from S3, and the claim reads no manifest. The check of step 1 already proves the parent is committed, because a reference only points to committed revisions. The claim's `meta` carries `manta.kind` and `manta.created_by`. DR draws the id of the new revision and writes `layers/<id>/claim.json`. The BE keeps no row for the claim; `claim.json` is its record.
3. The BE mints a write token for `layers/<id>/` (see [the two tokens](#2-the-two-tokens)).
4. The BE sends `POST /commits` to the session. The request carries the claim, the write token and the changeset (see [changeset format](#3-changeset-format)).
5. The session opens a WR on the parent and applies the operations in order. The WR does the restatement (F13).
6. The session passes the write token to `Claim.commit(source, credentials=...)`. DR writes the Parquet files and `manifest.json` under `layers/<id>/`.
7. The session returns the manifest in its answer. The BE compares id, parent and `meta` with its claim. The BE does not read `manifest.json` from S3 again.
8. The BE moves the named reference at commit confirmation, by a conditional write of `store.json`. It reads `store.json` again with its ETag. It checks that the reference still points to the expected revision, and that the new revision has the same `manta.kind` as that one. It writes the file with `PUT` and `If-Match: <ETag>`. On 412 another writer changed the file, so the BE reads again and repeats the check. After five tries it answers 503. Detail in [references in `store.json`](backend-mvp.md#6-references-in-storejson).

Later, with the revision index, the BE also inserts a revision row with the status `claimed` at step 2 and sets it to `committed` at step 7. It then moves the reference by a compare-and-set in SQL and writes `store.json` after it ([revision index](backend.md#1-revision-index)).

### The claim across processes

The BE sends the claim in DR's JSON form with its five fields (`claim.model_dump_json()`). The session rebuilds it with `Store.claim_from`, without a read of `claim.json` (F11). The store URI in the payload must equal the session's URI of that store. Both sides therefore build the URI by the same rule (see [session service](session.md#3-session-service)).

DR does not compare the claim object with `claim.json` (F26). Nothing depends on such a check: the BE made the claim, and it compares the returned manifest with it.

### What each party does

The BE starts every commit exchange. The session never calls the BE. This holds in every case:

| Case | How the BE starts it |
|---|---|
| One-shot commit | The FE sends the changeset to the BE. The BE claims, mints the token and calls the session. |
| Commit of a live WR (see [working records](session.md#6-working-records)) | The FE asks the BE. The BE claims, mints the token and sends both with the name of the working record. |

The BE never holds a `Record` and never folds. It works on claims and revisions only. It writes `claim.json` and `store.json` and receives the manifest, all small JSON objects. `Store.cleanup` runs in the BE only, under the backend key, never in the session.

The session does the fold, the restatement and the commit. It holds no write right of its own. It writes only with the token that the BE sends for one claimed layer.

DR creates the layer-scoped DuckDB secret and drops it. The session only passes the token on.

The playbook blocks of a run can use the same exchange later, when their permissions are trimmed. The BE (or the run flow) then claims and hands the block a token for one layer (see [runs and blocks](backend.md#2-runs-and-blocks)).

### Failure and cleanup

A claim without a commit stays as a `claim.json`. A BE task runs `Store.cleanup(older_than=...)` on each store of every project and removes it. Later, with the revision index, the task also removes the `claimed` rows in Postgres.

A commit that exceeds the 900 s of its token fails at its next write. The claim then stays pending until the cleanup.

If the reference moved since the FE read it, the check of step 8 fails and the BE answers 409. The body names the new revision. It exists, but no name points to it. A 412 alone is no conflict: a change of another reference of the same store also changes the ETag ([two concurrent commits](backend-mvp.md#two-concurrent-commits-on-one-reference)).

## 2. The two tokens

Both tokens are short-lived STS tokens (spike S6). The BE calls `sts:AssumeRole` with the master credential and an inline session policy. STS tokens need no cleanup.

| Token | When the BE mints it | Scope | How the session uses it |
|---|---|---|---|
| Read token | once per session start | the project prefix | An `S3Credentials` object set on the workspace. `Workspace.set_credentials` replaces it on the live workspace (F12, `PUT /credentials` in the [session service](session.md#3-session-service)). |
| Commit token | once per commit | one layer prefix | Passed to `Claim.commit(source, credentials=...)`. |

During a commit two DuckDB secrets exist:

1. the workspace's read secret;
2. a secret with `SCOPE 's3://<bucket>/<project>/<store>/layers/<id>/'`. DR creates it inside `Claim.commit` and drops it after the commit (F12).

DuckDB 2.0.0 picks the secret with the longest matching scope. This is tested (S6). So the commit token needs no read right outside its layer (R2). Reads of the ancestors use the session's read token.

### Policies

Read policy (project prefix `P`, bucket `B`):

```json
{"Version":"2012-10-17","Statement":[
 {"Effect":"Allow","Action":["s3:GetObject"],"Resource":"arn:aws:s3:::B/P/*"},
 {"Effect":"Allow","Action":["s3:ListBucket"],"Resource":"arn:aws:s3:::B",
  "Condition":{"StringLike":{"s3:prefix":["P/*"]}}}]}
```

Write policy (`L = P/<store>/layers/<id>`):

```json
{"Version":"2012-10-17","Statement":[
 {"Effect":"Allow","Action":["s3:PutObject","s3:GetObject","s3:AbortMultipartUpload"],
  "Resource":"arn:aws:s3:::B/L/*"},
 {"Effect":"Allow","Action":["s3:ListBucket"],"Resource":"arn:aws:s3:::B",
  "Condition":{"StringLike":{"s3:prefix":["L/*","L/"]}}}]}
```

The commit token needs PUT and GET under `layers/<id>/`, and a LIST on that prefix. The LIST is needed because DR's `exists` falls back to a LIST. Without the LIST right the commit raises before it writes (F24).

### Lifetimes

| Token | Lifetime |
|---|---|
| Read token | the session's hard limit (see [session lifetime](backend.md#3-session-lifetime)) |
| Commit token | 900 s |

A token cannot be handed back. It is a signed bearer credential. SeaweedFS 4.53 has no call that revokes one token (read in `weed/s3api/s3api_sts.go`). Until the commit token expires, a session can overwrite data files of the layer it committed. The commit token therefore gets the shortest lifetime, 900 s. This is the fixed minimum in that file. A commit that takes longer fails at its next write.

A role has its own `MaxSessionDuration` (same file). So a session role can cap lifetimes apart from the 7 days of the runs.

### Alignment with the storage grants of runs (F25)

A grant of the runs is a read list and a write list of folders, turned into one token. The session's tokens are grants of the same form, minted by the BE:

| Grant | Read | Write | Lifetime |
|---|---|---|---|
| Session read | `<project>/` | none | the session's hard limit |
| Commit | none | `<project>/<store>/layers/<id>/` (put, get, list) | 900 s |

The BE calls the session directly, so a grant needs no signature here.

Open, to agree with Kristijan: how the BE mints. It needs the minter key, or a minter of its own. A read-only role for session tokens (`GetObject`, `ListBucket`) is stricter than reuse of `manta-block-run`. The proposal is such a read-only role.

### Residual risks

- A compromised session could return one manifest and write another. The damage stays inside the user's own project. The BE lists the manifests that S3 holds, so no copy goes stale. Later, with the revision index, `sync_store` repairs the Postgres tables.
- Until the commit token expires, the session can overwrite data files of the layer it committed. The 900 s lifetime limits this.
- Until the storage grants reach the session, it holds the global S3 credential. Code alone confines it to the project prefix (I1).

### Object store requirements

SeaweedFS is the only target for now (F25, D11). AWS S3 and MinIO support the same flow. GCS does not.

SeaweedFS in dev moves from 4.05 to 4.53 with the `s3-security` branch (F25). DR was tested there through the environment chain. The MVP needs that move first: 4.05 is older than 4.18, DR's minimum for create-only writes.

The BE moves a reference with `If-Match` on PutObject ([what the object store must support](backend-mvp.md#what-the-object-store-must-support)). A store without it loses updates silently.

Not yet tested:

- A conditional `If-Match` write of `store.json` under a race on SeaweedFS 4.53: two PUTs with the same ETag at once must give one 200 and one 412.

- An STS token with a session token, passed as `S3Credentials`, for the workspace and for a commit (left-over of S6). DR tested both paths on SeaweedFS 4.52 with static keys only (F12).
- The duration of a large commit against the 900 s token (left-over of S3).

### Alternatives not taken

| Alternative | Why not |
|---|---|
| Presigned URLs for the Parquet writes | DuckDB cannot write to an https URL. |
| Real revocation: an identity or a role per commit, which the BE deletes when the session answers | The spec for runs names this, untested. It needs SeaweedFS's IAM write API, which stays disabled there. |
| The layer id prefix of the runs' step 6: a write right on `layers/<prefix>*` for the whole session | It needs no credential change in DR at all. But the session could then commit layers that the BE did not claim. |
| The BE reads `manifest.json` from S3 at confirmation | The session returns the manifest in its answer, so the read is not needed. The residual risk above follows. |

## 3. Changeset format

A changeset is an ordered list of operations: `set`, `add` and `remove`. The session applies them in order to a WR on the parent. Each operation becomes exactly one call of DR's `WorkingRecord`. A table payload travels as a Parquet part beside the list.

The format follows from three reasons:

- The session does the restatement, because it applies the operations to a WR (F13). The FE and the BE never build a complete layer.
- The same operations are the edit API of the future registered WR (see [working records](session.md#6-working-records)). A one-shot commit is "open WR, apply, commit, close".
- The FE's *direct* changes map to `set` with a scalar.

The changeset is a pre-stage of LayerData, not LayerData itself. It is the session's own format. Nothing is requested from DR (R5).

All statements about DR below refer to the pin `468f69b0` (D19). "Probe" marks a behaviour that a script showed against that commit, where the docs say nothing.

### The request

`POST /v1/projects/{id}/datarecord-stores/{store}/datarecord-revisions` takes a `multipart/form-data` body. The parts come in this order:

| # | Part name | Content type | Content | Read by |
|---|---|---|---|---|
| 1 | `commit` | `application/json` | the envelope of the commit | BE only |
| 2 | `changeset` | `application/json` | the format version and the operation list | BE (shape), session (content) |
| 3 and later | a name of the FE's choice, such as `t0` | `application/vnd.apache.parquet` | one table payload | session |

The envelope holds the fields that the BE needs for the [commit flow](#1-commit-flow):

```json
{"reference": "patch", "expected": "07b0661e-5c1a-4f7e-9a51-2f0e4c6d8b13", "register_as": "r2"}
```

| Field | Type | Required | Meaning |
|---|---|---|---|
| `reference` | string | yes | The reference to move, a key of `store.json`. |
| `expected` | UUID string | yes | The revision that the FE expects at `reference`. It is also the parent of the new revision. |
| `register_as` | string | no | A registration name. The BE registers the new revision under it at once ([routes](backend.md#5-routes-and-quack-auth-check)). |

The envelope has no parent field, because the parent is the expected revision. It has no base field either. A reference gets its base when `POST .../datarecord-references` creates it. A new scenario is therefore two calls: create the reference on its base, then commit to it.

The changeset proper is the second part:

```json
{"format": 1, "operations": [{"op": "set", "name": "p_nom_max", "at": {"entity": "DE0 1 onwind"}, "value": 25000}]}
```

`format` is the version of this format. It is `1`. The session refuses a version that it does not know. `operations` is the ordered operation list, with at least one operation.

A table part has a name that matches `^[a-z][a-z0-9_]{0,31}$`, other than `commit` and `changeset`. Its file name is the part name with `.parquet`. An operation refers to it by the part name. Each table part is referenced by exactly one operation.

The FE builds the body with `FormData`, which keeps the order of `append`:

```ts
const body = new FormData()
body.append('commit', new Blob([JSON.stringify(envelope)], { type: 'application/json' }))
body.append('changeset', new Blob([JSON.stringify(changeset)], { type: 'application/json' }))
body.append('t0', new Blob([parquetBytes], { type: 'application/vnd.apache.parquet' }), 't0.parquet')
```

The BE calls the session's `POST /commits` with the same multipart form. It replaces the `commit` part with its own envelope: the claim in DR's JSON form and the write token ([the two tokens](#2-the-two-tokens)). It passes the `changeset` part and the table parts on byte for byte. On success the BE answers 201 with the new revision and the reference, as in [references in `store.json`](backend-mvp.md#6-references-in-storejson).

Issue #267 asks for one call that carries the pending patches of the FE as a change set. The FE builds it, and the BE commits it as a new revision. The format answers this. The FE keeps its pending mutations in local storage, translates them to operations at save time, and sends one request. The issue asks for serialised layer data. The format sends operations instead, because only a WR completes a layer (F13). The request names the reference that moves in `store.json`, and `register_as` gives the FE the new revision without a second call.

### Operations

The schema of the `changeset` part, as TypeScript:

```ts
type Label = string | number | boolean          // a datetime label is an ISO 8601 string
type Labels = Label | Label[]                   // one label, or several
type Scalar = number | string | boolean | null  // null only for a property

interface Changeset {
  format: 1
  operations: Operation[]
}

type Operation = SetOperation | AddOperation | RemoveOperation

interface SetOperation {
  op: 'set'
  name: string                      // an attribute, or a property as "subject.name"
  at?: Record<string, Labels>       // dimension or field -> label(s); a missing key is every label
  where?: Record<string, Labels>    // property -> value(s); selects labels when the operation runs
  value?: Scalar                    // exactly one of value, values, table
  values?: Scalar[]                 // aligned to the one list in `at`
  table?: string                    // the name of a Parquet part
}

interface AddOperation {
  op: 'add'
  dim: string                                    // a dimension without one_of
  labels: Label[] | Record<string, Label>[]      // labels, or tuples of a multi-dimension
  properties?: Record<string, Scalar | Scalar[]> // one value for all labels, or one per label
}

interface RemoveOperation {
  op: 'remove'
  dim: string
  labels: Label[] | Record<string, Label>[]
}
```

Each operation becomes one call. `wr` is the WR on the parent:

| Operation | WR call | DR source |
|---|---|---|
| `set` with `value` | `wr.set(name, value, **at, **where)` | `mutable.py:870-875`, scalar path `1006-1015` |
| `set` with `values` | `wr.set(name, values, **at)` | sequence path `995-1005` |
| `set` with `table` | `wr.set(name, con.read_parquet(path), **at)` | frame path `955-984` |
| `add` | `wr.add(dim, labels, **properties)` | `mutable.py:1690-1764` |
| `remove` | `wr.remove(dim, labels)` | `mutable.py:1767-1830` |

The session writes a table part to a local temporary file and reads it as a DuckDB relation on the workspace's connection `con`. DR stages its rows in its own tables during the call, so the file can go after the call.

A `set` names an attribute by its plain name, or a property as `subject.name`, such as `entity.carrier`. This is DR's rule: a plain name is always an attribute (`docs/reference/data-model.md`, "Properties"). A property takes `value` or `values`, never `table`. A property of a multi-dimension, such as `connection.role`, takes `value` only (`mutable.py:1116-1121`). A field such as `connection.bus` cannot be set, because a field is part of the label (`mutable.py:1040-1046`).

Each DR call is one transaction. A refused call leaves the staged rows as they were (`docs/reference/editing.md`, "Transactions and staging").

The order of the operations matters, and DR defines the result of each order:

- A later `set` replaces each staged row of the attribute that one of its own rows covers. In the other order the more specific row stays and wins (`docs/reference/editing.md`, "A later `set`").
- Where two staged rows cross, the later `set` sets the value at the coordinates that both cover. The order never makes an edit fail (same heading).
- `where` selects labels on the WR as staged at that operation. A label that a later `add` creates is not reached (`docs/reference/editing.md`, "Property keywords").
- A `set` on a label that an earlier `remove` took raises `KeyError`. An `add` after a `remove` brings the label back with its values (`docs/reference/editing.md`, "`add` and `remove`").

### Coordinates

`at` gives the coordinates of a `set`. Each key is a flat dimension or a field of a multi-dimension of the attribute. DR takes the same names as keywords (`docs/reference/editing.md`, "Keywords").

| Case | `at` | Meaning |
|---|---|---|
| One label | `{"entity": "DE0 1 onwind"}` | The value at that label. |
| Several labels | `{"entity": ["DE0 1 solar", "DE0 2 solar"]}` | The same value at each label. |
| Several lists | `{"entity": ["a", "b"], "snapshot": ["2013-01-01T00:00:00", "2013-01-01T01:00:00"]}` | The value at every combination (probe). |
| Every label | the key is missing | One row with NULL in that dimension: every label, also labels that are added later. |
| One tuple of a multi-dimension | `{"entity": "DE0 1 H2 Electrolysis", "bus": "DE0 1 H2"}` | Every field of the multi-dimension is given. |
| Every tuple | no key of any field | One row with a NULL struct: every tuple. |

The rules:

- A multi-dimension is written by its fields, never by its own name. DR raises `KeyError` for `connection` as a keyword (`mutable.py:825-833`). A key `connection` or `snapshot` (multi-period) is therefore wrong.
- A multi-dimension takes every field or none. With one field missing, DR raises `ValueError` (probe). A field may hold a list, and then every combination must be a tuple of the axis, else `KeyError` (`mutable.py:1449`).
- A JSON `null` is not allowed in `at` and in `where`. A missing key is the only form of "every label". DR treats `entity=None` like a missing keyword (probe). For a field of a multi-dimension, DR refuses `None` beside a label with `KeyError` (probe). One form avoids both cases.
- An empty list is not allowed. DR would stage nothing and raise nothing (probe).
- A label has the JSON type of its dimension's dtype: string for `str`, integer for `int`. A `datetime` label is an ISO 8601 string without an offset, such as `"2013-01-01T00:00:00"`. The session converts it to `datetime.datetime`. DR refuses a string for a `datetime` dimension and does not parse it (`mutable.py:1331-1357`; probe).

A row with a missing key replaces the parent's rows that it covers. A child's `set("p_nom", 0.95)` over a parent with one `p_nom` row per entity reads 0.95 for every entity (probe, also after the commit). So "all labels" overwrites existing values.

A snapshot in a PyPSA store has one of two shapes (`docs/reference/tools.md`, "The schema"):

| Network | `snapshot` is | One snapshot in `at` |
|---|---|---|
| one period | a flat `datetime` dimension | `{"snapshot": "2013-01-01T00:00:00"}` |
| several periods | a multi-dimension over `period` (`int`) and `timestep` (`datetime`) | `{"period": 2030, "timestep": "2030-01-01T00:00:00"}` |

In a multi-period store, "all snapshots of one period" is not one row. The `set` lists the timesteps, or uses a table payload.

`snapshot` is outside `partial` in a PyPSA store (`tools/pypsa.py:2537`). A `set` on some snapshots of an entity therefore restates the entity's whole series. The WR carries the other snapshots at their current values (`mutable.py:1591-1663`; probe). This is the restatement of F13.

Most PyPSA attributes are also over `scenario` (`docs/reference/tools.md`, "The schema"). The FE leaves `scenario` out, so the value holds in every scenario.

`where` selects labels by a property, such as `{"ctype": "Generator", "carrier": "solar"}`. Several keys intersect. A list of values selects each value. DR evaluates the selection on the WR as staged at that operation and stores no filter (`docs/reference/editing.md`, "Property keywords"; `mutable.py:1189-1295`). The keys of `where` must not be dimensions or fields of the attribute. DR refuses a property that two reached dimensions declare, and a property beside the key of its own dimension in `at`. On an attribute over a multi-dimension, DR refused `ctype="Link"` without the `bus` field in a probe. The exact rule is not verified.

### Values

The session checks a scalar against the declared type before the call. DR's scalar path does not check it: it binds the value with the type that DuckDB infers and casts on insert (`mutable.py:1009-1015`). The probe showed `1.5` stored as `2` in an `int` attribute, `1.5` stored as `'1.5'` in a `str` attribute, and `1` accepted in a `bool` attribute.

| Value type | JSON form | Notes |
|---|---|---|
| `float` | a number, or `"inf"` or `"-inf"` | JSON has no non-finite number. The session refuses `NaN`. It passes a Python `float`. |
| `int` | an integer from -(2^53 - 1) to 2^53 - 1 | The session refuses a fraction. A larger integer needs a table payload with an `INT64` column. |
| `bool` | `true` or `false` | The session refuses `0` and `1`. |
| `str` | a string | |
| `datetime` | an ISO 8601 string without an offset | As for labels. |

`JSON.stringify` writes the shortest form that reads back to the same double, and Python's `json` reads it back exactly. So a float survives the round trip.

`value: null` is allowed for a property only. It clears the property, which DR needs before it removes a label that the property names (`docs/reference/editing.md`, "`add` and `remove`"). For an attribute the session refuses `null`. DR stages a row with a NULL value (probe), but its docs do not say what such a row means on read. The format has no "unset" of an attribute.

`values` is a list of scalars. `at` then holds exactly one list, of the same length, and `where` is empty. DR aligns the values by position and refuses any other shape (`mutable.py:995-1005`, `normalise_value` at `131-175`).

A table payload is one Parquet file. Its columns are:

| Column | When | Type |
|---|---|---|
| one per flat dimension of the attribute | for each dimension that varies inside the table | the dimension's type |
| one struct per multi-dimension, named for it | for each multi-dimension that varies inside the table | `STRUCT` with exactly its fields, each of its dimension's type |
| `value` | always | the attribute's type |

DR reads the columns by name, so their order does not matter (`mutable.py:1434-1447`). DR refuses any other column, `attribute` and `breakpoint` included (`mutable.py:970-981`). It refuses a multi-dimension as flat field columns (`schema/schema.py:611-657`; probe). A NULL in a dimension column means every label of that dimension (probe). A struct with some fields NULL is refused (`schema/schema.py:659-697`).

A column type fits where DR's `takes` accepts it (`schema/dtypes.py:48-77`):

| DR dtype | Parquet type | Also accepted |
|---|---|---|
| `float` | `DOUBLE` | `FLOAT`, the integer types, `DECIMAL` |
| `int` | `INT64` | `INT8` to `INT32`, `UINT8` to `UINT32` |
| `bool` | `BOOLEAN` | |
| `str` | `STRING` (UTF-8) | |
| `datetime` | `TIMESTAMP` in microseconds, without time zone | seconds, milliseconds, nanoseconds (truncated to microseconds) |

A column of NULLs passes whatever its type (`schema/schema.py:1105-1160`).

A dimension that does not vary inside the table is a single label in `at`, or is left out for "every label". `at` holds single labels only beside a table, and `where` is empty. DR refuses lists and property selections beside a frame (`mutable.py:955-962`). Where a column and an `at` key name the same dimension, DR keeps the column and ignores the key without an error (probe). The session therefore refuses that case. Two rows of one table at the same coordinate are staged both, without an error (probe). The session refuses them too. Two rows of one table that cross raise `ValueError` (`mutable.py:1523-1553`).

DR has no breakpoints in a `set`: it writes `breakpoint` as NULL (`mutable.py:1445`). A curve cannot travel in a changeset.

The FE uses `value` for one value at one or many labels. It uses `values` for a different value per label of one dimension, such as a rule that the FE expands. It uses a table for a series, or for more than about 1000 values. The FE writes a table with DuckDB-WASM, for example `COPY (SELECT snapshot, value FROM edited) TO 't0.parquet' (FORMAT parquet)`.

### Labels: `add` and `remove`

`add` stages new labels of one dimension, each as one whole row of its axis (`docs/reference/editing.md`, "`add` and `remove`"):

- `labels` of a flat dimension is a list of labels. DR refuses a frame for a flat dimension with `TypeError` (`mutable.py:98-112`; probe). So `add` takes no table payload. Labels travel in JSON only.
- `labels` of a multi-dimension is a list of objects. Each object maps every field to a label. DR refuses a missing field and a NULL field (`mutable.py:1913-1923, 1950-1956`).
- `properties` holds the properties of the dimension by plain name. Each is one value for all labels, or a list aligned to `labels` (`mutable.py:1751-1757`).
- A property that `properties` does not name is NULL on the row, because `add` restates the row whole. An `add` of an existing label therefore clears its other properties (probe). The FE changes one property of an existing label with `set` on `subject.name`.
- A property that refers to a dimension takes a label of that dimension's axis, else `KeyError` (`mutable.py:1163-1187`). A new `carrier` label comes first, then the entity that names it.
- A field of a new tuple must be a label of its axis, else `KeyError`. The entity comes first, then its `connection` tuples.
- A new label goes after the last label of the axis. A label that this changeset removed returns to its base place (`mutable.py:1696-1703`).
- `add` sets no attribute value. A new label takes the values of rows that leave its dimension NULL, from any layer, and else the default (`docs/reference/data-model.md`, "The broadcast rule"). The FE sets each value that the label needs with `set` after the `add`.
- DR refuses `add` and `remove` on a dimension with `one_of`, such as `ctype` and `role` (`mutable.py:1832-1852`).

In a PyPSA store a component attaches to a bus through a `connection` tuple, with the property `role`: `input`, `output` or `attached` (`docs/reference/tools.md`, "Ports"). The entity's properties are `ctype`, `carrier`, `sign` and `type`.

`remove` stages the axis without the labels (`docs/reference/editing.md`, "`add` and `remove`"):

- Every value at a removed label goes.
- Every tuple of any multi-dimension that holds the label goes, with its values. `remove("bus", ["north"])` removes every connection at `north`.
- A row that leaves the dimension NULL stays and applies to the labels that remain (`docs/reference/layers.md`, "Removing labels").
- DR refuses the call with `ValueError` while a property that refers to the dimension still names the label (`mutable.py:1972-2006`).
- DR ignores a label that the axis does not hold, without an error (probe). The session refuses it, so that a stale FE does not commit a silent no-op.

### Examples

Each example shows the operation list that the FE sends and the calls that the session makes. The envelope and the `format` field are left out. The labels are those of a PyPSA-Eur store with one period.

(a) One scalar on one entity:

```json
[{"op": "set", "name": "p_nom_max", "at": {"entity": "DE0 1 onwind"}, "value": 25000}]
```

```python
wr.set("p_nom_max", 25000.0, entity="DE0 1 onwind")
```

(b) One value for every solar generator, by a label list or by a property selection:

```json
[{"op": "set", "name": "capital_cost", "at": {"entity": ["DE0 1 solar", "DE0 2 solar"]}, "value": 30000},
 {"op": "set", "name": "capital_cost", "where": {"ctype": "Generator", "carrier": "solar"}, "value": 30000}]
```

```python
wr.set("capital_cost", 30000.0, entity=["DE0 1 solar", "DE0 2 solar"])
wr.set("capital_cost", 30000.0, ctype="Generator", carrier="solar")
```

Both stage one row per label. Neither reaches a solar generator that a later operation adds.

(c) A constant for all snapshots of one entity:

```json
[{"op": "set", "name": "p_max_pu", "at": {"entity": "DE0 1 onwind"}, "value": 0.9}]
```

```python
wr.set("p_max_pu", 0.9, entity="DE0 1 onwind")
```

Where the parent holds a series for this entity, the WR writes 0.9 at each of its snapshots (`docs/reference/resolution.md`, "A dimension outside `partial`"). Else it stages one row with `snapshot` NULL.

(d) A time series for one entity, in the part `t0`:

```json
[{"op": "set", "name": "p_max_pu", "at": {"entity": "DE0 1 onwind"}, "table": "t0"}]
```

`t0.parquet` has the columns `snapshot` (`TIMESTAMP`, microseconds) and `value` (`DOUBLE`), one row per snapshot.

```python
wr.set("p_max_pu", con.read_parquet(path_of_t0), entity="DE0 1 onwind")
```

A snapshot that the table leaves out keeps its current value. The WR restates it (probe).

(e) A value on a connection:

```json
[{"op": "set", "name": "efficiency", "at": {"entity": "DE0 1 H2 Electrolysis", "bus": "DE0 1 H2"}, "value": 0.7}]
```

```python
wr.set("efficiency", 0.7, entity="DE0 1 H2 Electrolysis", bus="DE0 1 H2")
```

(f) A new generator with its properties, its bus and two attributes:

```json
[{"op": "add", "dim": "entity", "labels": ["DE0 1 solar new"], "properties": {"ctype": "Generator", "carrier": "solar"}},
 {"op": "add", "dim": "connection", "labels": [{"entity": "DE0 1 solar new", "bus": "DE0 1"}], "properties": {"role": "attached"}},
 {"op": "set", "name": "p_nom", "at": {"entity": "DE0 1 solar new"}, "value": 500},
 {"op": "set", "name": "capital_cost", "at": {"entity": "DE0 1 solar new"}, "value": 30000}]
```

```python
wr.add("entity", ["DE0 1 solar new"], ctype="Generator", carrier="solar")
wr.add("connection", [{"entity": "DE0 1 solar new", "bus": "DE0 1"}], role="attached")
wr.set("p_nom", 500.0, entity="DE0 1 solar new")
wr.set("capital_cost", 30000.0, entity="DE0 1 solar new")
```

`solar` must be a label of `carrier`, and `DE0 1` a label of `bus`.

(g) Removing an entity:

```json
[{"op": "remove", "dim": "entity", "labels": ["DE0 1 oil"]}]
```

```python
wr.remove("entity", ["DE0 1 oil"])
```

The entity's values go, and so do its `connection` tuples with their values.

(h) Two lists with the same operations in another order. The parent has one `p_nom` row per generator.

| List | Operations | Result |
|---|---|---|
| A | `set p_nom 900 at entity "DE0 1 onwind"`, then `set p_nom 950` (no `at`) | `DE0 1 onwind` has 950. The second row covers the first and replaces it. One row stays. |
| B | `set p_nom 950` (no `at`), then `set p_nom 900 at entity "DE0 1 onwind"` | `DE0 1 onwind` has 900. Both rows stay, and the more specific row wins. |
| C | `set p_nom 7 where ctype "Generator"`, then `add entity "pv"` | `pv` has no row of its own. |
| D | `add entity "pv"`, then `set p_nom 7 where ctype "Generator"` | `pv` has 7. |

The probe gave these results on a small record. List A as JSON:

```json
[{"op": "set", "name": "p_nom", "at": {"entity": "DE0 1 onwind"}, "value": 900},
 {"op": "set", "name": "p_nom", "value": 950}]
```

### Validation and errors

The BE checks the request before it claims. It answers 422 for a wrong shape and 413 for a size limit:

- The body is `multipart/form-data`. The parts `commit` and `changeset` come first, in this order.
- The envelope has its fields with their types.
- The changeset has a known `format` and matches the schema of [operations](#operations). Each `set` has exactly one of `value`, `values` and `table`.
- Each `table` names a part of the request. Each table part is named by exactly one operation.

Proposed size limits, to be agreed:

| Limit | Proposal |
|---|---|
| `changeset` part | 4 MiB |
| operations per changeset | 10 000 |
| labels in one list (`at`, `values`, `labels`) | 100 000 |
| table parts per request | 64 |
| one table part | 64 MiB |
| the whole body | 256 MiB |

The session checks each operation against the parent's schema before it opens the WR:

- The name is a declared attribute or `subject.name` property. The dimension of `add` and `remove` is declared and has no `one_of`.
- The keys of `at` are dimensions or fields of the attribute. The keys of `where` are none of them.
- The scalar values fit the declared type ([values](#values)). Datetime strings parse and have no offset.
- No `null` and no empty list in `at`, `where` and `labels`.
- A table's columns and types fit, read from the Parquet footer. No column repeats an `at` key. No two rows share a coordinate.

The session then applies the operations in order. Before a `remove`, it checks that each label is on the axis. DR checks the rest at each call (`docs/reference/editing.md`, "Validation"): an unknown attribute or label, a missing tuple, a wrong type, a property value that names no label, a refused `remove`, and crossing rows inside one table. DR raises `KeyError`, `ValueError` or `TypeError`.

A failing operation aborts the whole changeset. The session closes the WR and commits nothing. The claim stays as `claim.json` until the cleanup ([failure and cleanup](#failure-and-cleanup)). The session answers 422. The BE passes the body on to the FE unchanged:

```json
{"code": "operation_refused", "index": 2, "op": "set", "exception": "KeyError",
 "message": "`set('p_nom', ...)` names 'entity' labels ['coal'], which the staged axis does not hold; `add` them first"}
```

`index` is the position of the failing operation in `operations`, from 0. `message` is DR's message, or the session's own for a check before the call. A check of the BE has the same body with `code` `invalid_changeset` and `index` null where no single operation fails. Any other exception in the session is a fault and answers 500.

### From the FE's edit model

The FE's `ScenarioMutation` (`baby-manta/src/data/scenarios.ts`) holds a *direct* change or a *rule*. Its fields are strings. The FE parses `value` by the attribute's value type, which the `static_<dtype>` view that showed the value names ([constant values and the owner map](frontend.md#2-constant-values-and-the-owner-map)). The order of `Scenario.mutations` is the order of the operations. `targetId` gives the component type, such as `ctype` `Generator`.

| FE mutation | Operations |
|---|---|
| direct: `property`, `value` on one entity | `set` with `name` = `property`, `at` = `{entity}`, `value` |
| rule `set`, with `filterField` a property of `entity` (`carrier`, `type`) | `set` with `where` = `{ctype, [filterField]: filterValue}`, `value` |
| rule `set`, with another filter | The FE selects the labels with SQL and sends `set` with a label list in `at`. |
| rule `add`, `multiply`, `min`, `max`, now | The FE reads the settled current values with SQL ([settling in the FE](frontend.md#4-settling-in-the-fe)), computes, and sends `set` with `values`, or with a table for a series. |
| rule `add`, `multiply`, `min`, `max`, later | one `apply` operation (below) |
| op `add` or `remove` | `add` or `remove`. The FE creates none today. |

`previousValue` stays in the FE. The `expected` revision of the envelope guards against a stale parent.

A rule acts once, on the labels that match when it runs. It is no standing rule: a label added in a later commit does not get the value.

### The rule operation (not decided)

A rule `add`, `multiply`, `min` or `max` needs the current values. For a series these are millions of values, which the FE would have to download, settle and upload again. A fourth operation lets the session compute them. This is a later addition. Decision D6 is open.

```json
{"op": "apply", "name": "p_nom_max", "fn": "multiply", "operand": 1.2,
 "where": {"ctype": "Generator", "carrier": "solar"}}
```

`fn` is `add`, `multiply`, `min` or `max`. `operand` is a scalar of the attribute's type. `at` and `where` select as in `set`. The session expands it on the WR in four steps:

1. It selects the labels that `at` and `where` give, on the WR as staged at that operation.
2. It reads `wr.attributes[name]` for these labels and settles the rows with DR's `settle` (`src/datarecord/settle.py:34`). Where no row covers a coordinate, it takes `Schema.default_for` (`schema/schema.py:812`).
3. It computes the new value in one DuckDB statement: `value + operand`, `value * operand`, `least(value, operand)` or `greatest(value, operand)`.
4. It stages the result with `wr.set(name, relation)`, one row per settled coordinate.

The result is deterministic. It reads only the WR at that operation, which the parent and the earlier operations fix. The SQL works row by row, with no order, no aggregate and no clock. On an `int` attribute only `add`, `min` and `max` with an integer operand are allowed.

### The same list in live editing

Later the same `changeset` part is the body of `POST .../datarecord-session/registrations/{name}/edits` for a registration of the kind `edit` ([working records](session.md#6-working-records), [flow 10](index.md#10-later-live-editing)). The differences:

- The body has no `commit` part. The WR already has its base revision, and nothing moves a reference.
- The BE appends the request to the edit log: the `changeset` part in Postgres, the table parts in S3 under the session prefix. It then passes the request to the session.
- The session applies the operations to the live WR. If an operation fails, the session calls `wr.rollback()`, which clears every staged row (`mutable.py:2063-2076`). It then replays the log without the failing request and answers 422 with the same body as above. The BE removes the request from the log.
- After a restart the session opens a fresh WR on the base revision and applies the logged requests in log order.
- The commit of a live WR carries no changeset ([what each party does](#what-each-party-does)).

For a replay to give the same WR, the format guarantees four things:

- The result depends only on the base revision, the DR version and the list. No operation reads a clock, a random source or state outside the WR.
- Selections by `where` and the reads of a rule run on the WR as staged at that operation, which the earlier operations fix.
- Values are exact: JSON numbers in their shortest round-trip form, table values as binary Parquet.
- A request is self-contained. Its operations name its own table parts only, and each log entry keeps its `format` version.

### What the format leaves out

- Schema changes: new attributes, properties, dimensions or dtypes. A WR stages edits under its base's schema and refuses undeclared columns (`mutable.py:2023-2059`).
- Renames of labels. DR has no rename. A rename is a `remove`, an `add` and a `set` per value, which the FE can compose.
- Curves and the unset of an attribute. DR's `set` writes no `breakpoint` (`mutable.py:1445`), and DR has no call that clears an attribute value.

## 4. Open points

- How does the BE mint tokens: with the minter key, or with a minter of its own? Proposal: agree with Kristijan.
- Which role do session tokens use? Proposal: a read-only role (`GetObject`, `ListBucket`), stricter than reuse of `manta-block-run`; to agree with Kristijan.
- Does an STS token with a session token work as `S3Credentials` on SeaweedFS 4.53, for the workspace and for a commit? Proposal: run the left-over of S6.
- Does SeaweedFS 4.53 honour `If-Match` on PutObject atomically? Proposal: the test in the [open points of the MVP backend note](backend-mvp.md#16-open-points).
- Does a large commit finish within the 900 s token? Proposal: measure it in the rerun of S3 on the stack.
- Does the changeset get the rule operation `apply` (D6)? Proposal: add it later as sketched in [the rule operation](#the-rule-operation-not-decided); until then the FE expands rules into `values` or a table.
- Does `apply` act on the default where no row covers a coordinate? Proposal: yes, on the settled value with `Schema.default_for`.
- Are the size limits of [validation and errors](#validation-and-errors) right? Proposal: start with them and measure the largest series edit.
- Does the changeset keep `where`, so that DR selects labels when the operation runs? Proposal: keep it, because the FE's rule `set` maps to it without a label list.
- Does `remove` of a label that the axis lacks fail? DR ignores it (probe). Proposal: the session refuses it.
- What does a staged row with a NULL `value` mean on read? Not verified; DR's docs say nothing. Proposal: the session refuses `null` for an attribute until DR documents it.
- Which `where` keys does DR accept on an attribute over a multi-dimension? Not verified; a probe refused `ctype` without `bus`. Proposal: test it on `efficiency` before the FE relies on it.
- Can a log replay after a move of the DR pin? A new DR version may apply a list differently. Proposal: each log entry records the DR commit hash, and the BE commits or drops open logs before the pin moves (D19).
- DR PR 142 keys `connection` by `entity` and `port`, with `bus` as a property (F31). Proposal: the format takes field names from the parent's schema and needs no change; the FE's code for connection coordinates moves with the pin.

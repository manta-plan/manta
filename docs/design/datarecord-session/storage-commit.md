# Design note: storage access and commit

How an edit becomes a revision: the commit flow, the claim, the two scoped S3 tokens with their policies, and the changeset format. Read with the S3 access control plan for runs (F25).

Part of the datarecord-session plan, draft 9. Start with the [overview](README.md). The codes F, S, R, D and I point to the [appendix](appendix.md).

This note covers the write path of the session. The [commit flow](#1-commit-flow) describes the commit exchange between FE, BE, the session and S3. [The two tokens](#2-the-two-tokens) describes the two S3 tokens and the requirements on the object store. The [changeset format](#3-changeset-format) describes the changeset that the FE sends.

In short: the session has no write access of its own. For each commit the BE claims a new revision with DR and mints a short-lived STS token that can write into that one layer. The BE then sends the claim, the token and the changeset to the session. The session applies the changeset to a WR on the parent and commits with the token. It returns the manifest, and the BE compares the manifest with its claim. The session reads with a second token for the project's folder. Both tokens are grants of the same form as the storage grants of runs (F25).

## 1. Commit flow

### The flow

```
FE --changeset--> BE                                    S                        S3
                  1. check ownership, parent committed
                  2. Store.claim(parent, meta)  ------------------------------> layers/<id>/claim.json
                     insert revision row, status=claimed
                  3. mint write token for layers/<id>/
                  4. POST /commits {claim, token, changeset} -->
                                                        5. WR(parent), apply ops
                                                           (restatement, F13)
                                                        6. Claim.commit(wr, credentials=token)
                                                           ---> layers/<id>/dimensions, attributes, manifest.json
                  <-- {manifest} -------------------------
                  7. compare id, parent, meta of the manifest with the claim
                     set status=committed
                  8. move the reference named in the request
FE <--revision---
```

1. The BE checks that the user owns the project and that the parent revision is committed.
2. The BE calls `Store.claim(parent, meta)`. The claim's `meta` carries `manta.kind` and `manta.created_by`. DR draws the id of the new revision and writes `layers/<id>/claim.json`. The BE inserts the revision row with the status `claimed`.
3. The BE mints a write token for `layers/<id>/` (see [the two tokens](#2-the-two-tokens)).
4. The BE sends `POST /commits` to the session. The request carries the claim, the write token and the changeset (see [changeset format](#3-changeset-format)). It also names the reference to move and the revision that the FE expects there.
5. The session opens a WR on the parent and applies the operations in order. The WR does the restatement (F13).
6. The session passes the write token to `Claim.commit(source, credentials=...)`. DR writes the Parquet files and `manifest.json` under `layers/<id>/`.
7. The session returns the manifest in its answer. The BE compares id, parent and `meta` with its claim and sets the row to `committed`. The BE does not read `manifest.json` from S3 again.
8. The BE moves the named reference at commit confirmation, by compare-and-set (see [revision index](backend.md#1-revision-index)).

### The claim across processes

The BE sends the claim in DR's JSON form with its five fields (`claim.model_dump_json()`). The session rebuilds it with `Store.claim_from`, without a read of `claim.json` (F11). The store URI in the payload must equal the session's URI of that store. Both sides therefore build the URI by the same rule (see [session service](session.md#3-session-service)).

DR does not compare the claim object with `claim.json` (F26). Nothing depends on such a check: the BE made the claim, and it compares the returned manifest with it.

### What each party does

The BE starts every commit exchange. The session never calls the BE. This holds in every case:

| Case | How the BE starts it |
|---|---|
| One-shot commit | The FE sends the changeset to the BE. The BE claims, mints the token and calls the session. |
| Commit of a live WR (see [working records](session.md#6-working-records)) | The FE asks the BE. The BE claims, mints the token and sends both with the name of the working record. |

The BE never holds a `Record` and never folds. It works on claims and revisions only. It writes `claim.json` and receives the manifest, both small JSON objects. `Store.cleanup` runs in the BE only, under the backend key, never in the session.

The session does the fold, the restatement and the commit. It holds no write right of its own. It writes only with the token that the BE sends for one claimed layer.

DR creates the layer-scoped DuckDB secret and drops it. The session only passes the token on.

The playbook blocks of a run can use the same exchange later, when their permissions are trimmed. The BE (or the run flow) then claims and hands the block a token for one layer (see [runs and blocks](backend.md#2-runs-and-blocks)).

### Failure and cleanup

A claim without a commit stays as a `claimed` row and a `claim.json`. A BE task removes both: `Store.cleanup(older_than=...)` for the claim files, and the `claimed` rows in Postgres.

A commit that exceeds the 900 s of its token fails at its next write. The claim then stays pending until the cleanup.

If the reference moved since the FE read it, the compare-and-set fails and the BE reports a conflict. The new revision exists, but no name points to it (see [revision index](backend.md#1-revision-index)).

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

- A compromised session could return one manifest and write another. The damage stays inside the user's own project, and `sync_store` repairs the mirror.
- Until the commit token expires, the session can overwrite data files of the layer it committed. The 900 s lifetime limits this.
- Until the storage grants reach the session, it holds the global S3 credential. Code alone confines it to the project prefix (I1).

### Object store requirements

SeaweedFS is the only target for now (F25, D11). AWS S3 and MinIO support the same flow. GCS does not.

SeaweedFS in dev moves from 4.05 to 4.53 with the `s3-security` branch (F25). DR was tested there through the environment chain.

Not yet tested:

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

A changeset is an ordered list of edit operations. Each operation maps one to one to the WR API:

| Operation | Maps to | Payload |
|---|---|---|
| `set` | `WorkingRecord.set(attribute, value, **coords)` | scalar and coordinates in JSON, or a table |
| `add` | `WorkingRecord.add(dim, labels, **columns)` | labels and property columns |
| `remove` | `WorkingRecord.remove(dim, labels)` | labels |

Wire form: multipart. One JSON part holds the operation list. Each table payload is one Parquet part in DR's long row shape (dimension columns, then `value`).

The format follows from three reasons:

- The session does the restatement, because it applies the operations to a WR (F13). The FE and the BE never build a complete layer.
- The same operations are the edit API of the future registered WR (see [working records](session.md#6-working-records)). A one-shot commit is "open WR, apply, commit, close".
- The FE's *direct* changes map to `set` with a scalar.

The FE's *rule* changes (multiply all `p_nom_max` of a carrier) need one more operation type. The session would expand it with SQL. This is open as decision D6. The proposal is to add it later.

The changeset is a pre-stage of LayerData, not LayerData itself. It is the session's own format. Nothing is requested from DR (R5).

## 4. Open points

- How does the BE mint tokens: with the minter key, or with a minter of its own? Proposal: agree with Kristijan.
- Which role do session tokens use? Proposal: a read-only role (`GetObject`, `ListBucket`), stricter than reuse of `manta-block-run`; to agree with Kristijan.
- Does an STS token with a session token work as `S3Credentials` on SeaweedFS 4.53, for the workspace and for a commit? Proposal: run the left-over of S6.
- Does a large commit finish within the 900 s token? Proposal: measure it in the rerun of S3 on the stack.
- Does the changeset get a rule operation (D6)? Proposal: add it later, expanded by the session with SQL.

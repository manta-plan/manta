# A Quack client can use the server's S3 secret on any bucket or prefix the credential permits

## Summary
The S3 secret that datarecord installs on a Quack server signs requests for any `s3://` URL a client asks for, not only the project's prefix. A client with a valid token reads whatever the credential can read. Secret values stay redacted; the client does not need them.

## Context
Manta has one S3 credential per deployment, so a client of project A can read project B and any other bucket the key covers (`store.py:135-164`). Quack runs client SQL as-is: "A Quack server exposes the full SQL surface of the underlying DuckDB instance" and the default authorization hook returns every query unchanged ([security](https://duckdb.org/docs/2.0/quack/security.html), **read**). Secrets "can have an optional scope, which is a file path prefix"; the secret with the longest matching prefix is used ([secrets manager](https://duckdb.org/docs/2.0/configuration/secrets_manager.html), **read**). An unscoped secret matches every path. Scope is a selection rule, not a restriction on the client.
Related: `..` bypasses `allowed_directories` on S3; see quack-issue-3.

## Minimal reproducer
`datarecord/.venv/bin/python -I repro.py [open|scope|allow]` (default `open`). Ports 9911 (fake S3) and 9912 (Quack). Dummy credentials; nothing leaves loopback. The `scope` mode adds a keyless catch-all secret so unmatched reads go to the fake endpoint, not to AWS.
```python
# datarecord/.venv/bin/python -I repro.py [open|scope|allow]
import http.server, re, subprocess, sys, threading, time
import duckdb

S3, QK, TOK = 9911, 9912, "tok-demo-1234"
mode = sys.argv[1] if len(sys.argv) > 1 else "open"

if len(sys.argv) > 2 and sys.argv[2] == "--serve":      # server child process
    db = duckdb.connect(":memory:")
    db.execute("INSTALL quack; LOAD quack; INSTALL httpfs; LOAD httpfs")
    scope = ", SCOPE 's3://bucket/projA/'" if mode == "scope" else ""
    db.execute(f"CREATE OR REPLACE SECRET (TYPE s3, KEY_ID 'AKIADUMMYSERVERKEY', SECRET 'dummy', "
               f"ENDPOINT '127.0.0.1:{S3}', URL_STYLE 'path', USE_SSL false{scope})")
    if mode == "scope":   # keyless catch-all, so unmatched reads go (unsigned) to the fake, not to AWS
        db.execute(f"CREATE SECRET fallback (TYPE s3, ENDPOINT '127.0.0.1:{S3}', URL_STYLE 'path', "
                   "USE_SSL false, SCOPE 's3://')")
    db.execute(f"CALL quack_serve('quack:localhost:{QK}', token='{TOK}')")
    if mode == "allow":
        db.execute("SET allowed_directories=['s3://bucket/projA/']")
        db.execute("SET enable_external_access=false")
        db.execute("SET lock_configuration=true")
    time.sleep(60)
    sys.exit()

log = []                                                # fake S3: record path + key id
class H(http.server.BaseHTTPRequestHandler):
    def _l(self):
        m = re.search(r"Credential=([^/]+)/", self.headers.get("Authorization") or "")
        log.append((self.command, self.path, m.group(1) if m else "(unsigned)"))
        self.send_response(404); self.send_header("Content-Length", "0"); self.end_headers()
    do_GET = do_HEAD = _l
    def log_message(self, *a): pass
srv = http.server.HTTPServer(("127.0.0.1", S3), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()

child = subprocess.Popen([sys.executable, "-I", __file__, mode, "--serve"])
try:
    time.sleep(4)
    c = duckdb.connect(":memory:")
    c.execute("INSTALL quack; LOAD quack")
    c.execute(f"ATTACH 'quack:localhost:{QK}' AS r (TOKEN '{TOK}')")
    for tag, url in [("own prefix  ", "s3://bucket/projA/a.parquet"),
                     ("other prefix", "s3://bucket/projB/a.parquet"),
                     ("other bucket", "s3://other-bucket/secret.parquet")]:
        n = len(log)
        try: c.execute(f"FROM r.query($$SELECT * FROM read_parquet('{url}')$$)").fetchall()
        except Exception as e: err = str(e).split("\n")[0][:70]
        sent = log[n:]
        print(f"{tag} {url:36} -> " + (f"S3 saw {sent[0][0]} {sent[0][1]} key={sent[0][2]}" if sent
              else f"nothing sent ({err})"))
finally:
    child.kill(); srv.shutdown()
print("expected: requests for projB/ and other-bucket never reach S3 signed with the server key")
```
Output, `open` mode (**verified**). Expected: only `projA/` is signed with the server key.
```
own prefix   s3://bucket/projA/a.parquet          -> S3 saw HEAD /bucket/projA/a.parquet key=AKIADUMMYSERVERKEY
other prefix s3://bucket/projB/a.parquet          -> S3 saw HEAD /bucket/projB/a.parquet key=AKIADUMMYSERVERKEY
other bucket s3://other-bucket/secret.parquet     -> S3 saw HEAD /other-bucket/secret.parquet key=AKIADUMMYSERVERKEY
```

## Environment
DuckDB 2.0.0 (quack, httpfs installed from the extension repo), Python 3.14.5, macOS 26.6.2 (Darwin 25.6.0).

## Where it belongs
Mostly expected DuckDB behaviour, so this is a Manta deployment issue. Upstream, at most a documentation note on the Quack security page that S3/GCS/Azure secrets on the server are usable by every authenticated client; I would not file a bug.

## Suggested fix
Results (**verified**, same script):
- (a) `SCOPE 's3://bucket/projA/'` on the secret: projA signed with the server key; projB and other-bucket arrived **unsigned** (`key=(unsigned)`). Signing stops, but the client can still send anonymous requests through the server. This is enough only if the endpoint rejects anonymous access. Without a catch-all secret, an unscoped path falls back to DuckDB's default S3 endpoint, so a client can make the server send anonymous requests to public AWS S3. This happened during this investigation (AWS answered 403). So `SCOPE` needs a keyless catch-all secret, as `scope` mode has, or the allowlist in (b). (Added by reviewer.)
- (b) `allowed_directories=['s3://bucket/projA/']`, `enable_external_access=false`, `lock_configuration=true` (set after `quack_serve`): projB and other-bucket got `Permission Error` and no request was sent.

Recommendation, in layers:
1. A per-project S3 credential, scoped at the storage layer (SeaweedFS identity or policy) to the project's prefix, read-only. This is the only layer that holds against bypasses, including `..`. Anonymous access disabled on the bucket.
2. `SCOPE 's3://bucket/projA/'` on the server secret (cheap, and it ties the secret to one prefix). Note the `..` caveat from quack-issue-3 is **untested** against scope matching.
3. `allowed_directories` + `enable_external_access=false` + `lock_configuration=true`, in the order in `quack.md` requirement 3.
4. An authorization hook with a function allowlist excluding `read_*`, `glob`, `quack_*` (see `quack.md` §4; **untested** beyond SELECT-only).
Alternatives: one DuckDB instance per project already follows from `quack.md` requirement 1; a presigned-URL or proxy-only access path (**untested**) would keep the key out of DuckDB entirely.

## Open questions
- Does SeaweedFS in our deployment support per-identity prefix policies, and do `..` or encoded paths reach the policy check unnormalised? **Untested.**
- Does the `scope` secret match `s3://bucket/projA/../projB/x`? **Untested** here.

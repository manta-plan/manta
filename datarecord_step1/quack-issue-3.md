# DuckDB `allowed_directories` does not resolve `..` in S3 paths: `s3://b/projA/../projB/` passes the check

## Summary

With `allowed_directories=['s3://bucket/projA/']` and `enable_external_access=false`, `s3://bucket/projA/../projB/a.parquet`
passes the check and httpfs requests `/bucket/projB/a.parquet`. Local paths are canonicalised first and are denied; remote
paths are not. DuckDB core plus httpfs, no Quack involved. **verified** on 2.0.0 and 1.5.5.

## Context

Manta plans to expose a server-side DuckDB to DuckDB-Wasm over Quack, with one project's datarecord store open from S3 and
`allowed_directories` confining it to that project's prefix. The S3 credential is bucket-wide, so the allowlist is the
only thing keeping a client inside `projA/`. It does not.

Docs (all three URLs resolve, `curl -sIL`):
- [Configuration](https://duckdb.org/docs/2.0/configuration/overview): "List of directories, and directory prefixes, that
  are ALWAYS allowed to be queried, even when enable_external_access is false."
- [Securing DuckDB](https://duckdb.org/docs/2.0/operations_manual/securing_duckdb/overview): "fine-grained access control
  for the file system". [Quack security](https://duckdb.org/docs/2.0/quack/security) never mentions it (grep, **verified**).

Nothing says remote paths are treated differently or that `..` is unhandled (**read**). Local `/allowed/../../etc/passwd` is
denied and `s3://bucket/projA-evil/` is denied, so prefix matching works; the gap is normalisation (both **verified**, below).

## Reproducer (no Quack)

`datarecord/.venv/bin/python -I repro.py` (needs `httpfs` installed or downloadable; talks only to 127.0.0.1).

```python
# allowed_directories does not resolve '..' in S3 paths. 127.0.0.1 only. Optional env: PORT, URL_STYLE.
import http.server, os, tempfile, threading
import duckdb

PORT = int(os.environ.get("PORT", "9921"))
STYLE = os.environ.get("URL_STYLE", "path")
LOG = []
class H(http.server.BaseHTTPRequestHandler):  # fake S3: log the request, answer 404
    def _l(self):
        LOG.append(f"{self.command} {self.path}")
        self.send_response(404); self.send_header("Content-Length", "0"); self.end_headers()
    do_GET = do_HEAD = _l
    def log_message(self, *a): pass
srv = http.server.HTTPServer(("127.0.0.1", PORT), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
allowed = tempfile.mkdtemp()
con = duckdb.connect()
con.execute("INSTALL httpfs; LOAD httpfs;")
con.execute(f"""CREATE SECRET s (TYPE S3, KEY_ID 'dummy', SECRET 'dummy', REGION 'us-east-1',
    ENDPOINT '127.0.0.1:{PORT}', URL_STYLE '{STYLE}', USE_SSL false)""")
con.execute(f"SET allowed_directories=['s3://bucket/projA/', '{allowed}/']")
con.execute("SET enable_external_access=false")
print("duckdb", duckdb.__version__, "url_style", STYLE)

CASES = [  # (label, SQL function, path, should the request reach the endpoint?)
    ("in-prefix control", "read_parquet", "s3://bucket/projA/a.parquet", True),
    ("sibling prefix", "read_parquet", "s3://bucket/projA-evil/a.parquet", False),
    ("S3 '..'", "read_parquet", "s3://bucket/projA/../projB/a.parquet", False),
    ("S3 '..' glob", "glob", "s3://bucket/projA/../projB/*.parquet", False),
    ("local '..' control", "read_csv", f"{allowed}/../../../etc/passwd", False),
]
for label, fn, path, should_reach in CASES:
    LOG.clear(); err = "none"
    try:
        con.execute(f"SELECT * FROM {fn}('{path}')")
    except Exception as e:
        err = type(e).__name__
    reached = bool(LOG)
    print(f"[{'ok' if reached == should_reach else 'BUG'}] {label}: {fn}('{path}')")
    print(f"      expected reach={should_reach}, actual reach={reached} {LOG[:1]} ({err})")
srv.shutdown()
```

Output, DuckDB 2.0.0, exit 0 (**verified**; temp dir shortened to `$TMP`; the trailing `(...)` is the exception class):

```
duckdb 2.0.0 url_style path
[ok] in-prefix control: read_parquet('s3://bucket/projA/a.parquet')
      expected reach=True, actual reach=True ['HEAD /bucket/projA/a.parquet'] (HTTPException)
[ok] sibling prefix: read_parquet('s3://bucket/projA-evil/a.parquet')
      expected reach=False, actual reach=False [] (PermissionException)
[BUG] S3 '..': read_parquet('s3://bucket/projA/../projB/a.parquet')
      expected reach=False, actual reach=True ['HEAD /bucket/projB/a.parquet'] (HTTPException)
[BUG] S3 '..' glob: glob('s3://bucket/projA/../projB/*.parquet')
      expected reach=False, actual reach=True ['GET /bucket/?encoding-type=url&list-type=2&prefix=projA%2F..%2FprojB%2F'] (HTTPException)
[ok] local '..' control: read_csv('$TMP/../../../etc/passwd')
      expected reach=False, actual reach=False [] (PermissionException)
```

`BUG` = the request reached the endpoint for a path outside `projA/`. For object reads DuckDB collapses the `..` itself, so
the server never sees one. For `glob` the listing carries `prefix=projA/../projB/` literally, which real S3 would match to
nothing: check bypassed, but no data exposure shown via `glob` (the earlier note that it "reached `/bucket/projB`" overstated this).

## Variants (**verified**, extra cases run from a scratch copy of the script)

- **`%2e%2e` / `%2E%2E`**: not a bypass. Sent as `%252e%252e`, a literal key under `projA/`.
- **Doubled slash** `projA//../projB/a.parquet`: not a bypass (`/bucket/projA/projB/a.parquet`); `projA/x/../../projB/` is.
- **Further escapes**: `projA/../../other/a.parquet` sent `HEAD /other/a.parquet`; `projA/..` sent `HEAD /bucket/`.
- **`URL_STYLE 'vhost'`** (endpoint `localhost:9922`): same bypass, `HEAD /projB/a.parquet`, Host `bucket.localhost`.
- **DuckDB 1.5.5**: same results (five core cases, plus encoded and bucket-escape). Not a 2.0 regression.

## SeaweedFS

**Untested.** `docker ps` listed no containers (so no `seaweedfs` from `docker/compose-dev-services.yaml`), and I did not
start any. Probably moot for object reads, since DuckDB collapses `..` client-side (**verified**); it matters only if a `..`
reaches the server (the `glob` prefix). To test: throwaway bucket, `PUT projB/a.txt`, then `GET /bucket/projA/../projB/a.txt`
via `curl --path-as-is --aws-sigv4`: 200 means it resolves. Delete the bucket.

## Environment

DuckDB 2.0.0 (`datarecord/.venv`) and 1.5.5 (`uv run --isolated`); CPython 3.14.5; macOS 26.6.2 arm64; httpfs via `INSTALL`.

## Where it belongs

DuckDB upstream, core path check rather than httpfs. **read**, tag `v2.0.0`:
- `src/common/file_system.cpp:997-1002`, `FileSystem::CanonicalizePath`: returns remote paths unchanged ("don't canonicalize
  remote paths"); only local paths get `.`/`..` collapsing.
- `src/main/config.cpp:926`, `DBConfig::SanitizeAllowedPath`, calls it; `CanAccessFile` (line 1017) then does a plain
  `StartsWith` against `allowed_directories`.

## Suggested fix

- Upstream: collapse `.` and `..` segments in remote paths (never above the bucket) before prefix matching, or reject `..` segments.
- Manta, primary: per-project storage credentials scoped to the project's prefix.
- Manta, optional: an authorization-hook check rejecting `..` in the query text (defence in depth).

## Open questions

- Is the remote exclusion in `CanonicalizePath` deliberate? The request path is collapsed anyway, so check and request disagree.
- Does `main` differ from `v2.0.0` (only the tag was read)? Does SeaweedFS resolve `..` itself (untested)?

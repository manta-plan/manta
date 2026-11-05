"""Make a duckdb-wasm dev build of DuckDB v2.0.0 usable by the test page.

The newest duckdb-wasm (1.33.1-dev110.0) runs DuckDB commit `d54cbbe3df`, which
is exactly the `v2.0.0` tag, but it was built without the tag. So:

- It looks for extensions under the commit, where none are published, and
  refuses the release's builds by their version field. This copies the
  release's builds with that field rewritten into `static/ext/`, the repository
  the test page points the dev build at. Rewriting the field voids the
  signature, so the page allows unsigned extensions.
- The published Quack build predates "Do not start the heartbeat thread on
  single-threaded wasm" (duckdb-quack 438dfe3), so ATTACH fails in the
  single-threaded build. `--quack` takes a `wasm_eh` build of duckdb-quack's
  main instead (see the README).

Only for the proof of concept, until duckdb-wasm publishes a v2.0.0 release
and Quack republishes its Wasm builds.

    uv run python scripts/prepare_wasm.py [--quack path/to/quack.duckdb_extension.wasm]
"""

from __future__ import annotations

import argparse
import urllib.request
from pathlib import Path

STATIC = Path(__file__).parent.parent / "static"
RELEASE, COMMIT = "v2.0.0", "d54cbbe3df"

# Quack, and what it autoloads to attach.
EXTENSIONS = ("quack", "httpfs")
PLATFORM = "wasm_eh"  # the single-threaded build with Wasm exceptions

FIELD = 32
FOOTER = 512
VERSION_FIELD = 5  # fields: …, abi, extension version, duckdb version, platform, magic


def fetch(url: str) -> bytes:
    # The extension bucket answers urllib's default user agent with 403.
    request = urllib.request.Request(url, headers={"User-Agent": "duckdb"})
    with urllib.request.urlopen(request) as response:
        return response.read()


def relabel(blob: bytes, release: str, commit: str) -> bytes:
    start = len(blob) - FOOTER + VERSION_FIELD * FIELD
    found = blob[start : start + FIELD].rstrip(b"\0").decode()
    # A local build carries `git describe` (v2.0.0-0-g<commit>), not the tag.
    if found.split("-")[0] != release:
        msg = f"expected DuckDB version {release!r} in the footer, found {found!r}"
        raise ValueError(msg)
    return blob[:start] + commit.encode().ljust(FIELD, b"\0") + blob[start + FIELD :]


def write(path: Path, blob: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)
    print(path.relative_to(STATIC.parent))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quack", type=Path, help="local wasm_eh build of Quack")
    args = parser.parse_args()

    for extension in EXTENSIONS:
        name = f"{extension}.duckdb_extension.wasm"
        if extension == "quack" and args.quack:
            blob = args.quack.read_bytes()
        else:
            blob = fetch(f"https://extensions.duckdb.org/{RELEASE}/{PLATFORM}/{name}")
        write(STATIC / "ext" / COMMIT / PLATFORM / name, relabel(blob, RELEASE, COMMIT))


if __name__ == "__main__":
    main()

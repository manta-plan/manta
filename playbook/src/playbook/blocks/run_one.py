# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Run a single block from the command line.

    python -m playbook.blocks.run_one <block> --record '{"url": ...}' --output-base <url> \
        [--source <block library>] [--config '<json>'] [--inputs '<json>']

This is the whole contract between a block container and whatever drives it -
Manta, a shell, a CI job: plain arguments in, ordinary log output, and one final
`RESULT_MARKER` line on stdout saying where the output record landed. The exit
code says whether the block succeeded. Nothing here knows or cares what is doing
the driving, which is what lets block images stay free of any orchestration code.
"""

import argparse
import json
import sys

from playbook.blocks.core import DataRecord
from playbook.blocks.registry import get_block, load_block_sources

RESULT_MARKER = "MANTA_BLOCK_RESULT "
"""Prefix of the one stdout line that carries the block's result record as JSON."""


def result_line(record: DataRecord) -> str:
    """The line `main` prints when a block finishes."""
    return f"{RESULT_MARKER}{json.dumps(record.to_dict())}"


def parse_result_line(line: str) -> DataRecord | None:
    """Read a result record back out of one line of output, or None if it isn't one.

    Drivers scan the block's output for the last line this accepts; keeping the
    parser next to the printer means the protocol cannot drift apart.
    """
    stripped = line.strip()
    if not stripped.startswith(RESULT_MARKER):
        return None
    return DataRecord.from_dict(json.loads(stripped[len(RESULT_MARKER) :]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m playbook.blocks.run_one",
        description="Run one registered block on a record and report where its result went.",
    )
    parser.add_argument("block", help="the block's registered name")
    parser.add_argument(
        "--record",
        required=True,
        help='the input record as JSON, e.g. \'{"url": "in.nc"}\'',
    )
    parser.add_argument(
        "--output-base",
        required=True,
        help="where the block should produce its output: a URL without an extension",
    )
    parser.add_argument("--config", default="{}", help="the block's settings, as JSON")
    parser.add_argument(
        "--inputs",
        default="{}",
        help="wired-in records by setting name, as JSON: {name: {url: ...}, ...}",
    )
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        metavar="MODULE",
        help=(
            "a block library whose import registers blocks, e.g. playbook_library; "
            "may be repeated. Without it, MANTA_BLOCK_SOURCES is used."
        ),
    )
    args = parser.parse_args(argv)

    # Blocks live in libraries this package knows nothing about, so the library
    # holding the one being asked for has to be named before it can be looked up.
    load_block_sources(args.source or None)

    block_cls = get_block(args.block)
    wired = {name: DataRecord.from_dict(value) for name, value in json.loads(args.inputs).items()}
    result = block_cls(block_cls.merge_config(json.loads(args.config), wired)).run(
        DataRecord.from_dict(json.loads(args.record)), args.output_base
    )

    print(result_line(result), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

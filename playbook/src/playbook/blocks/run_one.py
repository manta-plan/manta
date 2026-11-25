# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Run a single block from the command line.

    python -m playbook.blocks.run_one <block> --revision '{"store": ..., "id": ...}' \
        [--source <block library>] [--config '<json>']

This is the whole contract between a block container and whatever drives it -
Manta, a shell, a CI job: plain arguments in, ordinary log output, and one final
`RESULT_MARKER` line on stdout saying where the output revision landed. The exit
code says whether the block succeeded. Nothing here knows or cares what is doing
the driving, which is what lets block images stay free of any orchestration code.
"""

import argparse
import json
import sys
from contextlib import closing

from playbook.blocks.core import RevisionRef
from playbook.blocks.registry import get_block, load_block_sources

RESULT_MARKER = "MANTA_BLOCK_RESULT "
"""Prefix of the one stdout line that carries the block's result revision as JSON."""


def result_line(ref: RevisionRef) -> str:
    """The line `main` prints when a block finishes."""
    return f"{RESULT_MARKER}{json.dumps(ref.to_dict())}"


def parse_result_line(line: str) -> RevisionRef | None:
    """Read a result revision back out of one line of output, or None if it isn't one.

    Drivers scan the block's output for the last line this accepts; keeping the
    parser next to the printer means the protocol cannot drift apart.
    """
    stripped = line.strip()
    if not stripped.startswith(RESULT_MARKER):
        return None
    return RevisionRef.from_dict(json.loads(stripped[len(RESULT_MARKER) :]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m playbook.blocks.run_one",
        description="Run one registered block on a revision and report where its result went.",
    )
    parser.add_argument("block", help="the block's registered name")
    parser.add_argument(
        "--revision",
        required=True,
        help='the input revision as JSON, e.g. \'{"store": "<store>", "id": "<revision>"}\'',
    )
    parser.add_argument("--config", default="{}", help="the block's settings, as JSON")
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

    from datarecord import Workspace

    from playbook.blocks.run import open_revision

    # Blocks live in libraries this package knows nothing about, so the library
    # holding the one being asked for has to be named before it can be looked up.
    load_block_sources(args.source or None)

    block = get_block(args.block)(json.loads(args.config))
    with closing(Workspace()) as workspace:
        base = open_revision(workspace, RevisionRef.from_dict(json.loads(args.revision)))
        result = RevisionRef.from_revision(block.run(base))

    print(result_line(result), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

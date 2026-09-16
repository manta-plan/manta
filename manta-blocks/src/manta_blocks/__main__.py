# SPDX-FileCopyrightText: 2026 Manta Blocks contributors
#
# SPDX-License-Identifier: MIT

"""Print a description of the blocks available in this environment, as JSON.

    pixi run -e <env> python -m manta_blocks [block library module ...]

Any module names given are imported first, so their blocks register themselves; with
none given, modules are read from `MANTA_BLOCK_SOURCES`. Run it once per environment
and merge the results with `merge_catalogues` to get a description of every block in
the system, including the ones no single environment could import.
"""

import json
import sys

from manta_blocks.registry import catalogue, load_block_sources


def main(argv: list[str]) -> int:
    load_block_sources(argv or None)
    print(json.dumps(catalogue().model_dump(mode="json"), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

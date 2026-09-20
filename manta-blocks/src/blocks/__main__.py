# SPDX-FileCopyrightText: 2026 Manta Blocks contributors
#
# SPDX-License-Identifier: MIT

"""Print a description of the blocks available in this environment, as JSON.

    pixi run -e <env> python -m blocks

Run it once per environment and merge the results with `merge_catalogues` to get a
description of every block in the system, including the ones no single environment
could import.
"""

import json
import sys

from blocks.registry import catalogue


def main(argv: list[str]) -> int:
    if argv:
        print(f"usage: python -m blocks (got {argv})", file=sys.stderr)
        return 2
    print(json.dumps(catalogue().model_dump(mode="json"), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

# SPDX-FileCopyrightText: 2026 Manta Blocks contributors
#
# SPDX-License-Identifier: MIT

"""The blocks that ship with Manta.

These all need PyPSA, so they are imported only when something asks for one by name.
Look them up through `blocks.registry`, which knows where each of them lives.

`catalogue.json` is the **generated** description of these blocks (see
`python -m blocks` and `blocks.registry`), committed so that environments which
cannot import them - the Manta backend has no PyPSA - can still list them, draw
them, and validate playbook settings against them. Regenerate it after changing
anything a block declares (settings, dims, inputs, docstring first line):

    uv sync --extra pypsa
    MANTA_ENV=pypsa uv run python -m blocks > src/blocks/library/catalogue.json

The pypsa-marked test suite runs in an environment that can import the blocks, and
checks the committed file still matches them, so a stale catalogue fails there.
"""

import json
from importlib import resources

from blocks.registry import Catalogue


def library_catalogue() -> Catalogue:
    """The committed description of this library's blocks, importable anywhere."""
    raw = (resources.files(__package__) / "catalogue.json").read_text()
    return Catalogue.model_validate(json.loads(raw))

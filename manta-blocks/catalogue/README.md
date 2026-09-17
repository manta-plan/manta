<!--
SPDX-FileCopyrightText: 2026 Manta Blocks contributors

SPDX-License-Identifier: MIT
-->

# Block catalogue

`catalogue.json` is a **generated** description of every block in
`src/blocks/library/`: names, settings as JSON schema, dimensions, and the
environments they need. It exists so that things which cannot import the blocks -
Manta's backend has no PyPSA - can still list them, draw them, and validate playbook
settings against them (see `blocks/registry.py`).

It is committed rather than built on demand because generating it *requires* an
environment that can import the blocks. Regenerate it after changing anything a
block declares (settings, dims, inputs, docstring first line):

```bash
uv sync --extra pypsa
MANTA_ENV=pypsa uv run python -m blocks > catalogue/catalogue.json
```

The pypsa-marked test suite runs in the same environment, so a stale catalogue is a
review-time concern for now. Once this package moves to its own repository, CI should
regenerate the file and fail on a diff.

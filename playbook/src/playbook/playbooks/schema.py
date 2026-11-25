# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Write `playbook.schema.json`, the JSON schema of a playbook document, for editors.

uv run python -m playbook.playbooks.schema
"""

import json
from pathlib import Path

from playbook.playbooks.syntax import PlaybookDoc

SCHEMA_PATH = Path(__file__).with_name("playbook.schema.json")


def schema_text() -> str:
    """The JSON schema of a playbook document, as the committed file holds it."""
    return json.dumps(PlaybookDoc.model_json_schema(), indent=2) + "\n"


def main() -> None:
    SCHEMA_PATH.write_text(schema_text())


if __name__ == "__main__":
    main()

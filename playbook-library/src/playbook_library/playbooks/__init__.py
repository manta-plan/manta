# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""The playbooks that ship with this library, and how to find them.

A library playbook is a YAML document in this directory. Playbooks are looked up by
the name written inside the document, so what a user picks is what the document says
it is, not what a file happens to be called. The default of each input is the
playbook's default setting.

Reading a playbook from here does not import the blocks it names, so anything driving
Manta can list and offer them without a modelling environment.
"""

from importlib import resources

import yaml
from playbook.playbooks import PlaybookDoc, PlaybookLoadError, parse_doc


def library_playbooks() -> dict[str, PlaybookDoc]:
    """Every playbook document that ships in this library, by the name in it."""
    found: dict[str, PlaybookDoc] = {}
    for entry in sorted(resources.files(__package__).iterdir(), key=lambda e: e.name):
        if not entry.name.endswith(".yaml"):
            continue
        doc = parse_doc(yaml.safe_load(entry.read_text()), source=entry.name)
        if doc.name in found:
            raise PlaybookLoadError(f"two library playbooks both call themselves {doc.name!r}")
        found[doc.name] = doc
    return found

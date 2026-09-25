# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""The playbooks that ship with this library, and how to find them.

A library playbook is a YAML document in this directory, optionally with a default
settings document of the same filename under `configs/`. Playbooks are looked up by
the name written inside the document, so what a user picks is what the document says
it is, not what a file happens to be called.

Reading a playbook from here does not import the blocks it names, so anything driving
Manta can list and offer them without a modelling environment.
"""

from dataclasses import dataclass
from importlib import resources

import yaml
from playbook.playbooks.yaml_io import PlaybookDoc, PlaybookLoadError, parse_doc


@dataclass(frozen=True)
class LibraryPlaybook:
    """One playbook from the library: its document, and sensible default settings."""

    doc: PlaybookDoc
    default_config: dict


def library_playbooks() -> dict[str, LibraryPlaybook]:
    """Every playbook that ships in this library, by the name in its document."""
    found: dict[str, LibraryPlaybook] = {}
    root = resources.files(__package__)
    for entry in sorted(root.iterdir(), key=lambda e: e.name):
        if not entry.name.endswith(".yaml"):
            continue
        doc = parse_doc(yaml.safe_load(entry.read_text()), source=entry.name)
        if doc.name in found:
            raise PlaybookLoadError(f"two library playbooks both call themselves {doc.name!r}")
        found[doc.name] = LibraryPlaybook(doc=doc, default_config=_default_config(root, entry.name))
    return found


def _default_config(root, filename: str) -> dict:
    config_entry = root / "configs" / filename
    if not config_entry.is_file():
        return {}
    return yaml.safe_load(config_entry.read_text()) or {}

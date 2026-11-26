# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""The playbooks that ship with this library, and how to find them.

A library playbook is a YAML document in this directory, optionally with a document of
default settings of the same filename under `configs/`. The default settings are by
step id, in the shape that `apply_settings` takes. Playbooks are looked up by the name
written inside the document, so what a user picks is what the document says it is, not
what a file happens to be called. The default of each input is in the playbook itself.

Reading a playbook from here does not import the blocks it names, so anything driving
Manta can list and offer them without a modelling environment.
"""

from dataclasses import dataclass
from importlib import resources
from importlib.resources.abc import Traversable

import yaml
from playbook.playbooks import PlaybookDoc, PlaybookLoadError, parse_doc


@dataclass(frozen=True)
class LibraryPlaybook:
    """One playbook from the library: its document, and its default settings by step id."""

    doc: PlaybookDoc
    default_settings: dict[str, object]


def library_playbooks() -> dict[str, LibraryPlaybook]:
    """Return every playbook that ships in this library, by the name in its document.

    Raises:
        PlaybookLoadError: If a document is not a playbook, two documents have the
            same name, or a document of default settings is not a mapping.
    """
    found: dict[str, LibraryPlaybook] = {}
    root = resources.files(__package__)
    for entry in sorted(root.iterdir(), key=lambda e: e.name):
        if not entry.name.endswith(".yaml"):
            continue
        doc = parse_doc(yaml.safe_load(entry.read_text()), source=entry.name)
        if doc.name in found:
            raise PlaybookLoadError(f"two library playbooks both call themselves {doc.name!r}")
        found[doc.name] = LibraryPlaybook(doc=doc, default_settings=_default_settings(root, entry))
    return found


def _default_settings(root: Traversable, entry: Traversable) -> dict[str, object]:
    settings = root / "configs" / entry.name
    if not settings.is_file():
        return {}
    loaded = yaml.safe_load(settings.read_text())
    if not isinstance(loaded, dict):
        raise PlaybookLoadError(
            f"configs/{entry.name}: the default settings are a mapping of step id to "
            f"settings, not {loaded!r}. Write them as a mapping"
        )
    return loaded

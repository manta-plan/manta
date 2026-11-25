# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""The playbooks kept as fixtures, and a loader finding them by name."""

from pathlib import Path

import yaml

from playbook.playbooks.syntax import PlaybookDoc
from playbook.playbooks.yaml_io import LoadedPlaybook, PlaybookLoadError

FIXTURES = Path(__file__).parent / "fixtures"
SPEC_PLAYBOOKS = ["capacity_expansion", "expand_and_dispatch"]


def spec_raw(name: str) -> dict:
    return yaml.safe_load((FIXTURES / f"{name}.yaml").read_text())


def spec_doc(name: str) -> PlaybookDoc:
    return PlaybookDoc.model_validate(spec_raw(name))


class InMemoryPlaybookLoader:
    """A loader backed by a dict of documents, touching no files at all."""

    def __init__(self, docs: dict[str, PlaybookDoc]) -> None:
        self._docs = docs

    def load(self, locator: str) -> LoadedPlaybook:
        if locator not in self._docs:
            raise PlaybookLoadError(f"no playbook stored under {locator!r}")
        return LoadedPlaybook(key=locator, doc=self._docs[locator], loader=self)


SPEC_LOADER = InMemoryPlaybookLoader({name: spec_doc(name) for name in SPEC_PLAYBOOKS})
"""Finds a fixture playbook by its name, as `expand_and_dispatch` nests `capacity_expansion`."""

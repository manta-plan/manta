# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""The fixture playbooks, and a loader that finds them by name."""

from pathlib import Path

import yaml

from playbook.playbooks.syntax import PlaybookDoc
from playbook.playbooks.yaml_io import LoadedPlaybook, PlaybookLoadError

FIXTURES = Path(__file__).parent / "fixtures"
SPEC_PLAYBOOKS = ["capacity_expansion", "expand_and_dispatch"]
SPEC_REQUIRED_INPUTS = {
    "capacity_expansion": {},
    "expand_and_dispatch": {"dispatch_resolution": "1w"},
}
"""A value for each required input of each fixture playbook."""


def spec_raw(name: str) -> dict:
    return yaml.safe_load((FIXTURES / f"{name}.yaml").read_text())


def spec_doc(name: str) -> PlaybookDoc:
    return PlaybookDoc.model_validate(spec_raw(name))


class InMemoryPlaybookLoader:
    """A loader that reads from a dict of documents, and from no file."""

    def __init__(self, docs: dict[str, PlaybookDoc]) -> None:
        self._docs = docs

    def load(self, locator: str) -> LoadedPlaybook:
        if locator not in self._docs:
            raise PlaybookLoadError(f"no playbook stored under {locator!r}")
        return LoadedPlaybook(key=locator, doc=self._docs[locator], loader=self)


SPEC_LOADER = InMemoryPlaybookLoader({name: spec_doc(name) for name in SPEC_PLAYBOOKS})
"""A loader that finds a fixture playbook by its name, as `expand_and_dispatch` requires."""

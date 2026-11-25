# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Fixtures shared by the tests that run real blocks.

Each test gets one datarecord workspace, closed when it ends, and every revision it
reads or writes is opened on it.
"""

from collections.abc import Callable, Iterator
from contextlib import closing
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from playbook.playbooks import Playbook, PlaybookDoc, playbook_from_doc

from playbook_library.playbooks import library_playbooks

if TYPE_CHECKING:
    from datarecord import Revision, Workspace


@pytest.fixture
def workspace() -> Iterator["Workspace"]:
    from datarecord import Workspace

    with closing(Workspace()) as ws:
        yield ws


@pytest.fixture
def store_revision(tmp_path: Path, workspace: "Workspace") -> Callable[..., "Revision"]:
    """Write a network as the root revision of a new store, named `name`, under tmp_path."""
    from playbook_library.pypsa_helpers import store_network

    def write(n, name: str) -> "Revision":
        return store_network(n, workspace.store(str(tmp_path / name)))

    return write


@pytest.fixture
def tuned_playbook() -> Callable[..., Playbook]:
    """Build a library playbook with the settings of some steps replaced.

    It takes the playbook's name, then the settings of each step to replace, by step id
    and setting name. Everything else is as the library ships it.
    """

    def tune(name: str, settings: dict[str, dict]) -> Playbook:
        raw = library_playbooks()[name].model_dump(by_alias=True, exclude_unset=True)
        for step in raw["steps"]:
            step["with"] = {**step.get("with", {}), **settings.get(step["id"], {})}
        return playbook_from_doc(PlaybookDoc.model_validate(raw))

    return tune

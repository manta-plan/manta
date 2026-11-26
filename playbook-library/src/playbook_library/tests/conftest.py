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
from playbook.playbooks import Playbook, apply_settings, playbook_from_doc

from playbook_library import library_catalogue
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
    """Build a library playbook with its default settings, some of them replaced.

    The fixture takes the name of the playbook, then the settings to replace, by step id
    and setting name. Every other setting is as the library ships it. A block that
    cannot be imported is known from the committed catalogue.
    """

    def tune(name: str, settings: dict[str, dict] | None = None) -> Playbook:
        shipped = library_playbooks()[name]
        defaults = shipped.default_settings
        replaced = {
            step: {**defaults.get(step, {}), **value} for step, value in (settings or {}).items()
        }
        playbook = playbook_from_doc(shipped.doc, catalogue=library_catalogue())
        return apply_settings(playbook, {**defaults, **replaced})

    return tune

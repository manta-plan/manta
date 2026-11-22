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

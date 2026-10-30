# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Fixtures shared by the tests that run real blocks."""

from collections.abc import Callable
from pathlib import Path
from uuid import UUID

import pytest
from playbook.blocks.core import DataRecord


@pytest.fixture
def store_record(tmp_path: Path) -> Callable:
    """Write a network as the root revision of a new store, named `name`, under tmp_path."""
    from playbook_library.pypsa_helpers import store_network

    def write(n, name: str) -> DataRecord:
        return store_network(n, str(tmp_path / name))

    return write


@pytest.fixture
def ancestry() -> Callable[[DataRecord], list[UUID]]:
    """The revision ids from a record's store root down to the record, root first."""
    from datarecord import Workspace

    def lineage(record: DataRecord) -> list[UUID]:
        revision = Workspace().store(record.url).revision(record.uuid)
        return revision.ancestry()

    return lineage

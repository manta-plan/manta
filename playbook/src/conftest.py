# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Fixtures shared by the tests for both packages."""

from pathlib import Path

import pytest

from playbook.blocks.core import RevisionRef
from playbook.blocks.tests.fakes import commit_root


@pytest.fixture
def initial_revision(tmp_path: Path) -> RevisionRef:
    return commit_root(str(tmp_path / "store"))

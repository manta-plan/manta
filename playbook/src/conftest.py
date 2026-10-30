# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Fixtures shared by the tests for both packages."""

import pytest

from playbook.blocks.core import DataRecord
from playbook.blocks.tests.fakes import RECORD_UUID


@pytest.fixture
def initial_record() -> DataRecord:
    return DataRecord(url="root", uuid=RECORD_UUID)

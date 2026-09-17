# SPDX-FileCopyrightText: 2026 Manta Blocks contributors
#
# SPDX-License-Identifier: MIT

"""Fixtures shared by the tests for both packages."""

import pytest

from blocks.core import DataRecord


@pytest.fixture
def initial_record() -> DataRecord:
    return DataRecord(url="root")

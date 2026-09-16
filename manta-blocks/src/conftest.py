# SPDX-FileCopyrightText: 2026 Manta Blocks contributors
#
# SPDX-License-Identifier: MIT

"""Fixtures shared by the tests for both packages."""

import pytest
from prefect.testing.utilities import prefect_test_harness

from manta_blocks.core import DataRecord


@pytest.fixture(scope="session", autouse=True)
def _prefect_test_mode():
    """Run every test against a throwaway Prefect database."""
    with prefect_test_harness():
        yield


@pytest.fixture
def initial_record() -> DataRecord:
    return DataRecord(url="root")

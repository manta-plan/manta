# SPDX-FileCopyrightText: 2026 Manta Blocks contributors
#
# SPDX-License-Identifier: MIT

"""Fixtures shared by this library's tests."""

import pytest
from prefect.testing.utilities import prefect_test_harness


@pytest.fixture(scope="session", autouse=True)
def _prefect_test_mode():
    """Run every test against a throwaway Prefect database."""
    with prefect_test_harness():
        yield

# SPDX-FileCopyrightText: 2026 Manta Blocks contributors
#
# SPDX-License-Identifier: MIT

"""The committed catalogue of the library's blocks.

The file exists so that environments which cannot import the blocks (Manta's
backend) can still describe and validate them, so most checks here run without
PyPSA. The freshness check - does the file still match what the blocks actually
declare - can only run where the blocks import, so it carries the pypsa marker.
"""

import pytest

from blocks.library import library_catalogue
from blocks.registry import _LAZY


def test_the_committed_catalogue_loads_without_pypsa():
    catalogue = library_catalogue()
    assert set(catalogue.blocks) == set(_LAZY)


def test_the_committed_catalogue_carries_enough_to_validate_settings():
    for name, description in library_catalogue().blocks.items():
        assert description.env, name
        assert "properties" in description.config_schema, name


@pytest.mark.pypsa
def test_the_committed_catalogue_is_not_stale():
    # Regenerate with:
    #   MANTA_ENV=pypsa uv run python -m blocks > src/blocks/library/catalogue.json
    from blocks.registry import catalogue

    # Other tests register fake blocks in this process, so compare only the
    # library's own entries.
    fresh = {name: entry for name, entry in catalogue().blocks.items() if name in _LAZY}
    assert library_catalogue().blocks == fresh

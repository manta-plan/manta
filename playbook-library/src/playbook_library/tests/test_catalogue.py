# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""The committed catalogue of this library's blocks.

The file exists so that environments which cannot import the blocks - Manta's
backend, anything driving a playbook from outside - can still describe them and check
how a playbook wires them up. So most checks here run without PyPSA. The freshness
check - does the file still match what the blocks actually declare - can only run
where the blocks import, so it carries the pypsa marker.
"""

import pytest
from playbook.blocks import available_blocks

from playbook_library import library_catalogue


def library_block_names() -> set[str]:
    """The blocks this library registered, told apart from any others in the process."""
    return {
        name
        for name, locator in available_blocks().items()
        if locator.startswith("playbook_library.")
    }


def test_the_committed_catalogue_describes_exactly_the_registered_blocks():
    assert set(library_catalogue().blocks) == library_block_names()


def test_the_committed_catalogue_loads_without_pypsa():
    # Nothing in this module imports PyPSA, and the catalogue still reads.
    assert library_catalogue().blocks["cluster_time"].env == "pypsa"


def test_the_committed_catalogue_carries_enough_to_offer_a_blocks_settings():
    for name, description in library_catalogue().blocks.items():
        assert description.env, name
        assert "properties" in description.config_schema, name


def test_the_committed_catalogue_records_which_settings_are_wired_up():
    dispatch = library_catalogue().blocks["rolling_horizon_dispatch"]
    assert dispatch.inputs == frozenset({"capacity_source"})


@pytest.mark.pypsa
def test_the_committed_catalogue_is_not_stale():
    # Regenerate with: pixi run -e pypsa catalogue
    pytest.importorskip("pypsa", reason="describing the blocks means importing them")

    from playbook.blocks import catalogue

    names = library_block_names()
    fresh = {name: entry for name, entry in catalogue().blocks.items() if name in names}
    assert library_catalogue().blocks == fresh

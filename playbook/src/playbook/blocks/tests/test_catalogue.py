# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

import json

import pytest

from playbook.blocks import registry
from playbook.blocks.registry import (
    CATALOGUE_VERSION,
    INPUT_MARKER,
    BlockDescription,
    BlockRegistrationError,
    Catalogue,
    catalogue,
    merge_catalogues,
)
from playbook.blocks.tests.fakes import FakeNeedsUpstream


def test_catalogue_works_without_the_environments_it_describes():
    # PyPSA is not installed here, so the blocks that need it are left out rather
    # than causing an error. That is the whole point of describing blocks per
    # environment and merging afterwards.
    data = catalogue().model_dump(mode="json")
    json.dumps(data)  # raises if anything is not plain data
    assert "fake_passthrough" in data["blocks"]
    assert data["catalogue_version"] == CATALOGUE_VERSION


def test_catalogue_describes_a_block_fully_enough_to_draw_and_configure_it():
    entry = catalogue().blocks["fake_needs_upstream"]
    assert entry.name == "fake_needs_upstream"
    assert entry.env == "default"
    assert entry.module.endswith(":FakeNeedsUpstream")
    assert entry.inputs == frozenset({"source"})
    assert "properties" in entry.config_schema


def test_catalogue_marks_settings_that_another_block_fills_in():
    entry = catalogue().blocks["fake_needs_upstream"]
    properties = entry.config_schema["properties"]
    assert properties["source"][INPUT_MARKER] is True
    # A setting the user fills in themselves carries no such mark.
    assert INPUT_MARKER not in properties["label"]


def test_catalogue_records_the_environments_its_blocks_need():
    assert "default" in catalogue().environments


def test_catalogue_json_is_stable_between_runs():
    first = json.dumps(catalogue().model_dump(mode="json"), sort_keys=True)
    second = json.dumps(catalogue().model_dump(mode="json"), sort_keys=True)
    assert first == second


def test_merge_combines_catalogues_from_different_environments():
    here = catalogue()
    elsewhere = Catalogue(
        blocks={
            "far_away": BlockDescription(name="far_away", env="solver", module="somewhere:FarAway")
        }
    )
    merged = merge_catalogues([here, elsewhere])
    assert "fake_passthrough" in merged.blocks
    assert "far_away" in merged.blocks


def test_merge_accepts_the_same_block_described_the_same_way_twice():
    once = catalogue()
    merged = merge_catalogues([once, once])
    assert merged.blocks == once.blocks


def test_merge_rejects_two_different_blocks_under_one_name():
    mine = Catalogue(
        blocks={"shared": BlockDescription(name="shared", env="a", module="one:Shared")}
    )
    theirs = Catalogue(
        blocks={"shared": BlockDescription(name="shared", env="a", module="two:Shared")}
    )
    with pytest.raises(BlockRegistrationError, match="shared"):
        merge_catalogues([mine, theirs])


def test_a_described_block_can_be_used_without_being_importable():
    entry = BlockDescription(name="far_away", env="solver", module="somewhere:FarAway")
    spec = merge_catalogues([Catalogue(blocks={"far_away": entry})]).blocks["far_away"]
    assert spec.env == "solver"


def test_a_block_that_cannot_be_imported_here_is_left_out(monkeypatch):
    # A block belonging to another environment cannot be described here, so it is
    # left for a catalogue made where it can be, rather than being an error.
    monkeypatch.setitem(registry._LAZY, "needs_another_env", "not_installed_anywhere:Block")
    blocks = catalogue().blocks

    assert "needs_another_env" not in blocks
    # The blocks that can be imported are still described.
    assert "fake_needs_upstream" in blocks


def test_a_block_that_can_be_imported_here_is_described_from_the_real_class():
    entry = catalogue().blocks["fake_needs_upstream"]
    assert entry.module.endswith(FakeNeedsUpstream.__qualname__)

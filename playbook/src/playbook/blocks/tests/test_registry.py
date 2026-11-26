# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

import pytest

from playbook.blocks.registry import (
    BlockDescription,
    BlockNotRegisteredError,
    BlockRegistrationError,
    BlockUnavailableError,
    Catalogue,
    available_blocks,
    block_name,
    describe_block,
    get_block,
    load_block_sources,
    register,
    register_lazy,
    resolve_block,
)
from playbook.blocks.tests.fakes import FakeBlock, FakePassthrough


def test_get_block_resolves_registered_name():
    assert get_block("fake_passthrough") is FakePassthrough


def test_get_block_raises_on_unknown_name():
    with pytest.raises(BlockNotRegisteredError):
        get_block("does_not_exist")


def test_available_blocks_lists_registered_and_lazy_entries():
    register_lazy("fake_lazy_listed", "nowhere_in_particular:Block")
    blocks = available_blocks()

    assert "fake_passthrough" in blocks  # registered by importing its class
    assert blocks["fake_lazy_listed"] == "nowhere_in_particular:Block"


# --- How a block library announces its blocks ---


def test_a_lazily_registered_block_is_known_without_being_imported():
    # This is the whole contract between the framework and a block library: the name
    # is known everywhere, while the import happens only where the block runs.
    register_lazy("fake_lazy", "playbook.blocks.tests.fakes:FakePassthrough")
    assert "fake_lazy" in available_blocks()
    assert get_block("fake_lazy") is FakePassthrough


def test_registering_the_same_block_twice_is_harmless():
    # A library module is imported freely, so its registrations must not depend on
    # being run exactly once.
    register_lazy("fake_lazy_twice", "playbook.blocks.tests.fakes:FakePassthrough")
    register_lazy("fake_lazy_twice", "playbook.blocks.tests.fakes:FakePassthrough")
    assert get_block("fake_lazy_twice") is FakePassthrough


def test_two_libraries_cannot_claim_one_name():
    register_lazy("fake_lazy_contested", "one:Block")
    with pytest.raises(BlockRegistrationError, match="fake_lazy_contested"):
        register_lazy("fake_lazy_contested", "another:Block")


def test_a_block_whose_environment_is_missing_says_so_when_asked_for():
    register_lazy("fake_lazy_elsewhere", "not_installed_anywhere:Block")
    with pytest.raises(BlockUnavailableError, match="environment"):
        get_block("fake_lazy_elsewhere")


def test_block_sources_are_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("MANTA_BLOCK_SOURCES", "playbook.blocks.tests.fakes")
    assert load_block_sources() == ["playbook.blocks.tests.fakes"]


def test_no_block_sources_configured_is_not_an_error(monkeypatch):
    monkeypatch.delenv("MANTA_BLOCK_SOURCES", raising=False)
    assert load_block_sources() == []


def test_register_rejects_duplicate_name():
    with pytest.raises(BlockRegistrationError):

        @register("fake_passthrough")
        class Dup(FakeBlock):
            pass


def test_block_name_finds_the_registered_name():
    assert block_name(FakePassthrough) == "fake_passthrough"


def test_block_name_refuses_to_guess_for_an_unregistered_block():
    class NeverRegistered(FakeBlock):
        pass

    # Guessing here would produce a name that nothing could look up, and the mistake
    # would only surface once something tried to run the block.
    with pytest.raises(BlockNotRegisteredError, match="register"):
        block_name(NeverRegistered)


def test_describe_block_reads_what_the_block_declares():
    spec = describe_block(FakePassthrough)
    assert spec.name == "fake_passthrough"
    assert spec.env == "default"
    assert spec.available
    assert spec.block_class() is FakePassthrough


def test_resolve_block_by_name_gives_a_usable_block():
    spec = resolve_block("fake_passthrough")
    assert spec.block_class() is FakePassthrough


def test_resolve_block_falls_back_to_the_catalogue_for_a_name_nothing_has_registered():
    # A process that never imports any block library (an orchestrator resolving
    # blocks purely from a catalogue passed to it) hits BlockNotRegisteredError, not
    # BlockUnavailableError, for every block it resolves — the catalogue must still
    # cover it.
    catalogue = Catalogue(
        blocks={
            "fake_never_registered_here": BlockDescription(
                name="fake_never_registered_here", env="solver", module="somewhere:FarAway"
            )
        }
    )
    spec = resolve_block("fake_never_registered_here", catalogue)
    assert spec.env == "solver"
    assert not spec.available


def test_resolve_block_raises_when_neither_registered_nor_in_the_catalogue():
    with pytest.raises(BlockNotRegisteredError):
        resolve_block("fake_never_registered_here", Catalogue())

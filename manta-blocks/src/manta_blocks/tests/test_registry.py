# SPDX-FileCopyrightText: 2026 Manta Blocks contributors
#
# SPDX-License-Identifier: MIT

import pytest

from manta_blocks.core import BlockDims, ConfigSchema, DataRecord, MantaBlock
from manta_blocks.registry import (
    BlockNotFoundError,
    BlockRegistrationError,
    BlockUnavailableError,
    available_blocks,
    block_name,
    describe_block,
    get_block,
    load_block_sources,
    register,
    register_lazy,
    resolve_block,
)
from manta_blocks.tests.fakes import FakeBlock, FakeNeedsUpstream, FakePassthrough


def test_get_block_resolves_registered_name():
    assert get_block("fake_passthrough") is FakePassthrough


def test_get_block_raises_on_unknown_name():
    with pytest.raises(BlockNotFoundError):
        get_block("does_not_exist")


def test_available_blocks_lists_registered_and_lazy_entries():
    register_lazy("listed_but_never_imported", "nowhere.at_all:Listed")

    blocks = available_blocks()

    assert "fake_passthrough" in blocks
    assert "listed_but_never_imported" in blocks


def test_register_rejects_duplicate_name():
    with pytest.raises(BlockRegistrationError):

        @register("fake_passthrough")
        class Dup(FakeBlock):
            pass


def test_register_lazy_tolerates_the_same_registration_twice():
    # A library module calls register_lazy at import time, and imports can happen
    # more than once across test runs and tools; the exact same claim is harmless.
    register_lazy("lazy_twice", "somewhere.lazy:Twice")
    register_lazy("lazy_twice", "somewhere.lazy:Twice")

    assert available_blocks()["lazy_twice"] == "somewhere.lazy:Twice"


def test_register_lazy_rejects_a_name_claimed_for_another_block():
    register_lazy("lazy_contested", "somewhere.lazy:First")

    with pytest.raises(BlockRegistrationError, match="lazy_contested"):
        register_lazy("lazy_contested", "somewhere.lazy:Second")


def test_a_lazy_block_whose_environment_is_missing_reports_it_as_unavailable():
    register_lazy("lazy_unimportable", "not_installed_here.module:Block")

    with pytest.raises(BlockUnavailableError):
        get_block("lazy_unimportable")


def test_load_block_sources_reads_the_environment_variable(monkeypatch):
    # The fakes module is a stand-in for a block library: importing it is what
    # registers its blocks.
    monkeypatch.setenv("MANTA_BLOCK_SOURCES", "manta_blocks.tests.fakes")

    assert load_block_sources() == ["manta_blocks.tests.fakes"]


def test_load_block_sources_does_nothing_when_nothing_is_configured(monkeypatch):
    monkeypatch.delenv("MANTA_BLOCK_SOURCES", raising=False)

    assert load_block_sources() == []


def test_block_name_finds_the_registered_name():
    assert block_name(FakePassthrough) == "fake_passthrough"


def test_block_name_refuses_to_guess_for_an_unregistered_block():
    class NeverRegistered(FakeBlock):
        pass

    # Guessing here would produce a name that nothing could look up, and the mistake
    # would only surface once a deployment tried to run.
    with pytest.raises(BlockNotFoundError, match="register"):
        block_name(NeverRegistered)


def test_describe_block_reads_what_the_block_declares():
    spec = describe_block(FakeNeedsUpstream)
    assert spec.name == "fake_needs_upstream"
    assert spec.env == "default"
    assert spec.inputs == frozenset({"source"})
    assert spec.outputs == frozenset({"output"})
    assert spec.available
    assert spec.block_class() is FakeNeedsUpstream


def test_resolve_block_by_name_gives_a_usable_block():
    spec = resolve_block("fake_passthrough")
    assert spec.block_class() is FakePassthrough


class NotADataRecordConfig(ConfigSchema):
    source: int = 0


def test_a_block_cannot_wire_an_input_to_a_setting_that_has_no_such_name():
    with pytest.raises(Exception, match="INPUTS"):

        class Broken(MantaBlock[NotADataRecordConfig]):
            ENV = "default"
            CONFIG = NotADataRecordConfig
            DIMS = BlockDims()
            INPUTS = frozenset({"missing"})

            def flow(self, record: DataRecord) -> DataRecord:
                return record


def test_a_block_cannot_wire_an_input_to_a_setting_that_cannot_hold_a_record():
    with pytest.raises(Exception, match="DataRecord"):

        class Broken(MantaBlock[NotADataRecordConfig]):
            ENV = "default"
            CONFIG = NotADataRecordConfig
            DIMS = BlockDims()
            INPUTS = frozenset({"source"})

            def flow(self, record: DataRecord) -> DataRecord:
                return record


class RequiredRecordConfig(ConfigSchema):
    source: DataRecord


def test_a_wired_setting_has_to_have_a_default():
    with pytest.raises(Exception, match="default"):

        class Broken(MantaBlock[RequiredRecordConfig]):
            ENV = "default"
            CONFIG = RequiredRecordConfig
            DIMS = BlockDims()
            INPUTS = frozenset({"source"})

            def flow(self, record: DataRecord) -> DataRecord:
                return record

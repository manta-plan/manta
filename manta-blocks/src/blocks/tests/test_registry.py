# SPDX-FileCopyrightText: 2026 Manta Blocks contributors
#
# SPDX-License-Identifier: MIT

import pytest

from blocks.core import BlockDims, ConfigSchema, DataRecord, MantaBlock
from blocks.registry import (
    BlockNotFoundError,
    BlockRegistrationError,
    available_blocks,
    block_name,
    describe_block,
    get_block,
    register,
    resolve_block,
)
from blocks.tests.fakes import FakeBlock, FakeNeedsUpstream, FakePassthrough


def test_get_block_resolves_registered_name():
    assert get_block("fake_passthrough") is FakePassthrough


def test_get_block_raises_on_unknown_name():
    with pytest.raises(BlockNotFoundError):
        get_block("does_not_exist")


def test_available_blocks_lists_registered_and_lazy_entries():
    blocks = available_blocks()
    assert "fake_passthrough" in blocks
    assert "cluster_time" in blocks  # one of the blocks that ships with Manta


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

            def run(self, record: DataRecord, output_base: str) -> DataRecord:
                return record


def test_a_block_cannot_wire_an_input_to_a_setting_that_cannot_hold_a_record():
    with pytest.raises(Exception, match="DataRecord"):

        class Broken(MantaBlock[NotADataRecordConfig]):
            ENV = "default"
            CONFIG = NotADataRecordConfig
            DIMS = BlockDims()
            INPUTS = frozenset({"source"})

            def run(self, record: DataRecord, output_base: str) -> DataRecord:
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

            def run(self, record: DataRecord, output_base: str) -> DataRecord:
                return record

# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

import pytest
from pydantic import ValidationError, computed_field

from playbook.blocks.core import ConfigSchema, DataRecord, MantaBlock
from playbook.blocks.tests.fakes import FakeNeedsUpstream, FakePassthrough, FakeWritesOutput
from playbook.playbooks.playbook import Playbook, When


def test_a_wired_input_is_separate_from_the_record_handed_along(initial_record):
    pb = Playbook(name="exec-wiring")
    cluster = pb.add("cluster", FakePassthrough)
    pb.add("expand", FakePassthrough)
    pb.add("dispatch", FakeNeedsUpstream, inputs={"source": cluster.output})

    config = {
        "cluster": {"label": "cluster"},
        "expand": {"label": "expand"},
        "dispatch": {},
    }
    result = pb.run(initial_record, config, output_prefix="out")

    # `dispatch` gets the record from `expand` as usual, and separately the result of
    # `cluster` specifically, from before `expand` ran.
    assert result.url == "root+cluster+expand+needs(root+cluster)"


def test_only_the_matching_branch_runs(initial_record):
    pb = Playbook(name="exec-cond")
    pb.add("branch_a", FakePassthrough, when=When(config="globals.mode", equals="a"))
    pb.add("branch_b", FakePassthrough, when=When(config="globals.mode", equals="b"))

    config = {
        "globals": {"mode": "a"},
        "branch_a": {"label": "A"},
        "branch_b": {"label": "B"},
    }
    assert pb.run(initial_record, config, output_prefix="out").url == "root+A"

    config["globals"]["mode"] = "b"
    assert pb.run(initial_record, config, output_prefix="out").url == "root+B"


def test_a_step_that_does_not_run_passes_the_record_straight_on(initial_record):
    pb = Playbook(name="exec-skip")
    pb.add("maybe", FakePassthrough, when=When(config="globals.mode", equals="on"))

    result = pb.run(initial_record, {"globals": {"mode": "off"}}, output_prefix="out")
    assert result.url == "root"


def test_the_same_playbook_can_be_run_more_than_once(initial_record):
    # A block is built fresh each time it runs, so no run can be affected by an
    # earlier one.
    pb = Playbook(name="exec-reuse")
    pb.add("a", FakePassthrough)

    config = {"a": {"label": "a"}}
    assert pb.run(initial_record, config, output_prefix="out").url == "root+a"
    assert pb.run(initial_record, config, output_prefix="out").url == "root+a"


def test_each_step_is_told_to_write_under_the_run_prefix_by_its_own_name(
    initial_record,
):
    pb = Playbook(name="exec-outputs")
    pb.add("first", FakeWritesOutput)

    result = pb.run(initial_record, {"first": {}}, output_prefix="s3://bucket/run-1")
    assert result.url == "s3://bucket/run-1/first.txt"


def test_a_wired_input_is_checked_against_the_setting_it_goes_into():
    # `label` is text, so a record wired into it cannot work. It is checked, rather
    # than quietly leaving a record where text was expected.
    with pytest.raises(ValidationError, match="label"):
        FakeNeedsUpstream.merge_config({}, {"label": DataRecord(url="somewhere")})


def test_a_wired_input_reaches_the_setting_it_is_meant_for():
    config = FakeNeedsUpstream.merge_config({}, {"source": DataRecord(url="upstream")})
    assert config.source.url == "upstream"


class _DerivedSettingConfig(ConfigSchema):
    size: int = 1

    @computed_field
    def doubled(self) -> int:
        return self.size * 2


class _DerivedSettingBlock(MantaBlock[_DerivedSettingConfig]):
    ENV = "default"
    CONFIG = _DerivedSettingConfig

    def run(self, record: DataRecord, output_base: str) -> DataRecord:
        return record


def test_settings_given_as_an_object_can_be_merged_again():
    # A computed value is part of the settings object, but is not a setting: merging
    # must not hand it back in, where it would be refused as unknown.
    config = _DerivedSettingBlock.merge_config(_DerivedSettingConfig(size=3), {})
    assert config.size == 3


def test_settings_reach_the_block_that_needs_them(initial_record):
    pb = Playbook(name="exec-config")
    pb.add("first", FakePassthrough)
    pb.add("second", FakePassthrough)

    result = pb.run(
        initial_record,
        {"first": {"label": "one"}, "second": {"label": "two"}},
        output_prefix="out",
    )
    assert result.url == "root+one+two"

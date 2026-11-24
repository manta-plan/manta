# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

from uuid import UUID

import pytest
from datarecord import Revision
from pydantic import ValidationError, computed_field

from playbook.blocks.core import ConfigSchema, MantaBlock, RevisionRef
from playbook.blocks.tests.fakes import FakeNeedsUpstream, FakePassthrough, steps
from playbook.playbooks.playbook import Playbook, When

UPSTREAM = RevisionRef(store="s3://bucket/upstream", id=UUID(int=0))


def test_a_wired_input_is_separate_from_the_revision_handed_along(initial_revision):
    pb = Playbook(name="exec-wiring")
    cluster = pb.add("cluster", FakePassthrough)
    pb.add("expand", FakePassthrough)
    pb.add("dispatch", FakeNeedsUpstream, inputs={"source": cluster.output})

    config = {
        "cluster": {"label": "cluster"},
        "expand": {"label": "expand"},
        "dispatch": {},
    }
    result = pb.run(initial_revision, config)

    # `dispatch` gets the revision from `expand` as usual, and separately the result
    # of `cluster` specifically, from before `expand` ran.
    assert steps(result) == ["cluster", "expand", "needs(cluster)"]


def test_only_the_matching_branch_runs(initial_revision):
    pb = Playbook(name="exec-cond")
    pb.add("branch_a", FakePassthrough, when=When(config="globals.mode", equals="a"))
    pb.add("branch_b", FakePassthrough, when=When(config="globals.mode", equals="b"))

    config = {
        "globals": {"mode": "a"},
        "branch_a": {"label": "A"},
        "branch_b": {"label": "B"},
    }
    assert steps(pb.run(initial_revision, config)) == ["A"]

    config["globals"]["mode"] = "b"
    assert steps(pb.run(initial_revision, config)) == ["B"]


def test_a_step_that_does_not_run_passes_the_revision_straight_on(initial_revision):
    pb = Playbook(name="exec-skip")
    pb.add("maybe", FakePassthrough, when=When(config="globals.mode", equals="on"))

    assert pb.run(initial_revision, {"globals": {"mode": "off"}}) == initial_revision


def test_the_same_playbook_can_be_run_more_than_once(initial_revision):
    # A block is built fresh each time it runs, so no run can be affected by an
    # earlier one.
    pb = Playbook(name="exec-reuse")
    pb.add("a", FakePassthrough)

    config = {"a": {"label": "a"}}
    first, second = (pb.run(initial_revision, config) for _ in range(2))
    assert steps(first) == steps(second) == ["a"]
    assert first != second


def test_a_steps_result_is_a_new_revision_in_its_inputs_store(initial_revision):
    pb = Playbook(name="exec-outputs")
    pb.add("first", FakePassthrough)

    result = pb.run(initial_revision, {"first": {}})
    assert result.store == initial_revision.store
    assert result.id != initial_revision.id


def test_a_wired_input_is_checked_against_the_setting_it_goes_into():
    # `label` is text, so a revision wired into it cannot work. It is checked, rather
    # than quietly leaving a revision where text was expected.
    with pytest.raises(ValidationError, match="label"):
        FakeNeedsUpstream.merge_config({}, {"label": UPSTREAM})


def test_a_wired_input_reaches_the_setting_it_is_meant_for():
    assert FakeNeedsUpstream.merge_config({}, {"source": UPSTREAM}).source == UPSTREAM


class _DerivedSettingConfig(ConfigSchema):
    size: int = 1

    @computed_field
    def doubled(self) -> int:
        return self.size * 2


class _DerivedSettingBlock(MantaBlock[_DerivedSettingConfig]):
    ENV = "default"
    CONFIG = _DerivedSettingConfig

    def run(self, base: Revision) -> Revision:
        return base


def test_settings_given_as_an_object_can_be_merged_again():
    # A computed value is part of the settings object, but is not a setting: merging
    # must not hand it back in, where it would be refused as unknown.
    config = _DerivedSettingBlock.merge_config(_DerivedSettingConfig(size=3), {})
    assert config.size == 3


def test_settings_reach_the_block_that_needs_them(initial_revision):
    pb = Playbook(name="exec-config")
    pb.add("first", FakePassthrough)
    pb.add("second", FakePassthrough)

    result = pb.run(
        initial_revision,
        {"first": {"label": "one"}, "second": {"label": "two"}},
    )
    assert steps(result) == ["one", "two"]

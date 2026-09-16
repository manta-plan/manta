# SPDX-FileCopyrightText: 2026 Manta Blocks contributors
#
# SPDX-License-Identifier: MIT

import pytest
from pydantic import ValidationError

from manta_blocks.core import DataRecord
from manta_blocks.tests.fakes import FakeNeedsUpstream, FakePassthrough
from manta_playbooks.playbook import Playbook, When

pytestmark = pytest.mark.slow


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
    result = pb.run(initial_record, config)

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
    assert pb.run(initial_record, config).url == "root+A"

    config["globals"]["mode"] = "b"
    assert pb.run(initial_record, config).url == "root+B"


def test_a_step_that_does_not_run_passes_the_record_straight_on(initial_record):
    pb = Playbook(name="exec-skip")
    pb.add("maybe", FakePassthrough, when=When(config="globals.mode", equals="on"))

    assert pb.run(initial_record, {"globals": {"mode": "off"}}).url == "root"


def test_the_same_flow_can_be_run_more_than_once(initial_record):
    # A block is built fresh each time it runs, so one flow is reusable and no run
    # can be affected by an earlier one.
    pb = Playbook(name="exec-reuse")
    pb.add("a", FakePassthrough)

    flow = pb.to_flow({"a": {"label": "a"}})
    assert flow(initial_record).url == "root+a"
    assert flow(initial_record).url == "root+a"


def test_a_wired_input_is_checked_against_the_setting_it_goes_into():
    # `label` is text, so a record wired into it cannot work. It is checked, rather
    # than quietly leaving a record where text was expected.
    with pytest.raises(ValidationError, match="label"):
        FakeNeedsUpstream.merge_config({}, {"label": DataRecord(url="somewhere")})


def test_a_wired_input_reaches_the_setting_it_is_meant_for():
    config = FakeNeedsUpstream.merge_config({}, {"source": DataRecord(url="upstream")})
    assert config.source.url == "upstream"


def test_settings_reach_the_block_that_needs_them(initial_record):
    pb = Playbook(name="exec-config")
    pb.add("first", FakePassthrough)
    pb.add("second", FakePassthrough)

    result = pb.run(
        initial_record, {"first": {"label": "one"}, "second": {"label": "two"}}
    )
    assert result.url == "root+one+two"

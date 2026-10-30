# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""A playbook used as a single step inside a longer one.

The inner playbook keeps its own settings and its own step names; what it does not
wire up itself is offered to the outer playbook to feed, exactly like a block's own
inputs.
"""

import pytest
from pydantic import ValidationError

from playbook.blocks.tests.fakes import (
    FakeAddsClustered,
    FakeNeedsUpstream,
    FakePassthrough,
    RecordingRunner,
)
from playbook.playbooks.execution import execute_playbook
from playbook.playbooks.playbook import Playbook, When
from playbook.playbooks.yaml_io import StepDoc


def test_nested_playbook_unbound_inputs_are_namespaced():
    child = Playbook(name="child")
    child.add("inner_cluster", FakeAddsClustered)
    child.add("inner_dispatch", FakeNeedsUpstream)
    assert child.unbound_inputs() == {"inner_dispatch.source"}


def test_an_input_the_inner_playbook_wires_itself_is_not_asked_of_the_outer_one():
    child = Playbook(name="child")
    upstream = child.add("inner_cluster", FakePassthrough)
    child.add("inner_dispatch", FakeNeedsUpstream, inputs={"source": upstream.output})
    assert child.unbound_inputs() == frozenset()


def test_a_nested_playbook_executes_within_the_outer_run(initial_record):
    child = Playbook(name="child")
    child.add("inner", FakePassthrough)

    outer = Playbook(name="outer")
    outer.add("before", FakePassthrough)
    outer.add_playbook("nested", child)
    outer.add("after", FakePassthrough)

    config = {
        "before": {"label": "before"},
        "nested": {"inner": {"label": "inner"}},
        "after": {"label": "after"},
    }
    result = outer.run(initial_record, config)
    assert result.url == "root+before+inner+after"


def test_a_nested_playbook_inherits_the_outer_globals(initial_record):
    # Shared settings do not have to be repeated at every level, so a condition
    # inside a nested playbook can read a global the outer playbook set.
    child = Playbook(name="child")
    child.add("inner", FakePassthrough, when=When(config="globals.mode", equals="on"))

    outer = Playbook(name="outer")
    outer.add_playbook("nested", child)

    on = {"globals": {"mode": "on"}, "nested": {"inner": {"label": "inner"}}}
    assert outer.run(initial_record, on).url == "root+inner"

    off = {"globals": {"mode": "off"}, "nested": {"inner": {"label": "inner"}}}
    assert outer.run(initial_record, off).url == "root"


def test_a_nested_playbook_can_have_globals_of_its_own(initial_record):
    child = Playbook(name="child")
    child.add("inner", FakePassthrough, when=When(config="globals.mode", equals="on"))

    outer = Playbook(name="outer")
    outer.add_playbook("nested", child)

    config = {
        "globals": {"mode": "off"},
        "nested": {"globals": {"mode": "on"}, "inner": {"label": "inner"}},
    }
    assert outer.run(initial_record, config).url == "root+inner"


def test_nested_steps_reach_the_runner_by_their_qualified_path(initial_record):
    inner = Playbook(name="inner")
    inner.add("leaf", FakePassthrough)
    middle = Playbook(name="middle")
    middle.add_playbook("region", inner)
    middle.add("cluster", FakePassthrough)
    outer = Playbook(name="outer")
    outer.add("before", FakePassthrough)
    outer.add_playbook("stage_2030", middle)

    runner = RecordingRunner()
    execute_playbook(outer, initial_record, {}, runner=runner)

    assert [call["step_name"] for call in runner.calls] == [
        "before",
        "stage_2030/region/leaf",
        "stage_2030/cluster",
    ]


@pytest.mark.parametrize(
    "add",
    [
        lambda: Playbook(name="p").add("a/b", FakePassthrough),
        lambda: Playbook(name="p").add_playbook("a/b", Playbook(name="child")),
        lambda: StepDoc(name="a/b", block="fake_passthrough"),
    ],
    ids=["block", "nested", "doc"],
)
def test_a_step_name_with_a_slash_is_rejected(add):
    with pytest.raises(ValidationError, match="name"):
        add()

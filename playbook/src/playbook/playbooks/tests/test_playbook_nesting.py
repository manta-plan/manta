# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""A playbook used as a single step inside a longer one.

The inner playbook keeps its own settings and its own step names; what it does not
wire up itself is offered to the outer playbook to feed, exactly like a block's own
inputs.
"""

from playbook.blocks.tests.fakes import (
    FakeAddsClustered,
    FakeNeedsUpstream,
    FakePassthrough,
)
from playbook.playbooks.playbook import Playbook, When


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
    result = outer.run(initial_record, config, output_prefix="out")
    assert result.url == "root+before+inner+after"


def test_a_nested_playbook_inherits_the_outer_globals(initial_record):
    # Shared settings do not have to be repeated at every level, so a condition
    # inside a nested playbook can read a global the outer playbook set.
    child = Playbook(name="child")
    child.add("inner", FakePassthrough, when=When(config="globals.mode", equals="on"))

    outer = Playbook(name="outer")
    outer.add_playbook("nested", child)

    on = {"globals": {"mode": "on"}, "nested": {"inner": {"label": "inner"}}}
    assert outer.run(initial_record, on, output_prefix="out").url == "root+inner"

    off = {"globals": {"mode": "off"}, "nested": {"inner": {"label": "inner"}}}
    assert outer.run(initial_record, off, output_prefix="out").url == "root"


def test_a_nested_playbook_can_have_globals_of_its_own(initial_record):
    child = Playbook(name="child")
    child.add("inner", FakePassthrough, when=When(config="globals.mode", equals="on"))

    outer = Playbook(name="outer")
    outer.add_playbook("nested", child)

    config = {
        "globals": {"mode": "off"},
        "nested": {"globals": {"mode": "on"}, "inner": {"label": "inner"}},
    }
    assert outer.run(initial_record, config, output_prefix="out").url == "root+inner"

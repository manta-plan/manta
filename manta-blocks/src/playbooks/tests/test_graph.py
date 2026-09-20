# SPDX-FileCopyrightText: 2026 Manta Blocks contributors
#
# SPDX-License-Identifier: MIT

"""A playbook drawn out without running it."""

import json

from blocks.tests.fakes import (
    FakeAddsClustered,
    FakeExplodes,
    FakeNeedsUpstream,
    FakePassthrough,
    FakeStrictConfig,
)
from playbooks.graph import INITIAL_NODE, graph_to_mermaid
from playbooks.playbook import Playbook, When


def _wired(pb: Playbook) -> Playbook:
    cluster = pb.add("cluster", FakePassthrough)
    pb.add("expand", FakePassthrough)
    pb.add("dispatch", FakeNeedsUpstream, inputs={"source": cluster.output})
    return pb


def test_the_graph_has_a_node_per_step_plus_the_starting_data():
    graph = _wired(Playbook(name="p")).to_graph()
    assert [node.id for node in graph.nodes] == [
        INITIAL_NODE,
        "cluster",
        "expand",
        "dispatch",
    ]
    assert graph.nodes[0].type == "initial_data"
    assert all(node.type == "block" for node in graph.nodes[1:])


def test_the_record_handed_along_and_a_wired_input_are_different_arrows():
    graph = _wired(Playbook(name="p")).to_graph()
    spine = [(e.source, e.target) for e in graph.edges if e.kind == "spine"]
    wired = [e for e in graph.edges if e.kind == "wired"]

    assert spine == [
        (INITIAL_NODE, "cluster"),
        ("cluster", "expand"),
        ("expand", "dispatch"),
    ]
    assert len(wired) == 1
    assert (wired[0].source, wired[0].target) == ("cluster", "dispatch")
    assert wired[0].target_input == "source"
    assert wired[0].source_output == "output"


def test_a_node_says_which_block_it_is_and_where_its_settings_live():
    graph = _wired(Playbook(name="p")).to_graph()
    dispatch = next(node for node in graph.nodes if node.id == "dispatch")
    assert dispatch.block == "fake_needs_upstream"
    assert dispatch.env == "default"
    assert dispatch.config_key == "dispatch"
    assert dispatch.inputs == ["source"]
    assert dispatch.outputs == ["output"]


def test_a_step_that_does_not_run_stays_in_the_graph_marked_inactive():
    pb = Playbook(name="p")
    pb.add("branch_a", FakePassthrough, when=When(config="globals.mode", equals="a"))
    pb.add("branch_b", FakePassthrough, when=When(config="globals.mode", equals="b"))

    graph = pb.to_graph({"globals": {"mode": "a"}})
    active = {node.id: node.active for node in graph.nodes if node.type == "block"}

    # Both are shown, so a user can see the branch not taken and change their mind.
    assert active == {"branch_a": True, "branch_b": False}
    assert [(e.source, e.target) for e in graph.edges if e.kind == "spine"] == [
        (INITIAL_NODE, "branch_a")
    ]


def test_a_node_says_why_it_is_or_is_not_running():
    pb = Playbook(name="p")
    pb.add("maybe", FakePassthrough, when=When(config="globals.mode", equals="on"))

    node = pb.to_graph({"globals": {"mode": "off"}}).nodes[1]
    assert node.when.config == "globals.mode"
    assert node.when.equals == "on"
    assert node.when.holds is False


def test_without_settings_nothing_is_ruled_out():
    pb = Playbook(name="p")
    pb.add("maybe", FakePassthrough, when=When(config="globals.mode", equals="on"))

    node = pb.to_graph().nodes[1]
    assert node.active is True
    assert node.when.holds is None


def test_the_graph_follows_the_dimensions_along_the_way():
    pb = Playbook(name="p", initial_dims=frozenset({"snapshot"}))
    pb.add("cluster", FakeAddsClustered)

    graph = pb.to_graph({})
    assert graph.nodes[0].dims == ["snapshot"]
    assert graph.nodes[1].dims == ["clustered", "snapshot"]


def test_a_nested_playbook_is_drawn_out_inside_its_node():
    inner = Playbook(name="inner")
    inner.add("leaf", FakePassthrough)

    outer = Playbook(name="outer")
    outer.add_playbook("regional", inner)

    node = outer.to_graph({}).nodes[1]
    assert node.type == "playbook"
    assert node.playbook == "inner"
    assert [n.id for n in node.graph.nodes] == [INITIAL_NODE, "leaf"]


def test_a_nested_node_says_what_can_be_fed_into_it():
    inner = Playbook(name="inner")
    inner.add("leaf", FakeNeedsUpstream)

    outer = Playbook(name="outer")
    outer.add_playbook("regional", inner)

    node = outer.to_graph({}).nodes[1]
    assert node.unbound_inputs == ["leaf.source"]


def test_drawing_a_playbook_never_runs_it():
    # The old way of drawing a playbook ran it to trace the shape, which for a real
    # block means starting a solver just to get a picture.
    pb = Playbook(name="p")
    pb.add("explodes", FakeExplodes)
    assert pb.to_graph({}).nodes[1].block == "fake_explodes"
    assert "explodes" in pb.to_mermaid({})


def test_a_graph_can_be_sent_as_plain_data():
    graph = _wired(Playbook(name="p")).to_graph({})
    data = graph.model_dump(mode="json")
    json.dumps(data)  # raises if anything is not plain data
    assert data["graph_version"] == 1
    assert data["name"] == "p"


def test_a_graph_can_be_built_for_a_playbook_whose_settings_are_wrong():
    # Drawing has to work while a playbook is still being put together, otherwise
    # nothing could be shown until it was already correct.
    pb = Playbook(name="p")
    pb.add("strict", FakeStrictConfig)
    assert pb.to_graph({"strict": {}}).nodes[1].block == "fake_strict_config"


# --- Mermaid, which is just one way of drawing the graph ---


def test_mermaid_shows_both_kinds_of_arrow():
    mermaid = _wired(Playbook(name="p")).to_mermaid({})
    assert "flowchart TD" in mermaid
    assert "cluster --> expand" in mermaid
    assert "expand --> dispatch" in mermaid
    assert "cluster -.->|source| dispatch" in mermaid


def test_mermaid_marks_a_step_that_does_not_run():
    pb = Playbook(name="p")
    pb.add("branch_a", FakePassthrough, when=When(config="globals.mode", equals="a"))
    pb.add("branch_b", FakePassthrough, when=When(config="globals.mode", equals="b"))

    mermaid = pb.to_mermaid({"globals": {"mode": "a"}})
    assert "branch_a" in mermaid
    assert "(not run)" in mermaid
    assert "style branch_b stroke-dasharray" in mermaid


def test_mermaid_of_a_graph_matches_the_graph_it_came_from():
    graph = _wired(Playbook(name="p")).to_graph({})
    assert graph_to_mermaid(graph) == _wired(Playbook(name="p")).to_mermaid({})

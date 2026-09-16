# SPDX-FileCopyrightText: 2026 Manta Blocks contributors
#
# SPDX-License-Identifier: MIT

"""A playbook as boxes and arrows.

Worked out purely by reading the playbook, so drawing one never runs any of it. That
matters as soon as the blocks are real: asking for a picture should not start a solver.

There are two kinds of arrow. A `spine` arrow is the record handed from each step to
the next, which is how most work flows. A `wired` arrow is a step reaching back for a
particular earlier result and putting it into one of its settings.

Steps switched off by a condition stay in the graph, marked inactive, so a user can
see the branch that was not taken and change their mind.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from manta_playbooks.playbook import BlockStep, Playbook, Step, When, child_config

GRAPH_VERSION = 1
"""Bumped when the graph's shape changes, so a reader can tell what it has."""

INITIAL_NODE = "__initial__"
"""The node standing for the data the playbook starts from."""


class WhenSummary(BaseModel):
    """The condition on a step, and whether it currently holds."""

    model_config = ConfigDict(frozen=True)

    config: str
    equals: object
    holds: bool | None = None
    """None when no settings were given, or the setting was not found."""


class GraphNode(BaseModel):
    """One box: a step, or the data the playbook starts from."""

    model_config = ConfigDict(frozen=True)

    id: str
    type: Literal["initial_data", "block", "playbook"]
    label: str
    """What to write in the box."""

    block: str | None = None
    """For a block step, the block's registered name."""
    env: str | None = None
    playbook: str | None = None
    """For a nested step, the inner playbook's name."""

    config_key: str | None = None
    """Where this step's settings live in the settings document."""

    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)

    when: WhenSummary | None = None
    active: bool = True
    """Whether this step runs with the settings given."""

    dims: list[str] = Field(default_factory=list)
    """The dimensions the data has once this step has run."""

    graph: "PlaybookGraph | None" = None
    """For a nested step, the inner playbook drawn out in full."""

    unbound_inputs: list[str] = Field(default_factory=list)
    """For a nested step, what the outer playbook can feed it."""


class GraphEdge(BaseModel):
    """One arrow between two boxes."""

    model_config = ConfigDict(frozen=True)

    source: str
    target: str
    kind: Literal["spine", "wired"]

    source_output: str | None = None
    target_input: str | None = None
    """For a wired arrow, which result goes into which setting."""


class PlaybookGraph(BaseModel):
    """A whole playbook as boxes and arrows."""

    model_config = ConfigDict(frozen=True)

    graph_version: int = GRAPH_VERSION
    name: str
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


GraphNode.model_rebuild()


def _summarise_when(when: When | None, config: dict | None) -> WhenSummary | None:
    if when is None:
        return None
    holds = when.check(config) if config is not None else None
    return WhenSummary(config=when.config, equals=when.equals, holds=holds)


def _is_active(step: Step, config: dict | None) -> bool:
    """Whether a step runs. Without settings, nothing is ruled out."""
    if config is None or step.when is None:
        return True
    return bool(step.when.check(config))


def playbook_graph(playbook: Playbook, config: dict | None = None) -> PlaybookGraph:
    """Draw out `playbook` without running any of it.

    With `config`, steps are marked with whether they run and the dimensions are
    followed along the way. Without it, every step is treated as running, since
    nothing is known that would rule one out.
    """
    fold_config = config if config is not None else {}
    nodes: list[GraphNode] = [
        GraphNode(
            id=INITIAL_NODE,
            type="initial_data",
            label="initial data",
            dims=sorted(playbook.initial_dims),
        )
    ]
    edges: list[GraphEdge] = []

    dims = frozenset(playbook.initial_dims)
    previous = INITIAL_NODE

    for step in playbook.steps:
        active = _is_active(step, config)
        if active:
            dims = step.dims(fold_config).apply(dims)

        nodes.append(_node_for(step, active, dims, fold_config))

        if active:
            edges.append(GraphEdge(source=previous, target=step.name, kind="spine"))
            previous = step.name

        edges.extend(
            GraphEdge(
                source=ref.step,
                target=step.name,
                kind="wired",
                source_output=ref.output,
                target_input=input_name,
            )
            for input_name, ref in sorted(step.inputs.items())
        )

    return PlaybookGraph(name=playbook.name, nodes=nodes, edges=edges)


def _node_for(
    step: Step, active: bool, dims: frozenset[str], config: dict
) -> GraphNode:
    shared = {
        "id": step.name,
        "config_key": step.name,
        "inputs": sorted(step.declared_inputs()),
        "outputs": sorted(step.declared_outputs()),
        "when": _summarise_when(step.when, config or None),
        "active": active,
        "dims": sorted(dims),
    }
    if isinstance(step, BlockStep):
        return GraphNode(
            type="block",
            label=step.name,
            block=step.block.name,
            env=step.block.env,
            **shared,
        )
    return GraphNode(
        type="playbook",
        label=step.name,
        playbook=step.playbook.name,
        graph=playbook_graph(step.playbook, child_config(config, step.name) or None),
        unbound_inputs=sorted(step.playbook.unbound_inputs()),
        **shared,
    )


def graph_to_mermaid(graph: PlaybookGraph, indent: str = "") -> str:
    """Draw a graph as a Mermaid flowchart."""
    lines = [f"{indent}flowchart TD"]
    lines.extend(_mermaid_body(graph, indent + "    "))
    return "\n".join(lines)


def _mermaid_body(graph: PlaybookGraph, indent: str) -> list[str]:
    lines = []
    for node in graph.nodes:
        lines.append(f"{indent}{node.id}{_mermaid_shape(node)}")
    for edge in graph.edges:
        if edge.kind == "spine":
            lines.append(f"{indent}{edge.source} --> {edge.target}")
        else:
            lines.append(
                f"{indent}{edge.source} -.->|{edge.target_input}| {edge.target}"
            )
    for node in graph.nodes:
        if not node.active:
            lines.append(f"{indent}style {node.id} stroke-dasharray: 4 4")
    return lines


def _mermaid_shape(node: GraphNode) -> str:
    if node.type == "initial_data":
        return f'(["{node.label}"])'
    detail = node.block or f"playbook {node.playbook}"
    text = f"{node.label}<br/>{detail}"
    if not node.active:
        text += "<br/>(not run)"
    if node.type == "playbook":
        return f'[["{text}"]]'
    return f'["{text}"]'

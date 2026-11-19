import { useEffect, useMemo } from "react";
import dagre from "@dagrejs/dagre";
import {
  ReactFlow,
  MarkerType,
  useEdgesState,
  useNodesState,
  type Edge,
  type NodeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { GraphModel, GraphNodeModel } from "../lib/location-graph";
import { CircleNode, type CircleNodeType } from "./circle-node";
import { DiamondNode, type DiamondNodeType } from "./diamond-node";

const NODE_TYPES: NodeTypes = { circle: CircleNode, diamond: DiamondNode };
const NODE_SIZE = 64;
const EDGE_LABEL_STYLE = { fill: "var(--color-surface-100)", fontSize: 10, fontWeight: 600 };
const EDGE_LABEL_BG_STYLE = { fill: "var(--color-surface-800)" };

type FlowNode = CircleNodeType | DiamondNodeType;

// Left to right, in the direction energy flows (input → link → output).
// dagre copes with the cycles a location has (AC → H2 → AC).
function layout(model: GraphModel, dense: boolean): { nodes: FlowNode[]; edges: Edge[] } {
  const graph = new dagre.graphlib.Graph();
  graph.setGraph({
    rankdir: "LR",
    nodesep: dense ? 14 : 28,
    ranksep: dense ? 70 : 110,
    marginx: 16,
    marginy: 16,
  });
  graph.setDefaultEdgeLabel(() => ({}));
  for (const node of model.nodes) graph.setNode(node.id, { width: NODE_SIZE, height: NODE_SIZE });
  for (const edge of model.edges) graph.setEdge(edge.source, edge.target);
  dagre.layout(graph);

  const nodes = model.nodes.map((node: GraphNodeModel): FlowNode => {
    const { x, y } = graph.node(node.id);
    return {
      id: node.id,
      type: node.shape,
      position: { x: x - NODE_SIZE / 2, y: y - NODE_SIZE / 2 },
      data: { label: node.label, title: node.title, color: node.color, textColor: node.textColor },
    } as FlowNode;
  });
  const edges = model.edges.map((edge): Edge => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    sourceHandle: "right-source",
    targetHandle: "left-target",
    label: edge.label,
    labelStyle: EDGE_LABEL_STYLE,
    labelBgStyle: EDGE_LABEL_BG_STYLE,
    labelBgPadding: [4, 2],
    labelBgBorderRadius: 3,
    markerEnd: { type: MarkerType.ArrowClosed, color: edge.color },
    style: { stroke: edge.color, strokeWidth: dense ? 1.25 : 2 },
  }));
  return { nodes, edges };
}

export function LocationGraph({
  model,
  dense = false,
  highlightedId = null,
  onNodeClick,
}: {
  model: GraphModel;
  // Many nodes: tighter spacing, thinner edges.
  dense?: boolean;
  highlightedId?: string | null;
  onNodeClick?: (node: GraphNodeModel) => void;
}) {
  const laidOut = useMemo(() => layout(model, dense), [dense, model]);
  const byId = useMemo(() => new Map(model.nodes.map((node) => [node.id, node])), [model]);
  const [nodes, setNodes, onNodesChange] = useNodesState<FlowNode>(laidOut.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(laidOut.edges);

  useEffect(() => {
    setNodes(laidOut.nodes);
    setEdges(laidOut.edges);
  }, [laidOut, setEdges, setNodes]);

  // Highlight without re-laying out, so dragged nodes stay put.
  useEffect(() => {
    setNodes((current) =>
      current.map((node) =>
        node.data.highlighted === (node.id === highlightedId)
          ? node
          : ({
              ...node,
              data: { ...node.data, highlighted: node.id === highlightedId },
            } as FlowNode),
      ),
    );
  }, [highlightedId, setNodes]);

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      nodeTypes={NODE_TYPES}
      fitView
      fitViewOptions={{ padding: 0.12 }}
      minZoom={0.1}
      nodesDraggable
      nodesConnectable={false}
      onNodeClick={(_event, node) => {
        const clicked = byId.get(node.id);
        if (clicked) onNodeClick?.(clicked);
      }}
      proOptions={{ hideAttribution: true }}
    />
  );
}

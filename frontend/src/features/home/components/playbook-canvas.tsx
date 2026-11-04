import { useMemo, useState, type DragEvent } from "react";
import {
  ReactFlow,
  Background,
  BackgroundVariant,
  useNodesState,
  useEdgesState,
  type NodeTypes,
  type Edge,
  type ReactFlowInstance,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { PlaybookStageNode, type PlaybookStageNodeType } from "./playbook-stage-node";
import { PlaybookGatewayNode, type PlaybookGatewayNodeType } from "./playbook-gateway-node";
import {
  findPlaybookBlock,
  getPlaybookFlow,
  PLAYBOOK_BLOCK_DRAG_TYPE,
  type PlaybookStageNodeConfig,
} from "../data/playbooks";

const NODE_TYPES: NodeTypes = { stage: PlaybookStageNode, gateway: PlaybookGatewayNode };

type PlaybookCanvasNode = PlaybookStageNodeType | PlaybookGatewayNodeType;

// Half of PlaybookStageNode's w-64, and roughly half its height, so a
// dropped block lands centered under the cursor.
const DROP_OFFSET = { x: 128, y: 40 };

export function PlaybookCanvas({
  playbookId,
  selectedNodeId,
  onNodeSelect,
}: {
  playbookId: string;
  selectedNodeId: string | null;
  onNodeSelect: (node: PlaybookStageNodeConfig) => void;
}) {
  const flow = getPlaybookFlow(playbookId);
  const initialNodes: PlaybookCanvasNode[] = useMemo(
    () =>
      flow.nodes.map((n) => ({
        id: n.id,
        type: n.kind ?? "stage",
        position: n.position,
        data: n.data,
      })),
    [flow.nodes],
  );
  const initialEdges: Edge[] = useMemo(
    () => flow.edges.map((e) => ({ id: e.id, source: e.source, target: e.target })),
    [flow.edges],
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [flowInstance, setFlowInstance] = useState<ReactFlowInstance<PlaybookCanvasNode>>();
  const [edges, , onEdgesChange] = useEdgesState(initialEdges);
  const visibleNodes = useMemo(
    () => nodes.map((node) => ({ ...node, selected: node.id === selectedNodeId })),
    [nodes, selectedNodeId],
  );

  const handleDragOver = (e: DragEvent) => {
    if (!e.dataTransfer.types.includes(PLAYBOOK_BLOCK_DRAG_TYPE)) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
  };

  // Dropped blocks live only in this canvas's local state — there's no
  // persistence yet, so they disappear when the page is left.
  const handleDrop = (e: DragEvent) => {
    const payload = e.dataTransfer.getData(PLAYBOOK_BLOCK_DRAG_TYPE);
    if (!payload || !flowInstance) return;
    e.preventDefault();
    const { categoryId, blockId } = JSON.parse(payload) as { categoryId: string; blockId: string };
    const match = findPlaybookBlock(categoryId, blockId);
    if (!match) return;
    const { category, block } = match;
    const position = flowInstance.screenToFlowPosition({ x: e.clientX, y: e.clientY });
    const node: PlaybookStageNodeType = {
      id: `${block.id}-${Date.now()}`,
      type: "stage",
      position: { x: position.x - DROP_OFFSET.x, y: position.y - DROP_OFFSET.y },
      data: {
        category: category.label,
        icon: category.icon,
        color: category.color,
        title: block.title,
        subtitle: block.subtitle,
      },
    };
    setNodes((prev) => [...prev, node]);
  };

  return (
    <div className="h-full w-full" onDragOver={handleDragOver} onDrop={handleDrop}>
      <ReactFlow
        onInit={setFlowInstance}
        nodes={visibleNodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={(_, node) =>
          onNodeSelect({ id: node.id, kind: node.type, position: node.position, data: node.data })
        }
        nodeTypes={NODE_TYPES}
        nodesDraggable
        nodesConnectable={false}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Lines} gap={24} color="var(--color-surface-700)" />
      </ReactFlow>
    </div>
  );
}

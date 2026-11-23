// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: MIT

import { Background, BackgroundVariant, ReactFlow, type Edge, type NodeTypes } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { PlaybookStep } from "../../../utils/playbookTypes";
import { RunFlowNode, type RunFlowNodeStatus, type RunFlowNodeType } from "./run-flow-node";

// Wide enough that a node (14rem) never touches its neighbour.
const nodeSpacing = 300;
// Defined here, not in the component: React Flow warns when `nodeTypes` changes between renders.
const nodeTypes: NodeTypes = { "run-step": RunFlowNode };

type RunFlowSnapshotProps = {
  /** The steps that run, in step order. */
  steps: PlaybookStep[];
  status: RunFlowNodeStatus;
  /** The step whose settings are open. */
  selectedStepName: string | null;
  onSelectStep: (stepName: string) => void;
};

// A read-only picture of a run: its blocks in order. "Planned" before the run starts,
// "Executed" after. Clicking a block opens its settings.
export function RunFlowSnapshot({
  steps,
  status,
  selectedStepName,
  onSelectStep,
}: RunFlowSnapshotProps) {
  const isPlanned = status === "planned";

  const nodes: RunFlowNodeType[] = steps.map((step, index) => ({
    id: step.name,
    type: "run-step",
    position: { x: index * nodeSpacing, y: 40 },
    selected: step.name === selectedStepName,
    data: {
      title: step.name,
      category: step.block ?? "Nested playbook",
      subtitle: step.block_summary ?? "",
      status,
    },
  }));
  const edges: Edge[] = steps.slice(1).map((step, index) => ({
    id: `${steps[index].name}->${step.name}`,
    source: steps[index].name,
    target: step.name,
  }));

  return (
    <div className="border-surface-600 flex h-64 w-full shrink-0 flex-col border-b">
      <div className="shrink-0 px-3 py-2">
        <h2 className="text-surface-400 text-[11px] font-semibold tracking-wide uppercase">
          {isPlanned ? "Planned Flow" : "Executed Flow"}
        </h2>
        <p className="text-surface-500 text-[11px]">
          {isPlanned
            ? "Click a block to configure its settings for this run."
            : "Click a block to view its settings for this run."}
        </p>
      </div>
      <div className="min-h-0 flex-1">
        {steps.length === 0 ? (
          <div className="text-surface-400 flex h-full items-center justify-center text-[12px]">
            No block will run with these settings.
          </div>
        ) : (
          <ReactFlow
            // A new set of blocks is fitted to the view again.
            key={steps.map((step) => step.name).join("|")}
            edges={edges}
            fitView
            fitViewOptions={{ padding: 0.25 }}
            nodes={nodes}
            nodesConnectable={false}
            nodesDraggable={false}
            nodeTypes={nodeTypes}
            onNodeClick={(_, node) => onSelectStep(node.id)}
            proOptions={{ hideAttribution: true }}
          >
            <Background
              color="var(--color-surface-700)"
              gap={24}
              variant={BackgroundVariant.Lines}
            />
          </ReactFlow>
        )}
      </div>
    </div>
  );
}

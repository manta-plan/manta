// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import clsx from "clsx";
import { LuCheck, LuCircleX, LuLoaderCircle, LuWorkflow } from "react-icons/lu";

// "planned": the run has not started, so no block has a state. The others are the run's
// state: the backend gives no state per block, so every block shows that of the run.
export type RunFlowNodeStatus = "planned" | "running" | "done" | "failed" | "idle";

export type RunFlowNodeData = {
  /** The step's name. */
  title: string;
  /** The block it runs, or "Nested playbook". */
  category: string;
  subtitle: string;
  status: RunFlowNodeStatus;
};

export type RunFlowNodeType = Node<RunFlowNodeData, "run-step">;

const handleClassName = "!h-2 !w-2 !border !border-surface-500 !bg-surface-800";

const statusLabels: Partial<Record<RunFlowNodeStatus, string>> = {
  running: "Running",
  done: "Done",
  failed: "Failed",
};

export function RunFlowNode({ data, selected }: NodeProps<RunFlowNodeType>) {
  const statusLabel = statusLabels[data.status];

  return (
    <div
      className={clsx(
        "bg-surface-800 border-surface-600 w-56 cursor-pointer overflow-hidden rounded-lg border shadow-md transition-all duration-150",
        selected &&
          "ring-accent-400 ring-offset-surface-900 shadow-accent-600/25 scale-[1.02] shadow-xl ring-2 ring-offset-2",
      )}
    >
      <Handle
        className={clsx(handleClassName, selected && "!border-accent-300 !bg-accent-500")}
        position={Position.Left}
        type="target"
      />
      <div className="border-surface-600 bg-surface-700/50 flex items-center justify-between gap-1.5 border-b px-3 py-2">
        <div className="flex min-w-0 items-center gap-1.5">
          <LuWorkflow className="text-accent-300 shrink-0" size={13} aria-hidden="true" />
          <span className="text-accent-300 truncate text-[10px] font-semibold tracking-wide uppercase">
            {data.category}
          </span>
        </div>
        {statusLabel === undefined ? null : (
          <span className="flex shrink-0 items-center gap-1 text-[10px]">
            {data.status === "done" ? (
              <LuCheck className="text-ok-500" size={13} aria-hidden="true" />
            ) : data.status === "failed" ? (
              <LuCircleX className="text-danger-500" size={13} aria-hidden="true" />
            ) : (
              <LuLoaderCircle
                className="text-accent-400 animate-spin"
                size={13}
                aria-hidden="true"
              />
            )}
            <span className="text-surface-300">{statusLabel}</span>
          </span>
        )}
      </div>
      <div className="px-3 py-2">
        <div className="text-surface-50 text-[12px] font-semibold">{data.title}</div>
        {data.subtitle === "" ? null : (
          <div className="text-surface-400 mt-0.5 text-[11px]">{data.subtitle}</div>
        )}
      </div>
      <Handle
        className={clsx(handleClassName, selected && "!border-accent-300 !bg-accent-500")}
        position={Position.Right}
        type="source"
      />
    </div>
  );
}

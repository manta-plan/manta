import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import clsx from "clsx";
import type { PlaybookStageNodeData } from "../data/playbooks";

export type PlaybookGatewayNodeType = Node<PlaybookStageNodeData, "gateway">;

export function PlaybookGatewayNode({ data, selected }: NodeProps<PlaybookGatewayNodeType>) {
  return (
    <div
      className={clsx(
        "grid h-28 w-28 place-items-center rounded-full border-2 border-surface-500 bg-surface-800 text-[16px] font-semibold text-surface-100 shadow-md",
        selected && "ring-2 ring-accent-400 ring-offset-2 ring-offset-surface-900",
      )}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="!border-surface-500 !bg-surface-800 !h-2 !w-2 !border"
      />
      {data.title}
      <Handle
        type="source"
        position={Position.Right}
        className="!border-surface-500 !bg-surface-800 !h-2 !w-2 !border"
      />
    </div>
  );
}

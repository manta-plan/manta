import { Handle, Position, type NodeProps, type Node } from "@xyflow/react";
import clsx from "clsx";
import { PLAYBOOK_STAGE_COLOR_CLASSES, type PlaybookStageNodeData } from "../data/playbooks";

export type PlaybookStageNodeType = Node<PlaybookStageNodeData, "stage">;

// Handles are kept visible (unlike CircleNode/DiamondNode) — this pipeline
// style is meant to show its connection points, matching dummy-flow.png.
const HANDLE_CLASS = "!h-2 !w-2 !border !border-surface-500 !bg-surface-800";

export function PlaybookStageNode({ data, selected }: NodeProps<PlaybookStageNodeType>) {
  const colors = PLAYBOOK_STAGE_COLOR_CLASSES[data.color];
  const Icon = data.icon;

  return (
    <div
      className={clsx(
        "w-64 overflow-hidden rounded-lg border bg-surface-800 shadow-md transition-all duration-150",
        colors.border,
        selected &&
          "scale-[1.02] ring-2 ring-accent-400 ring-offset-2 ring-offset-surface-900 shadow-xl shadow-accent-600/25",
      )}
    >
      <Handle
        type="target"
        position={Position.Left}
        className={clsx(HANDLE_CLASS, selected && "!border-accent-300 !bg-accent-500")}
      />
      <div
        className={`flex items-center gap-1.5 border-b px-3 py-2 ${colors.headerBg} ${colors.border}`}
      >
        <Icon size={13} className={colors.text} />
        <span className={`text-[10px] font-semibold tracking-wide uppercase ${colors.text}`}>
          {data.category}
        </span>
      </div>
      <div className="px-3 py-2.5">
        <div className="text-surface-50 text-[13px] font-semibold">{data.title}</div>
        <div className="text-surface-400 mt-0.5 text-[11px]">{data.subtitle}</div>
        {data.tags && data.tags.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {data.tags.map((tag) => (
              <span
                key={tag}
                className="border-surface-600 bg-surface-700 text-surface-300 rounded-full border px-2 py-0.5 font-mono text-[10px]"
              >
                {tag}
              </span>
            ))}
          </div>
        )}
      </div>
      <Handle
        type="source"
        position={Position.Right}
        className={clsx(HANDLE_CLASS, selected && "!border-accent-300 !bg-accent-500")}
      />
    </div>
  );
}

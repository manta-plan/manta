import { Handle, Position, type NodeProps, type Node } from "@xyflow/react";

export type DiamondNodeType = Node<
  { label: string; color: string; textColor: string; title?: string; highlighted?: boolean },
  "diamond"
>;

// Handles are hidden (see CircleNode) — purely geometric anchors, not
// user-facing since connection dragging is disabled.
const HANDLE_CLASS = "!opacity-0 !pointer-events-none";

export function DiamondNode({ data }: NodeProps<DiamondNodeType>) {
  return (
    <div title={data.title} className="relative flex h-16 w-16 items-center justify-center">
      <div
        className="absolute top-1/2 left-1/2 h-11 w-11 -translate-x-1/2 -translate-y-1/2 rotate-45 border-2 shadow-md"
        style={{
          backgroundColor: data.color,
          borderColor: data.highlighted ? "var(--color-accent-400)" : data.color,
          boxShadow: data.highlighted
            ? "0 0 0 3px var(--color-surface-900), 0 0 0 5px var(--color-accent-400)"
            : undefined,
        }}
      />
      <Handle type="target" position={Position.Top} id="top-target" className={HANDLE_CLASS} />
      <Handle type="source" position={Position.Top} id="top-source" className={HANDLE_CLASS} />
      <Handle
        type="target"
        position={Position.Bottom}
        id="bottom-target"
        className={HANDLE_CLASS}
      />
      <Handle
        type="source"
        position={Position.Bottom}
        id="bottom-source"
        className={HANDLE_CLASS}
      />
      <Handle type="source" position={Position.Left} id="left-source" className={HANDLE_CLASS} />
      <Handle type="target" position={Position.Left} id="left-target" className={HANDLE_CLASS} />
      <Handle type="source" position={Position.Right} id="right-source" className={HANDLE_CLASS} />
      <Handle type="target" position={Position.Right} id="right-target" className={HANDLE_CLASS} />
      <span
        className="relative z-10 px-1 text-center text-[10px] leading-tight font-medium whitespace-pre-line"
        style={{ color: data.textColor }}
      >
        {data.label}
      </span>
    </div>
  );
}

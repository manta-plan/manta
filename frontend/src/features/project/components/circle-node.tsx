import { Handle, Position, type NodeProps, type Node } from "@xyflow/react";

export type CircleNodeType = Node<
  { label: string; color: string; textColor: string; title?: string; highlighted?: boolean },
  "circle"
>;

// Handles are purely geometric anchor points for our statically-defined edges —
// connection dragging is disabled (`nodesConnectable={false}` on <ReactFlow>),
// so there's nothing for the user to interact with here. Hidden visually
// (opacity-0) rather than unmounted, since React Flow still needs the DOM
// element's layout position to route edges correctly; pointer-events-none so
// they never create a dead zone that blocks dragging the node itself.
const HANDLE_CLASS = "!opacity-0 !pointer-events-none";

export function CircleNode({ data }: NodeProps<CircleNodeType>) {
  return (
    <div
      title={data.title}
      className="flex h-16 w-16 items-center justify-center rounded-full border-2 text-center text-[10px] leading-tight font-medium whitespace-pre-line shadow-md"
      style={{
        backgroundColor: data.color,
        borderColor: data.color,
        color: data.textColor,
        boxShadow: data.highlighted
          ? "0 0 0 3px var(--color-surface-900), 0 0 0 5px var(--color-accent-400)"
          : undefined,
      }}
    >
      {/* Centered handles: used by single, non-competing edges (e.g. Coal -> AC bus). */}
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
      {/*
        Offset handles: for a node pair with traffic in both directions (e.g.
        AC <-> Hydrogen bus), using the centered handles for both edges makes
        them mirror-image swaps of each other, and since a bezier's label sits
        at the endpoint average, the two labels land on the exact same point.
        These 10%/90% handles let each direction consistently favor one side,
        so both the lines and their labels end up genuinely separated.
      */}
      <Handle
        type="source"
        position={Position.Top}
        id="top-source-r"
        style={{ left: "90%" }}
        className={HANDLE_CLASS}
      />
      <Handle
        type="target"
        position={Position.Top}
        id="top-target-l"
        style={{ left: "10%" }}
        className={HANDLE_CLASS}
      />
      <Handle
        type="target"
        position={Position.Top}
        id="top-target-r"
        style={{ left: "90%" }}
        className={HANDLE_CLASS}
      />
      <Handle
        type="target"
        position={Position.Bottom}
        id="bottom-target-r"
        style={{ left: "90%" }}
        className={HANDLE_CLASS}
      />
      <Handle
        type="source"
        position={Position.Bottom}
        id="bottom-source-l"
        style={{ left: "10%" }}
        className={HANDLE_CLASS}
      />
      {/* Left/right handles: for horizontally-adjacent node pairs. */}
      <Handle type="source" position={Position.Left} id="left-source" className={HANDLE_CLASS} />
      <Handle type="target" position={Position.Left} id="left-target" className={HANDLE_CLASS} />
      <Handle type="source" position={Position.Right} id="right-source" className={HANDLE_CLASS} />
      <Handle type="target" position={Position.Right} id="right-target" className={HANDLE_CLASS} />
      {data.label}
    </div>
  );
}

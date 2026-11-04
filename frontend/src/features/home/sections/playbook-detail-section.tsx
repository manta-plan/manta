import { useState } from "react";
import { Link, useParams } from "wouter";
import clsx from "clsx";
import { LuArrowLeft, LuX, LuSquareStack } from "react-icons/lu";
import { PlaybookBlocksPanel } from "../components/playbook-blocks-panel";
import { PlaybookCanvas } from "../components/playbook-canvas";
import { NodeDetailView } from "../components/node-detail-view";
import { INITIAL_PLAYBOOKS, type PlaybookStageNodeConfig } from "../data/playbooks";

export function PlaybookDetailSection() {
  const { playbookId } = useParams<{ playbookId: string }>();
  const playbook = INITIAL_PLAYBOOKS.find((p) => p.id === playbookId);
  // Held as the node itself rather than an id: blocks dropped onto the
  // canvas exist only in PlaybookCanvas's state, not in the static flow.
  const [selectedNode, setSelectedNode] = useState<PlaybookStageNodeConfig | null>(null);

  const isDetailOpen = selectedNode !== null;
  const DetailIcon = selectedNode?.data.icon ?? LuSquareStack;

  return (
    <div className="flex h-full w-full flex-col">
      <div className="border-surface-600 flex h-10 shrink-0 items-center gap-2 border-b px-4">
        <Link
          href="/playbooks"
          className="text-surface-300 hover:bg-surface-700 hover:text-surface-50 flex items-center gap-1.5 rounded px-1.5 py-1 text-[12px] font-medium outline-none"
        >
          <LuArrowLeft size={14} />
          Playbooks
        </Link>
        <span className="text-surface-600">/</span>
        <span className="text-surface-50 text-[13px] font-semibold">
          {playbook?.name ?? "Playbook"}
        </span>
      </div>

      <div className="relative flex flex-1 overflow-hidden">
        <PlaybookBlocksPanel />

        <div className="relative flex-1 overflow-hidden">
          <PlaybookCanvas
            key={playbookId}
            playbookId={playbookId}
            selectedNodeId={selectedNode?.id ?? null}
            onNodeSelect={setSelectedNode}
          />

          <aside
            className={clsx(
              "absolute top-0 right-0 z-20 flex h-full w-72 flex-col border-l border-surface-600/60 bg-surface-800/70 backdrop-blur-xl transition-transform duration-200 ease-out",
              isDetailOpen
                ? "translate-x-0 pointer-events-auto"
                : "translate-x-full pointer-events-none",
            )}
          >
            <div className="border-surface-600/60 flex h-8 shrink-0 items-center justify-between border-b px-3">
              <div className="text-surface-200 flex min-w-0 items-center gap-1.5 text-[11px] font-semibold tracking-wide uppercase">
                <DetailIcon size={12} className="shrink-0" />
                <span className="truncate">{selectedNode?.data.title ?? "Node Details"}</span>
                <span className="border-surface-600 text-surface-400 shrink-0 rounded border px-1 py-px text-[9px] font-medium tracking-wide">
                  Preview
                </span>
              </div>
              <button
                onClick={() => setSelectedNode(null)}
                className="text-surface-400 hover:text-surface-100 outline-none"
              >
                <LuX size={14} />
              </button>
            </div>
            <div className="flex flex-1 flex-col overflow-hidden">
              <NodeDetailView node={selectedNode ?? undefined} />
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}

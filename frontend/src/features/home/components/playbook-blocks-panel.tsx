import { useState } from "react";
import { LuChevronRight, LuChevronDown, LuWorkflow } from "react-icons/lu";
import { PLAYBOOK_BLOCK_CATEGORIES, PLAYBOOK_BLOCK_DRAG_TYPE } from "../data/playbooks";

export function PlaybookBlocksPanel() {
  const [collapsedIds, setCollapsedIds] = useState<Set<string>>(new Set());

  const toggleCollapsed = (id: string) => {
    setCollapsedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  return (
    <aside className="border-surface-600 bg-surface-800 flex h-full w-72 shrink-0 flex-col border-r">
      <div className="border-surface-600 bg-surface-800 text-surface-200 flex shrink-0 items-center gap-1.5 border-b px-3 py-1.5 text-[11px] font-semibold tracking-wide uppercase">
        <LuWorkflow size={12} />
        <span>Playbook Blocks</span>
      </div>
      <div className="flex-1 overflow-y-auto p-2">
        {PLAYBOOK_BLOCK_CATEGORIES.map((category) => {
          const isCollapsed = collapsedIds.has(category.id);
          const Icon = category.icon;
          return (
            <div
              key={category.id}
              className="border-surface-700 mb-2 overflow-hidden rounded-md border"
            >
              <button
                type="button"
                onClick={() => toggleCollapsed(category.id)}
                className="bg-surface-700/50 hover:bg-surface-700 flex w-full items-center gap-1.5 px-3 py-2 text-left outline-none"
              >
                <Icon size={13} className="text-surface-300 shrink-0" />
                <span className="text-surface-300 flex-1 truncate text-[11px] font-semibold tracking-wide uppercase">
                  {category.label}
                </span>
                {isCollapsed ? (
                  <LuChevronRight size={12} className="text-surface-500 shrink-0" />
                ) : (
                  <LuChevronDown size={12} className="text-surface-500 shrink-0" />
                )}
              </button>
              {!isCollapsed && (
                <div className="flex flex-col gap-1.5 p-2">
                  {category.blocks.map((block) => (
                    <div
                      key={block.id}
                      draggable
                      onDragStart={(e) => {
                        e.dataTransfer.setData(
                          PLAYBOOK_BLOCK_DRAG_TYPE,
                          JSON.stringify({ categoryId: category.id, blockId: block.id }),
                        );
                        e.dataTransfer.effectAllowed = "copy";
                      }}
                      className="border-surface-600 bg-surface-900 hover:border-accent-500 cursor-grab rounded border px-3 py-2 active:cursor-grabbing"
                    >
                      <div className="text-surface-50 text-[12px] font-medium">{block.title}</div>
                      <div className="text-surface-400 mt-0.5 text-[11px]">{block.subtitle}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </aside>
  );
}

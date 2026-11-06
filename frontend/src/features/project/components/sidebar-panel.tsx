import type { PointerEventHandler, ReactNode } from "react";
import type { IconType } from "react-icons";

interface SidebarPanelProps {
  icon: IconType;
  label: string;
  action?: ReactNode;
  onHeaderPointerDown?: PointerEventHandler<HTMLDivElement>;
  onHeaderPointerMove?: PointerEventHandler<HTMLDivElement>;
  children: ReactNode;
}

export function SidebarPanel({
  icon: Icon,
  label,
  action,
  onHeaderPointerDown,
  onHeaderPointerMove,
  children,
}: SidebarPanelProps) {
  return (
    <div className="flex h-full flex-col">
      <div
        onPointerDown={onHeaderPointerDown}
        onPointerMove={onHeaderPointerMove}
        className={`border-surface-600 bg-surface-800 text-surface-200 flex shrink-0 items-center gap-1.5 border-b px-3 py-1.5 text-[11px] font-semibold tracking-wide uppercase ${onHeaderPointerDown ? "cursor-row-resize touch-none select-none" : ""}`}
      >
        <Icon size={12} />
        <span className="min-w-0 flex-1 truncate" title={label}>
          {label}
        </span>
        {action}
      </div>
      <div className="flex-1 overflow-hidden">{children}</div>
    </div>
  );
}

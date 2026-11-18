import type { IconType } from "react-icons";

interface SidebarEmptyStateProps {
  icon: IconType;
  text: string;
}

export function SidebarEmptyState({ icon: Icon, text }: SidebarEmptyStateProps) {
  return (
    <div className="text-surface-500 flex h-full flex-col items-center justify-center gap-1.5 text-center">
      <Icon size={20} />
      <span className="text-[12px]">{text}</span>
    </div>
  );
}

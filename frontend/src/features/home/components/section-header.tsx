import type { ReactNode } from "react";

interface SectionHeaderProps {
  title: string;
  description: string;
  action?: ReactNode;
}

export function SectionHeader({ title, description, action }: SectionHeaderProps) {
  return (
    <div className="mb-6 flex items-start justify-between">
      <div>
        <h1 className="text-surface-50 text-[18px] font-semibold">{title}</h1>
        <p className="text-surface-400 mt-0.5 text-[12px]">{description}</p>
      </div>
      {action}
    </div>
  );
}

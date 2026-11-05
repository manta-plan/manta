import type { ReactNode } from "react";
import { LuPlus } from "react-icons/lu";
import { FaFly } from "react-icons/fa";

// Shared building blocks for the Run / Inspect / Report workspace home pages,
// which all follow the same adaptive layout: concept first while the project
// has nothing yet, statistics first once it does.

export function OverviewSectionHeader({
  title,
  children,
}: {
  title: string;
  children?: ReactNode;
}) {
  return (
    <div className="border-surface-700 flex h-10 items-center justify-between border-b px-5">
      <h2 className="text-surface-300 text-[11px] font-semibold tracking-wide uppercase">
        {title}
      </h2>
      {children}
    </div>
  );
}

export function OverviewTourButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="text-surface-300 hover:bg-surface-800 hover:text-surface-50 flex h-6 items-center gap-1.5 rounded px-2 text-[11px] font-medium outline-none"
    >
      <FaFly size={12} />
      Take the tour
    </button>
  );
}

export function OverviewStat({
  label,
  value,
  detail,
}: {
  label: string;
  value: number;
  detail?: string;
}) {
  return (
    <div className="bg-surface-900 px-5 py-4">
      <div className="text-surface-400 text-[11px] font-medium tracking-wide uppercase">
        {label}
      </div>
      <div className="text-surface-50 mt-1 text-[22px] font-semibold tabular-nums">{value}</div>
      <div className="text-surface-400 mt-0.5 h-4 text-[11px]">{detail}</div>
    </div>
  );
}

export function OverviewStatGrid({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="border-surface-700 border-b">
      <OverviewSectionHeader title={title} />
      <div className="bg-surface-700 grid grid-cols-2 gap-px lg:grid-cols-4">{children}</div>
    </section>
  );
}

// Stands in for the statistics grid while there is nothing to count. The
// action is omitted when its prerequisite (e.g. a succeeded run) is missing.
export function OverviewEmptyStats({
  title,
  message,
  action,
}: {
  title: string;
  message: string;
  action?: { label: string; onClick: () => void };
}) {
  return (
    <section className="border-surface-700 border-b">
      <OverviewSectionHeader title={title} />
      <div className="flex min-h-28 max-w-xl flex-col justify-center px-5 py-5">
        <p className="text-surface-400 text-[13px] leading-6">{message}</p>
        {action && (
          <button
            type="button"
            onClick={action.onClick}
            className="border-surface-600 text-surface-200 hover:bg-surface-800 hover:text-surface-50 mt-4 flex h-8 w-fit items-center gap-1.5 rounded border px-3 text-[12px] font-medium outline-none"
          >
            <LuPlus size={14} />
            {action.label}
          </button>
        )}
      </div>
    </section>
  );
}

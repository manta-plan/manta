// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: MIT

import type { ReactNode } from "react";
import { LuPlus } from "react-icons/lu";

// Building blocks of the workspace home pages. The Run tab follows baby-manta's layout:
// the concept first while the project has no runs, the statistics first once it has.

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
      <dt className="text-surface-400 text-[11px] font-medium tracking-wide uppercase">{label}</dt>
      <dd className="text-surface-50 mt-1 text-[22px] font-semibold tabular-nums">{value}</dd>
      <dd className="text-surface-400 mt-0.5 h-4 text-[11px]">{detail}</dd>
    </div>
  );
}

export function OverviewStatGrid({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="border-surface-700 border-b">
      <OverviewSectionHeader title={title} />
      <dl className="bg-surface-700 grid grid-cols-2 gap-px lg:grid-cols-4">{children}</dl>
    </section>
  );
}

// Stands in for the statistics grid while there is nothing to count.
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
        {action ? (
          <button
            className="border-surface-600 text-surface-200 hover:bg-surface-800 hover:text-surface-50 mt-4 flex h-8 w-fit items-center gap-1.5 rounded border px-3 text-[12px] font-medium outline-none"
            onClick={action.onClick}
            type="button"
          >
            <LuPlus size={14} aria-hidden="true" />
            {action.label}
          </button>
        ) : null}
      </div>
    </section>
  );
}

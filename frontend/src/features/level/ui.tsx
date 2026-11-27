// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import type { ReactNode } from "react";
import { SkeletonBlock } from "../../components/widget-states";

// The level page's building blocks: a figure (tile), a titled panel, and the
// page's shape while it loads.

/** A figure; while `loading`, its value and detail are a skeleton of the same size. */
export function Card({
  label,
  value,
  detail,
  loading = false,
}: {
  label: string;
  value: string;
  detail?: ReactNode;
  loading?: boolean;
}) {
  return (
    <div className="border-surface-700 bg-surface-900 flex min-w-0 flex-col gap-1 border px-4 py-3">
      <div className="text-surface-400 flex items-center gap-2 text-[10px] font-medium tracking-wide uppercase">
        <span className="truncate">{label}</span>
      </div>
      {loading ? (
        <div role="status" aria-label={`Loading ${label}`} className="flex flex-col gap-1">
          {/* The value's and detail's line heights, so nothing moves when they arrive. */}
          <div className="flex h-[33px] items-center">
            <SkeletonBlock className="h-6 w-28" />
          </div>
          <div className="flex h-[16.5px] items-center">
            <SkeletonBlock className="h-2.5 w-36" />
          </div>
        </div>
      ) : (
        <>
          <div className="text-surface-50 truncate text-[22px] font-semibold tabular-nums">
            {value}
          </div>
          {detail && <div className="text-surface-400 truncate text-[11px]">{detail}</div>}
        </>
      )}
    </div>
  );
}

const SAMPLE_CARDS = ["Entities", "Existing capacity", "Optimised", "Output"];
const SAMPLE_ROWS = Array.from({ length: 10 }, (_, index) => index);

/** A page's shape while its first data loads: its cards, then a table. */
export function PageSkeleton({ label }: { label: string }) {
  return (
    <div role="status" aria-label={label} className="flex shrink-0 flex-col gap-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {SAMPLE_CARDS.map((card) => (
          <div
            key={card}
            className="border-surface-700 bg-surface-900 flex flex-col gap-2.5 border px-4 py-3"
          >
            <SkeletonBlock className="h-2.5 w-20" />
            <SkeletonBlock className="h-6 w-28" />
            <SkeletonBlock className="h-2.5 w-36" />
          </div>
        ))}
      </div>
      <section className="border-surface-700 bg-surface-900 border">
        <div className="border-surface-700 border-b px-4 py-2.5">
          <SkeletonBlock className="h-3 w-20" />
        </div>
        <div className="flex flex-col gap-3 px-3 py-3">
          {SAMPLE_ROWS.map((row) => (
            <div key={row} className="flex items-center gap-6">
              <SkeletonBlock className="h-3 w-56" />
              <SkeletonBlock className="h-3 w-24" />
              <SkeletonBlock className="h-3 w-20" />
              <SkeletonBlock className="ml-auto h-3 w-16" />
              <SkeletonBlock className="h-3 w-16" />
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

export function Panel({
  title,
  action,
  children,
  className = "",
}: {
  title: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`border-surface-700 bg-surface-900 flex min-w-0 flex-col border ${className}`}
    >
      <div className="border-surface-700 flex shrink-0 items-center justify-between gap-3 border-b px-4 py-2">
        <div className="text-surface-100 flex min-w-0 items-center gap-2 text-[12px] font-medium">
          {title}
        </div>
        {action}
      </div>
      <div className="relative min-h-0 flex-1">{children}</div>
    </section>
  );
}

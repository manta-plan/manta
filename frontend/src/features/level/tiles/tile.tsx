// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import type { ReactNode } from "react";
import { LuChevronRight } from "react-icons/lu";
import { Card } from "../ui";

// One stat tile. While loading it is the page's Card skeleton. A tile that
// opens a level is a button: › after its label and a dotted underline under
// its value. A run result's value is blue; a failed read shows "—" with the
// error as its tooltip.

export interface TileSpec {
  key: string;
  label: string;
  value: string;
  detail?: ReactNode;
  /** The value is a run result's (shown in the accent colour). */
  result?: boolean;
  /** A carrier colour dot before the value. */
  dot?: string | null;
  /** A name rather than a figure: smaller, so it fits. */
  small?: boolean;
  /** Existing and new capacity, as a two-part bar. */
  bar?: { existing: number; added: number };
  /** What it opens. */
  onOpen?: () => void;
  openLabel?: string;
  loading?: boolean;
  /** The tooltip: an error, or the full value or detail. */
  title?: string;
}

export function Tile({ spec }: { spec: TileSpec }) {
  if (spec.loading) return <Card label={spec.label} value="" loading />;
  const valueClass = `${spec.small ? "text-[15px]" : "text-[22px]"} truncate font-semibold tabular-nums ${spec.result ? "text-accent-300" : "text-surface-50"}`;
  const linkValue = spec.onOpen
    ? "underline decoration-dotted decoration-surface-500 underline-offset-4 group-hover:text-accent-300 group-hover:decoration-accent-400"
    : "";
  const body = (
    <>
      <div className="text-surface-400 flex items-center gap-1 text-[10px] font-medium tracking-wide uppercase">
        <span className="truncate">{spec.label}</span>
        {spec.onOpen && <LuChevronRight aria-hidden className="text-accent-400 h-3 w-3 shrink-0" />}
      </div>
      <div className="flex h-[33px] min-w-0 items-center gap-2">
        {spec.dot !== undefined && (
          <span
            aria-hidden
            className="h-2.5 w-2.5 shrink-0 rounded-full"
            style={{ background: spec.dot ?? "var(--color-surface-500)" }}
          />
        )}
        <span className={`${valueClass} ${linkValue}`}>{spec.value}</span>
      </div>
      {spec.detail !== undefined && (
        <div className="text-surface-400 truncate text-[11px]">{spec.detail}</div>
      )}
      {spec.bar && <CapacityBar {...spec.bar} />}
    </>
  );
  const frame =
    "flex min-w-0 flex-col gap-1 border border-surface-700 bg-surface-900 px-4 py-3 text-left";
  if (spec.onOpen) {
    return (
      <button
        type="button"
        onClick={spec.onOpen}
        title={spec.title ?? spec.openLabel}
        aria-label={`${spec.label}: ${spec.value}. ${spec.openLabel ?? ""}`}
        className={`group ${frame} hover:bg-surface-800 focus-visible:outline-accent-400 focus-visible:outline`}
      >
        {body}
      </button>
    );
  }
  return (
    <div className={frame} title={spec.title}>
      {body}
    </div>
  );
}

function CapacityBar({ existing, added }: { existing: number; added: number }) {
  const total = existing + added;
  if (!(total > 0)) return null;
  return (
    <div aria-hidden className="bg-surface-800 mt-0.5 flex h-1 w-full overflow-hidden">
      <i className="bg-surface-400 block" style={{ width: `${(existing / total) * 100}%` }} />
      <i className="bg-accent-400 block" style={{ width: `${(added / total) * 100}%` }} />
    </div>
  );
}

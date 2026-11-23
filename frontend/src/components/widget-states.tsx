// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: MIT

import type { CSSProperties, ReactNode } from "react";
import { LuMapPinOff, LuRotateCw, LuTriangleAlert } from "react-icons/lu";
import { skeletonWidth } from "../features/project/lib/skeleton";

/** How far a widget's data has got. */
export type LoadState =
  | { status: "loading" }
  | { status: "error"; error: string; retry: () => void }
  | { status: "ready"; isRefreshing: boolean };

// What a widget's body shows while its data isn't there: a placeholder
// while it loads, the error with a way to try again, and a thin bar while
// newer data replaces what's on screen.

const SKELETON_BARS = [62, 88, 45, 74, 30, 56, 81, 40];

/** A grey pulsing block standing in for content; size it with `className`. */
export function SkeletonBlock({
  className = "",
  style,
}: {
  className?: string;
  style?: CSSProperties;
}) {
  return (
    <div
      aria-hidden
      style={style}
      className={`bg-surface-800 animate-pulse rounded ${className}`}
    />
  );
}

/** The same, on the sidebar's panels, whose background is the block's colour. */
export function SidebarSkeletonBlock({
  className = "",
  style,
}: {
  className?: string;
  style?: CSSProperties;
}) {
  return (
    <div
      aria-hidden
      style={style}
      className={`bg-surface-700 animate-pulse rounded ${className}`}
    />
  );
}

/** Sidebar list rows (on the sidebar's background) standing in for what's loading: a short bar per row, `indent` px in. */
export function SkeletonRows({
  count,
  indent = 12,
  height = 24,
  label = "Loading",
}: {
  count: number;
  indent?: number;
  height?: number;
  label?: string;
}) {
  return (
    <div role="status" aria-label={label}>
      {Array.from({ length: count }, (_, index) => (
        <div
          key={index}
          style={{ height, paddingLeft: indent }}
          className="flex items-center gap-1.5 pr-3"
        >
          <SidebarSkeletonBlock className="h-3 w-3 shrink-0 rounded-full" />
          <SidebarSkeletonBlock className="h-2.5" style={{ width: skeletonWidth(index) }} />
        </div>
      ))}
    </div>
  );
}

export function WidgetSkeleton() {
  return (
    <div
      role="status"
      aria-label="Loading"
      className="absolute inset-0 flex items-end gap-3 px-2 pt-6 pb-4"
    >
      {SKELETON_BARS.map((height, index) => (
        <div
          key={index}
          className="bg-surface-800 flex-1 animate-pulse rounded-sm"
          style={{ height: `${height}%` }}
        />
      ))}
    </div>
  );
}

export function WidgetError({ error, onRetry }: { error: string; onRetry: () => void }) {
  return (
    <div
      role="alert"
      className="absolute inset-0 flex flex-col items-center justify-center gap-2 px-6 text-center"
    >
      <LuTriangleAlert size={16} className="text-warn-500" />
      <div className="text-surface-200 text-[12px] font-medium">Couldn't load this widget</div>
      <div className="text-surface-400 max-w-md text-[11px]">{error}</div>
      <button
        type="button"
        onClick={onRetry}
        className="border-surface-600 bg-surface-800 text-surface-200 hover:bg-surface-700 focus-visible:border-accent-500 mt-1 flex h-7 items-center gap-1.5 rounded border px-2 text-[12px] font-medium outline-none"
      >
        <LuRotateCw size={12} />
        Try again
      </button>
    </div>
  );
}

/** Along its positioned parent's top edge, or `bottom` (under a header). */
export function RefreshBar({ edge = "top" }: { edge?: "top" | "bottom" }) {
  return (
    <div
      role="status"
      aria-label="Updating"
      className={`bg-accent-500/70 pointer-events-none absolute inset-x-0 z-10 h-0.5 animate-pulse ${edge === "top" ? "top-0" : "-bottom-px"}`}
    />
  );
}

export function WidgetMessage({ children }: { children: string }) {
  return (
    <div className="text-surface-400 absolute inset-0 flex items-center justify-center px-6 text-center text-[12px]">
      {children}
    </div>
  );
}

/** In place of a map that would have nothing on it: no basemap, a plain reason. */
export function WidgetNoMap({ reason, hint }: { reason: string; hint?: string }) {
  return (
    <div
      role="status"
      className="bg-surface-900 absolute inset-0 flex flex-col items-center justify-center gap-2 px-6 text-center"
    >
      <LuMapPinOff size={20} className="text-surface-400" />
      <div className="text-surface-200 text-[12px] font-medium">{reason}</div>
      {hint && <div className="text-surface-400 max-w-80 text-[11px] leading-4">{hint}</div>}
    </div>
  );
}

/** The body for a load state: the children once ready, with the bar while refreshing. */
export function WidgetBody({ state, children }: { state?: LoadState; children: ReactNode }) {
  if (state?.status === "loading") return <WidgetSkeleton />;
  if (state?.status === "error") return <WidgetError error={state.error} onRetry={state.retry} />;
  return (
    <>
      {children}
      {state?.status === "ready" && state.isRefreshing && <RefreshBar />}
    </>
  );
}

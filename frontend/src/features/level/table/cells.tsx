// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import type { MouseEvent, ReactNode } from "react";
import { LuChartLine, LuCheck, LuCopy, LuMapPin } from "react-icons/lu";
import { formatNumber } from "../../project/lib/record-format";
import { useCopyToClipboard } from "../../project/lib/use-copy-to-clipboard";
import { useLevelStore, type PickedSeries } from "../level-store";

// What a table cell shows beyond plain text: links to other levels, the
// carrier dot, status, the map pin, the copy icon and series chips. Every
// control stops its click so the row's own click (open the entity) doesn't
// fire too.

const stop = (handler: () => void) => (event: MouseEvent) => {
  event.stopPropagation();
  handler();
};

/** A link-styled button inside a row. */
export function LinkButton({
  onClick,
  title,
  children,
  mono = false,
}: {
  onClick: () => void;
  title?: string;
  children: ReactNode;
  mono?: boolean;
}) {
  return (
    <button
      type="button"
      title={title}
      onClick={stop(onClick)}
      className={`hover:text-accent-300 focus-visible:text-accent-300 max-w-full truncate text-left outline-none hover:underline ${mono ? "font-mono text-[11.5px]" : ""}`}
    >
      {children}
    </button>
  );
}

export function Dot({ color }: { color: string | null | undefined }) {
  return (
    <span
      aria-hidden
      className="h-2.5 w-2.5 shrink-0 rounded-full border border-black/20"
      style={{ backgroundColor: color ?? "var(--color-surface-500)" }}
    />
  );
}

export function CarrierCell({
  carrier,
  name,
  color,
  onOpen,
}: {
  carrier: string | null;
  name: string;
  color: string | null;
  onOpen?: () => void;
}) {
  return (
    <span className="flex min-w-0 items-center gap-1.5">
      <Dot color={color} />
      {carrier && onOpen ? (
        <LinkButton onClick={onOpen} title={`Open ${name}`}>
          {name}
        </LinkButton>
      ) : (
        <span className="truncate">{name}</span>
      )}
    </span>
  );
}

const STATUS_COLOR: Record<string, string> = {
  existing: "text-emerald-400",
  estimate: "text-amber-400",
  candidate: "text-surface-400",
};

export function StatusCell({ status }: { status: string | null }) {
  if (!status) return <span className="text-surface-500">—</span>;
  return (
    <span className={`flex items-center gap-1.5 ${STATUS_COLOR[status] ?? "text-surface-300"}`}>
      <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-current" />
      {status}
    </span>
  );
}

/** The Geolocated cell: a pin for an entity with a site of its own, "route" for a line with a path. */
export function GeoButton({ entity, kind }: { entity: string; kind: "point" | "route" | null }) {
  const setMapFocus = useLevelStore((s) => s.setMapFocus);
  const focus = useLevelStore((s) => s.mapFocus);
  if (!kind) return null;
  const active = focus?.entity === entity;
  const className = `inline-flex h-5 items-center gap-1 rounded border px-1.5 text-[11px] outline-none focus-visible:border-accent-500 ${
    active
      ? "border-accent-500 bg-accent-600/20 text-accent-200"
      : "border-surface-600 text-surface-300 hover:border-accent-500 hover:text-accent-300"
  }`;
  return kind === "route" ? (
    <button
      type="button"
      title="Show the route on the map"
      aria-label={`Show the route of ${entity} on the map`}
      onClick={stop(() => setMapFocus({ kind: "route", entity }))}
      className={className}
    >
      route
    </button>
  ) : (
    <button
      type="button"
      title="Show on the map"
      aria-label={`Show ${entity} on the map`}
      onClick={stop(() => setMapFocus({ kind: "entity", entity }))}
      className={className}
    >
      <LuMapPin size={11} />
    </button>
  );
}

export function CopyId({ text }: { text: string }) {
  const { copied, copy } = useCopyToClipboard();
  return (
    <button
      type="button"
      title={copied ? "Copied" : "Copy the id"}
      aria-label={`Copy ${text}`}
      onClick={stop(() => copy(text))}
      className="text-surface-500 hover:text-surface-100 focus-visible:ring-accent-500 shrink-0 rounded p-0.5 opacity-0 outline-none group-hover:opacity-100 focus-visible:opacity-100 focus-visible:ring-1"
    >
      {copied ? <LuCheck size={11} /> : <LuCopy size={11} />}
    </button>
  );
}

const samePick = (a: PickedSeries, b: PickedSeries) =>
  a.entity === b.entity && a.attribute === b.attribute && a.bus === b.bus;

/** A series chip: "<attribute> · <n> h" picks the series into the chart drawer, or drops it. */
export function SeriesChip({ series, hours }: { series: PickedSeries; hours: number }) {
  const picked = useLevelStore((s) => s.pickedSeries.some((item) => samePick(item, series)));
  const toggle = useLevelStore((s) => s.togglePickedSeries);
  return (
    <button
      type="button"
      aria-pressed={picked}
      title={picked ? "Remove from the chart" : "Add to the chart"}
      onClick={stop(() => toggle(series))}
      className={`focus-visible:ring-accent-500 inline-flex h-5 max-w-full items-center gap-1 rounded border px-1.5 text-[11px] whitespace-nowrap not-italic outline-none focus-visible:ring-1 ${
        picked
          ? "border-accent-500 bg-accent-600/25 text-accent-100"
          : "border-surface-600 text-accent-300 hover:border-accent-500"
      }`}
    >
      <LuChartLine size={11} className="shrink-0" />
      <span className="truncate">
        {series.attribute} · {formatNumber(Math.round(hours))} h
      </span>
    </button>
  );
}

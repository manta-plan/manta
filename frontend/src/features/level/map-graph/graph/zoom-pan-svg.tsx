// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: MIT

import {
  useEffect,
  useRef,
  useState,
  type MouseEvent,
  type PointerEvent,
  type ReactNode,
} from "react";
import { LuFrame, LuMinus, LuPlus } from "react-icons/lu";

// An SVG the user can zoom (wheel, + and −) and pan (drag), with a reset.
// A drag never counts as a click on what it started on.

type ViewBox = [number, number, number, number];

const MIN_SCALE = 1 / 40;
const MAX_SCALE = 1.6;

export function ZoomPanSvg({
  width,
  height,
  resetKey,
  label,
  children,
}: {
  width: number;
  height: number;
  resetKey: string;
  label: string;
  children: ReactNode;
}) {
  const base: ViewBox = [0, 0, width, height];
  const [view, setView] = useState<ViewBox | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const drag = useRef<{ x: number; y: number; view: ViewBox; moved: boolean } | null>(null);
  const suppressClick = useRef(false);
  const shown = view ?? base;

  // Another graph: its own full view.
  useEffect(() => setView(null), [resetKey]);

  const clamp = (w: number) => Math.min(width * MAX_SCALE, Math.max(width * MIN_SCALE, w));
  /** Zoom by `factor` (<1 in) around a point in viewBox units. */
  const zoomAt = (factor: number, cx: number, cy: number, from = shown) => {
    const w = clamp(from[2] * factor);
    const k = w / from[2];
    const h = from[3] * k;
    setView([cx - (cx - from[0]) * k, cy - (cy - from[1]) * k, w, h]);
  };
  const toView = (clientX: number, clientY: number, from = shown) => {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect || rect.width === 0)
      return { x: from[0] + from[2] / 2, y: from[1] + from[3] / 2, scale: 1 };
    // preserveAspectRatio meet: one scale for both axes.
    const scale = Math.max(from[2] / rect.width, from[3] / rect.height);
    const offsetX = (rect.width * scale - from[2]) / 2;
    const offsetY = (rect.height * scale - from[3]) / 2;
    return {
      x: from[0] - offsetX + (clientX - rect.left) * scale,
      y: from[1] - offsetY + (clientY - rect.top) * scale,
      scale,
    };
  };

  // Wheel zoom (non-passive, so the page doesn't scroll).
  const latest = useRef({ shown, zoomAt, toView });
  useEffect(() => {
    latest.current = { shown, zoomAt, toView };
  });
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const { toView: at, zoomAt: zoom } = latest.current;
      const p = at(event.clientX, event.clientY);
      zoom(Math.exp(event.deltaY * 0.0015), p.x, p.y);
    };
    svg.addEventListener("wheel", onWheel, { passive: false });
    return () => svg.removeEventListener("wheel", onWheel);
  }, []);

  const onPointerDown = (event: PointerEvent<SVGSVGElement>) => {
    if (event.button !== 0) return;
    drag.current = { x: event.clientX, y: event.clientY, view: shown, moved: false };
  };
  const onPointerMove = (event: PointerEvent<SVGSVGElement>) => {
    const start = drag.current;
    if (!start) return;
    const dx = event.clientX - start.x;
    const dy = event.clientY - start.y;
    if (!start.moved && Math.hypot(dx, dy) < 4) return;
    if (!start.moved) {
      start.moved = true;
      event.currentTarget.setPointerCapture(event.pointerId);
    }
    const { scale } = toView(event.clientX, event.clientY, start.view);
    setView([start.view[0] - dx * scale, start.view[1] - dy * scale, start.view[2], start.view[3]]);
  };
  const onPointerUp = () => {
    suppressClick.current = Boolean(drag.current?.moved);
    drag.current = null;
  };
  const onClickCapture = (event: MouseEvent) => {
    if (!suppressClick.current) return;
    suppressClick.current = false;
    event.stopPropagation();
  };

  const centre = () => [shown[0] + shown[2] / 2, shown[1] + shown[3] / 2] as const;
  const button =
    "flex h-7 w-7 items-center justify-center rounded text-surface-200 outline-none hover:bg-surface-700 hover:text-surface-50 focus-visible:ring-1 focus-visible:ring-accent-500 disabled:opacity-40";

  return (
    <div className="bg-surface-950 relative h-full w-full overflow-hidden">
      <svg
        ref={svgRef}
        viewBox={shown.map((n) => n.toFixed(1)).join(" ")}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label={label}
        className="h-full w-full cursor-grab touch-none select-none active:cursor-grabbing"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onClickCapture={onClickCapture}
      >
        {children}
      </svg>
      <div
        role="toolbar"
        aria-label="Graph view"
        aria-orientation="vertical"
        className="border-surface-600 bg-surface-800/95 absolute top-2 right-2 flex w-9 flex-col items-center gap-0.5 rounded-md border p-0.5 shadow-lg shadow-black/30"
      >
        <button
          type="button"
          className={button}
          aria-label="Zoom in"
          title="Zoom in"
          onClick={() => zoomAt(1 / 1.4, ...centre())}
        >
          <LuPlus size={16} strokeWidth={1.75} />
        </button>
        <button
          type="button"
          className={button}
          aria-label="Zoom out"
          title="Zoom out"
          onClick={() => zoomAt(1.4, ...centre())}
        >
          <LuMinus size={16} strokeWidth={1.75} />
        </button>
        <button
          type="button"
          className={`${button} ${view ? "text-accent-400" : ""}`}
          aria-label="Reset the view"
          title="Reset the view"
          disabled={!view}
          onClick={() => setView(null)}
        >
          <LuFrame size={16} strokeWidth={1.75} />
        </button>
      </div>
    </div>
  );
}

import { useEffect, useRef, useState, type PointerEvent } from "react";

// Zoom and pan an element with a CSS transform: wheel zooms around the
// cursor, drag pans, double-click resets. Scale 1 is the element's own
// (fitted) size, so it never shrinks below the box it sits in.

export type ZoomPanView = { scale: number; x: number; y: number };
type Size = { width: number; height: number };

export const IDENTITY_VIEW: ZoomPanView = { scale: 1, x: 0, y: 0 };

/** Keep the scaled content covering its box: no gap on any side. */
export function clampView(view: ZoomPanView, box: Size): ZoomPanView {
  const minX = box.width - box.width * view.scale;
  const minY = box.height - box.height * view.scale;
  return {
    scale: view.scale,
    x: Math.min(0, Math.max(minX, view.x)),
    y: Math.min(0, Math.max(minY, view.y)),
  };
}

/** Zoom to `scale`, keeping the point (px, py) in box coordinates still. */
export function zoomAround(
  view: ZoomPanView,
  scale: number,
  px: number,
  py: number,
  box: Size,
): ZoomPanView {
  const k = scale / view.scale;
  return clampView({ scale, x: px - (px - view.x) * k, y: py - (py - view.y) * k }, box);
}

export function useZoomPan<T extends HTMLElement>({
  minScale = 1,
  maxScale = 6,
  wheelSpeed = 0.0015,
}: { minScale?: number; maxScale?: number; wheelSpeed?: number } = {}) {
  const ref = useRef<T>(null);
  const [view, setView] = useState<ZoomPanView>(IDENTITY_VIEW);
  const drag = useRef<{ x: number; y: number; view: ZoomPanView } | null>(null);

  // Native, non-passive listener: React's wheel handler is passive, so it
  // can't stop the page from scrolling.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const rect = el.getBoundingClientRect();
      setView((prev) => {
        const scale = Math.min(
          maxScale,
          Math.max(minScale, prev.scale * Math.exp(-event.deltaY * wheelSpeed)),
        );
        return zoomAround(prev, scale, event.clientX - rect.left, event.clientY - rect.top, rect);
      });
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [minScale, maxScale, wheelSpeed]);

  const onPointerDown = (event: PointerEvent<T>) => {
    if (event.button !== 0) return;
    drag.current = { x: event.clientX, y: event.clientY, view };
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const onPointerMove = (event: PointerEvent<T>) => {
    const start = drag.current;
    if (!start) return;
    const rect = event.currentTarget.getBoundingClientRect();
    setView(
      clampView(
        {
          scale: start.view.scale,
          x: start.view.x + event.clientX - start.x,
          y: start.view.y + event.clientY - start.y,
        },
        rect,
      ),
    );
  };
  const onPointerUp = () => {
    drag.current = null;
  };

  return {
    ref,
    view,
    reset: () => setView(IDENTITY_VIEW),
    /** Spread on the box that receives the gestures. */
    handlers: {
      onPointerDown,
      onPointerMove,
      onPointerUp,
      onPointerCancel: onPointerUp,
      onDoubleClick: () => setView(IDENTITY_VIEW),
    },
    /** Apply to the content inside the box. */
    contentStyle: {
      transform: `translate(${view.x}px, ${view.y}px) scale(${view.scale})`,
      transformOrigin: "0 0",
    },
  };
}

// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useState, type PointerEvent } from "react";
import { createPortal } from "react-dom";
import { MIN_SELECTION, rectFromPoints, type Rect } from "../lib/capture-region";

/** Full-viewport crosshair overlay: drag to pick a region, Esc to cancel. */
export function RegionSelector({
  onSelect,
  onCancel,
}: {
  onSelect: (rect: Rect) => void;
  onCancel: () => void;
}) {
  const [start, setStart] = useState<{ x: number; y: number } | null>(null);
  const [rect, setRect] = useState<Rect | null>(null);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel]);

  const handleDown = (event: PointerEvent) => {
    event.currentTarget.setPointerCapture(event.pointerId);
    setStart({ x: event.clientX, y: event.clientY });
    setRect(null);
  };

  const handleMove = (event: PointerEvent) => {
    if (start) setRect(rectFromPoints(start, { x: event.clientX, y: event.clientY }));
  };

  const handleUp = (event: PointerEvent) => {
    if (!start) return;
    const final = rectFromPoints(start, { x: event.clientX, y: event.clientY });
    setStart(null);
    if (final.width < MIN_SELECTION || final.height < MIN_SELECTION) onCancel();
    else onSelect(final);
  };

  return createPortal(
    <div
      data-capture-exclude
      onPointerDown={handleDown}
      onPointerMove={handleMove}
      onPointerUp={handleUp}
      className="fixed inset-0 z-[100] cursor-crosshair touch-none select-none"
    >
      {rect ? (
        <div
          className="border-accent-400 pointer-events-none absolute border-2"
          style={{
            left: rect.x,
            top: rect.y,
            width: rect.width,
            height: rect.height,
            // Dims everything outside the selection.
            boxShadow: "0 0 0 9999px rgba(0, 0, 0, 0.5)",
          }}
        />
      ) : (
        <div className="absolute inset-0 bg-black/40" />
      )}
      <div className="pointer-events-none absolute top-4 left-1/2 -translate-x-1/2 rounded bg-black/70 px-3 py-1.5 text-[12px] text-white">
        Drag to select an area · Esc to cancel
      </div>
    </div>,
    document.body,
  );
}

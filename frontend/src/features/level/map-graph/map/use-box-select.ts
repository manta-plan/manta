import { useEffect, useRef, useState, type RefObject } from "react";
import type { MapRef } from "react-map-gl/maplibre";
import type { LngLat } from "./map-geo";

// Box selection: Shift+drag adds every location whose point falls in the
// box; with "Select locations" on, a plain drag replaces the selection.

export interface SelectBox {
  left: number;
  top: number;
  width: number;
  height: number;
}

export function useBoxSelect({
  mapRef,
  isLoaded,
  isSelecting,
  points,
  selected,
  onSelect,
}: {
  mapRef: RefObject<MapRef | null>;
  isLoaded: boolean;
  isSelecting: boolean;
  points: Map<string, LngLat>;
  selected: string[];
  onSelect: (locations: string[]) => void;
}): SelectBox | null {
  const [box, setBox] = useState<SelectBox | null>(null);
  // The latest values for the native listeners.
  const latest = useRef({ isSelecting, points, selected, onSelect });
  useEffect(() => {
    latest.current = { isSelecting, points, selected, onSelect };
  });

  useEffect(() => {
    const map = mapRef.current?.getMap();
    if (!isLoaded || !map) return;
    const container = map.getCanvasContainer();
    let start: { x: number; y: number; add: boolean } | null = null;

    const local = (event: MouseEvent) => {
      const rect = container.getBoundingClientRect();
      return { x: event.clientX - rect.left, y: event.clientY - rect.top };
    };
    const boxFrom = (a: { x: number; y: number }, b: { x: number; y: number }): SelectBox => ({
      left: Math.min(a.x, b.x),
      top: Math.min(a.y, b.y),
      width: Math.abs(a.x - b.x),
      height: Math.abs(a.y - b.y),
    });

    const onMove = (event: MouseEvent) => {
      if (start) setBox(boxFrom(start, local(event)));
    };
    const onUp = (event: MouseEvent) => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      if (!start) return;
      const area = boxFrom(start, local(event));
      const add = start.add;
      start = null;
      setBox(null);
      if (!latest.current.isSelecting) map.dragPan.enable();
      if (area.width < 4 && area.height < 4) return;
      const inside: string[] = [];
      for (const [location, point] of latest.current.points) {
        const { x, y } = map.project(point);
        if (
          x >= area.left &&
          x <= area.left + area.width &&
          y >= area.top &&
          y <= area.top + area.height
        )
          inside.push(location);
      }
      latest.current.onSelect(add ? [...latest.current.selected, ...inside] : inside);
    };
    const onDown = (event: MouseEvent) => {
      if (event.button !== 0 || !(event.shiftKey || latest.current.isSelecting)) return;
      event.preventDefault();
      event.stopPropagation();
      map.dragPan.disable();
      start = { ...local(event), add: event.shiftKey };
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    };
    // Capture, so a Shift+drag never starts a pan.
    container.addEventListener("mousedown", onDown, true);
    return () => {
      container.removeEventListener("mousedown", onDown, true);
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [isLoaded, mapRef]);

  return box;
}

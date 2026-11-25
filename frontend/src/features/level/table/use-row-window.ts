// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useState, type RefObject } from "react";

// Which rows of a long table are in view: only those (and a few around them)
// render, so a level of thousands of entities scrolls as lightly as one of
// ten. Rows have one fixed height.

export const ROW_HEIGHT = 27;
const OVERSCAN = 12;

/** The rows [start, end) to render for a scroll position, viewport height and row count. */
export function rowRange(
  top: number,
  height: number,
  count: number,
): { start: number; end: number } {
  const start = Math.max(0, Math.floor(top / ROW_HEIGHT) - OVERSCAN);
  const end = Math.min(count, Math.ceil((top + height) / ROW_HEIGHT) + OVERSCAN);
  return { start, end };
}

export function useRowWindow(
  ref: RefObject<HTMLElement | null>,
  count: number,
): { start: number; end: number } {
  const [view, setView] = useState({ top: 0, height: 600 });
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const update = () =>
      setView((current) =>
        current.top === element.scrollTop && current.height === element.clientHeight
          ? current
          : { top: element.scrollTop, height: element.clientHeight },
      );
    update();
    element.addEventListener("scroll", update, { passive: true });
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => {
      element.removeEventListener("scroll", update);
      observer.disconnect();
    };
  }, [ref]);
  return rowRange(view.top, view.height, count);
}

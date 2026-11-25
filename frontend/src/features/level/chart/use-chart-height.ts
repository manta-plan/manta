// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useState } from "react";
import { useInFullscreen } from "../fullscreen/fullscreen-context";

// A chart's height: as given on the page; full screen, grown so a full-size
// chart (240px on the page) fills the dialog under the drawer's bar, others
// in proportion (stacked plots of several units still share it).

const FULL = 240;
/** The dialog is 92vh tall; this much of it is the bar, caption and hint. */
const CHROME = 150;

function dialogSpace() {
  return Math.round(window.innerHeight * 0.92 - CHROME);
}

export function useChartHeight(height: number): number {
  const inDialog = useInFullscreen();
  const [space, setSpace] = useState(dialogSpace);
  useEffect(() => {
    if (!inDialog) return;
    const onResize = () => setSpace(dialogSpace());
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [inDialog]);
  return inDialog ? Math.max(height, Math.round((space * height) / FULL)) : height;
}

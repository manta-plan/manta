// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { createContext, useContext } from "react";
import type { ReportTheme } from "../data/report-themes";
import { useAppStore } from "../../home/store";

// How a widget is shown. On an inspection page there's no context and a
// widget is a live card in the app's theme; a report block provides one, so
// the same widget draws bare (no card actions), fills its block, and keeps
// to the report's own colors instead of the app's light or dark mode.

export type ColorScheme = "light" | "dark";

export interface WidgetPresentation {
  mode: "report";
  scheme: ColorScheme;
  theme: ReportTheme;
  /** Shown in place of the widget's own title. */
  title?: string;
  /** The result the widget shows, kept after a custom title so the reader still sees it. */
  resultLabel?: string;
}

export const WidgetPresentationContext = createContext<WidgetPresentation | null>(null);

export function useWidgetPresentation() {
  return useContext(WidgetPresentationContext);
}

/** The report theme a widget is drawn in, if it's in a report. */
export function useWidgetTheme(): ReportTheme | null {
  return useContext(WidgetPresentationContext)?.theme ?? null;
}

/** The scheme a widget's charts and maps draw in. */
export function useWidgetColorScheme(): ColorScheme {
  const appTheme = useAppStore((s) => s.theme);
  return useContext(WidgetPresentationContext)?.scheme ?? appTheme;
}

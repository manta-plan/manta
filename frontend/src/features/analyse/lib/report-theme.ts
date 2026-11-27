// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import type { CSSProperties } from "react";
import type { EChartsOption } from "echarts";
import { CARD_SHADOWS, FONT_STACKS, type ReportTheme } from "../data/report-themes";
import { mixHex } from "./color-util";

// Turning a theme into what draws it: CSS variables on the page (the app's
// own neutral and accent tokens, redefined for the page's subtree, so every
// component inside re-themes without knowing), and colours for the charts,
// which paint to canvas and can't read CSS variables.

/** The theme as inline CSS variables, to set on the page element. */
export function reportThemeStyle(theme: ReportTheme): CSSProperties {
  const { text, mutedText, background, accent, card } = theme;
  const vars: Record<string, string> = {
    // Neutrals, strongest text to the page itself. Cards are surface-900.
    "--color-surface-50": text,
    "--color-surface-100": text,
    "--color-surface-200": mixHex(text, mutedText, 0.5),
    "--color-surface-300": mutedText,
    "--color-surface-400": mixHex(mutedText, background, 0.35),
    "--color-surface-500": mixHex(card.border, text, 0.3),
    "--color-surface-600": mixHex(card.border, text, 0.12),
    "--color-surface-700": card.border,
    "--color-surface-800": background,
    "--color-surface-900": card.background,
    "--color-surface-950": background,
    // The lighter accents are for text on dark; on a light page they go dark enough to read.
    "--color-accent-300":
      theme.scheme === "dark" ? mixHex(accent, "#ffffff", 0.5) : mixHex(accent, "#000000", 0.1),
    "--color-accent-400": theme.scheme === "dark" ? mixHex(accent, "#ffffff", 0.25) : accent,
    "--color-accent-500": accent,
    "--color-accent-600": mixHex(accent, "#000000", 0.15),
    "--color-accent-700": mixHex(accent, "#000000", 0.35),
    "--report-card-background": card.background,
    "--report-card-border": card.border,
    "--report-card-radius": `${card.radius}px`,
    "--report-card-shadow": CARD_SHADOWS[card.shadow],
    "--report-font-heading": FONT_STACKS[theme.fonts.heading].stack,
    "--report-font-body": FONT_STACKS[theme.fonts.body].stack,
  };
  return {
    ...(vars as CSSProperties),
    backgroundColor: background,
    color: text,
    fontFamily: FONT_STACKS[theme.fonts.body].stack,
  };
}

/** What charts draw their text, axes and tooltips in. */
export function themedChartColors(theme: ReportTheme) {
  return {
    text: theme.mutedText,
    axisLine: theme.card.border,
    splitLine: mixHex(theme.card.border, theme.card.background, 0.5),
    tooltipBackground: theme.card.background,
    strongText: theme.text,
  };
}

function swapColor(value: unknown, from: string, to: string): unknown {
  if (typeof value === "string") return value.toLowerCase() === from ? to : value;
  if (Array.isArray(value)) return value.map((item) => swapColor(item, from, to));
  if (value && typeof value === "object" && Object.getPrototypeOf(value) === Object.prototype) {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [key, swapColor(item, from, to)]),
    );
  }
  return value;
}

/**
 * A chart option in the theme's colours. The widgets' neutral series colour
 * becomes the palette's first colour and any series without a colour of its
 * own takes the palette in turn; semantic colours, like a carrier's, stay.
 */
export function paintChartOption(
  option: EChartsOption,
  theme: ReportTheme,
  neutralColor: string,
): EChartsOption {
  const painted = swapColor(option, neutralColor.toLowerCase(), theme.palette[0]) as EChartsOption;
  return {
    color: theme.palette,
    textStyle: { fontFamily: FONT_STACKS[theme.fonts.body].stack },
    ...painted,
  };
}

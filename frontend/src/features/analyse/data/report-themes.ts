// A report's look as plain data: colours, fonts and how cards are drawn. A
// theme is stored inside the report (a copy of a preset, then edited), so
// changing a preset later never alters a saved report.

export type FontKey = "sans" | "serif" | "humanist" | "mono";

// System stacks only: nothing to download, and they print as they look.
export const FONT_STACKS: Record<FontKey, { label: string; stack: string }> = {
  sans: {
    label: "Sans",
    stack: "ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
  },
  serif: {
    label: "Serif",
    stack: "'Iowan Old Style', 'Palatino Linotype', Palatino, Georgia, serif",
  },
  humanist: {
    label: "Humanist",
    stack: "Optima, Candara, 'Gill Sans', 'Trebuchet MS', sans-serif",
  },
  mono: { label: "Mono", stack: "ui-monospace, 'SF Mono', Menlo, Consolas, monospace" },
};

export type CardShadow = "none" | "soft" | "strong";

export const CARD_SHADOWS: Record<CardShadow, string> = {
  none: "none",
  soft: "0 1px 3px rgb(0 0 0 / 0.14)",
  strong: "0 6px 18px rgb(0 0 0 / 0.22)",
};

export type HeaderStyle = "none" | "band" | "rule";
export type Backdrop = "none" | "wash" | "corner" | "stripe" | "dots";
export type LogoPosition = "header-right" | "footer-left" | "footer-right";

export const BACKDROP_LABELS: Record<Backdrop, string> = {
  none: "None",
  wash: "Soft wash",
  corner: "Corner",
  stripe: "Side stripe",
  dots: "Dots",
};
export const LOGO_POSITION_LABELS: Record<LogoPosition, string> = {
  "header-right": "Header",
  "footer-left": "Footer left",
  "footer-right": "Footer right",
};

/** What goes on every page around the blocks: in the margins and behind the content. */
export interface ReportDecoration {
  header: { style: HeaderStyle; showTitle: boolean };
  footer: { rule: boolean; pageNumbers: boolean; text: string };
  backdrop: Backdrop;
  /** The image is stored in the report, as a data URL. */
  logo: { src: string; alt: string; position: LogoPosition } | null;
}

export interface ReportTheme {
  /** The preset it began as; the editor offers to reset to it. */
  id: string;
  name: string;
  /** Light or dark base: it sets the neutral shades, the maps' basemap and what charts assume. */
  scheme: "light" | "dark";
  background: string;
  text: string;
  mutedText: string;
  accent: string;
  /** Series colours for charts whose series have no colour of their own. */
  palette: string[];
  card: { background: string; border: string; radius: number; shadow: CardShadow };
  fonts: { heading: FontKey; body: FontKey };
  decoration: ReportDecoration;
}

export const REPORT_THEME_PRESETS: ReportTheme[] = [
  {
    id: "paper",
    name: "Paper",
    scheme: "light",
    background: "#ffffff",
    text: "#0f172a",
    mutedText: "#64748b",
    accent: "#2563eb",
    palette: [
      "#2f6fdc",
      "#d9a521",
      "#3fa86a",
      "#3a9c92",
      "#8d6bd1",
      "#d4693a",
      "#6b7a8f",
      "#c04f7a",
    ],
    card: { background: "#f8fafc", border: "#e2e8f0", radius: 4, shadow: "none" },
    fonts: { heading: "sans", body: "sans" },
    decoration: {
      header: { style: "none", showTitle: false },
      footer: { rule: false, pageNumbers: true, text: "" },
      backdrop: "none",
      logo: null,
    },
  },
  {
    id: "midnight",
    name: "Midnight",
    scheme: "dark",
    background: "#0b1626",
    text: "#e6eef6",
    mutedText: "#8da4bd",
    accent: "#5699ff",
    palette: [
      "#5699ff",
      "#f0b429",
      "#4cc38a",
      "#3fc1c9",
      "#a78bfa",
      "#ff8a5b",
      "#9fb3c8",
      "#ef6f9f",
    ],
    card: { background: "#12233a", border: "#22405f", radius: 8, shadow: "soft" },
    fonts: { heading: "sans", body: "sans" },
    decoration: {
      header: { style: "band", showTitle: true },
      footer: { rule: false, pageNumbers: true, text: "" },
      backdrop: "wash",
      logo: null,
    },
  },
  {
    id: "editorial",
    name: "Editorial",
    scheme: "light",
    background: "#fbf8f3",
    text: "#2b2118",
    mutedText: "#7a6a58",
    accent: "#b4452c",
    palette: [
      "#b4452c",
      "#d79a3a",
      "#6f8f4e",
      "#3f7f86",
      "#7a5c8e",
      "#c9764f",
      "#8a7a68",
      "#a33a5a",
    ],
    card: { background: "#ffffff", border: "#e7ddd0", radius: 2, shadow: "none" },
    fonts: { heading: "serif", body: "sans" },
    decoration: {
      header: { style: "rule", showTitle: true },
      footer: { rule: true, pageNumbers: true, text: "" },
      backdrop: "none",
      logo: null,
    },
  },
  {
    id: "forest",
    name: "Forest",
    scheme: "light",
    background: "#f4f8f4",
    text: "#12301f",
    mutedText: "#55715f",
    accent: "#2f855a",
    palette: [
      "#2f855a",
      "#c99a2e",
      "#3b82a0",
      "#7aa93c",
      "#8f6bb3",
      "#d0713e",
      "#5f8a7a",
      "#b8506b",
    ],
    card: { background: "#ffffff", border: "#d3e4d8", radius: 10, shadow: "soft" },
    fonts: { heading: "humanist", body: "humanist" },
    decoration: {
      header: { style: "band", showTitle: false },
      footer: { rule: false, pageNumbers: true, text: "" },
      backdrop: "corner",
      logo: null,
    },
  },
  {
    id: "ledger",
    name: "Ledger",
    scheme: "light",
    background: "#ffffff",
    text: "#111111",
    mutedText: "#666666",
    accent: "#111111",
    palette: [
      "#111827",
      "#6b7280",
      "#b91c1c",
      "#9ca3af",
      "#1d4ed8",
      "#4b5563",
      "#d1d5db",
      "#047857",
    ],
    card: { background: "#ffffff", border: "#111111", radius: 0, shadow: "none" },
    fonts: { heading: "mono", body: "sans" },
    decoration: {
      header: { style: "rule", showTitle: true },
      footer: { rule: true, pageNumbers: true, text: "" },
      backdrop: "none",
      logo: null,
    },
  },
];

export const DEFAULT_REPORT_THEME = REPORT_THEME_PRESETS[0];

export function presetTheme(id: string): ReportTheme {
  return structuredClone(
    REPORT_THEME_PRESETS.find((preset) => preset.id === id) ?? DEFAULT_REPORT_THEME,
  );
}

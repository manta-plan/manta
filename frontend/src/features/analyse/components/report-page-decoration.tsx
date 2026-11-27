// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import type { CSSProperties } from "react";
import type { Backdrop, ReportTheme } from "../data/report-themes";

const ACCENT = "var(--color-accent-500)";
const accentAt = (percent: number) => `color-mix(in srgb, ${ACCENT} ${percent}%, transparent)`;

/** The patterns drawn behind the blocks, from the theme's accent. */
function backdropStyle(backdrop: Backdrop, width: number, height: number): CSSProperties | null {
  switch (backdrop) {
    case "none":
      return null;
    case "wash":
      return {
        background: `radial-gradient(90% 55% at 100% 0%, ${accentAt(16)}, transparent 70%), radial-gradient(70% 40% at 0% 100%, ${accentAt(9)}, transparent 70%)`,
      };
    case "stripe":
      return {
        background: `linear-gradient(to right, ${ACCENT} 0 8px, ${accentAt(35)} 8px 11px, transparent 11px)`,
      };
    case "dots":
      return {
        backgroundImage: `radial-gradient(${accentAt(40)} 1.6px, transparent 1.8px)`,
        backgroundSize: "14px 14px",
        WebkitMaskImage: "linear-gradient(225deg, black, transparent 55%)",
        maskImage: "linear-gradient(225deg, black, transparent 55%)",
        width: Math.min(width, 320),
        height: Math.min(height, 320),
        left: "auto",
        bottom: "auto",
      };
    case "corner":
      return null;
  }
}

/**
 * What a page carries around its blocks, from the report's theme: a backdrop
 * behind them, a header and a footer in the margins, and the logo. It sits
 * under the blocks and takes no pointer events.
 */
export function ReportPageDecoration({
  theme,
  width,
  height,
  reportName,
  pageNumber,
  pageCount,
}: {
  theme: ReportTheme;
  width: number;
  height: number;
  reportName: string;
  pageNumber: number;
  pageCount: number;
}) {
  const { header, footer, backdrop, logo } = theme.decoration;
  const backdropCss = backdropStyle(backdrop, width, height);
  const logoImage = logo && (
    <img src={logo.src} alt={logo.alt} className="h-5 max-w-[96px] object-contain" />
  );

  return (
    <div aria-hidden className="pointer-events-none absolute inset-0">
      {backdropCss && <div className="absolute inset-0" style={backdropCss} />}
      {backdrop === "corner" && (
        <>
          <div
            className="absolute top-0 right-0"
            style={{
              width: 150,
              height: 150,
              background: accentAt(85),
              clipPath: "polygon(0 0, 100% 0, 100% 100%)",
            }}
          />
          <div
            className="absolute top-0 right-0"
            style={{
              width: 230,
              height: 230,
              background: accentAt(18),
              clipPath: "polygon(0 0, 100% 0, 100% 100%)",
            }}
          />
        </>
      )}

      {header.style === "band" && (
        <div className="absolute top-0 right-0 left-0 h-3" style={{ background: ACCENT }} />
      )}
      {header.style === "rule" && (
        <div className="absolute right-12 left-12 h-0.5" style={{ top: 42, background: ACCENT }} />
      )}
      {(header.showTitle || logo?.position === "header-right") && (
        <div
          className="absolute right-12 left-12 flex items-center justify-between gap-3"
          style={{ top: 18, height: 20 }}
        >
          <span className="text-surface-300 truncate text-[10px] font-medium tracking-[0.12em] uppercase">
            {header.showTitle ? reportName : ""}
          </span>
          {logo?.position === "header-right" && logoImage}
        </div>
      )}

      {footer.rule && (
        <div className="bg-surface-600 absolute right-12 left-12 h-px" style={{ bottom: 42 }} />
      )}
      {(footer.pageNumbers ||
        footer.text ||
        logo?.position === "footer-left" ||
        logo?.position === "footer-right") && (
        <div
          className="text-surface-300 absolute right-12 left-12 flex items-center gap-3 text-[10px]"
          style={{ bottom: 18, height: 20 }}
        >
          {logo?.position === "footer-left" && logoImage}
          <span className="min-w-0 flex-1 truncate">{footer.text}</span>
          {footer.pageNumbers && (
            <span className="shrink-0 tabular-nums">
              Page {pageNumber} of {pageCount}
            </span>
          )}
          {logo?.position === "footer-right" && logoImage}
        </div>
      )}
    </div>
  );
}

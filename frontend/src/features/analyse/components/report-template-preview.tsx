// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import type { PageSetup, ReportBlock } from "../data/reports";
import { blockBox, pageMetrics } from "../lib/report-layout";

const KIND_STYLE: Record<ReportBlock["content"]["kind"], string> = {
  widget: "bg-accent-500/30 border border-accent-500/60",
  heading: "bg-surface-200",
  text: "bg-surface-400/60",
  divider: "bg-surface-500",
  image: "bg-surface-500",
  shape: "bg-accent-500/40",
};

/** A page's first sheet as a few coloured boxes, to tell layouts apart at a glance. */
export function ReportTemplatePreview({
  blocks,
  setup,
  widthPx = 56,
}: {
  blocks: ReportBlock[];
  setup: PageSetup;
  widthPx?: number;
}) {
  const metrics = pageMetrics(setup);
  const scale = widthPx / metrics.width;
  return (
    <div
      aria-hidden
      className="border-surface-500 bg-surface-950 relative shrink-0 overflow-hidden rounded-[2px] border"
      style={{ width: widthPx, height: metrics.height * scale }}
    >
      {blocks.map((block) => {
        const box = blockBox(block.rect, metrics);
        return (
          <div
            key={block.id}
            className={`absolute rounded-[1px] ${KIND_STYLE[block.content.kind]}`}
            style={{
              left: box.left * scale,
              top: box.top * scale,
              width: box.width * scale,
              height: box.height * scale,
            }}
          />
        );
      })}
    </div>
  );
}

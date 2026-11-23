// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: MIT

import { useCallback } from "react";
import { formatNumber } from "../../project/lib/record-format";
import { useProjectStore } from "../../project/store/project-store";

// Small helpers the table's cells share.

/** A carrier's nice name and colour. */
export function useCarrierInfo() {
  const carriers = useProjectStore((s) => s.record?.carriers);
  return useCallback(
    (carrier: string | null) => ({
      name: carrier ? carriers?.[carrier]?.niceName || carrier : "—",
      color: carrier ? (carriers?.[carrier]?.color ?? null) : null,
    }),
    [carriers],
  );
}

/** A number for a cell: rounded to what the eye can use. */
export function formatCell(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  const scale = 10 ** digits;
  return formatNumber(
    Math.abs(value) >= 100 ? Math.round(value) : Math.round(value * scale) / scale,
  );
}

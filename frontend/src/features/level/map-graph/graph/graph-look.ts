// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: MIT

import { useProjectStore } from "../../../project/store/project-store";
import { LINE } from "./graph-parts";

// Carrier colours and names, and short ids, for the graphs' labels.

/** A carrier's colour and name, from the record. */
export function useCarrierLook() {
  const carriers = useProjectStore((s) => s.record?.carriers);
  return {
    color: (carrier: string | null) => (carrier && carriers?.[carrier]?.color) || LINE,
    name: (carrier: string | null) =>
      carrier ? carriers?.[carrier]?.niceName || carrier : "no carrier",
  };
}

/** An id cut to `max` characters, for labels. */
export function shortId(id: string, max = 18): string {
  return id.length > max ? `${id.slice(0, max - 1)}…` : id;
}

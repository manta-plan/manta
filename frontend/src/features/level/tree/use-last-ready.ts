// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: MIT

import { useState } from "react";
import type { ShownData } from "../../project/lib/record-data";

/**
 * The read's data, or the last data it had while newer loads (another
 * period): the tree keeps its rows and open folders instead of blinking to
 * a skeleton. Null until the first read arrives.
 */
export function useLastReady<T>(state: ShownData<T>): T | null {
  const [last, setLast] = useState<T | null>(null);
  const ready = state.status === "ready" ? state.data : null;
  // Derived state, set during render (React's documented pattern).
  if (ready !== null && ready !== last) setLast(ready);
  return ready ?? last;
}

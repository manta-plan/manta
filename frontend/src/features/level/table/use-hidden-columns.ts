import { useCallback, useState } from "react";

// Hidden columns, remembered by header across levels in this browser.

const STORAGE_KEY = "level-table-hidden-columns";

function readHidden(): string[] {
  try {
    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]") as unknown;
    return Array.isArray(stored)
      ? stored.filter((item): item is string => typeof item === "string")
      : [];
  } catch {
    return [];
  }
}

function writeHidden(hidden: string[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(hidden));
  } catch {
    // Storage off (a private window): the choice lasts this session.
  }
}

export function useHiddenColumns() {
  const [hidden, setHidden] = useState<string[]>(readHidden);
  const update = useCallback((next: string[]) => {
    setHidden(next);
    writeHidden(next);
  }, []);
  return { hidden: new Set(hidden), setHidden: update, all: hidden };
}

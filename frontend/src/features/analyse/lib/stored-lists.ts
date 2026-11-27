// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

// A project's views and reports are saved as one list per project in this
// browser's storage, which every open tab of the app shares. A tab saving its
// whole list would drop what another tab added since it loaded, so a save
// merges: this tab's items, then the stored ones it doesn't have (unless it
// deleted them). Two tabs changing the same item still keep the last save.

const deletedIds = new Set<string>();

/** Remembers that this tab deleted an item, so a save doesn't bring it back from storage. */
export function markDeleted(id: string) {
  deletedIds.add(id);
}

export function mergeWithStored<T extends { id: string }>(mine: T[], stored: T[] | undefined): T[] {
  const ids = new Set(mine.map((item) => item.id));
  return [
    ...mine,
    ...(stored ?? []).filter((item) => !ids.has(item.id) && !deletedIds.has(item.id)),
  ];
}

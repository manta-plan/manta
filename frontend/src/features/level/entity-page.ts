// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

// One entity's page id, where an inspection's would go (the level page reads it).

// ------------------------------------------------------------ Page ids

const PREFIX = "entity:";

/** The page's id where an inspection's would go: /inspect/entity:<id>, the id encoded (it holds spaces and slashes). */
export function entityPageId(entity: string) {
  return `${PREFIX}${encodeURIComponent(entity)}`;
}

export function entityOfPageId(id: string | null | undefined): string | null {
  if (!id?.startsWith(PREFIX)) return null;
  const encoded = id.slice(PREFIX.length);
  try {
    return decodeURIComponent(encoded);
  } catch {
    return encoded;
  }
}

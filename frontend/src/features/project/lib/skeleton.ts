// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

// Widths for skeleton rows of names, varied so a list of them reads as a list.
const SKELETON_WIDTHS = [58, 72, 44, 66, 51, 79, 39, 62];

/** One width from a repeating set, for the `index`th placeholder row. */
export function skeletonWidth(index: number): string {
  return `${SKELETON_WIDTHS[index % SKELETON_WIDTHS.length]}%`;
}

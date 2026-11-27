// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

// Small colour helpers for deriving shades from a theme's few base colours.

function channels(hex: string): [number, number, number] {
  const value = hex.replace("#", "");
  const full =
    value.length === 3
      ? value
          .split("")
          .map((c) => c + c)
          .join("")
      : value;
  return [
    parseInt(full.slice(0, 2), 16),
    parseInt(full.slice(2, 4), 16),
    parseInt(full.slice(4, 6), 16),
  ];
}

/** `from` moved `amount` (0 to 1) of the way towards `to`, as a hex colour. */
export function mixHex(from: string, to: string, amount: number): string {
  const [a, b] = [channels(from), channels(to)];
  return (
    "#" +
    a
      .map((channel, index) =>
        Math.round(channel + (b[index] - channel) * amount)
          .toString(16)
          .padStart(2, "0"),
      )
      .join("")
  );
}

export function isHexColor(value: string): boolean {
  return /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.test(value);
}

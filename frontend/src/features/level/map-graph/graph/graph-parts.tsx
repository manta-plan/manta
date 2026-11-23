// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: MIT

import type { KeyboardEvent, ReactNode } from "react";

// Pieces both graphs draw with.

export const MUTED = "#64748b";
export const LINE = "#94a3b8";
export const FOCUS = "#5699ff";
export const HALO = "#38bdf8";

/** A clickable part of a graph: a button to the keyboard and screen readers, with a tooltip. */
export function Hit({
  label,
  onActivate,
  opacity = 1,
  children,
}: {
  label: string;
  onActivate: () => void;
  opacity?: number;
  children: ReactNode;
}) {
  const onKeyDown = (event: KeyboardEvent<SVGGElement>) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    onActivate();
  };
  return (
    <g
      role="button"
      tabIndex={0}
      aria-label={label}
      onClick={onActivate}
      onKeyDown={onKeyDown}
      opacity={opacity}
      className="cursor-pointer outline-none focus-visible:[&>*]:stroke-sky-400"
    >
      <title>{label}</title>
      {children}
    </g>
  );
}

/** A shape per component type: Load a diamond, stores a square, the rest a circle. */
export function EntityShape({
  ctype,
  x,
  y,
  size,
  color,
}: {
  ctype: string;
  x: number;
  y: number;
  size: number;
  color: string;
}) {
  if (ctype === "Load")
    return (
      <rect
        x={x - size}
        y={y - size}
        width={size * 2}
        height={size * 2}
        transform={`rotate(45 ${x} ${y})`}
        fill={color}
      />
    );
  if (ctype === "Store" || ctype === "StorageUnit")
    return (
      <rect x={x - size} y={y - size} width={size * 2} height={size * 2} rx={2} fill={color} />
    );
  return <circle cx={x} cy={y} r={size + 1} fill={color} />;
}

// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { Popover } from "@base-ui/react/popover";
import { useState, type ReactNode } from "react";
import { LuLayers } from "react-icons/lu";
import {
  LINE_COLOURING_OPTIONS,
  REGION_SHADING_ROWS,
  useMapLayerStore,
  type LayerOption,
} from "./map-layer-store";

// "Map layers": topology and siting on or off, one region shading and one
// line colouring. Options read from run results are greyed out in Build.

const NEEDS_RESULTS = "Needs results: switch to Inspect";

function Group({ title, note, children }: { title: string; note: string; children: ReactNode }) {
  return (
    <div className="border-surface-700 flex flex-col gap-1 border-t pt-2">
      <div className="flex items-baseline gap-2">
        <span className="text-surface-100 text-[11px] font-semibold">{title}</span>
        <span className="text-surface-500 text-[10px]">{note}</span>
      </div>
      {children}
    </div>
  );
}

function Radio<T extends string>({
  name,
  option,
  checked,
  withResults,
  onPick,
}: {
  name: string;
  option: LayerOption<T>;
  checked: boolean;
  withResults: boolean;
  onPick: (id: T) => void;
}) {
  const disabled = Boolean(option.needsResults) && !withResults;
  return (
    <label
      title={disabled ? NEEDS_RESULTS : undefined}
      className={`flex items-center gap-1 ${disabled ? "text-surface-600 cursor-not-allowed" : "text-surface-200 hover:text-surface-50 cursor-pointer"}`}
    >
      <input
        type="radio"
        name={name}
        checked={checked && !disabled}
        disabled={disabled}
        onChange={() => onPick(option.id)}
        className="accent-accent-500"
      />
      {option.label}
    </label>
  );
}

export function MapLayersPopover({ withResults }: { withResults: boolean }) {
  const [open, setOpen] = useState(false);
  const layers = useMapLayerStore();
  const anyColour = layers.regionShading !== null || layers.lineColouring !== null;

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger
        aria-label="Map layers"
        title="Map layers"
        className={`focus-visible:ring-accent-500 flex h-7 w-7 items-center justify-center rounded transition-colors outline-none focus-visible:ring-1 ${
          open
            ? "bg-accent-600 text-white"
            : anyColour
              ? "text-accent-400 hover:bg-surface-700"
              : "text-surface-200 hover:bg-surface-700 hover:text-surface-50"
        }`}
      >
        <LuLayers size={16} strokeWidth={1.75} />
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Positioner className="z-50 outline-none" side="left" align="start" sideOffset={8}>
          <Popover.Popup
            aria-label="Map layers"
            className="border-surface-600 bg-surface-800 text-surface-200 flex w-80 flex-col gap-2 rounded-md border p-3 text-[11px] shadow-2xl shadow-black/50 outline-none"
          >
            <div className="text-surface-50 text-[12px] font-semibold">Map layers</div>
            <Group title="Topology" note="buses, lines and links to buses">
              <label className="flex cursor-pointer items-center gap-1.5">
                <input
                  type="checkbox"
                  checked={layers.showTopology}
                  onChange={(event) => layers.setShowTopology(event.target.checked)}
                  className="accent-accent-500"
                />
                Show
              </label>
            </Group>
            <Group title="Entity siting" note="located plants; the focused entity stays">
              <label className="flex cursor-pointer items-center gap-1.5">
                <input
                  type="checkbox"
                  checked={layers.showSiting}
                  onChange={(event) => layers.setShowSiting(event.target.checked)}
                  className="accent-accent-500"
                />
                Show
              </label>
            </Group>
            <Group title="Region shading" note="pick one">
              <div role="radiogroup" aria-label="Region shading" className="flex flex-col gap-1">
                <label className="flex cursor-pointer items-center gap-1">
                  <input
                    type="radio"
                    name="region-shading"
                    checked={layers.regionShading === null}
                    onChange={() => layers.setRegionShading(null)}
                    className="accent-accent-500"
                  />
                  Off
                </label>
                {REGION_SHADING_ROWS.map(({ row, options }) => (
                  <div key={row} className="grid grid-cols-[5rem_1fr] items-center">
                    <span className="text-surface-400">{row}</span>
                    <span className="flex flex-wrap gap-x-3">
                      {options.map((option) => (
                        <Radio
                          key={option.id}
                          name="region-shading"
                          option={option}
                          checked={layers.regionShading === option.id}
                          withResults={withResults}
                          onPick={layers.setRegionShading}
                        />
                      ))}
                    </span>
                  </div>
                ))}
              </div>
            </Group>
            <Group title="Line colouring" note="shows lines even with topology off">
              <div role="radiogroup" aria-label="Line colouring" className="flex flex-wrap gap-x-3">
                <label className="flex cursor-pointer items-center gap-1">
                  <input
                    type="radio"
                    name="line-colouring"
                    checked={layers.lineColouring === null}
                    onChange={() => layers.setLineColouring(null)}
                    className="accent-accent-500"
                  />
                  Off
                </label>
                {LINE_COLOURING_OPTIONS.map((option) => (
                  <Radio
                    key={option.id}
                    name="line-colouring"
                    option={option}
                    checked={layers.lineColouring === option.id}
                    withResults={withResults}
                    onPick={layers.setLineColouring}
                  />
                ))}
              </div>
            </Group>
            <p className="text-surface-500 text-[10px]">
              Highlights and the focused entity always draw on top. Greyed-out options need run
              results, so they work only in Inspect.
            </p>
          </Popover.Popup>
        </Popover.Positioner>
      </Popover.Portal>
    </Popover.Root>
  );
}

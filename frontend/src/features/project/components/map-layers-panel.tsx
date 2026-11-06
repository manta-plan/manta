import { useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { LuChevronsDown, LuEye, LuEyeOff, LuRotateCcw, LuSettings2, LuTable } from "react-icons/lu";
import {
  LINES_LAYER,
  REGIONS_LAYER,
  TRANSFORMERS_LAYER,
  isLayerVisible,
  layerStyle,
  linkLayerCarrier,
  mapLayerCategories,
  type MapLayerCategory,
  type MapLayerDef,
  type MapLayerGeometry,
} from "../data/map-layers";
import { NODAL } from "../store/types";
import { useProjectStore } from "../store/project-store";
import { SidebarPanel } from "./sidebar-panel";

// The entity table a layer's "Open in Table View" opens: its ctype, and the
// carrier when the layer is one. Locations and labels aren't entities.
function tableForLayer(
  id: string,
  carrierOf: (ctype: string) => string | null,
): { ctype: string; carrier: string | null } | null {
  if (id === REGIONS_LAYER) return { ctype: "Shape", carrier: null };
  if (id === LINES_LAYER) return { ctype: "Line", carrier: carrierOf("Line") };
  if (id === TRANSFORMERS_LAYER) return { ctype: "Transformer", carrier: carrierOf("Transformer") };
  const carrier = linkLayerCarrier(id);
  return carrier === null ? null : { ctype: "Link", carrier };
}

function useMapLayerCategories(): MapLayerCategory[] {
  const record = useProjectStore((s) => s.record);
  const resolution = useProjectStore((s) => s.resolution);
  return useMemo(() => {
    const linkCarriers = [
      ...new Set(
        record?.branches
          .filter((branch) => branch.ctype === "Link")
          .map((branch) => branch.carrier ?? "") ?? [],
      ),
    ]
      .sort()
      .map((carrier) => ({
        carrier,
        label: record?.carriers[carrier]?.niceName || carrier,
        color: record?.carriers[carrier]?.color ?? "#94a3b8",
      }));
    return mapLayerCategories(linkCarriers, resolution !== NODAL);
  }, [record, resolution]);
}

function LayerSwatch({
  geometry,
  color,
  dimmed,
}: {
  geometry: MapLayerGeometry;
  color: string;
  dimmed: boolean;
}) {
  const style = dimmed
    ? { backgroundColor: "var(--color-surface-600)", borderColor: "var(--color-surface-500)" }
    : undefined;

  if (geometry === "point") {
    return (
      <span
        className="h-2 w-2 shrink-0 rounded-full border"
        style={style ?? { backgroundColor: color, borderColor: color }}
      />
    );
  }
  if (geometry === "line") {
    return (
      <span className="flex h-3.5 w-3.5 shrink-0 items-center justify-center">
        <span
          className="h-[2px] w-full rounded-full"
          style={{ backgroundColor: dimmed ? "var(--color-surface-500)" : color }}
        />
      </span>
    );
  }
  return (
    <span
      className="h-3.5 w-3.5 shrink-0 rounded-[3px] border"
      style={
        dimmed
          ? { backgroundColor: "var(--color-surface-700)", borderColor: "var(--color-surface-500)" }
          : { backgroundColor: `${color}40`, borderColor: color }
      }
    />
  );
}

function LayerStyleControls({ layer }: { layer: MapLayerDef }) {
  const layerId = layer.id;
  const style = layerStyle(
    useProjectStore((s) => s.mapLayerStyle),
    layer,
  );
  const setMapLayerColor = useProjectStore((s) => s.setMapLayerColor);
  const setMapLayerOpacity = useProjectStore((s) => s.setMapLayerOpacity);
  const resetMapLayerStyle = useProjectStore((s) => s.resetMapLayerStyle);

  return (
    <div className="flex h-full flex-col gap-3 overflow-y-auto p-3">
      <div className="text-surface-400 text-[11px]">{layer.description}</div>

      <label className="flex flex-col gap-1">
        <span className="text-surface-400 text-[11px] font-medium">
          {layer.geometry === "polygon" ? "Fill opacity" : "Opacity"} —{" "}
          {Math.round(style.opacity * 100)}%
        </span>
        <input
          type="range"
          min={0}
          max={1}
          step={0.01}
          value={style.opacity}
          onChange={(event) => setMapLayerOpacity(layerId, Number(event.target.value))}
          className="accent-accent-600 h-1.5 w-full"
        />
      </label>

      {layer.colorEditable ? (
        <label className="flex flex-col gap-1">
          <span className="text-surface-400 text-[11px] font-medium">Color</span>
          <div className="flex items-center gap-2">
            <input
              type="color"
              value={style.color}
              onChange={(event) => setMapLayerColor(layerId, event.target.value)}
              className="border-surface-600 bg-surface-900 h-7 w-10 cursor-pointer rounded border p-0.5"
            />
            <span className="text-surface-300 font-mono text-[11px]">{style.color}</span>
          </div>
        </label>
      ) : (
        <div className="text-surface-500 text-[11px]">
          This layer's color is set per feature (
          {layerId === REGIONS_LAYER ? "by zone" : "by theme"}), so there's no single color to
          override here.
        </div>
      )}

      <button
        type="button"
        onClick={() => resetMapLayerStyle(layerId)}
        className="border-surface-600 text-surface-300 hover:bg-surface-700 hover:text-surface-50 flex w-fit items-center gap-1.5 rounded border px-2 py-1 text-[11px] font-medium outline-none"
      >
        <LuRotateCcw size={12} />
        Reset to Default
      </button>
    </div>
  );
}

export function MapLayersPanel() {
  const panelRef = useRef<HTMLDivElement>(null);
  const [primaryHeight, setPrimaryHeight] = useState<number | null>(null);
  const mapLayerVisibility = useProjectStore((s) => s.mapLayerVisibility);
  const setMapLayerVisible = useProjectStore((s) => s.setMapLayerVisible);
  const mapLayerStyle = useProjectStore((s) => s.mapLayerStyle);
  const selectedMapLayerId = useProjectStore((s) => s.selectedMapLayerId);
  const selectMapLayer = useProjectStore((s) => s.selectMapLayer);
  const openEntityTable = useProjectStore((s) => s.openEntityTable);
  const record = useProjectStore((s) => s.record);
  const resolution = useProjectStore((s) => s.resolution);
  const categories = useMapLayerCategories();
  const zonal = resolution !== NODAL;
  const carrierOf = (ctype: string) =>
    record?.entityCounts.find((count) => count.ctype === ctype)?.carrier ?? null;

  const selectedLayer =
    categories
      .flatMap((category) => category.layers)
      .find((layer) => layer.id === selectedMapLayerId) ?? null;

  // Same resize mechanism as Sidebar's Model/Runs/etc. <-> Scenario
  // Mutations split — a draggable divider between this panel's layer list
  // and its own style-controls section, rather than a separate app-wide
  // drawer.
  const updatePrimaryHeight = (height: number) => {
    const panelHeight = panelRef.current?.clientHeight ?? 0;
    const minimumHeight = 120;
    setPrimaryHeight(Math.max(minimumHeight, Math.min(height, panelHeight - minimumHeight)));
  };
  const resizeFromPointer = (event: PointerEvent<HTMLDivElement>) => {
    const top = panelRef.current?.getBoundingClientRect().top;
    if (top !== undefined) updatePrimaryHeight(event.clientY - top);
  };
  const startResize = (event: PointerEvent<HTMLDivElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId);
    resizeFromPointer(event);
  };
  const continueResize = (event: PointerEvent<HTMLDivElement>) => {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) resizeFromPointer(event);
  };
  const resizeFromKeyboard = (event: KeyboardEvent<HTMLDivElement>) => {
    if (!["ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const panelHeight = panelRef.current?.clientHeight ?? 0;
    const currentHeight = primaryHeight ?? panelHeight / 2;
    if (event.key === "Home") updatePrimaryHeight(120);
    else if (event.key === "End") updatePrimaryHeight(panelHeight - 120);
    else updatePrimaryHeight(currentHeight + (event.key === "ArrowUp" ? -24 : 24));
  };

  return (
    <div
      ref={panelRef}
      data-tour="map-layers-panel"
      className="flex flex-1 flex-col overflow-hidden"
    >
      <div
        className="flex min-h-[7.5rem] flex-col overflow-hidden"
        style={
          selectedMapLayerId === null
            ? { flex: 1 }
            : {
                height:
                  primaryHeight === null
                    ? "50%"
                    : `clamp(7.5rem, ${primaryHeight}px, calc(100% - 7.5rem))`,
              }
        }
      >
        <div className="min-h-0 flex-1 overflow-y-auto p-2">
          {categories.map((category) => (
            <div key={category.id} className="mb-3 last:mb-0">
              <div className="text-surface-500 mb-1 px-1.5 text-[10px] font-semibold tracking-wide uppercase">
                {category.label}
              </div>
              <div className="flex flex-col gap-0.5">
                {category.layers.map((layer) => {
                  const visible = isLayerVisible(mapLayerVisibility, layer);
                  const EyeIcon = visible ? LuEye : LuEyeOff;
                  const table = tableForLayer(layer.id, carrierOf);
                  const isSelected = selectedMapLayerId === layer.id;
                  return (
                    <div
                      key={layer.id}
                      className={`group flex w-full items-center gap-0.5 rounded ${isSelected ? "bg-accent-600/20" : "hover:bg-surface-700/60"}`}
                    >
                      <button
                        type="button"
                        title={visible ? "Hide layer" : "Show layer"}
                        onClick={() => setMapLayerVisible(layer.id, !visible)}
                        className="hover:bg-surface-600 shrink-0 rounded p-1.5 outline-none"
                      >
                        <EyeIcon
                          size={14}
                          className={visible ? "text-surface-200" : "text-surface-600"}
                        />
                      </button>
                      <button
                        type="button"
                        title={layer.description}
                        onClick={() => selectMapLayer(layer.id)}
                        className="flex min-w-0 flex-1 items-center gap-2 rounded py-1.5 pr-1.5 text-left outline-none"
                      >
                        <LayerSwatch
                          geometry={layer.geometry}
                          color={
                            zonal && layer.id === REGIONS_LAYER
                              ? "#a855f7"
                              : layerStyle(mapLayerStyle, layer).color
                          }
                          dimmed={!visible}
                        />
                        <span
                          className={`min-w-0 flex-1 truncate text-[12px] ${
                            isSelected
                              ? "text-surface-50 font-medium"
                              : visible
                                ? "text-surface-100 font-medium"
                                : "text-surface-500"
                          }`}
                        >
                          {layer.label}
                        </span>
                      </button>
                      {table && (
                        <button
                          type="button"
                          title="Open in Table View"
                          onClick={() => openEntityTable(table.ctype, table.carrier)}
                          className="text-surface-400 hover:bg-surface-600 hover:text-surface-50 mr-1 hidden shrink-0 rounded p-0.5 outline-none group-hover:flex"
                        >
                          <LuTable size={12} />
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </div>

      {selectedMapLayerId !== null && selectedLayer && (
        <>
          <div
            role="separator"
            aria-label="Resize layer panels"
            aria-orientation="horizontal"
            tabIndex={0}
            onPointerDown={startResize}
            onPointerMove={continueResize}
            onKeyDown={resizeFromKeyboard}
            className="before:bg-surface-600 hover:before:bg-accent-500 focus-visible:before:bg-accent-500 relative h-1 shrink-0 cursor-row-resize touch-none outline-none before:absolute before:top-0 before:right-0 before:left-0 before:h-px before:transition-colors"
          />
          <div className="min-h-[7.5rem] flex-1 overflow-hidden">
            <SidebarPanel
              icon={LuSettings2}
              label={`${selectedLayer.label} Style`}
              onHeaderPointerDown={startResize}
              onHeaderPointerMove={continueResize}
              action={
                <button
                  type="button"
                  title="Collapse layer style"
                  onPointerDown={(event) => event.stopPropagation()}
                  onClick={() => selectMapLayer(selectedMapLayerId)}
                  className="text-surface-400 hover:text-surface-100 outline-none"
                >
                  <LuChevronsDown size={13} />
                </button>
              }
            >
              <LayerStyleControls layer={selectedLayer} />
            </SidebarPanel>
          </div>
        </>
      )}
    </div>
  );
}

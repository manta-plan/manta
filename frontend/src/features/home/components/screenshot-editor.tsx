import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import clsx from "clsx";
import { LuHighlighter, LuMaximize, LuPencil, LuUndo2, LuZoomIn, LuZoomOut } from "react-icons/lu";
import { FreehandMarker, HighlighterMarker, MarkerArea, Renderer } from "@markerjs/markerjs3";

type Tool = "pen" | "highlighter";

const ZOOM_STEP = 0.25;
const MIN_ZOOM = 0.25;
const MAX_ZOOM = 4;

const COLORS = ["#ef4444", "#f59e0b", "#22c55e", "#3b82f6", "#ffffff"];
const TOOLS = {
  pen: { type: FreehandMarker, width: 4, opacity: 1, icon: LuPencil, label: "Pen" },
  highlighter: {
    type: HighlighterMarker,
    width: 18,
    opacity: 0.4,
    icon: LuHighlighter,
    label: "Highlighter",
  },
} as const;

/** Pen + highlighter annotation over a screenshot. Done returns the flattened PNG. */
export function ScreenshotEditor({
  src,
  onDone,
  onCancel,
}: {
  src: string;
  onDone: (file: File) => void;
  onCancel: () => void;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const areaRef = useRef<MarkerArea | null>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);
  const [tool, setTool] = useState<Tool>("pen");
  const [color, setColor] = useState(COLORS[0]);
  const [canUndo, setCanUndo] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  // Mount the headless MarkerArea once per image.
  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const img = document.createElement("img");
    img.src = src;
    imgRef.current = img;
    const area = new MarkerArea();
    area.style.width = "100%";
    area.style.height = "100%";
    // Open fitted and centred, and refit when the window changes size.
    area.autoZoomIn = true;
    area.autoZoomOut = true;
    const fit = () => area.autoZoom();
    area.addEventListener("areashow", fit);
    window.addEventListener("resize", fit);
    area.targetImage = img;
    area.addEventListener("areastatechange", () => setCanUndo(area.isUndoPossible));
    host.appendChild(area);
    areaRef.current = area;
    return () => {
      window.removeEventListener("resize", fit);
      area.remove();
      areaRef.current = null;
    };
  }, [src]);

  // Ctrl/Cmd+wheel zooms the image. Native listener: React's wheel handler is
  // passive, so preventDefault (which stops browser page zoom) needs this.
  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const onWheel = (event: WheelEvent) => {
      if (!event.ctrlKey && !event.metaKey) return;
      event.preventDefault();
      zoomBy(event.deltaY < 0 ? ZOOM_STEP : -ZOOM_STEP);
    };
    host.addEventListener("wheel", onWheel, { passive: false });
    return () => host.removeEventListener("wheel", onWheel);
  }, []);

  const zoomBy = (delta: number) => {
    const area = areaRef.current;
    if (!area) return;
    area.zoomLevel = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, area.zoomLevel + delta));
  };

  // (Re)arm drawing whenever the tool or colour changes, and after each
  // stroke so the user can keep drawing without reselecting the tool.
  useEffect(() => {
    const area = areaRef.current;
    if (!area) return;
    const { type, width, opacity } = TOOLS[tool];
    const arm = () => {
      const editor = area.createMarker(type);
      if (editor) {
        editor.strokeColor = color;
        editor.strokeWidth = width;
        editor.opacity = opacity;
      }
    };
    const timer = window.setTimeout(arm, 0);
    area.addEventListener("markercreate", arm);
    return () => {
      window.clearTimeout(timer);
      area.removeEventListener("markercreate", arm);
    };
  }, [tool, color, src]);

  const save = async () => {
    const area = areaRef.current;
    const img = imgRef.current;
    if (!area || !img) return;
    setIsSaving(true);
    try {
      const renderer = new Renderer();
      renderer.targetImage = img;
      renderer.naturalSize = true;
      renderer.imageType = "image/png";
      const dataUrl = await renderer.rasterize(area.getState());
      const blob = await (await fetch(dataUrl)).blob();
      onDone(new File([blob], "screenshot.png", { type: "image/png" }));
    } finally {
      setIsSaving(false);
    }
  };

  return createPortal(
    <div
      data-capture-exclude
      className="fixed inset-0 z-[90] flex flex-col bg-black/85 p-4"
      role="dialog"
      aria-label="Edit screenshot"
    >
      <div className="mb-3 flex items-center gap-2">
        {(Object.keys(TOOLS) as Tool[]).map((key) => {
          const Icon = TOOLS[key].icon;
          return (
            <button
              key={key}
              type="button"
              onClick={() => setTool(key)}
              aria-pressed={tool === key}
              aria-label={TOOLS[key].label}
              title={TOOLS[key].label}
              className={clsx(
                "flex h-8 w-8 items-center justify-center rounded outline-none",
                tool === key
                  ? "bg-accent-600 text-white"
                  : "bg-surface-700 text-surface-200 hover:bg-surface-600",
              )}
            >
              <Icon size={15} />
            </button>
          );
        })}
        <div className="mx-1 flex items-center gap-1.5">
          {COLORS.map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => setColor(c)}
              aria-label={`Colour ${c}`}
              aria-pressed={color === c}
              style={{ backgroundColor: c }}
              className={clsx(
                "h-5 w-5 rounded-full border outline-none",
                color === c ? "border-2 border-white ring-2 ring-white/40" : "border-white/30",
              )}
            />
          ))}
        </div>
        <button
          type="button"
          onClick={() => areaRef.current?.undo()}
          disabled={!canUndo}
          aria-label="Undo"
          title="Undo"
          className="bg-surface-700 text-surface-200 hover:bg-surface-600 flex h-8 w-8 items-center justify-center rounded outline-none disabled:opacity-40"
        >
          <LuUndo2 size={15} />
        </button>
        <div className="ml-2 flex items-center gap-1">
          {[
            { label: "Zoom out", icon: LuZoomOut, run: () => zoomBy(-ZOOM_STEP) },
            { label: "Zoom in", icon: LuZoomIn, run: () => zoomBy(ZOOM_STEP) },
            { label: "Fit to screen", icon: LuMaximize, run: () => areaRef.current?.autoZoom() },
          ].map(({ label, icon: Icon, run }) => (
            <button
              key={label}
              type="button"
              onClick={run}
              aria-label={label}
              title={label}
              className="bg-surface-700 text-surface-200 hover:bg-surface-600 flex h-8 w-8 items-center justify-center rounded outline-none"
            >
              <Icon size={15} />
            </button>
          ))}
        </div>
        <div className="ml-auto flex gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="text-surface-200 hover:bg-surface-700 h-8 rounded px-3 text-[12px] font-medium outline-none"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => void save()}
            disabled={isSaving}
            className="bg-accent-600 hover:bg-accent-500 h-8 rounded px-3 text-[12px] font-medium text-white outline-none disabled:opacity-50"
          >
            Done
          </button>
        </div>
      </div>
      <div ref={hostRef} className="flex min-h-0 flex-1 items-center justify-center" />
    </div>,
    document.body,
  );
}

// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import clsx from "clsx";
import {
  LuMaximize,
  LuPentagon,
  LuSquare,
  LuTrash2,
  LuUndo2,
  LuZoomIn,
  LuZoomOut,
} from "react-icons/lu";
import {
  ShapeType,
  createImageAnnotator,
  type ImageAnnotation,
  type ImageAnnotator,
  type PolygonGeometry,
  type RectangleGeometry,
} from "@annotorious/annotorious";
import "@annotorious/annotorious/annotorious.css";
import { FILL_ALPHA, drawAnnotations, type AnnotationShape } from "../lib/draw-annotations";

type Tool = "rectangle" | "polygon";

const ZOOM_STEP = 0.25;
const MIN_ZOOM = 0.25;
const MAX_ZOOM = 4;

type HexColor = `#${string}`;

const COLORS: HexColor[] = ["#ef4444", "#f59e0b", "#22c55e", "#3b82f6", "#ffffff"];
const TOOLS = {
  rectangle: { icon: LuSquare, label: "Rectangle" },
  polygon: { icon: LuPentagon, label: "Polygon (click points, click the first to close)" },
} as const;

/** Rectangle + polygon marks over a screenshot. Done returns the flattened PNG. */
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
  const annoRef = useRef<ImageAnnotator | null>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);
  // Each mark keeps the colour it was drawn in, by annotation id.
  const colorsRef = useRef(new Map<string, HexColor>());
  const colorRef = useRef(COLORS[0]);
  const [tool, setTool] = useState<Tool>("rectangle");
  const [color, setColor] = useState(COLORS[0]);
  const [canUndo, setCanUndo] = useState(false);
  const [hasMarks, setHasMarks] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  // Zoom relative to the fitted size; `fit` is image px -> screen px at zoom 1.
  const [zoom, setZoom] = useState(1);
  const [fit, setFit] = useState(0);

  // Mount Annotorious once per image. It wraps the <img> in its own div, so
  // the image is created here rather than rendered by React.
  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const colors = colorsRef.current;
    let cancelled = false;
    let anno: ImageAnnotator | null = null;
    const img = document.createElement("img");
    img.src = src;
    img.alt = "Screenshot";
    img.draggable = false;
    imgRef.current = img;

    const refit = () => {
      if (!img.naturalWidth) return;
      setFit(
        Math.min(1, host.clientWidth / img.naturalWidth, host.clientHeight / img.naturalHeight),
      );
    };

    void img.decode().then(() => {
      if (cancelled) return;
      host.appendChild(img);
      anno = createImageAnnotator(img, {
        drawingEnabled: true,
        theme: "dark",
        style: (annotation) => {
          const stroke = colorsRef.current.get(annotation.id) ?? colorRef.current;
          return { stroke, strokeWidth: 3, fill: stroke, fillOpacity: FILL_ALPHA };
        },
      });
      // Centred in the scroll box, and scrollable on every side once zoomed.
      anno.element.style.margin = "auto";
      anno.element.style.flexShrink = "0";
      const sync = () => {
        setCanUndo(anno?.canUndo() ?? false);
        setHasMarks((anno?.getAnnotations().length ?? 0) > 0);
      };
      anno.on("createAnnotation", (annotation) => {
        colorsRef.current.set(annotation.id, colorRef.current);
        sync();
      });
      anno.on("updateAnnotation", sync);
      anno.on("deleteAnnotation", sync);
      annoRef.current = anno;
      refit();
    });
    window.addEventListener("resize", refit);
    return () => {
      cancelled = true;
      window.removeEventListener("resize", refit);
      anno?.destroy();
      img.remove();
      annoRef.current = null;
      colors.clear();
    };
  }, [src]);

  // The image's on-screen size is the zoom; Annotorious follows its size.
  useEffect(() => {
    const img = imgRef.current;
    if (!img || !fit) return;
    img.style.width = `${img.naturalWidth * fit * zoom}px`;
    img.style.maxWidth = "none";
  }, [fit, zoom]);

  // `fit` turns non-zero once Annotorious is mounted, so the tool is set then too.
  useEffect(() => {
    annoRef.current?.setDrawingTool(tool);
  }, [tool, fit]);

  useEffect(() => {
    colorRef.current = color;
  }, [color]);

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

  const zoomBy = (delta: number) =>
    setZoom((z) => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, z + delta)));

  const undo = () => {
    const anno = annoRef.current;
    if (!anno) return;
    anno.undo();
    setCanUndo(anno.canUndo());
    setHasMarks(anno.getAnnotations().length > 0);
  };

  const clearAll = () => {
    const anno = annoRef.current;
    if (!anno) return;
    anno.clearAnnotations();
    setCanUndo(anno.canUndo());
    setHasMarks(false);
  };

  const save = async () => {
    const anno = annoRef.current;
    const img = imgRef.current;
    if (!anno || !img) return;
    setIsSaving(true);
    try {
      const canvas = document.createElement("canvas");
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.drawImage(img, 0, 0);
      drawAnnotations(ctx, toShapes(anno.getAnnotations(), colorsRef.current), img.naturalWidth);
      const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/png"));
      if (blob) onDone(new File([blob], "screenshot.png", { type: "image/png" }));
    } finally {
      setIsSaving(false);
    }
  };

  const iconButton =
    "bg-surface-700 text-surface-200 hover:bg-surface-600 flex h-8 w-8 items-center justify-center rounded outline-none disabled:opacity-40";

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
          onClick={undo}
          disabled={!canUndo}
          aria-label="Undo"
          title="Undo"
          className={iconButton}
        >
          <LuUndo2 size={15} />
        </button>
        <button
          type="button"
          onClick={clearAll}
          disabled={!hasMarks}
          aria-label="Clear all marks"
          title="Clear all marks"
          className={iconButton}
        >
          <LuTrash2 size={15} />
        </button>
        <div className="ml-2 flex items-center gap-1">
          {[
            { label: "Zoom out", icon: LuZoomOut, run: () => zoomBy(-ZOOM_STEP) },
            { label: "Zoom in", icon: LuZoomIn, run: () => zoomBy(ZOOM_STEP) },
            { label: "Fit to screen", icon: LuMaximize, run: () => setZoom(1) },
          ].map(({ label, icon: Icon, run }) => (
            <button
              key={label}
              type="button"
              onClick={run}
              aria-label={label}
              title={label}
              className={iconButton}
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
      <div ref={hostRef} className="flex min-h-0 flex-1 overflow-auto" />
    </div>,
    document.body,
  );
}

/** Annotorious annotations -> shapes in image pixels, in the colour each was drawn. */
function toShapes(
  annotations: ImageAnnotation[],
  colors: Map<string, HexColor>,
): AnnotationShape[] {
  return annotations.flatMap((annotation): AnnotationShape[] => {
    const { selector } = annotation.target;
    const color = colors.get(annotation.id) ?? COLORS[0];
    if (selector.type === ShapeType.RECTANGLE) {
      const { x, y, w, h } = selector.geometry as RectangleGeometry;
      return [{ type: "RECTANGLE", color, x, y, w, h }];
    }
    if (selector.type === ShapeType.POLYGON) {
      return [{ type: "POLYGON", color, points: (selector.geometry as PolygonGeometry).points }];
    }
    return [];
  });
}

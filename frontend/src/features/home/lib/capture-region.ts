// Snipping-tool capture: render the page with snapdom, then crop the region
// the user dragged. snapdom only sees this page's DOM, not other windows.

export interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** Smallest drag (CSS px) treated as a selection; anything less is a stray click. */
export const MIN_SELECTION = 8;

/** Rect spanning two drag points, whichever direction the user dragged. */
export function rectFromPoints(a: { x: number; y: number }, b: { x: number; y: number }): Rect {
  return {
    x: Math.min(a.x, b.x),
    y: Math.min(a.y, b.y),
    width: Math.abs(a.x - b.x),
    height: Math.abs(a.y - b.y),
  };
}

/**
 * Source rectangle (canvas pixels) for a viewport selection. `origin` is where
 * the captured element sits in the viewport (negative when the page is
 * scrolled) and `scale` is canvas pixels per CSS pixel.
 */
export function computeCrop(
  selection: Rect,
  origin: { x: number; y: number },
  scale: number,
): Rect {
  return {
    x: Math.round((selection.x - origin.x) * scale),
    y: Math.round((selection.y - origin.y) * scale),
    width: Math.max(1, Math.round(selection.width * scale)),
    height: Math.max(1, Math.round(selection.height * scale)),
  };
}

/** Page background, so transparent areas don't come out white in the PNG. */
function pageBackground(): string {
  const body = getComputedStyle(document.body).backgroundColor;
  if (body && body !== "transparent" && body !== "rgba(0, 0, 0, 0)") return body;
  const surface = getComputedStyle(document.documentElement)
    .getPropertyValue("--color-surface-900")
    .trim();
  return surface || "#ffffff";
}

export async function captureRegion(selection: Rect): Promise<File> {
  // Loaded on demand so the library stays out of the main bundle.
  const { snapdom } = await import("@zumer/snapdom");
  const root = document.documentElement;
  const origin = root.getBoundingClientRect();
  const result = await snapdom(root, {
    scale: window.devicePixelRatio || 1,
    exclude: ["[data-capture-exclude]"],
    backgroundColor: pageBackground(),
  });
  const full = await result.toCanvas();
  const crop = computeCrop(selection, origin, full.width / origin.width);

  const canvas = document.createElement("canvas");
  canvas.width = crop.width;
  canvas.height = crop.height;
  canvas
    .getContext("2d")
    ?.drawImage(full, crop.x, crop.y, crop.width, crop.height, 0, 0, crop.width, crop.height);
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/png"));
  if (!blob) throw new Error("Couldn't capture the screen.");
  return new File([blob], "screenshot.png", { type: "image/png" });
}

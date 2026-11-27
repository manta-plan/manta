// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

// Images placed on a report are stored inside it, in the browser's local
// storage, so they are shrunk first. Small PNG, JPEG, WebP, GIF and SVG
// files go in as they are.

export const REPORT_IMAGE_TYPES = [
  "image/png",
  "image/jpeg",
  "image/webp",
  "image/gif",
  "image/svg+xml",
] as const;
const KEEP_AS_IS_BYTES = 400 * 1024;
const MAX_STORED_BYTES = 900 * 1024;
const MAX_DIMENSION = 1600;

export class ReportImageError extends Error {}

function readDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new ReportImageError("Couldn't read that image."));
    reader.readAsDataURL(blob);
  });
}

async function shrink(file: File): Promise<Blob> {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, MAX_DIMENSION / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  const context = canvas.getContext("2d");
  // JPEG has no transparency, so lay the image on white.
  if (context) {
    context.fillStyle = "#ffffff";
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  }
  bitmap.close();
  const blob = await new Promise<Blob | null>((resolve) =>
    canvas.toBlob(resolve, "image/jpeg", 0.85),
  );
  if (!blob) throw new ReportImageError("Couldn't process that image.");
  return blob;
}

/** The image as a data URL small enough to keep in the report, plus a name for its alt text. */
export async function prepareReportImage(file: File): Promise<{ src: string; name: string }> {
  if (!(REPORT_IMAGE_TYPES as readonly string[]).includes(file.type))
    throw new ReportImageError("Use a PNG, JPEG, WebP, GIF or SVG image.");
  // Animated GIFs and SVGs would be flattened by a re-encode.
  const canShrink = file.type !== "image/gif" && file.type !== "image/svg+xml";
  const blob = file.size > KEEP_AS_IS_BYTES && canShrink ? await shrink(file) : file;
  if (blob.size > MAX_STORED_BYTES)
    throw new ReportImageError(
      "That image is too large to keep in a report. Use one under 900 KB.",
    );
  return { src: await readDataUrl(blob), name: file.name.replace(/\.[^.]+$/, "") };
}

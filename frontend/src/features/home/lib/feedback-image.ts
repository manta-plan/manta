// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

// Screenshot attachments for the feedback form. The sheet's Apps Script
// accepts PNG, JPEG, WebP or GIF up to 5 MB (see its doPost); anything
// larger is downscaled here first (as PNG), since full-screen retina PNGs routinely
// exceed that.

export const FEEDBACK_IMAGE_TYPES = ["image/png", "image/jpeg", "image/webp", "image/gif"] as const;
const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
// Longest sides tried, in order, when shrinking — still sharp enough to read UI text.
const DIMENSION_STEPS = [2560, 1920, 1280];

export interface FeedbackImage {
  name: string;
  type: string;
  size: number;
  base64: string;
  /** Object URL for the dialog's thumbnail; revoke when discarded. */
  previewUrl: string;
}

export class FeedbackImageError extends Error {}

/** Next smaller longest-side step below `current`, or null when already at the smallest. */
export function nextDimension(current: number | null): number | null {
  if (current === null) return DIMENSION_STEPS[0];
  return DIMENSION_STEPS.find((step) => step < current) ?? null;
}

async function encode(bitmap: ImageBitmap, longest: number): Promise<Blob> {
  const scale = Math.min(1, longest / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext("2d")?.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/png"));
  if (!blob) throw new FeedbackImageError("Couldn't process that image.");
  return blob;
}

// Stays PNG (JPEG would flatten transparency): downscale step by step until it fits.
async function shrink(file: File): Promise<Blob> {
  const bitmap = await createImageBitmap(file);
  try {
    let longest = nextDimension(null);
    while (longest !== null) {
      const blob = await encode(bitmap, longest);
      if (blob.size <= MAX_IMAGE_BYTES) return blob;
      longest = nextDimension(longest);
    }
  } finally {
    bitmap.close();
  }
  throw new FeedbackImageError("Image must be under 5 MB.");
}

function toBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    // Result is a data URL ("data:image/png;base64,…"); keep only the payload.
    reader.onload = () => resolve(String(reader.result).split(",")[1] ?? "");
    reader.onerror = () => reject(new FeedbackImageError("Couldn't read that image."));
    reader.readAsDataURL(blob);
  });
}

export async function prepareFeedbackImage(file: File): Promise<FeedbackImage> {
  if (!(FEEDBACK_IMAGE_TYPES as readonly string[]).includes(file.type)) {
    throw new FeedbackImageError("Use a PNG, JPEG, WebP or GIF image.");
  }
  let blob: Blob = file;
  let name = file.name || "screenshot.png";
  // GIFs may be animated, which a canvas re-encode would flatten — only the
  // still formats get shrunk.
  if (file.size > MAX_IMAGE_BYTES && file.type !== "image/gif") {
    blob = await shrink(file);
    name = name.replace(/\.[^.]+$/, "") + ".png";
  }
  if (blob.size > MAX_IMAGE_BYTES) throw new FeedbackImageError("Image must be under 5 MB.");
  return {
    name,
    type: blob.type,
    size: blob.size,
    base64: await toBase64(blob),
    previewUrl: URL.createObjectURL(blob),
  };
}

export function formatImageSize(bytes: number): string {
  return bytes < 1024 * 1024
    ? `${Math.max(1, Math.round(bytes / 1024))} KB`
    : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

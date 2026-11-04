// Screenshot attachments for the feedback form. The sheet's Apps Script
// accepts PNG, JPEG, WebP or GIF up to 5 MB (see its doPost); anything
// larger is re-encoded here first, since full-screen retina PNGs routinely
// exceed that.

export const FEEDBACK_IMAGE_TYPES = ["image/png", "image/jpeg", "image/webp", "image/gif"] as const;
const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
// Longest side after shrinking — still sharp enough to read UI text.
const MAX_DIMENSION = 2560;

export interface FeedbackImage {
  name: string;
  type: string;
  size: number;
  base64: string;
  /** Object URL for the dialog's thumbnail; revoke when discarded. */
  previewUrl: string;
}

export class FeedbackImageError extends Error {}

async function shrink(file: File): Promise<Blob> {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, MAX_DIMENSION / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext("2d")?.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  const blob = await new Promise<Blob | null>((resolve) =>
    canvas.toBlob(resolve, "image/jpeg", 0.85),
  );
  if (!blob) throw new FeedbackImageError("Couldn't process that image.");
  return blob;
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
    name = name.replace(/\.[^.]+$/, "") + ".jpg";
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

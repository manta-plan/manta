import { format } from "date-fns";

export function formatRunStartedAt(startedAt: string) {
  return format(new Date(startedAt), "MMM d, HH:mm");
}

export function formatRunDuration(durationSeconds: number | null) {
  if (durationSeconds === null) {
    return "-";
  }

  const minutes = Math.floor(durationSeconds / 60);
  const seconds = durationSeconds % 60;

  return `${minutes}m ${String(seconds).padStart(2, "0")}s`;
}

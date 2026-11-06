import { LuCheck, LuCopy } from "react-icons/lu";
import { useCopyToClipboard } from "../lib/use-copy-to-clipboard";

// Raw WKT is unreadable inline and the map already highlights the feature,
// so geometry attributes show a short stand-in plus this copy button rather
// than their value — and aren't offered as a free-text edit.
export const GEOMETRY_FIELD = "geometry";

export function CopyWktButton({ wkt }: { wkt: string }) {
  const { copied, copy } = useCopyToClipboard();

  return (
    <button
      type="button"
      onClick={() => copy(wkt)}
      title={copied ? "Copied" : "Copy WKT"}
      aria-label="Copy WKT"
      className="text-accent-400 hover:text-accent-300 shrink-0 outline-none"
    >
      {copied ? <LuCheck size={11} /> : <LuCopy size={11} />}
    </button>
  );
}

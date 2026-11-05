import { useEffect, useState } from "react";

// `copied` flips true for a moment after a successful copy, for inline
// "Copied" feedback without a toast.
export function useCopyToClipboard(resetMs = 1500) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const timeout = setTimeout(() => setCopied(false), resetMs);
    return () => clearTimeout(timeout);
  }, [copied, resetMs]);

  const copy = (text: string) =>
    void navigator.clipboard.writeText(text).then(() => setCopied(true));
  return { copied, copy };
}

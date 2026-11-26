import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { WidgetSkeleton } from "../../../components/widget-states";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ReportBlock } from "../data/reports";
import type { ReportTheme } from "../data/report-themes";
import { ReportWidgetHost } from "./report-widget-host";

/** Whether widget blocks can draw yet: they need the record's results. */
export type WidgetsStatus =
  | { status: "ready" }
  | { status: "loading" }
  | { status: "error"; error: string };

const HEADING_CLASS = {
  1: "text-[28px] leading-9",
  2: "text-[20px] leading-7",
  3: "text-[15px] leading-6",
};

/**
 * Text that doesn't fit its block: in the editor (`flagOverflow`), a fade and a
 * note say it's cut off, instead of it disappearing silently. Print shows the
 * block as it is.
 */
function Clipped({
  flagOverflow,
  className,
  style,
  children,
}: {
  flagOverflow: boolean;
  className: string;
  style?: CSSProperties;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [isCut, setCut] = useState(false);
  useEffect(() => {
    const element = ref.current;
    if (!element || !flagOverflow) return;
    const check = () => setCut(element.scrollHeight > element.clientHeight + 1);
    check();
    const observer = new ResizeObserver(check);
    observer.observe(element);
    for (const child of element.children) observer.observe(child);
    return () => observer.disconnect();
  }, [flagOverflow, children]);
  return (
    <div className="relative h-full">
      <div ref={ref} className={`h-full overflow-hidden ${className}`} style={style}>
        {children}
      </div>
      {flagOverflow && isCut && (
        <div className="pointer-events-none absolute inset-x-0 bottom-0 flex h-8 items-end justify-end bg-gradient-to-t from-black/25 to-transparent print:hidden">
          <span className="bg-danger-500 m-1 rounded px-1.5 py-0.5 text-[10px] font-medium text-white">
            Text cut off: resize the block
          </span>
        </div>
      )}
    </div>
  );
}

/** What one block shows on a page. `flagOverflow`: say when text doesn't fit (the editor, not print). */
export function ReportBlockView({
  block,
  widgets,
  theme,
  flagOverflow = false,
}: {
  block: ReportBlock;
  widgets: WidgetsStatus;
  theme: ReportTheme;
  flagOverflow?: boolean;
}) {
  const { content } = block;
  switch (content.kind) {
    case "widget":
      if (widgets.status === "ready") return <ReportWidgetHost content={content} theme={theme} />;
      if (widgets.status === "loading")
        return (
          <div className="border-surface-700 relative h-full rounded border">
            <WidgetSkeleton />
          </div>
        );
      return (
        <div className="border-surface-600 text-surface-400 flex h-full items-center justify-center border border-dashed px-4 text-center text-[11px]">
          {widgets.error}
        </div>
      );
    case "heading":
      return (
        <Clipped
          flagOverflow={flagOverflow}
          className={`text-surface-50 font-semibold ${HEADING_CLASS[content.level]}`}
          style={{ fontFamily: "var(--report-font-heading)" }}
        >
          {content.text}
        </Clipped>
      );
    case "text":
      return (
        <Clipped flagOverflow={flagOverflow} className="note-content">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              a: ({ children, href }) => (
                <a href={href} target="_blank" rel="noreferrer">
                  {children}
                </a>
              ),
            }}
          >
            {content.text}
          </ReactMarkdown>
        </Clipped>
      );
    case "divider":
      return (
        <div className="flex h-full items-center">
          <div className="bg-surface-600 h-px w-full" />
        </div>
      );
    case "image":
      return <img src={content.src} alt={content.alt} className="h-full w-full object-contain" />;
    case "shape":
      if (content.shape === "line") {
        return (
          <div className="flex h-full items-center">
            <div className="bg-accent-500 h-0.5 w-full" />
          </div>
        );
      }
      return (
        <div
          className={`border-accent-500 bg-accent-600/15 h-full w-full border ${content.shape === "ellipse" ? "rounded-full" : ""}`}
        />
      );
  }
}

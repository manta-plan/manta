import type { ReactNode } from "react";

interface HomeSectionFrameProps {
  children: ReactNode;
  maxWidthClassName?: string;
}

export function HomeSectionFrame({
  children,
  maxWidthClassName = "max-w-5xl",
}: HomeSectionFrameProps) {
  return <div className={`mx-auto w-full ${maxWidthClassName} px-8 py-8`}>{children}</div>;
}

interface HomeCardProps {
  children: ReactNode;
  className?: string;
}

export function HomeCard({ children, className = "" }: HomeCardProps) {
  return (
    <div className={`border-surface-700 bg-surface-800 rounded-lg border p-4 ${className}`}>
      {children}
    </div>
  );
}

interface StatusPillProps {
  children: ReactNode;
  tone?: "neutral" | "ok";
}

export function StatusPill({ children, tone = "neutral" }: StatusPillProps) {
  const toneClass = tone === "ok" ? "text-ok-500" : "text-surface-400";
  const dotClass = tone === "ok" ? "bg-ok-500" : "bg-surface-500";

  return (
    <span className={`flex items-center gap-1.5 text-[11px] ${toneClass}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${dotClass}`} />
      {children}
    </span>
  );
}

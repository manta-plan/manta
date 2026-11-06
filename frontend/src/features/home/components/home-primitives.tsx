import type { ReactNode } from "react";
import { Link } from "wouter";

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

interface HomeCardLinkProps extends HomeCardProps {
  href: string;
}

export function HomeCardLink({ children, href, className = "" }: HomeCardLinkProps) {
  return (
    <Link
      href={href}
      className={`border-surface-700 bg-surface-800 hover:border-accent-500 flex flex-col gap-3 rounded-lg border p-4 text-left transition-colors ${className}`}
    >
      {children}
    </Link>
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

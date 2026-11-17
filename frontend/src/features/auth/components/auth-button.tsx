import type { ReactNode } from "react";

type AuthButtonProps = {
  children: ReactNode;
  icon?: ReactNode;
  type?: "button" | "submit";
  variant?: "primary" | "secondary";
  disabled?: boolean;
  className?: string;
  onClick?: () => void;
};

export function AuthButton({
  children,
  icon,
  type = "button",
  variant = "secondary",
  disabled = false,
  className = "",
  onClick,
}: AuthButtonProps) {
  const variantClass =
    variant === "primary"
      ? "bg-primary text-primary-foreground hover:bg-primary-hover active:bg-primary-active"
      : "border border-slate-300 bg-white text-slate-700 hover:bg-slate-50";

  return (
    <button
      type={type}
      disabled={disabled}
      onClick={onClick}
      className={`flex h-9 w-full items-center justify-center gap-2 rounded text-[13px] font-medium transition disabled:cursor-not-allowed disabled:opacity-70 ${variantClass} ${className}`}
    >
      {icon}
      {children}
    </button>
  );
}

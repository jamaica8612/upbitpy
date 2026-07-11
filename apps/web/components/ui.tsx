"use client";

import { ReactNode } from "react";

export function Card({ title, children, className = "", right }: {
  title?: ReactNode; children: ReactNode; className?: string; right?: ReactNode;
}) {
  return (
    <div className={`bg-panel border border-line rounded-lg ${className}`}>
      {(title || right) && (
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-line">
          <h3 className="text-sm font-semibold">{title}</h3>
          {right}
        </div>
      )}
      <div className="p-4">{children}</div>
    </div>
  );
}

export function Stat({ label, value, tone = "neutral", sub, hint }: {
  label: string; value: ReactNode; tone?: "up" | "down" | "neutral" | "accent"; sub?: ReactNode; hint?: string;
}) {
  const color =
    tone === "up" ? "text-up" : tone === "down" ? "text-down" : tone === "accent" ? "text-accent" : "text-fg";
  return (
    <div className="bg-panel border border-line rounded-lg px-4 py-3" title={hint}>
      <div className="text-xs text-muted flex items-center gap-1">
        {label}
        {hint && <span className="cursor-help text-[10px]">ⓘ</span>}
      </div>
      <div className={`text-lg font-bold ${color}`}>{value}</div>
      {sub && <div className="text-xs text-muted mt-0.5">{sub}</div>}
    </div>
  );
}

export function Button({ children, onClick, variant = "primary", disabled, className = "", type = "button" }: {
  children: ReactNode; onClick?: () => void; variant?: "primary" | "ghost" | "danger";
  disabled?: boolean; className?: string; type?: "button" | "submit";
}) {
  const styles = {
    primary: "bg-accent text-black hover:opacity-90 font-semibold",
    ghost: "bg-panel-2 border border-line text-fg hover:bg-panel",
    danger: "bg-up/20 border border-up/50 text-up hover:bg-up/30",
  };
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`px-3 py-1.5 rounded-md text-sm transition disabled:opacity-40 disabled:cursor-not-allowed ${styles[variant]} ${className}`}
    >
      {children}
    </button>
  );
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="block" title={hint}>
      <span className="text-xs text-muted flex items-center gap-1">
        {label}
        {hint && <span className="cursor-help text-[10px]">ⓘ</span>}
      </span>
      <div className="mt-1">{children}</div>
    </label>
  );
}

export const inputCls =
  "w-full bg-panel-2 border border-line rounded-md px-2.5 py-1.5 text-sm focus:outline-none focus:border-accent";

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: "up" | "down" | "warn" | "neutral" | "good" }) {
  const styles = {
    up: "bg-up/15 text-up",
    down: "bg-down/15 text-down",
    warn: "bg-accent/15 text-accent",
    good: "bg-good/15 text-good",
    neutral: "bg-panel-2 text-muted",
  };
  return <span className={`inline-block px-2 py-0.5 rounded text-xs ${styles[tone]}`}>{children}</span>;
}

export function Warning({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-start gap-2 bg-accent/10 border border-accent/30 rounded-md px-3 py-2 text-xs text-accent">
      <span>⚠️</span>
      <span>{children}</span>
    </div>
  );
}

export function ErrorBox({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-start gap-2 bg-up/10 border border-up/30 rounded-md px-3 py-2 text-sm text-up">
      <span>❌</span>
      <div>{children}</div>
    </div>
  );
}

"use client";

import { cn } from "@/lib/utils";
import type { AgentType } from "@/lib/types";

export const AGENT_META: Record<AgentType, { label: string; color: string; dot: string; ring: string; bg: string }> = {
  triage:     { label: "Triage",     color: "text-amber-500",   dot: "#d97706", ring: "rgba(217,119,6,0.20)",  bg: "rgba(217,119,6,0.06)" },
  technical:  { label: "Technical",  color: "text-cyan-600",    dot: "#0891b2", ring: "rgba(8,145,178,0.20)",   bg: "rgba(8,145,178,0.06)"  },
  billing:    { label: "Billing",    color: "text-emerald-600", dot: "#059669", ring: "rgba(5,150,105,0.20)",   bg: "rgba(5,150,105,0.06)"  },
  knowledge:  { label: "Knowledge",  color: "text-violet-500",  dot: "#7c3aed", ring: "rgba(124,58,237,0.20)",  bg: "rgba(124,58,237,0.06)" },
  escalation: { label: "Escalation", color: "text-red-500",    dot: "#dc2626", ring: "rgba(220,38,38,0.20)",   bg: "rgba(220,38,38,0.06)"  },
};

interface Props {
  agent: AgentType;
  size?: "xs" | "sm" | "md";
  pulse?: boolean;
  showIcon?: boolean;
}

export function AgentBadge({ agent, size = "sm", pulse, showIcon = false }: Props) {
  const meta = AGENT_META[agent];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full font-medium select-none",
        size === "xs"  && "text-[10px] px-1.5 py-0.5",
        size === "sm"  && "text-xs px-2 py-0.5",
        size === "md"  && "text-sm px-2.5 py-1",
      )}
      style={{
        background: meta.bg,
        color: meta.dot,
        boxShadow: `inset 0 0 0 1px ${meta.ring}`,
        fontFamily: "var(--font-mono)",
      }}
    >
      <span
        className="rounded-full flex-shrink-0"
        style={{
          width: size === "md" ? 7 : 6,
          height: size === "md" ? 7 : 6,
          background: meta.dot,
          boxShadow: `0 0 6px ${meta.dot}`,
          animation: pulse ? "pulse-dot 1.6s ease-in-out infinite" : "none",
        }}
      />
      {meta.label}
    </span>
  );
}

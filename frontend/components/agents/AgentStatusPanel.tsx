"use client";

import { useConversationStore } from "@/store/conversation";
import { cn } from "@/lib/utils";
import type { AgentType } from "@/lib/types";
import { AGENT_META } from "@/components/agents/AgentBadge";

const ALL_AGENTS: AgentType[] = ["triage", "technical", "billing", "knowledge", "escalation"];

export function AgentStatusPanel() {
  const currentAgent = useConversationStore((s) => s.currentAgent);
  const activeAgents = useConversationStore((s) => s.activeAgents);

  return (
    <div className="space-y-0.5">
      <p
        className="text-[10px] uppercase tracking-widest font-semibold mb-3 px-1"
        style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}
      >
        Agents
      </p>

      {ALL_AGENTS.map((agent) => {
        const meta     = AGENT_META[agent];
        const isActive = currentAgent === agent;
        const wasUsed  = activeAgents.includes(agent);

        return (
          <div
            key={agent}
            className={cn(
              "flex items-center gap-2.5 px-3 py-2 rounded-lg select-none",
              !isActive && !wasUsed && "opacity-25"
            )}
            style={{
              transition: "all 0.15s ease",
              ...(isActive
                ? { background: meta.bg, border: `1px solid ${meta.ring}` }
                : wasUsed
                ? { background: "#1a1d27", border: "1px solid rgba(255,255,255,0.06)" }
                : { background: "transparent", border: "1px solid transparent" }
              )
            }}
          >
            {/* Status dot */}
            <span
              className="block flex-shrink-0 rounded-full"
              style={{
                width: 6,
                height: 6,
                background: meta.dot,
                boxShadow: isActive ? `0 0 10px ${meta.dot}` : "none",
                animation: isActive ? "pulse-dot 1.6s ease-in-out infinite" : "none",
              }}
            />

            {/* Label */}
            <span
              className={cn(
                "text-xs font-medium flex-1 leading-none",
                isActive   ? "" : wasUsed ? "text-slate-300" : "text-slate-500"
              )}
              style={isActive ? { color: meta.dot } : {}}
            >
              {meta.label}
            </span>

            {/* Indicator */}
            {isActive ? (
              <span
                className="text-[9px] px-1.5 py-0.5 rounded-md"
                style={{
                  background: meta.bg,
                  color: meta.dot,
                  fontFamily: "var(--font-mono)",
                  border: `1px solid ${meta.ring}`,
                }}
              >
                active
              </span>
            ) : wasUsed ? (
              <span
                className="h-1 w-1 rounded-full"
                style={{ background: meta.dot, opacity: 0.3 }}
              />
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

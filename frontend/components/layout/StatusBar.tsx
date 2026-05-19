"use client";

import { useConversationStore } from "@/store/conversation";
import { AgentBadge } from "@/components/agents/AgentBadge";
import { cn } from "@/lib/utils";

export function StatusBar() {
  const { currentAgent, totalLatencyMs, tokenCount, provider, cragPath, isStreaming } = useConversationStore();

  return (
    <div
      className="flex items-center gap-5 px-5 h-9 flex-shrink-0"
      style={{
        background: "var(--bg-surface)",
        borderTop: "1px solid var(--border-faint)",
        fontFamily: "var(--font-mono)",
      }}
    >
      {/* Streaming indicator */}
      {isStreaming && (
        <div className="flex items-center gap-1.5">
          <span
            className="h-1.5 w-1.5 rounded-full"
            style={{ background: "var(--accent-bright)", animation: "pulse-dot 1s ease-in-out infinite" }}
          />
          <span className="text-[11px]" style={{ color: "var(--accent-bright)" }}>
            processing
          </span>
        </div>
      )}

      {currentAgent && (
        <div className="flex items-center gap-1.5">
          <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>agent</span>
          <AgentBadge agent={currentAgent} size="xs" />
        </div>
      )}

      {totalLatencyMs > 0 && (
        <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>
          {(totalLatencyMs / 1000).toFixed(1)}s
        </span>
      )}

      {tokenCount > 0 && (
        <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>
          {tokenCount.toLocaleString()} tokens
        </span>
      )}

      {cragPath && (
        <span
          className={cn(
            "text-[11px] px-1.5 py-0.5 rounded",
            cragPath === "web_fallback" ? "text-amber-400" :
            cragPath === "supplement"   ? "text-violet-400" : "text-emerald-400"
          )}
          style={{ background: "var(--bg-overlay)" }}
        >
          {cragPath === "web_fallback" ? "⚡ web search"
         : cragPath === "supplement"   ? "◈ supplemented"
         : "✓ direct"}
        </span>
      )}

      <div className="flex-1" />
      <span className="text-[11px]" style={{ color: "var(--text-faint)" }}>
        {provider} · llama-3.3-70b
      </span>
    </div>
  );
}

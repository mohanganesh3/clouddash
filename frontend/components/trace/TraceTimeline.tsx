"use client";

import { motion, AnimatePresence } from "framer-motion";
import { GitBranch, ChevronRight, Zap } from "lucide-react";
import { useConversationStore } from "@/store/conversation";
import { AGENT_META } from "@/components/agents/AgentBadge";
import type { AgentType } from "@/lib/types";

const NODE_CONFIG: Record<string, { label: string; category: "pipeline" | "agent" | "retrieval" }> = {
  language_detect:   { label: "Language Detection", category: "pipeline"   },
  RunnableSequence:  { label: "Runnable Chain",     category: "pipeline"   },
  triage:            { label: "Triage Router",      category: "agent"      },
  technical:         { label: "Technical Agent",    category: "agent"      },
  billing:           { label: "Billing Agent",      category: "agent"      },
  knowledge:         { label: "Knowledge Agent",    category: "agent"      },
  escalation:        { label: "Escalation Agent",   category: "agent"      },
  output_guard:      { label: "Output Guardrail",   category: "pipeline"   },
  rewrite:           { label: "Query Rewrite",      category: "retrieval"  },
  parallel_retrieve: { label: "Hybrid Retrieval",   category: "retrieval"  },
  fuse:              { label: "RRF Fusion",          category: "retrieval"  },
  rerank:            { label: "Re-ranking",         category: "retrieval"  },
  relevance_eval:    { label: "Relevance Eval",     category: "retrieval"  },
  supplement:        { label: "Supplement",         category: "retrieval"  },
  web_fallback:      { label: "Web Search",         category: "retrieval"  },
  done:              { label: "Complete",           category: "pipeline"   },
};

const KNOWN_AGENTS = new Set(["triage", "technical", "billing", "knowledge", "escalation"]);

const RETRIEVAL_COLOR = "#7c3aed";

function fmtLatency(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`;
}

export function TraceTimeline() {
  const { traceNodes, traceTools, handoverHistory, totalLatencyMs } = useConversationStore();

  if (traceNodes.length === 0) {
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "48px 0", gap: 10 }}>
        <div style={{ width: 44, height: 44, borderRadius: 12, background: "#1a1d27", border: "1px solid rgba(255,255,255,0.06)", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <GitBranch style={{ width: 18, height: 18, color: "#374151" }} />
        </div>
        <p style={{ fontSize: 11, fontFamily: "'JetBrains Mono', monospace", color: "#374151", textAlign: "center", lineHeight: 1.6 }}>
          send a message<br />to see agent trace
        </p>
      </div>
    );
  }

  const doneCount = traceNodes.filter(n => n.status === "end").length;
  const agentNodes = traceNodes.filter(n => KNOWN_AGENTS.has(n.name) && n.status === "end");
  const totalMs = totalLatencyMs || 0;

  return (
    <div>
      {/* ── Summary header ── */}
      {doneCount > 0 && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          style={{
            marginBottom: 14,
            padding: "8px 12px",
            borderRadius: 8,
            background: "rgba(13,148,136,0.06)",
            border: "1px solid rgba(13,148,136,0.14)",
            display: "flex",
            alignItems: "center",
            gap: 8,
          }}
        >
          <span style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", color: "#14b8a6", textTransform: "uppercase", letterSpacing: "0.08em" }}>
            {doneCount} steps
          </span>
          {agentNodes.length > 0 && (
            <>
              <span style={{ width: 3, height: 3, borderRadius: "50%", background: "#374151", flexShrink: 0 }} />
              <span style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", color: "#6b7280" }}>
                {agentNodes.length} agent{agentNodes.length > 1 ? "s" : ""}
              </span>
            </>
          )}
          {handoverHistory.length > 0 && (
            <>
              <span style={{ width: 3, height: 3, borderRadius: "50%", background: "#374151", flexShrink: 0 }} />
              <span style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", color: "#6b7280" }}>
                {handoverHistory.length} handover{handoverHistory.length > 1 ? "s" : ""}
              </span>
            </>
          )}
          {totalMs > 0 && (
            <span style={{ marginLeft: "auto", fontSize: 10, fontFamily: "'JetBrains Mono', monospace", color: "#4b5563" }}>
              {fmtLatency(totalMs)}
            </span>
          )}
        </motion.div>
      )}

      {/* ── Timeline ── */}
      <div style={{ position: "relative" }}>
        {/* Vertical connector line */}
        {traceNodes.length > 1 && (
          <div style={{ position: "absolute", left: 10, top: 12, bottom: 12, width: 1, background: "rgba(255,255,255,0.05)" }} />
        )}

        <AnimatePresence>
          {traceNodes.map((node, i) => {
            const isDone = node.status === "end";
            const isRunning = node.status === "start";
            const config = NODE_CONFIG[node.name] ?? { label: node.name, category: "pipeline" as const };
            const isAgent = config.category === "agent";
            const isRetrieval = config.category === "retrieval";
            const agentMeta = isAgent ? AGENT_META[node.name as AgentType] : null;

            // Handover banner before agent node (skip first agent)
            const prevAgentNode = isAgent && i > 0
              ? traceNodes.slice(0, i).reverse().find(n => KNOWN_AGENTS.has(n.name))
              : null;
            const handover = prevAgentNode
              ? handoverHistory.find(h => h.from === prevAgentNode.name && h.to === node.name)
              : null;

            return (
              <motion.div
                key={`${node.name}-${i}`}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.2, delay: Math.min(i * 0.05, 0.4) }}
              >
                {/* Handover transition badge */}
                {handover && (
                  <div style={{ display: "flex", alignItems: "center", gap: 5, margin: "4px 0 4px 26px" }}>
                    <Zap style={{ width: 8, height: 8, color: "#14b8a6" }} />
                    <span style={{ fontSize: 9, fontFamily: "'JetBrains Mono', monospace", color: "#14b8a6" }}>
                      handover: {handover.reason?.replace(/_/g, " ") || "routed"}
                    </span>
                  </div>
                )}

                {/* Node row */}
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    padding: isAgent ? "7px 10px 7px 28px" : "3px 8px 3px 28px",
                    marginBottom: isAgent ? 3 : 0,
                    borderRadius: isAgent ? 8 : 4,
                    position: "relative",
                    background: isAgent && agentMeta
                      ? agentMeta.bg
                      : isRetrieval
                      ? "rgba(124,58,237,0.04)"
                      : "transparent",
                    border: isAgent && agentMeta
                      ? `1px solid ${agentMeta.ring}`
                      : isRetrieval
                      ? "1px solid rgba(124,58,237,0.12)"
                      : "1px solid transparent",
                  }}
                >
                  {/* Status dot (positioned on the timeline) */}
                  <div style={{
                    position: "absolute",
                    left: 7,
                    width: 7,
                    height: 7,
                    borderRadius: "50%",
                    zIndex: 1,
                    background: isDone
                      ? (isAgent && agentMeta ? agentMeta.dot : isRetrieval ? RETRIEVAL_COLOR : "#10b981")
                      : (isAgent && agentMeta ? agentMeta.dot : "#14b8a6"),
                    boxShadow: isRunning
                      ? `0 0 8px ${isAgent && agentMeta ? agentMeta.dot : "#14b8a6"}`
                      : "none",
                    animation: isRunning ? "pulse-dot 1.2s ease-in-out infinite" : "none",
                  }} />

                  {/* Label */}
                  <span style={{
                    flex: 1,
                    fontSize: isAgent ? 11 : 10,
                    fontWeight: isAgent ? 600 : 400,
                    fontFamily: "'JetBrains Mono', monospace",
                    color: isAgent && agentMeta
                      ? agentMeta.dot
                      : isRetrieval
                      ? RETRIEVAL_COLOR
                      : isDone ? "#9ca3af" : "#d1d5db",
                  }}>
                    {config.label}
                  </span>

                  {/* Latency badge */}
                  {isDone && node.latency_ms != null && node.latency_ms > 0 && (
                    <span style={{ fontSize: 9, fontFamily: "'JetBrains Mono', monospace", color: "#374151", flexShrink: 0 }}>
                      {fmtLatency(node.latency_ms)}
                    </span>
                  )}
                  {isRunning && (
                    <span style={{ fontSize: 9, fontFamily: "'JetBrains Mono', monospace", color: isAgent && agentMeta ? agentMeta.dot : "#14b8a6", flexShrink: 0 }}>
                      …
                    </span>
                  )}
                </div>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>

      {/* ── Tool calls ── */}
      {traceTools.length > 0 && (
        <div style={{ marginTop: 14, paddingTop: 10, borderTop: "1px solid rgba(255,255,255,0.05)" }}>
          <p style={{ fontSize: 9, fontFamily: "'JetBrains Mono', monospace", color: "#374151", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 6, paddingLeft: 4 }}>
            Tool Calls ({traceTools.length})
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
            {traceTools.map((t, i) => (
              <motion.div
                key={`tool-${i}`}
                initial={{ opacity: 0, x: -4 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.04 }}
                style={{
                  display: "flex", alignItems: "center", gap: 8,
                  padding: "5px 10px", borderRadius: 6,
                  background: "#1a1d27", border: "1px solid rgba(255,255,255,0.05)",
                }}
              >
                <span style={{ fontSize: 10, color: "#d97706", flexShrink: 0 }}>⚙</span>
                <span style={{ flex: 1, fontSize: 10, fontFamily: "'JetBrains Mono', monospace", color: "#9ca3af", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {t.name}
                </span>
                <span style={{
                  fontSize: 9, flexShrink: 0, fontFamily: "'JetBrains Mono', monospace",
                  color: t.status === "end" ? "#10b981" : "#14b8a6",
                }}>
                  {t.status === "end" ? "✓" : "…"}
                </span>
              </motion.div>
            ))}
          </div>
        </div>
      )}

      {/* ── Handover chain (if any) ── */}
      {handoverHistory.length > 0 && (
        <div style={{ marginTop: 14, paddingTop: 10, borderTop: "1px solid rgba(255,255,255,0.05)" }}>
          <p style={{ fontSize: 9, fontFamily: "'JetBrains Mono', monospace", color: "#374151", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 6, paddingLeft: 4 }}>
            Routing Chain
          </p>
          <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 4, paddingLeft: 4 }}>
            {(() => {
              const chain: string[] = [];
              if (handoverHistory.length > 0) {
                chain.push(handoverHistory[0].from);
                handoverHistory.forEach(h => chain.push(h.to));
              }
              return chain.map((agent, i) => {
                const meta = AGENT_META[agent as AgentType];
                if (!meta) return null;
                return (
                  <div key={i} style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    <span style={{ fontSize: 9, fontFamily: "'JetBrains Mono', monospace", padding: "2px 6px", borderRadius: 4, background: meta.bg, color: meta.dot, border: `1px solid ${meta.ring}` }}>
                      {meta.label}
                    </span>
                    {i < chain.length - 1 && (
                      <ChevronRight style={{ width: 8, height: 8, color: "#374151" }} />
                    )}
                  </div>
                );
              });
            })()}
          </div>
        </div>
      )}
    </div>
  );
}

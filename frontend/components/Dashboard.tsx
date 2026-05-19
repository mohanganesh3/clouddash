"use client";

import { useRef, useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Header } from "@/components/layout/Header";
import { AgentStatusPanel } from "@/components/agents/AgentStatusPanel";
import { StreamingMessage } from "@/components/chat/StreamingMessage";
import { HandoverBanner } from "@/components/chat/HandoverBanner";
import { MessageInput } from "@/components/chat/MessageInput";
import { ScenarioButtons } from "@/components/chat/ScenarioButtons";
import { TraceTimeline } from "@/components/trace/TraceTimeline";
import { RetrievedChunks } from "@/components/trace/RetrievedChunks";
import { AgentGraphSVG } from "@/components/visuals/AgentGraphSVG";
import { HITLApprovalDialog } from "@/components/chat/HITLApprovalDialog";
import { useConversationStore } from "@/store/conversation";
import { useStreamingChat } from "@/hooks/useStreamingChat";
import { GitBranch, Database, History, ChevronRight, PlusCircle, ShieldCheck, Workflow, SearchCheck } from "lucide-react";
import { AGENT_META } from "@/components/agents/AgentBadge";

type RightTab = "trace" | "chunks" | "history";

function fmtMs(ms: number) {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`;
}

const PANEL: React.CSSProperties = {
  background: "#131620",
  border: "1px solid rgba(255,255,255,0.07)",
  borderRadius: 14,
};

const INNER: React.CSSProperties = {
  background: "#0f1117",
  border: "1px solid rgba(255,255,255,0.05)",
  borderRadius: 10,
};

function EmptyState() {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", padding: "0 48px" }}>
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        style={{ textAlign: "center", maxWidth: 600, width: "100%" }}
      >
        <div style={{ width: "min(420px, 86vw)", margin: "0 auto 18px", opacity: 0.96 }}>
          <AgentGraphSVG />
        </div>
        <div style={{
          display: "inline-flex", alignItems: "center", gap: 7,
          padding: "4px 12px", borderRadius: 999, marginBottom: 28,
          background: "rgba(13,148,136,0.07)", border: "1px solid rgba(13,148,136,0.18)",
        }}>
          <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#14b8a6", display: "inline-block", boxShadow: "0 0 8px rgba(20,184,166,0.5)" }} />
          <span style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", color: "#14b8a6", letterSpacing: "0.08em", textTransform: "uppercase" }}>
            System Online
          </span>
        </div>

        <h1 style={{ fontSize: 30, fontWeight: 650, color: "#f0f0f5", lineHeight: 1.2, marginBottom: 12 }}>
          CloudDash Support Intelligence
        </h1>
        <p style={{ fontSize: 14, color: "#6b7280", lineHeight: 1.7 }}>
          Ask about alerts, billing, access, or product gaps.<br />
          The live trace shows routing, retrieval, guardrails, handover, and HITL approval.
        </p>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 8, marginTop: 24 }}>
          {[
            { label: "LangGraph", Icon: Workflow, color: "#d97706" },
            { label: "CRAG + RRF", Icon: SearchCheck, color: "#7c3aed" },
            { label: "Guarded HITL", Icon: ShieldCheck, color: "#059669" },
          ].map(({ label, Icon, color }) => (
            <div key={label} style={{ background: "rgba(255,255,255,0.035)", border: `1px solid ${color}33`, borderRadius: 8, padding: "9px 10px", display: "flex", alignItems: "center", justifyContent: "center", gap: 7 }}>
              <Icon style={{ width: 13, height: 13, color }} />
              <span style={{ color: "#9ca3af", fontSize: 11, fontFamily: "'JetBrains Mono', monospace" }}>{label}</span>
            </div>
          ))}
        </div>
      </motion.div>
    </div>
  );
}

function HandoverAuditTrail() {
  const { handoverHistory } = useConversationStore();

  if (!handoverHistory.length) {
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", opacity: 0.4 }}>
        <History style={{ width: 16, height: 16, color: "#6b7280", marginBottom: 6 }} />
        <p style={{ fontSize: 11, fontFamily: "'JetBrains Mono', monospace", color: "#6b7280" }}>no handovers yet</p>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {handoverHistory.map((h, i) => {
        const fromMeta = AGENT_META[h.from];
        const toMeta = AGENT_META[h.to];
        return (
          <motion.div
            key={i}
            initial={{ opacity: 0, x: 6 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.05 }}
            style={{ ...INNER, padding: "10px 12px" }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
              <span style={{ fontSize: 10, padding: "2px 7px", borderRadius: 4, fontFamily: "'JetBrains Mono', monospace", background: fromMeta.bg, color: fromMeta.dot, border: `1px solid ${fromMeta.ring}` }}>
                {fromMeta.label}
              </span>
              <ChevronRight style={{ width: 10, height: 10, color: "#4b5563" }} />
              <span style={{ fontSize: 10, padding: "2px 7px", borderRadius: 4, fontFamily: "'JetBrains Mono', monospace", background: toMeta.bg, color: toMeta.dot, border: `1px solid ${toMeta.ring}` }}>
                {toMeta.label}
              </span>
            </div>
            {h.reason && <p style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", color: "#4b5563", marginBottom: 4 }}>{h.reason.replace(/_/g, " ")}</p>}
            {h.summary && <p style={{ fontSize: 11, color: "#9ca3af", lineHeight: 1.55 }}>{h.summary}</p>}
          </motion.div>
        );
      })}
    </div>
  );
}

export function Dashboard() {
  const {
    messages, isStreaming, currentHandover,
    retrievedChunks, handoverHistory, totalLatencyMs, activeAgents, cragPath,
    pendingInterrupt,
  } = useConversationStore();
  const { sendMessage, stop, newConversation } = useStreamingChat();
  const [rightTab, setRightTab] = useState<RightTab>("trace");
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-switch to chunks tab when chunks arrive
  useEffect(() => {
    if (retrievedChunks.length > 0) setRightTab("chunks");
  }, [retrievedChunks.length]);

  // Auto-switch to history when handovers arrive
  useEffect(() => {
    if (handoverHistory.length > 0) setRightTab("history");
  }, [handoverHistory.length]);

  // Auto-switch back to trace while streaming
  useEffect(() => {
    if (isStreaming) setRightTab("trace");
  }, [isStreaming]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, isStreaming]);

  const hasConversation = messages.length > 0;

  const TABS: Array<{ id: RightTab; label: string; Icon: React.ElementType; badge?: number }> = [
    { id: "trace", label: "Trace", Icon: GitBranch },
    { id: "chunks", label: "Chunks", Icon: Database, badge: retrievedChunks.length || undefined },
    { id: "history", label: "Audit", Icon: History, badge: handoverHistory.length || undefined },
  ];

  return (
    <div style={{
      height: "100vh", width: "100vw",
      background: "#0c0e13",
      display: "flex", flexDirection: "column",
      padding: "12px 16px 16px", gap: 10,
      overflow: "hidden", boxSizing: "border-box",
      position: "relative",
      color: "#f0f0f5",
      fontFamily: "'Inter', ui-sans-serif, system-ui, sans-serif",
    }}>

      {/* HEADER */}
      <div style={{ ...PANEL, flexShrink: 0 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ flex: 1 }}><Header /></div>
          {hasConversation && (
            <button
              onClick={newConversation}
              style={{
                display: "flex", alignItems: "center", gap: 5,
                marginRight: 14, padding: "5px 10px", borderRadius: 7, fontSize: 11,
                fontFamily: "'JetBrains Mono', monospace", color: "#6b7280",
                background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.06)",
                cursor: "pointer", transition: "color 0.15s, background 0.15s",
              }}
              title="New conversation"
            >
              <PlusCircle style={{ width: 11, height: 11 }} />
              New
            </button>
          )}
        </div>
      </div>

      {/* BODY */}
      <div style={{ flex: 1, display: "flex", gap: 10, overflow: "hidden", minHeight: 0 }}>

        {/* LEFT: Agents */}
        <aside style={{ ...PANEL, width: 236, flexShrink: 0, padding: "20px 14px", display: "flex", flexDirection: "column", overflow: "hidden" }}>
          <div style={{ margin: "-6px -2px 12px", padding: "8px 4px 12px", borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
            <AgentGraphSVG />
          </div>
          <AgentStatusPanel />
        </aside>

        {/* CENTER: Chat */}
        <main style={{ ...PANEL, flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
          <div style={{ flex: 1, overflowY: "auto" }}>
            {messages.length === 0 ? (
              <EmptyState />
            ) : (
              <div style={{ padding: "28px 32px 0", maxWidth: 760, margin: "0 auto" }}>
                <AnimatePresence initial={false}>
                  {messages.map((msg) => (
                    <StreamingMessage key={msg.id} message={msg} />
                  ))}
                </AnimatePresence>
                <HandoverBanner handover={currentHandover} />
                <div ref={bottomRef} style={{ height: 20 }} />
              </div>
            )}
          </div>

          {/* Metrics bar — shows after conversation ends */}
          {!isStreaming && totalLatencyMs > 0 && (
            <div style={{ flexShrink: 0, borderTop: "1px solid rgba(255,255,255,0.05)", padding: "6px 20px", display: "flex", alignItems: "center", gap: 16, background: "rgba(13,148,136,0.03)" }}>
              <span style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", color: "#14b8a6" }}>{fmtMs(totalLatencyMs)}</span>
              {activeAgents.length > 0 && (
                <span style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", color: "#4b5563" }}>
                  {activeAgents.length} agent{activeAgents.length > 1 ? "s" : ""}: {activeAgents.join(" → ")}
                </span>
              )}
              {cragPath && cragPath !== "direct" && (
                <span style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", color: cragPath === "web_fallback" ? "#d97706" : "#7c3aed" }}>
                  {cragPath === "web_fallback" ? "⚡ web" : "◈ supplemented"}
                </span>
              )}
              {retrievedChunks.length > 0 && (
                <span style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", color: "#4b5563" }}>
                  {retrievedChunks.length} chunk{retrievedChunks.length > 1 ? "s" : ""} retrieved
                </span>
              )}
            </div>
          )}
          <div style={{ flexShrink: 0, borderTop: "1px solid rgba(255,255,255,0.06)", background: "#0f1117" }}>
            <div style={{ maxWidth: 760, margin: "0 auto" }}>
              <ScenarioButtons onSelect={(msg, sid) => sendMessage(msg, sid)} disabled={isStreaming} />
              <MessageInput onSend={sendMessage} onStop={stop} isStreaming={isStreaming} />
            </div>
          </div>
        </main>

        {/* RIGHT: Trace */}
        <aside style={{ ...PANEL, width: 286, flexShrink: 0, display: "flex", flexDirection: "column", overflow: "hidden" }}>
          <div style={{ display: "flex", padding: "6px 6px 0", borderBottom: "1px solid rgba(255,255,255,0.05)", flexShrink: 0 }}>
            {TABS.map(({ id, label, Icon, badge }) => {
              const active = rightTab === id;
              return (
                <button
                  key={id}
                  onClick={() => setRightTab(id)}
                  style={{
                    flex: 1, display: "flex", alignItems: "center", justifyContent: "center", gap: 5,
                    padding: "7px 4px 8px", fontSize: 11, fontFamily: "'JetBrains Mono', monospace",
                    color: active ? "#14b8a6" : "#4b5563",
                    background: active ? "rgba(13,148,136,0.07)" : "transparent",
                    border: "none", borderBottom: active ? "2px solid #14b8a6" : "2px solid transparent",
                    borderRadius: "6px 6px 0 0", cursor: "pointer",
                    transition: "color 0.15s, background 0.15s",
                  }}
                >
                  <Icon style={{ width: 12, height: 12 }} />
                  {label}
                  {badge && badge > 0 && (
                    <span style={{ fontSize: 9, fontFamily: "'JetBrains Mono', monospace", padding: "0 4px", borderRadius: 4, background: active ? "rgba(13,148,136,0.2)" : "rgba(255,255,255,0.06)", color: active ? "#14b8a6" : "#4b5563" }}>
                      {badge}
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          <div style={{ flex: 1, overflowY: "auto", padding: 12 }}>
            <AnimatePresence mode="wait">
              {rightTab === "trace" && (
                <motion.div key="trace" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.12 }}>
                  <TraceTimeline />
                </motion.div>
              )}
              {rightTab === "chunks" && (
                <motion.div key="chunks" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.12 }}>
                  <RetrievedChunks />
                </motion.div>
              )}
              {rightTab === "history" && (
                <motion.div key="history" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.12 }}>
                  <HandoverAuditTrail />
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </aside>

      </div>

      {pendingInterrupt && <HITLApprovalDialog />}
    </div>
  );
}

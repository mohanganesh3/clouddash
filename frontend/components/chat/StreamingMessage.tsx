"use client";

import { motion } from "framer-motion";
import { AgentBadge, AGENT_META } from "@/components/agents/AgentBadge";
import type { ChatMessage } from "@/lib/types";
import { useConversationStore } from "@/store/conversation";

interface Props {
  message: ChatMessage;
}

// ── Simple inline markdown renderer ──────────────────────────────────────────
function renderMarkdown(text: string): React.ReactNode {
  const lines = text.split("\n");
  const elements: React.ReactNode[] = [];
  let blockKey = 0;
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Heading
    if (line.startsWith("### ")) {
      elements.push(<h3 key={`block-${blockKey++}`} className="font-semibold text-sm mt-3 mb-1" style={{ color: "#e2e8f0" }}>{renderInline(line.slice(4))}</h3>);
      i++; continue;
    }
    if (line.startsWith("## ")) {
      elements.push(<h3 key={`block-${blockKey++}`} className="font-semibold text-sm mt-3 mb-1" style={{ color: "#e2e8f0" }}>{renderInline(line.slice(3))}</h3>);
      i++; continue;
    }

    // Code block
    if (line.startsWith("```")) {
      const lang = line.slice(3).trim();
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) {
        codeLines.push(lines[i]);
        i++;
      }
      elements.push(
        <pre key={`block-${blockKey++}`} className="my-2 rounded-lg overflow-x-auto text-[12px]"
             style={{ background: "#0c0e13", border: "1px solid rgba(255,255,255,0.10)", padding: "12px 14px" }}>
          <code style={{ color: "#e2e8f0", fontFamily: "'JetBrains Mono', monospace" }}>
            {codeLines.join("\n")}
          </code>
        </pre>
      );
      i++; continue;
    }

    // Bullet list
    if (line.match(/^[-*•]\s/)) {
      const items: string[] = [];
      while (i < lines.length && lines[i].match(/^[-*•]\s/)) {
        items.push(lines[i].slice(2));
        i++;
      }
      elements.push(
        <ul key={`block-${blockKey++}`} className="my-1 space-y-1" style={{ paddingLeft: 16 }}>
          {items.map((item, j) => (
            <li key={`item-${j}`} className="text-sm flex items-start gap-2">
              <span style={{ color: "#14b8a6", marginTop: 4, flexShrink: 0 }}>·</span>
              <span>{renderInline(item)}</span>
            </li>
          ))}
        </ul>
      );
      continue;
    }

    // Numbered list
    if (line.match(/^\d+\.\s/)) {
      const items: string[] = [];
      while (i < lines.length && lines[i].match(/^\d+\.\s/)) {
        items.push(lines[i].replace(/^\d+\.\s/, ""));
        i++;
      }
      elements.push(
        <ol key={`block-${blockKey++}`} className="my-1 space-y-1" style={{ paddingLeft: 20, listStyleType: "decimal" }}>
          {items.map((item, j) => (
            <li key={`item-${j}`} className="text-sm" style={{ color: "var(--text-primary)" }}>
              {renderInline(item)}
            </li>
          ))}
        </ol>
      );
      continue;
    }

    // Horizontal rule
    if (line.match(/^---+$/)) {
      elements.push(<hr key={`block-${blockKey++}`} style={{ border: "none", borderTop: "1px solid var(--border-subtle)", margin: "8px 0" }} />);
      i++; continue;
    }

    // Empty line
    if (line.trim() === "") {
      elements.push(<div key={`block-${blockKey++}`} className="h-1.5" />);
      i++; continue;
    }

    // Regular paragraph
    elements.push(
      <p key={`block-${blockKey++}`} className="text-sm leading-relaxed">{renderInline(line)}</p>
    );
    i++;
  }

  return <>{elements}</>;
}

function renderInline(text: string): React.ReactNode {
  // Process: citation [KB-XXX §N], **bold**, `code`, *italic*
  const parts: React.ReactNode[] = [];
  let remaining = text;
  let key = 0;

  const patterns = [
    // Citations
    { re: /\[([A-Z]{2}-[\w-]+)\s*§\s*(\d+)\]/, render: (m: RegExpMatchArray) => (
      <span key={key++} className="citation-chip" title={`${m[1]} §${m[2]}`}>
        {m[1]} §{m[2]}
      </span>
    )},
    { re: /\[([A-Z]{2}-[\w-]+)\]/, render: (m: RegExpMatchArray) => (
      <span key={key++} className="citation-chip">{m[1]}</span>
    )},
    // Bold
    { re: /\*\*(.+?)\*\*/, render: (m: RegExpMatchArray) => (
      <strong key={key++} style={{ fontWeight: 600, color: "#e2e8f0" }}>{m[1]}</strong>
    )},
    // Code
    { re: /`([^`]+)`/, render: (m: RegExpMatchArray) => (
      <code key={key++} style={{
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: "0.8em",
        background: "rgba(13, 148, 136, 0.10)",
        border: "1px solid rgba(13, 148, 136, 0.18)",
        borderRadius: 4,
        padding: "2px 6px",
        color: "#5eead4",
      }}>{m[1]}</code>
    )},
    // Italic
    { re: /\*(.+?)\*/, render: (m: RegExpMatchArray) => (
      <em key={key++} style={{ fontStyle: "italic", color: "#9ca3af" }}>{m[1]}</em>
    )},
  ];

  while (remaining.length > 0) {
    let earliest: { idx: number; len: number; node: React.ReactNode } | null = null;

    for (const { re, render } of patterns) {
      const m = remaining.match(re);
      if (m && m.index !== undefined) {
        if (!earliest || m.index < earliest.idx) {
          earliest = { idx: m.index, len: m[0].length, node: render(m) };
        }
      }
    }

    if (!earliest) {
      parts.push(<span key={key++}>{remaining}</span>);
      break;
    }

    if (earliest.idx > 0) {
      parts.push(<span key={key++}>{remaining.slice(0, earliest.idx)}</span>);
    }
    parts.push(earliest.node);
    remaining = remaining.slice(earliest.idx + earliest.len);
  }

  return <>{parts}</>;
}

// ── Thinking animation ────────────────────────────────────────────────────────
function AgentSignalSVG({ color = "#14b8a6" }: { color?: string }) {
  return (
    <svg width="52" height="34" viewBox="0 0 52 34" fill="none" aria-hidden="true">
      <path d="M5 18C11 7 21 5 29 11C35 15 38 24 47 17" stroke={color} strokeWidth="1.6" strokeLinecap="round" opacity="0.55" />
      <path d="M5 25C13 17 21 17 28 22C35 27 40 27 47 21" stroke="#a78bfa" strokeWidth="1.4" strokeLinecap="round" opacity="0.42" />
      <circle cx="11" cy="12" r="3" fill={color}>
        <animate attributeName="opacity" values="0.45;1;0.45" dur="1.6s" repeatCount="indefinite" />
      </circle>
      <circle cx="28" cy="11" r="3" fill="#f59e0b">
        <animate attributeName="opacity" values="0.35;1;0.35" dur="1.6s" begin="0.25s" repeatCount="indefinite" />
      </circle>
      <circle cx="43" cy="20" r="3" fill="#a78bfa">
        <animate attributeName="opacity" values="0.35;1;0.35" dur="1.6s" begin="0.5s" repeatCount="indefinite" />
      </circle>
    </svg>
  );
}

function ThinkingPanel() {
  const thinkingSteps = useConversationStore((s) => s.thinkingSteps);
  const currentAgent = useConversationStore((s) => s.currentAgent);
  const agentMeta = currentAgent ? AGENT_META[currentAgent] : null;
  const visible = thinkingSteps.slice(-5);

  return (
    <div className="thinking-panel">
      <div className="thinking-panel__visual">
        <AgentSignalSVG color={agentMeta?.dot ?? "#14b8a6"} />
        <div>
          <p className="thinking-panel__title">
            {agentMeta ? `${agentMeta.label} is working` : "CloudDash agents are working"}
          </p>
          <p className="thinking-panel__subtitle">live graph trace</p>
        </div>
      </div>
      <div className="thinking-panel__steps">
        {visible.length > 0 ? visible.map((step, index) => (
          <div key={`${step.name}-${index}`} className="thinking-panel__step">
            <span
              className="thinking-panel__dot"
              style={{
                background: step.status === "end" ? "#10b981" : agentMeta?.dot ?? "#14b8a6",
                animation: step.status === "start" ? "pulse-dot 1.1s ease-in-out infinite" : "none",
              }}
            />
            <span>{step.label}</span>
            <span className="thinking-panel__state">{step.status === "end" ? "done" : "running"}</span>
          </div>
        )) : (
          <div className="thinking-panel__step">
            <span className="thinking-panel__dot" />
            <span>Starting support graph</span>
            <span className="thinking-panel__state">running</span>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────
export function StreamingMessage({ message }: Props) {
  const streamingContent = useConversationStore((s) => s.streamingContent);
  const isUser = message.role === "user";

  const displayContent = message.streaming ? streamingContent : message.content;
  const agentMeta = message.agent ? AGENT_META[message.agent] : null;

  if (isUser) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.2 }}
        className="flex justify-end px-4 py-2"
      >
        <div className="max-w-[72%] flex items-end gap-2.5">
          <div
            className="px-4 py-3 rounded-2xl rounded-tr-sm text-sm leading-relaxed"
            style={{
              background: "linear-gradient(135deg, #0d9488 0%, #22d3ee 100%)",
              color: "#fff",
              boxShadow: "0 4px 20px rgba(13,148,136,0.25)",
            }}
          >
            <div className="prose-user">{renderMarkdown(message.content)}</div>
          </div>
          <div
            className="h-7 w-7 rounded-full flex-shrink-0 flex items-center justify-center text-xs font-semibold mb-0.5"
            style={{
              background: "linear-gradient(135deg, #0d9488, #22d3ee)",
              color: "#fff",
              boxShadow: "0 2px 8px rgba(13,148,136,0.25)",
            }}
          >
            U
          </div>
        </div>
      </motion.div>
    );
  }

  // Assistant message
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className="flex gap-3 px-4 py-2"
    >
      {/* Agent avatar */}
      <div className="flex-shrink-0 mt-0.5">
        {agentMeta ? (
          <div
            className="h-7 w-7 rounded-full flex items-center justify-center text-xs font-bold"
            style={{
              background: agentMeta.bg,
              border: `1px solid ${agentMeta.ring}`,
              color: agentMeta.dot,
              boxShadow: `0 0 8px ${agentMeta.dot}30`,
            }}
          >
            {agentMeta.label[0]}
          </div>
        ) : (
          <div
            className="h-7 w-7 rounded-full"
            style={{
              background: "#2a2e3d",
              border: "1px solid rgba(255,255,255,0.06)",
            }}
          />
        )}
      </div>

      {/* Bubble */}
      <div className="max-w-[76%] space-y-2 min-w-0">
        {/* Agent label row */}
        {message.agent && !message.streaming && (
          <div className="flex items-center gap-2">
            <AgentBadge agent={message.agent} size="xs" />
            {message.latency_ms && (
              <span className="text-[11px]" style={{ color: "#6b7280", fontFamily: "'JetBrains Mono', monospace" }}>
                {message.latency_ms >= 1000 ? `${(message.latency_ms / 1000).toFixed(1)}s` : `${message.latency_ms}ms`}
              </span>
            )}
          </div>
        )}

        {/* Content bubble */}
        <div
          className="rounded-2xl rounded-tl-sm px-4 py-3 text-sm"
          style={{
            background: "#1a1d27",
            border: "1px solid rgba(255,255,255,0.06)",
            boxShadow: "0 2px 12px rgba(0,0,0,0.2)",
          }}
        >
          {message.streaming ? (
            displayContent.trim().length > 0 ? (
              <div style={{ position: "relative" }}>
                <div className="prose-message">{renderMarkdown(displayContent)}</div>
                <span style={{
                  display: "inline-block", width: 2, height: "1em",
                  background: "#14b8a6", marginLeft: 2, verticalAlign: "text-bottom",
                  animation: "pulse-dot 0.8s ease-in-out infinite",
                }} />
              </div>
            ) : (
              <ThinkingPanel />
            )
          ) : (
            <div className="prose-message">
              {renderMarkdown(displayContent)}
            </div>
          )}
        </div>

        {/* Footer chips */}
        {!message.streaming && (
          <div className="flex items-center gap-2 flex-wrap">
            {message.crag_path && message.crag_path !== "direct" && (
              <span
                className="text-[10px] px-2 py-0.5 rounded-full"
                style={{
                  fontFamily: "'JetBrains Mono', monospace",
                  background: message.crag_path === "web_fallback" ? "rgba(245,158,11,0.10)" : "rgba(167,139,250,0.10)",
                  color: message.crag_path === "web_fallback" ? "#f59e0b" : "#a78bfa",
                  border: `1px solid ${message.crag_path === "web_fallback" ? "rgba(245,158,11,0.25)" : "rgba(167,139,250,0.25)"}`,
                }}
              >
                {message.crag_path === "web_fallback" ? "⚡ web search" : "◈ supplemented"}
              </span>
            )}
          </div>
        )}
      </div>
    </motion.div>
  );
}

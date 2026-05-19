"use client";

import { useConversationStore } from "@/store/conversation";
import { Database, Globe, AlertCircle } from "lucide-react";

const CRAG_CONFIG = {
  direct:       { label: "KB direct",     color: "#10b981",  bg: "rgba(16,185,129,0.06)",   icon: Database },
  supplement:   { label: "Supplemented",  color: "#7c3aed",  bg: "rgba(124,58,237,0.06)", icon: Database },
  web_fallback: { label: "Web search",    color: "#d97706",  bg: "rgba(217,119,6,0.06)",  icon: Globe    },
};

function ScoreBar({ score }: { score: number }) {
  const pct = Math.min(100, Math.round(score * 100));
  const color = pct > 70 ? "#10b981" : pct > 40 ? "#d97706" : "#ef4444";
  return (
    <div className="flex items-center gap-2">
      <div className="score-bar" style={{ width: 48 }}>
        <div
          className="score-bar-fill"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
      <span className="text-[10px]" style={{ color: "#6b7280", fontFamily: "'JetBrains Mono', monospace", minWidth: 28 }}>
        {pct}%
      </span>
    </div>
  );
}

export function RetrievedChunks() {
  const { retrievedChunks, cragPath } = useConversationStore();

  if (!retrievedChunks.length) {
    return (
      <div className="flex flex-col items-center justify-center py-16 gap-3">
        <div
          className="h-12 w-12 rounded-xl flex items-center justify-center"
          style={{ background: "#1a1d27", border: "1px solid rgba(255,255,255,0.06)" }}
        >
          <Database className="h-5 w-5" style={{ color: "#374151" }} />
        </div>
        <p className="text-xs text-center" style={{ color: "#374151", fontFamily: "'JetBrains Mono', monospace" }}>
          no retrieval yet
        </p>
      </div>
    );
  }

  const cragCfg = cragPath ? CRAG_CONFIG[cragPath] : null;

  return (
    <div className="space-y-2.5">
      {/* CRAG path pill */}
      {cragCfg && (
        <div
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-[11px] font-mono mb-3"
          style={{
            background: cragCfg.bg,
            color: cragCfg.color,
            border: `1px solid ${cragCfg.color}30`,
          }}
        >
          <cragCfg.icon className="h-3.5 w-3.5" />
          {cragCfg.label}
          <span className="ml-auto" style={{ color: "#6b7280" }}>
            {retrievedChunks.length} chunks
          </span>
        </div>
      )}

      {/* Chunks */}
      {retrievedChunks.map((chunk, i) => (
        <div
          key={chunk.chunk_id ?? i}
          className="rounded-lg p-3 space-y-2"
          style={{
            background: "#1a1d27",
            border: "1px solid rgba(255,255,255,0.06)",
          }}
        >
          {/* Header */}
          <div className="flex items-start justify-between gap-2">
            <span
              className="text-[10px] font-semibold"
              style={{ color: "#14b8a6", fontFamily: "'JetBrains Mono', monospace" }}
            >
              [{chunk.kb_id} §{chunk.section}]
            </span>
            <div className="flex items-center gap-1.5">
              {chunk.source === "web" && (
                <Globe className="h-3 w-3" style={{ color: "#d97706" }} />
              )}
              <ScoreBar score={chunk.score} />
            </div>
          </div>

          {/* Title */}
          <p className="text-xs font-medium" style={{ color: "#f0f0f5" }}>
            {chunk.title}
          </p>

          {/* Why */}
          {chunk.why && (
            <p className="text-[10px] italic" style={{ color: "#6b7280" }}>
              {chunk.why}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}

"use client";

import { motion, AnimatePresence } from "framer-motion";
import { ArrowRight, Zap } from "lucide-react";
import { AGENT_META } from "@/components/agents/AgentBadge";
import type { HandoverEvent } from "@/lib/types";

interface Props {
  handover: HandoverEvent | null;
}

export function HandoverBanner({ handover }: Props) {
  return (
    <AnimatePresence>
      {handover && (
        <motion.div
          key={`${handover.from}-${handover.to}`}
          initial={{ opacity: 0, y: -4, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: -4, scale: 0.98 }}
          transition={{ duration: 0.2 }}
          className="mx-auto my-3 flex items-center gap-3 rounded-xl px-4 py-2.5 text-sm max-w-3xl"
          style={{
            background: "#1a1d27",
            border: "1px solid rgba(255,255,255,0.08)",
          }}
        >
          <Zap className="h-3.5 w-3.5 flex-shrink-0" style={{ color: "#14b8a6" }} />

          <span className="text-[10px]" style={{ color: "#6b7280", fontFamily: "'JetBrains Mono', monospace" }}>
            handover
          </span>

          {/* From badge */}
          <span
            className="text-[10px] px-2 py-0.5 rounded-md font-mono"
            style={{
              background: AGENT_META[handover.from].bg,
              color: AGENT_META[handover.from].dot,
              border: `1px solid ${AGENT_META[handover.from].ring}`,
            }}
          >
            {AGENT_META[handover.from].label}
          </span>

          <ArrowRight className="h-3 w-3 flex-shrink-0" style={{ color: "#4b5563" }} />

          {/* To badge */}
          <span
            className="text-[10px] px-2 py-0.5 rounded-md font-mono font-semibold"
            style={{
              background: AGENT_META[handover.to].bg,
              color: AGENT_META[handover.to].dot,
              border: `1px solid ${AGENT_META[handover.to].ring}`,
            }}
          >
            {AGENT_META[handover.to].label}
          </span>

          {handover.reason && (
            <span className="ml-auto text-[10px] truncate max-w-[180px]"
                  style={{ color: "#6b7280", fontFamily: "'JetBrains Mono', monospace" }}>
              {handover.reason.replace(/_/g, " ")}
            </span>
          )}

          <span className="text-[10px] flex items-center gap-1" style={{ color: "#10b981" }}>
            <span className="h-1 w-1 rounded-full" style={{ background: "#10b981" }} />
            context preserved
          </span>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

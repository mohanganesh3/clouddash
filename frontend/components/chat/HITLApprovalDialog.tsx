"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { AlertTriangle, CheckCircle2, XCircle, Edit3 } from "lucide-react";
import { api } from "@/lib/api";
import { useConversationStore } from "@/store/conversation";
import type { EscalationTicket } from "@/lib/types";
import { v4 as uuidv4 } from "uuid";

const PRIORITY_COLORS = {
  critical: "text-red-400 bg-red-500/10 border-red-500/30",
  high: "text-orange-400 bg-orange-500/10 border-orange-500/30",
  medium: "text-amber-400 bg-amber-500/10 border-amber-500/30",
  low: "text-slate-400 bg-slate-500/10 border-slate-500/30",
};

export function HITLApprovalDialog() {
  const { pendingInterrupt, conversationId, setPendingInterrupt, addMessage } = useConversationStore();
  const [editing, setEditing] = useState(false);
  const [editedTicket, setEditedTicket] = useState<EscalationTicket | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const data = pendingInterrupt;
  if (!data) return null;

  const ticket = editedTicket ?? data.ticket;
  const priorityColor = PRIORITY_COLORS[ticket.priority] ?? PRIORITY_COLORS.medium;

  const handleDecision = async (decision: "approve" | "reject") => {
    if (!conversationId) return;
    setSubmitting(true);
    try {
      const result = await api.resumeHITL(
        conversationId,
        decision === "approve" && editedTicket ? "edit" : decision,
        decision === "approve" && editedTicket ? editedTicket : undefined
      );
      if (result.status === "resumed" && result.message) {
        addMessage({
          id: uuidv4(),
          role: "assistant",
          content: result.message,
          agent: result.agent ?? "escalation",
          latency_ms: result.latency_ms,
        });
      }
    } finally {
      setPendingInterrupt(null);
      setSubmitting(false);
      setEditing(false);
      setEditedTicket(null);
    }
  };

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      >
        <motion.div
          initial={{ scale: 0.92, y: 12 }}
          animate={{ scale: 1, y: 0 }}
          exit={{ scale: 0.92, y: 12 }}
          className="w-full max-w-lg rounded-2xl border border-slate-700 bg-slate-950 shadow-2xl overflow-hidden"
        >
          {/* header */}
          <div className="flex items-center gap-3 px-6 py-4 border-b border-slate-800 bg-rose-500/5">
            <AlertTriangle className="h-5 w-5 text-rose-400 flex-shrink-0" />
            <div>
              <h2 className="text-sm font-semibold text-slate-100">Escalation Approval Required</h2>
              <p className="text-xs text-slate-400 mt-0.5">Review before creating human support ticket</p>
            </div>
          </div>

          <div className="p-6 space-y-4">
            {/* priority badge */}
            <div className="flex items-center gap-2">
              <span className={`text-xs font-mono px-2.5 py-1 rounded-full border ${priorityColor}`}>
                {ticket.priority.toUpperCase()}
              </span>
              <span className="text-xs text-slate-400 font-mono">{ticket.customer_id}</span>
            </div>

            {/* issue summary */}
            <div>
              <p className="text-xs text-slate-500 mb-1 font-mono">issue</p>
              {editing ? (
                <textarea
                  className="w-full rounded-lg bg-slate-900 border border-slate-700 text-slate-100 text-sm px-3 py-2 resize-none focus:outline-none focus:ring-1 focus:ring-blue-500"
                  rows={2}
                  value={editedTicket?.issue_summary ?? ticket.issue_summary}
                  onChange={(e) => setEditedTicket((t) => ({
                    ...(t ?? ticket),
                    issue_summary: e.target.value
                  }))}
                />
              ) : (
                <p className="text-sm text-slate-200">{ticket.issue_summary}</p>
              )}
            </div>

            {/* recommended actions */}
            <div>
              <p className="text-xs text-slate-500 mb-1 font-mono">recommended actions</p>
              <ul className="space-y-1">
                {ticket.recommended_actions.map((a, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-slate-300">
                    <span className="text-blue-400 mt-0.5 flex-shrink-0">→</span>
                    {a}
                  </li>
                ))}
              </ul>
            </div>

            {data.customer_message && (
              <div className="rounded-lg bg-slate-900 border border-slate-800 p-3">
                <p className="text-xs text-slate-500 mb-1 font-mono">customer message</p>
                <p className="text-sm text-slate-300 italic">&ldquo;{data.customer_message}&rdquo;</p>
              </div>
            )}
          </div>

          {/* actions */}
          <div className="flex items-center gap-2 px-6 py-4 border-t border-slate-800 bg-slate-900/50">
            <button
              onClick={() => { setEditing(!editing); if (!editedTicket) setEditedTicket(ticket); }}
              className="flex items-center gap-1.5 text-xs font-mono px-3 py-2 rounded-lg border border-slate-700 text-slate-400 hover:bg-slate-800 transition-colors"
            >
              <Edit3 className="h-3.5 w-3.5" />
              {editing ? "cancel edit" : "edit"}
            </button>
            <div className="flex-1" />
            <button
              onClick={() => handleDecision("reject")}
              disabled={submitting}
              className="flex items-center gap-1.5 text-xs font-mono px-4 py-2 rounded-lg border border-rose-500/30 text-rose-400 hover:bg-rose-500/10 transition-colors disabled:opacity-50"
            >
              <XCircle className="h-3.5 w-3.5" />
              reject
            </button>
            <button
              onClick={() => handleDecision("approve")}
              disabled={submitting}
              className="flex items-center gap-1.5 text-xs font-mono px-4 py-2 rounded-lg bg-emerald-600 text-white hover:bg-emerald-500 transition-colors disabled:opacity-50"
            >
              <CheckCircle2 className="h-3.5 w-3.5" />
              {submitting ? "creating..." : "approve & create ticket"}
            </button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}

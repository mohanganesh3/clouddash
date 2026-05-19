import type { HITLResumeResponse } from "@/lib/types";

export const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8020";
const BASE = BASE_URL;

export const api = {
  health: () => fetch(`${BASE}/api/health`).then((r) => r.json()),

  agents: () => fetch(`${BASE}/api/agents`).then((r) => r.json()),

  reloadAgents: () =>
    fetch(`${BASE}/api/agents/reload`, { method: "POST" }).then((r) => r.json()),

  getConversation: (id: string) =>
    fetch(`${BASE}/api/conversations/${id}`).then((r) => r.json()),

  getTrace: (traceId: string) =>
    fetch(`${BASE}/api/trace/${traceId}`).then((r) => r.json()),

  resumeHITL: (conversationId: string, decision: string, ticket?: unknown) =>
    fetch(`${BASE}/api/hitl/${conversationId}/resume`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision, ticket }),
    }).then((r) => r.json() as Promise<HITLResumeResponse>),

  chatUrl: (message: string, conversationId?: string) => {
    const url = new URL(`${BASE}/api/chat`);
    return url.toString();
  },

  chatBody: (message: string, conversationId?: string, scenarioId?: string) =>
    JSON.stringify({ message, conversation_id: conversationId, scenario_id: scenarioId }),
};

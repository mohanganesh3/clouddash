export type AgentType = "triage" | "technical" | "billing" | "knowledge" | "escalation";

export type CRAGPath = "direct" | "supplement" | "web_fallback";

export interface Citation {
  kb_id: string;
  title: string;
  section: number;
  chunk_id: string;
  relevance_score: number;
  snippet: string;
}

export interface RetrievedChunk {
  chunk_id?: string;
  kb_id: string;
  title: string;
  section: number;
  score: number;
  why: string;
  source: "kb" | "web";
}

export interface HandoverEvent {
  from: AgentType;
  to: AgentType;
  reason: string;
  summary?: string;
}

export interface EscalationTicket {
  ticket_id?: string;
  priority: "critical" | "high" | "medium" | "low";
  customer_id: string;
  issue_summary: string;
  recommended_actions: string[];
  conversation_summary: string;
  sentiment: string;
}

export interface TraceNode {
  name: string;
  status: "start" | "end" | "running";
  ts: number;
  latency_ms?: number;
}

export interface TraceToolCall {
  name: string;
  args?: Record<string, unknown>;
  status: "start" | "end";
  ts: number;
}

export interface ThinkingStep {
  name: string;
  label: string;
  status: "start" | "end";
  ts: number;
}

export type MessageRole = "user" | "assistant";

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  agent?: AgentType;
  citations?: Citation[];
  crag_path?: CRAGPath;
  latency_ms?: number;
  streaming?: boolean;
}

export interface ConversationSummary {
  id: string;
  preview: string;
  ts: number;
  agent?: AgentType;
}

export interface SSEEvent {
  event: string;
  data: Record<string, unknown>;
}

export interface HITLResumeResponse {
  status: "resumed" | "error";
  conversation_id?: string;
  message?: string;
  agent?: AgentType;
  latency_ms?: number;
}

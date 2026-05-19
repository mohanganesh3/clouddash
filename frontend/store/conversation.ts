import { create } from "zustand";
import type {
  ChatMessage,
  RetrievedChunk,
  HandoverEvent,
  TraceNode,
  TraceToolCall,
  ThinkingStep,
  EscalationTicket,
  AgentType,
  CRAGPath,
} from "@/lib/types";

interface ConversationStore {
  // active conversation
  conversationId: string | null;
  messages: ChatMessage[];
  streamingContent: string;
  isStreaming: boolean;

  // trace panel
  traceNodes: TraceNode[];
  traceTools: TraceToolCall[];
  thinkingSteps: ThinkingStep[];
  retrievedChunks: RetrievedChunk[];
  cragPath: CRAGPath | null;

  // handovers
  handoverHistory: HandoverEvent[];
  currentHandover: HandoverEvent | null;

  // agent
  currentAgent: AgentType | null;
  activeAgents: AgentType[];

  // HITL
  pendingInterrupt: { ticket: EscalationTicket; customer_message: string } | null;

  // metrics
  totalLatencyMs: number;
  tokenCount: number;
  provider: string;

  setConversationId: (id: string) => void;
  addMessage: (msg: ChatMessage) => void;
  startTurn: () => void;
  updateStreamingContent: (content: string) => void;
  finalizeStreaming: (msgId: string, final: Partial<ChatMessage>) => void;
  setCurrentAgent: (agent: AgentType) => void;
  addTraceNode: (node: TraceNode) => void;
  updateTraceNode: (name: string, status: "end", latency_ms?: number) => void;
  addTraceTool: (tool: TraceToolCall) => void;
  upsertThinkingStep: (step: ThinkingStep) => void;
  setChunks: (chunks: RetrievedChunk[], path: CRAGPath) => void;
  addHandover: (h: HandoverEvent) => void;
  setPendingInterrupt: (data: { ticket: EscalationTicket; customer_message: string } | null) => void;
  setTotalLatency: (ms: number) => void;
  setProvider: (p: string) => void;
  reset: () => void;
}

export const useConversationStore = create<ConversationStore>((set, get) => ({
  conversationId: null,
  messages: [],
  streamingContent: "",
  isStreaming: false,
  traceNodes: [],
  traceTools: [],
  thinkingSteps: [],
  retrievedChunks: [],
  cragPath: null,
  handoverHistory: [],
  currentHandover: null,
  currentAgent: null,
  activeAgents: [],
  pendingInterrupt: null,
  totalLatencyMs: 0,
  tokenCount: 0,
  provider: "groq",

  setConversationId: (id) => set({ conversationId: id }),

  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),

  startTurn: () =>
    set({
      streamingContent: "",
      isStreaming: true,
      traceNodes: [],
      traceTools: [],
      thinkingSteps: [],
      retrievedChunks: [],
      cragPath: null,
      currentHandover: null,
      totalLatencyMs: 0,
      tokenCount: 0,
    }),

  updateStreamingContent: (content) =>
    set((s) => ({
      streamingContent: s.streamingContent + content,
      tokenCount: s.tokenCount + 1,
      isStreaming: true,
    })),

  finalizeStreaming: (msgId, final) =>
    set((s) => ({
      messages: s.messages.map((m) =>
        m.id === msgId ? {
          ...m,
          ...final,
          content:
            final.content ||
            (s.streamingContent.trim().length > 0
              ? s.streamingContent
              : m.content || "The backend completed the turn but did not return a final answer."),
          streaming: false,
        } : m
      ),
      streamingContent: "",
      isStreaming: false,
    })),

  setCurrentAgent: (agent) =>
    set((s) => ({
      currentAgent: agent,
      activeAgents: s.activeAgents.includes(agent) ? s.activeAgents : [...s.activeAgents, agent],
    })),

  addTraceNode: (node) =>
    set((s) => ({ traceNodes: [...s.traceNodes, node] })),

  updateTraceNode: (name, status, latency_ms) =>
    set((s) => ({
      traceNodes: s.traceNodes.map((n) =>
        n.name === name && n.status === "start" ? { ...n, status, latency_ms } : n
      ),
    })),

  addTraceTool: (tool) =>
    set((s) => ({ traceTools: [...s.traceTools, tool] })),

  upsertThinkingStep: (step) =>
    set((s) => {
      const idx = s.thinkingSteps.findIndex((t) => t.name === step.name);
      if (idx === -1) return { thinkingSteps: [...s.thinkingSteps, step] };
      const next = [...s.thinkingSteps];
      next[idx] = { ...next[idx], ...step };
      return { thinkingSteps: next };
    }),

  setChunks: (chunks, path) => set({ retrievedChunks: chunks, cragPath: path }),

  addHandover: (h) =>
    set((s) => ({
      handoverHistory: [...s.handoverHistory, h],
      currentHandover: h,
      currentAgent: h.to,
    })),

  setPendingInterrupt: (data) => set({ pendingInterrupt: data }),

  setTotalLatency: (ms) => set({ totalLatencyMs: ms }),

  setProvider: (p) => set({ provider: p }),


  reset: () =>
    set({
      messages: [],
      streamingContent: "",
      isStreaming: false,
      traceNodes: [],
      traceTools: [],
      thinkingSteps: [],
      retrievedChunks: [],
      cragPath: null,
      handoverHistory: [],
      currentHandover: null,
      currentAgent: null,
      activeAgents: [],
      pendingInterrupt: null,
      totalLatencyMs: 0,
      tokenCount: 0,
    }),
}));

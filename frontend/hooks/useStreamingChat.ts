"use client";

import { useCallback, useRef } from "react";
import { useConversationStore } from "@/store/conversation";
import { api, BASE_URL } from "@/lib/api";
import type { AgentType, CRAGPath, EscalationTicket, HandoverEvent } from "@/lib/types";
import { v4 as uuidv4 } from "uuid";

// install: npm i uuid @types/uuid
// had to add uuid manually — nanoid is in the next.js bundle but uuid is fine for IDs

export function useStreamingChat() {
  const store = useConversationStore();
  const abortRef = useRef<AbortController | null>(null);

  const sendMessage = useCallback(
    async (text: string, scenarioId?: string) => {
      if (store.isStreaming) return;

      // new conversation or reuse existing
      let convId = store.conversationId;
      if (!convId) {
        convId = uuidv4();
        store.setConversationId(convId);
      }

      store.startTurn();

      // add user message immediately
      store.addMessage({
        id: uuidv4(),
        role: "user",
        content: text,
      });

      // placeholder for streaming assistant message
      const assistantId = uuidv4();
      store.addMessage({
        id: assistantId,
        role: "assistant",
        content: "",
        streaming: true,
      });

      abortRef.current = new AbortController();

      try {
        const resp = await fetch(`${BASE_URL}/api/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: api.chatBody(text, convId ?? undefined, scenarioId),
          signal: abortRef.current.signal,
        });

        if (!resp.ok || !resp.body) {
          store.finalizeStreaming(assistantId, {
            content: "Failed to connect to server. Is the backend running?",
          });
          return;
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let rawBuf = "";
        let finalMsg: Partial<import("@/lib/types").ChatMessage> = {};
        let finalized = false;

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          rawBuf += decoder.decode(value, { stream: true });

          // SSE format: each event is "event: X\ndata: {...}\n\n"
          const blocks = rawBuf.split("\n\n");
          rawBuf = blocks.pop() ?? ""; // keep incomplete block

          for (const block of blocks) {
            if (!block.trim()) continue;
            const blockLines = block.split("\n");
            const eventLine = blockLines.find((l) => l.startsWith("event: "));
            const dataLine = blockLines.find((l) => l.startsWith("data: "));
            const etype = eventLine?.slice(7).trim() ?? "";
            const rawData = dataLine?.slice(6).trim() ?? "";
            if (!rawData) continue;

            let data: Record<string, unknown> = {};
            try { data = JSON.parse(rawData); } catch { continue; }

            switch (etype) {
              case "meta":
                if (data.conversation_id) store.setConversationId(data.conversation_id as string); // eslint-disable-line
                break;

              case "phase":
                store.upsertThinkingStep({
                  name: data.name as string,
                  label: data.label as string,
                  status: data.status as "start" | "end",
                  ts: data.ts as number,
                });
                break;

              case "node":
                if (data.status === "start") {
                  store.addTraceNode({ name: data.name as string, status: "start", ts: data.ts as number });
                  // update active agent from node name
                  const knownAgents: AgentType[] = ["triage", "technical", "billing", "knowledge", "escalation"];
                  if (knownAgents.includes(data.name as AgentType)) {
                    store.setCurrentAgent(data.name as AgentType);
                  }
                } else {
                  store.updateTraceNode(data.name as string, "end", data.latency_ms as number);
                }
                break;

              case "tool":
                store.addTraceTool({
                  name: data.name as string,
                  args: data.args as Record<string, unknown>,
                  status: data.status as "start" | "end",
                  ts: Date.now(),
                });
                break;

              case "token":
                if (typeof data.content === "string" && data.content.trim().length > 0) {
                  store.updateStreamingContent(data.content);
                }
                break;

              case "answer_start":
                if (data.agent) store.setCurrentAgent(data.agent as AgentType);
                break;

              case "chunks":
                store.setChunks(
                  data.chunks as import("@/lib/types").RetrievedChunk[],
                  (data.crag_path as CRAGPath) ?? "direct"
                );
                break;

              case "handover":
                store.addHandover(data as unknown as HandoverEvent);
                break;

              case "interrupt":
                store.setPendingInterrupt({
                  ticket: data.ticket_draft as EscalationTicket,
                  customer_message: (data.customer_message as string) ?? "",
                });
                finalMsg = {
                  content: (data.customer_message as string) || "This needs human approval before I create the support ticket.",
                  agent: "escalation",
                };
                if (!finalized) {
                  store.finalizeStreaming(assistantId, finalMsg);
                  finalized = true;
                }
                break;

              case "final":
                finalMsg = {
                  content: data.message as string,
                  agent: data.agent as AgentType,
                  citations: data.citations as import("@/lib/types").Citation[],
                  crag_path: data.crag_path as CRAGPath,
                  latency_ms: data.latency_ms as number,
                };
                if (!finalized) {
                  store.finalizeStreaming(assistantId, finalMsg);
                  finalized = true;
                }
                break;

              case "done":
                store.setTotalLatency(data.total_latency_ms as number);
                break;

              case "error":
                finalMsg = { content: (data.message as string) ?? "An error occurred." };
                if (!finalized) {
                  store.finalizeStreaming(assistantId, finalMsg);
                  finalized = true;
                }
                break;
            }
          }
        }

        if (!finalized) {
          store.finalizeStreaming(assistantId, finalMsg);
        }
      } catch (err: unknown) {
        if (err instanceof Error && err.name !== "AbortError") {
          const detail = err.message ? ` (${err.message})` : "";
          store.finalizeStreaming(assistantId, {
            content: `Backend unreachable at ${BASE_URL}${detail}. Make sure the server is running.`,
          });
        }
      }
    },
    [store]
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const newConversation = useCallback(() => {
    store.setConversationId(uuidv4());
    store.reset();
  }, [store]);

  return { sendMessage, stop, newConversation };
}

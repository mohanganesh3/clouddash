# REQUIREMENTS MATRIX — Forensic Read of the Assignment

> Every line of the assignment → concrete deliverable → rubric line it satisfies → differentiator vs. baseline submission.

Legend: **Rubric** = SD (System Design 25%) · KB (Knowledge Base 25%) · HO (Handover 20%) · CQ (Code Quality 15%) · GP (Guardrails & Production 15%)

---

## Section 1 — Problem Statement

| Requirement (verbatim) | Deliverable | Rubric | Baseline submission | Our edge |
|---|---|---|---|---|
| "Accept a customer query via a simple API endpoint or CLI interface" | FastAPI `POST /conversations`, `POST /conversations/{id}/messages`, `GET /conversations/{id}` + CLI fallback | SD, CQ | Single endpoint, no session model | Full conversation lifecycle, trace_id in every response |
| "Route the query to the appropriate specialized agent based on intent classification" | Triage Agent classifies + routes via Agent Registry | SD | Hardcoded if/else | Registry-driven, multi-intent support (Scenario 2) |
| "Retrieve relevant information from a knowledge base to ground agent responses" | Hybrid RAG with citations | KB | Naive cosine | BM25 + dense + RRF + reranker + contextual chunking |
| "Seamlessly hand over context between agents when a conversation crosses domain boundaries" | Typed `HandoverPacket` | HO | History-list passing | Pydantic schema, ack/reject, prior_attempts |
| "Escalate to a human operator (simulated) when the system cannot resolve" | Escalation Agent + simulated human queue | HO, SD | Print "escalated" | Structured packet with sentiment + urgency, queue endpoint, replayable |

---

## Section 1.1 — Product Context

| Implicit signal | Deliverable |
|---|---|
| 4 issue categories: technical, billing, account, general | We build agents for the 3 named (Tech/Billing/Escalation) + Triage handles general/account inquiries by default — and document this in DESIGN.md |
| "B2B SaaS platform" | KB articles use B2B language (org admin, RBAC, SSO) |
| Multi-cloud (AWS/GCP/Azure) | KB has at least one article per cloud provider |

---

## Section 2.1 — Agent Architecture

| Required agent | Capabilities (verbatim) | Our implementation |
|---|---|---|
| **Triage** | Intent classification, entity extraction, routing logic | Haiku-powered classifier, Pydantic `Intent` enum, multi-intent decomposition for Scenario 2 |
| **Technical Support** | KB retrieval, step-by-step troubleshooting, code snippet generation | Sonnet, RAG-grounded, returns structured troubleshooting with citations |
| **Billing** | Account lookup (mock), plan comparison, policy citation | Sonnet + mock CRM tool, plan-comparison utility, policy-citation enforcement |
| **Escalation** | Context summarization, priority classification, handover packaging | Haiku for summary, sentiment + urgency classifier, packages full audit chain |
| *(implicit)* "You may add more if your design calls for it" | We add a **`KnowledgeAgent`** (general inquiries / FAQ) so Triage doesn't hand to a billing agent for "what is CloudDash" — keeps domains clean |

---

## Section 2.2 — Knowledge Base Integration

| Requirement | Deliverable | Rubric | Edge |
|---|---|---|---|
| Ingest provided KB | `knowledge_base/` with 18+ Markdown articles + frontmatter | KB | We exceed the 15–20 minimum (one extra per category) |
| Chunking, embedding, indexing | `retrieval/ingest.py` with markdown-aware chunker | KB | Contextual prefix per chunk (Anthropic's contextual retrieval) |
| Vector store | ChromaDB (local, persisted) | KB | Swappable interface — interview talking point |
| **Conversation-aware query rewriting** | `retrieval/query_rewriter.py` — uses last 3 turns | KB | Most candidates skip this entirely |
| **Cite/reference retrieved chunks** | Inline `[KB-XXX § N]` markers + raw chunks in API response | KB | Citation grounding validator (post-LLM) ensures every claim is cited |
| Bonus: hybrid retrieval | BM25 + dense + RRF | KB | ✅ implemented |
| Bonus: reranking | bge-reranker-v2-m3 | KB | ✅ implemented |

---

## Section 2.3 — Agent Handover Protocol

| Requirement | Deliverable | Rubric | Edge |
|---|---|---|---|
| Preserve full conversation history or structured summary | Both — full history available + LLM summary in packet | HO | Two-layer: full history for replay, summary for receiving agent's context |
| Transfer extracted entities without loss | `extracted_entities: Dict` in packet, schema-validated | HO | Pydantic enforces required fields per handover reason |
| Receiving agent acknowledges and continues seamlessly | `HandoverAck` message emitted before customer-facing reply | HO | Most submissions skip the ack step |
| **Handle failed handovers gracefully** — fall back to Triage or Escalation | Circuit breaker + fallback chain in orchestrator | HO, GP | Explicit `HandoverReject` path with retry then fallback |
| **Log every handover event** with timestamp, source, target, reason, context snapshot | Structured JSONL log + `/trace/{id}` endpoint | HO, GP | Replayable — we can show the timeline live |

---

## Section 2.4 — Conversation Interface

| Option | We deliver |
|---|---|
| Option A (Recommended): REST API | ✅ FastAPI primary interface |
| Option B: CLI | ✅ Bonus — `python -m clouddash.cli` for terminal demo |
| Option C (Bonus): Web UI | ✅ Minimal HTMX UI bundled in FastAPI — one-page chat with live trace panel |

---

## Section 3.1 — Code Quality & Structure

| Requirement | Deliverable |
|---|---|
| Clean separation of concerns | `agents/`, `orchestrator/`, `retrieval/`, `handover/`, `guardrails/`, `api/`, `config/`, `evals/`, `tests/` |
| Typed data models (Pydantic/dataclasses) | Pydantic v2 everywhere — `models.py` with `ConversationState`, `Message`, `HandoverPacket`, `AgentResponse`, `Citation`, `RetrievedChunk` |
| Meaningful error handling — not bare try/except | Custom exception hierarchy: `CloudDashError` → `RetrievalError`, `HandoverError`, `GuardrailViolation`, `LLMError` |
| README with: setup, architecture, decisions, limitations | `README.md` (concise) + `DESIGN.md` (ADRs) + `ARCHITECTURE.md` (Mermaid diagrams) + `TRADEOFFS.md` |

---

## Section 3.2 — Observability & Logging

| Requirement | Deliverable |
|---|---|
| Structured JSON logging for every agent invocation, KB retrieval, handover | `structlog` JSONRenderer; every log line has `trace_id`, `turn_id`, `agent`, `event_type` |
| Unique trace ID per conversation | UUID v4 generated on conversation start, propagated via context-var |
| Bonus: Langfuse / LangSmith / Phoenix | Langfuse client, optional via env var |

---

## Section 3.3 — Guardrails & Safety

| Requirement | Deliverable |
|---|---|
| At least one input guardrail | **Three:** prompt-injection detector, off-topic filter, PII inbound scrubber |
| At least one output guardrail | **Three:** citation grounding check, PII outbound redaction, schema validator |
| Never fabricate CloudDash info | Citation grounding validator + "not in KB" refusal pattern + escalation offer (Scenario 4) |

---

## Section 3.4 — Configuration & Extensibility

| Requirement | Deliverable | Edge |
|---|---|---|
| Agent definitions configurable via YAML/JSON | `config/agents.yaml`, `config/routing.yaml`, `config/prompts/*.md` | All system prompts live as Markdown files — versionable, diffable, reviewable |
| **Adding a new agent should not require modifying core orchestration code** | `AgentRegistry` with dynamic class loading via `importlib` | Live demo: add Onboarding Agent in 60s |

---

## Section 6 — Test Scenarios (the live demo gauntlet)

| # | Scenario | What we explicitly handle |
|---|---|---|
| 1 | Single-agent (alerts after AWS update, Pro plan) | Triage → Tech with `customer_plan: Pro` extracted; KB retrieves AWS-integration + alert-config articles; cited reply |
| 2 | Cross-agent handover (SSO check + plan upgrade) | Multi-intent decomposition in Triage → Tech first → Billing receives full prior context via `HandoverPacket` with `prior_attempts` populated |
| 3 | Escalation (double charge, demands manager) | Billing detects refund-authority limit → Escalation packages: `urgency=high`, `sentiment=frustrated`, `customer_id`, full conversation summary |
| 4 | KB miss (Datadog support) | Retrieval returns low-confidence; grounding guardrail blocks fabrication; agent acknowledges + offers feature-request creation |

We will **encode these as eval cases** so we know they pass before submission. Each gets a transcript saved to `EVAL_RESULTS.md`.

---

## Section 7.2 — Submission (the easily-missed line)

| Requirement | Status |
|---|---|
| Working codebase + README setup | Plan |
| `.env.example` | Plan |
| 15–20 KB articles | Plan: 18 articles |
| Architecture document/diagram | `ARCHITECTURE.md` with Mermaid |
| **PUBLIC DEPLOYMENT WITH LIVE URL** | Plan: Render.com free tier |

---

## Section 8 — Live Discussion Prep (we design FOR these questions)

| Question they will ask | Our prepared answer (engineered into the design) |
|---|---|
| Walk through architecture decisions | `DESIGN.md` ADRs — we read them aloud |
| Run system live, demo Section 6 scenarios | One-command demo + eval harness output already on screen |
| Production scale: multi-tenancy, rate limiting, cost optimization, monitoring | `TRADEOFFS.md` § "Production Evolution" — covers each |
| Failure modes, edge cases | Circuit breakers + fallback chain + audit log replay |
| **Add Onboarding Agent without modifying existing code** | **Live 60-second demo** — type the new agent file + 6 lines of YAML, restart, run a query |

---

## What We Are NOT Building (per Section 7.3 + judgment)

| Skipped | Why |
|---|---|
| Docker / Kubernetes / CI/CD | Section 7.3 explicitly says don't |
| Polished frontend / React app | Section 7.3 explicitly says don't; minimal HTMX is enough |
| Real payment integration | Mock CRM is sufficient and explicitly endorsed |
| Authentication / multi-tenancy | Out of scope; covered as a production-evolution discussion item |
| Streaming responses | Nice-to-have; skip for working code |
| 100% test coverage | Section 7.3 explicitly says don't; we ship ~12 high-signal tests |

All of these go into `TRADEOFFS.md` with a one-line justification.

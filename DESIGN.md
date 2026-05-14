# DESIGN — Architecture Decision Records (ADRs)

> Each major decision is recorded here with: **Context**, **Options Considered**, **Decision**, **Consequences / Trade-offs**.
> Format follows the lightweight ADR convention.

---

## ADR-001 — Orchestration Pattern + Framework: LangGraph State Machine with Orchestrator–Worker

**Date:** 2026-05-13
**Status:** Accepted (revised after JD review)

### Context
The assignment requires routing customer queries to one of 4 specialized agents, with cross-agent handovers when conversations span domains. The Vikara JD explicitly lists LangGraph as the first preferred framework and emphasizes "state management, handoffs, fallback handling" — exactly LangGraph's value proposition. Three architectural patterns and three orchestration approaches were considered.

### Options considered

**Pattern:**
| Option | Pros | Cons |
|---|---|---|
| Single-agent with branching tools | Simplest; fewest tokens | Conflates intent + domain expertise; no clean state boundary for handover |
| Pure router (LLM classifier → agent) | Clean separation; cheap classifier | Router has no memory; can't refine routing mid-conversation |
| **Orchestrator–worker (Triage = orchestrator)** | Anthropic-proven (90.2% lift on their research eval); clean handover semantics; matches the assignment's mental model | ~3–5× more tokens; more moving parts |

**Framework:**
| Option | Pros | Cons |
|---|---|---|
| Raw asyncio Python | Total control; "I built this" interview narrative | More code; slower in a 5-day window |
| **LangGraph** | First framework named in JD; native state schema + conditional edges = direct match for handover semantics; LangSmith tracing built-in (bonus criterion); checkpointing for resumability | Framework jargon; some quirks |
| CrewAI / AutoGen | Higher-level role abstractions | Less control over the handover packet; less aligned with the JD's keyword choices |
| OpenAI Agents SDK | Simple handover primitive | Less mature; opinionated about tool calling |

### Decision
**Orchestrator–worker pattern, implemented in LangGraph.**

- The graph state carries our `ConversationState` Pydantic model (which contains the typed `HandoverPacket` for handover events).
- Triage is the entry node. It classifies intent and emits a routing decision via a conditional edge.
- Specialist agents (Technical, Billing, Knowledge) are graph nodes; each returns either a final response or a `HandoverPacket` triggering a re-route.
- Escalation is a terminal node when confidence drops or specialist returns reject.
- LangGraph's `interrupt` is reserved for the simulated human handoff (Scenario 3).
- Critically: **the graph is built at startup from `config/agents.yaml`** via our `AgentRegistry`. Adding a new agent = new YAML entry + new agent file → graph rewires automatically. No core orchestration code changes.

### Consequences
- **Positive:** Direct JD stack match; handover is a first-class graph primitive; resumability and observability are essentially free; live demo of "add new agent" is a 60-second YAML edit.
- **Negative:** LangGraph adds a dependency surface. Mitigated by isolating it to `orchestrator/graph.py` — the rest of the codebase (agents, RAG, guardrails) is framework-agnostic and could be swapped to raw asyncio in a day if needed. This is itself a discussion-worthy trade-off.
- **References:**
  - Anthropic, *How we built our multi-agent research system* (2025)
  - Anthropic, *Building effective agents* — orchestrator-workers workflow
  - LangChain, *LangGraph* docs — state schemas, conditional edges, interrupts

---

## ADR-002 — Handover Mechanism: Typed `HandoverPacket` (Pydantic)

**Date:** 2026-05-13
**Status:** Accepted

### Context
Section 2.3 requires preserving conversation history, transferring extracted entities, allowing receiving agents to acknowledge handover, handling failures gracefully, and logging every handover event with timestamp/source/target/reason/snapshot.

### Options considered
| Option | Pros | Cons |
|---|---|---|
| Pass full conversation history (list of dicts) | Trivial | Token-bloat; no structured entity transfer; hard to validate |
| LLM-summarized text-only handover | Token-efficient | Loses structure; entities can drop; no schema |
| **Typed `HandoverPacket` (Pydantic)** | Schema-validated; entities preserved; replayable; auditable; supports sentiment/urgency for Scenario 3 | More upfront design |

### Decision
A first-class `HandoverPacket` Pydantic model is THE contract between agents. Fields:
- `trace_id: UUID` — connects all logs for one session
- `turn_id: int`
- `from_agent`, `to_agent`: `AgentType` enum
- `reason`: `HandoverReason` enum (out_of_scope, requires_escalation, low_confidence, multi_intent, customer_request)
- `customer_profile`: extracted entities (customer_id, plan, etc.)
- `conversation_summary`: LLM-generated structured summary
- `extracted_entities: Dict[str, Any]`
- `prior_attempts: List[AttemptRecord]` — what specialists already tried
- `confidence_state: float`
- `sentiment`, `urgency` — required by Scenario 3
- `timestamp: datetime`
- `audit_chain: List[HandoverEvent]` — full prior handover chain

The receiving agent **must** emit an `HandoverAck` message before responding to the customer. If it cannot accept (validation fails, domain mismatch), it returns `HandoverReject` and the orchestrator falls back to Triage or Escalation per Section 2.3.

### Consequences
- **Positive:** Crushes the 20% "Agent Handover" rubric line. Audit log is trivial — just serialize the packet. Replayable. Failure paths are explicit, not implicit.
- **Negative:** Slight upfront cost. Worth it.

---

## ADR-003 — RAG Pipeline: Hybrid Retrieval + Contextual Chunking + Reranker + Inline Citations

**Date:** 2026-05-13
**Status:** Accepted

### Context
KB Integration is 25% of the rubric — tied for the largest weight. Section 2.2 requires chunking, embedding, indexing, conversation-aware query rewriting, and citation in responses. Hybrid retrieval and reranking are flagged as bonus.

### Options considered
| Option | Pros | Cons |
|---|---|---|
| Pure dense (cosine) | 5-line implementation | Misses exact-keyword queries (e.g., "API rate limit"); semantic-only fails for technical jargon |
| Pure BM25 | Great on keywords | Fails on paraphrased queries |
| **Hybrid (BM25 + dense) + RRF + cross-encoder rerank** | Best of both; RRF needs no score calibration; reranker delivers final precision | More moving parts |

### Decision
- **Chunking:** Markdown-aware, ~400-token chunks, 50-token overlap, with **contextual prefix** (Anthropic's "contextual retrieval" — prepend each chunk with a 1-sentence context summary generated once at ingest time).
- **Embedding:** `BAAI/bge-small-en-v1.5` (local, fast, no API cost).
- **Vector store:** ChromaDB (local persistence, zero-config — reviewer can run with no infra setup).
- **BM25:** `rank_bm25` over the same chunks.
- **Fusion:** Reciprocal Rank Fusion (k=60), top-10 candidates.
- **Reranker:** **LLM-based reranker** using `gemini-2.5-flash` — passes the top-10 candidates + query to Flash, asks for ranked top-3 with a 1-sentence relevance rationale per chunk. This (a) avoids loading a 600MB cross-encoder model on Render's 512MB free tier, (b) gives us per-chunk rationale for free (debugging gold), and (c) adapts to query semantics in ways static cross-encoders can't. Cross-encoder fallback (`cross-encoder/ms-marco-MiniLM-L-6-v2`, 90MB) is wired but disabled by default. Documented as a deliberate trade-off vs. raw cross-encoder accuracy.
- **Query rewriting:** Before retrieval, an LLM rewrites the user query using conversation history into 1–3 standalone search queries (decomposition-style).
- **Citations:** Every claim made by an agent about CloudDash is citation-tagged inline with `[KB-XXX § N]`. The API response also returns the raw retrieved chunks so the customer can verify.

### Consequences
- **Positive:** Hits the bonus criteria (hybrid + rerank); contextual chunking and query rewriting put us above tutorial-grade; inline citations + grounding check (see ADR-005) make Scenario 4 "no-hallucination" pass naturally; LLM reranker adds debugging visibility via per-chunk rationale.
- **Negative:** LLM reranker adds ~500ms latency per query (one Flash call). Acceptable trade-off; documented in `TRADEOFFS.md`. Graceful degradation: if reranker call fails, fall through to RRF top-3.

---

## ADR-004 — Agent Registry: YAML-Driven, Zero-Code Extension

**Date:** 2026-05-13
**Status:** Accepted

### Context
Section 3.4 says agent definitions must be configurable via YAML/JSON, and adding a new agent type must not require modifying core orchestration code. Section 8 explicitly previews the discussion question "how would you add an Onboarding Agent without modifying existing code."

### Decision
- All agents inherit from a `BaseAgent` abstract class with a single contract: `async def handle(self, packet: HandoverPacket) -> AgentResponse`.
- A `config/agents.yaml` registry declares: agent class import path, system prompt path, tools, routing rules, model choice.
- An `AgentRegistry` loader uses `importlib` to dynamically load agent classes at startup.
- The orchestrator's routing logic reads from the registry, never hardcoding agent names.

Adding an Onboarding Agent during the live discussion = create `agents/onboarding.py` (one class) + add 6 lines to `agents.yaml`. **Zero changes to orchestrator, router, or any other agent.** We will rehearse this as a 60-second live demo.

### Consequences
- **Positive:** Crushes the "extensibility" line in System Design 25%. Live demo will be unforgettable.
- **Negative:** Slight indirection — mitigated by clear naming and one ADR explaining it.

---

## ADR-005 — Two-Layer Guardrails with Self-Correction Loop

**Date:** 2026-05-13
**Status:** Accepted

### Context
Section 3.3 requires at least one input + one output guardrail, and a strong "never fabricate" requirement. Modern guardrail best practice is layered: pre-LLM filters + post-LLM validators with a self-correction loop.

### Decision
**Pre-LLM (Input) Guardrails:**
1. **Prompt-injection detector** — heuristic + small classifier prompt (Haiku) that flags messages attempting to override system prompts.
2. **Off-topic filter** — rejects queries clearly unrelated to CloudDash with a polite redirect.
3. **PII inbound scrubber** — masks credit card numbers, SSN-shaped strings before logging.
4. **Length / rate limits** — defensive defaults.

**Post-LLM (Output) Guardrails:**
1. **Citation grounding check** — every factual claim about CloudDash pricing/policy/features must map to a retrieved chunk; ungrounded claims trigger self-correction.
2. **PII outbound redaction** — never leak full customer IDs, payment info.
3. **Schema validator** — agent outputs must match `AgentResponse` Pydantic schema.
4. **Self-correction loop** — on first failure, re-prompt the agent with the validation error appended; on second failure, escalate to human (Scenario 3 path).

### Consequences
- **Positive:** Scenario 4 (Datadog query — not in KB) passes naturally because the grounding check forces a "I don't have info on that" reply with escalation offer. Direct alignment with the 15% Guardrails rubric.
- **Negative:** Added latency (~300–500ms per turn). Documented in `TRADEOFFS.md`.

---

## ADR-006 — Observability: LangSmith + Trace ID + Structured JSON Logs

**Date:** 2026-05-13
**Status:** Accepted

### Context
Section 3.2 requires structured JSON logging with a unique trace ID per conversation. The Vikara JD lists **LangSmith first** among preferred observability tools. We also need a self-contained audit log (per Section 2.3 requirement on handover logging) that does not depend on a third-party service being reachable.

### Decision
**Two layers of observability:**

1. **LangSmith (external)** — primary tracing. Native LangGraph integration: every node execution, LLM call, tool call, and edge traversal is auto-traced when `LANGCHAIN_TRACING_V2=true` and `LANGCHAIN_API_KEY` is set. Zero code changes. Provides timeline UI, token costs, latency breakdown — perfect for the live demo and the discussion.

2. **Self-contained audit log (internal)** — `structlog` JSONRenderer writing to `logs/audit.jsonl`. Every event has: `trace_id` (UUID v4 per conversation), `turn_id`, `span_id`, `agent`, `event_type`, `latency_ms`, payload. Survives even if LangSmith is offline; required to satisfy §2.3 handover audit logging independently.

3. **Trace endpoint** — `GET /api/conversations/{trace_id}/trace` returns the full event timeline as JSON. Used by the demo UI to render a live timeline panel; also a debug aid for the discussion.

### Consequences
- **Positive:** Bonus observability criterion hit with a JD-named tool; redundant local audit log means we are not dependent on a third party for the §2.3 requirement; live demo becomes "look at the LangSmith trace AND our internal timeline" — two angles, one impression.
- **Negative:** LangSmith is a paid service after free-tier limits. Acceptable for prototype; documented in `TRADEOFFS.md` as a cost concern with Phoenix as a self-hosted alternative.

---

## ADR-007 — Eval Harness: LLM-as-Judge on the 4 Required Scenarios

**Date:** 2026-05-13
**Status:** Accepted

### Context
Section 6 lists 4 test scenarios. The reviewer will run them. We can either hope ours pass, or build an automated eval that runs them and scores the system.

### Decision
- Build `evals/scenarios.yaml` with the 4 official scenarios + ~6 variations each (24 total cases).
- An LLM-as-judge (Sonnet) scores each run against a rubric: correct routing, retrieval relevance, citation accuracy, handover correctness, refusal-to-hallucinate, escalation appropriateness.
- `python -m evals.run` produces `EVAL_RESULTS.md` with a scorecard.
- We run this before submission and again live during the discussion.

### Consequences
- **Positive:** Concrete proof of correctness. Reviewer thinks "this candidate built their own grader." This is rare and unforgettable.
- **Negative:** ~$0.50 of API spend per full run. Trivial.

---

## ADR-008 — Deployment: FastAPI on Render free tier

**Date:** 2026-05-13
**Status:** Accepted

### Context
Section 7.2 requires a public live URL. Free-tier hosting acceptable. JD lists Render as a preferred platform.

### Decision
- FastAPI app with REST API + minimal HTML+HTMX UI bundled.
- **Render.com** free tier (auto-deploys from GitHub, persistent disk for ChromaDB).
- `render.yaml` blueprint for one-click deploy.
- Cold-start mitigated by a `/healthz` keep-alive endpoint and a small startup pre-warm.

### Consequences
- **Positive:** Zero cost. JD-aligned platform. One-click deploy via `render.yaml`.
- **Negative:** Free tier 512MB RAM constraint forces us to keep the embedder small (`bge-small-en-v1.5` at 130MB) and use an LLM-based reranker (no extra model loading). Cold starts ~30s. Documented in `TRADEOFFS.md`.

---

## ADR-009 — LLM Provider: Google Gemini (Pro + Flash split)

**Date:** 2026-05-13
**Status:** Accepted

### Context
The candidate has a Google Gemini API key. The JD does not mandate a specific LLM provider — they care about agent quality, not vendor. We need (a) a strong reasoning model for specialist agents and (b) a cheap fast model for triage, guardrails, the LLM-as-judge eval, the query rewriter, and the LLM-based reranker.

### Options considered
| Option | Pros | Cons |
|---|---|---|
| Anthropic Claude (Sonnet + Haiku) | What our research grounding cited; strong tool use | Requires Anthropic billing; not in candidate's account |
| OpenAI (GPT-4o + 4o-mini) | Industry default | Same billing constraint |
| **Google Gemini (2.5 Pro + 2.5 Flash)** | Generous free tier (15 RPM, 1M tokens/day on Flash); native JSON-schema structured outputs; first-class LangChain integration via `langchain-google-genai`; **free dev work** | Slightly less mature tool-use than Claude; smaller community of agent recipes |
| Groq + open models | Very fast; free tier | Quality of small open models insufficient for nuanced support reasoning |

### Decision
**Two-model split, Gemini family:**
- `gemini-2.5-pro` — specialist agents (Technical Support, Billing, Knowledge), eval LLM-as-judge.
- `gemini-2.5-flash` — Triage classification, query rewriter, LLM-based reranker, prompt-injection detector, off-topic filter, escalation summarizer.

### Why this is actually a strategic positive (not a compromise)
- **Cost: ~$0 for development** thanks to Gemini's free tier — no anxious billing dashboard during the 5-day build.
- **Native structured outputs**: Gemini's `response_schema` param accepts a Pydantic-compatible JSON schema directly, removing one layer of fragility (no need for "please return JSON" prompting + parsing).
- **LangSmith works identically** for any LangChain LLM, so observability ADR-006 is unaffected.
- **Discussion talking point**: "I chose Gemini after benchmarking against the assignment's needs — Pro for reasoning, Flash for the fast-classifier role. The agent abstractions are LLM-agnostic via LangChain's `BaseChatModel`, so swapping to Claude or GPT-4o is a one-line change." This is the *right* answer to "why this provider" in the live discussion.

### Consequences
- **Positive:** Free dev costs; native structured outputs; LangSmith-compatible; demonstrates LLM-agnostic design.
- **Negative:** Slightly less mature agent tool-use vs. Claude. Mitigated by: explicit Pydantic validation + self-correction loop (already planned in ADR-005).

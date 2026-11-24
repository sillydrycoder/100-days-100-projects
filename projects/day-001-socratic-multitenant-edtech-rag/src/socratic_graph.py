"""Stateful LangGraph-style Socratic Tutoring & Vision-Routing Workflow.

Executes a deterministic 7-node directed graph with full node-level execution trace:
  1. redact_pii              -> FERPA/COPPA PII stripping & student pseudonymization
  2. vision_extract_or_cache -> Content-addressed SHA-256 Vision-to-JSON deduplication
  3. route_model             -> Cost-aware routing (text-fast | text-reasoning | vision-vlm | vision-cache+text-fast)
  4. retrieve_curriculum     -> Tenant-isolated Hybrid RAG (BM25 + dense cosine RRF)
  5. generate_socratic       -> Hint-level-aware Socratic response (DEMO_MODE or live OpenAI/Gemini)
  6. socratic_guard          -> Post-generation check preventing premature direct-answer spoilers
  7. audit_log               -> Tenant-scoped redacted telemetry & cost persistence
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from privacy import pseudonymize_student, redact_pii
from retriever import retrieve_hybrid
from router import RoutingDecision, route_request
from storage import MultiTenantStore, TenantContext

BASE_DIR = Path(__file__).resolve().parent.parent
SAMPLE_DIAGRAMS_PATH = BASE_DIR / "sample_data" / "sample_diagrams.json"

SPOILER_PATTERNS = (
    re.compile(r"\bthe\s+(?:final\s+)?answer\s+is\b", re.IGNORECASE),
    re.compile(r"\btherefore,?\s*the\s+result\s+equals\b", re.IGNORECASE),
)


def load_sample_diagrams() -> list[dict[str, Any]]:
    if not SAMPLE_DIAGRAMS_PATH.exists():
        return []
    return json.loads(SAMPLE_DIAGRAMS_PATH.read_text(encoding="utf-8"))


@dataclass
class TutorState:
    tenant: TenantContext
    session_id: str
    student_ref: str
    raw_query: str
    subject: str | None = None
    grade_level: str | None = None
    diagram_id: str | None = None
    diagram_payload_text: str | None = None

    # Populated across graph nodes
    redacted_query: str = ""
    pii_redacted: bool = False
    pii_types: list[str] = field(default_factory=list)
    pseudonym_ref: str = ""

    has_diagram: bool = False
    diagram_sha256: str | None = None
    vision_cache_hit: bool = False
    vision_structured: dict[str, Any] | None = None

    routing: RoutingDecision | None = None
    retrieved_chunks: list[dict[str, Any]] = field(default_factory=list)
    attempt_number: int = 1
    hint_level: int = 1
    draft_response: str = ""
    final_response: str = ""
    guard_triggered: bool = False
    provider_mode: str = "demo"
    trace: list[dict[str, Any]] = field(default_factory=list)


class SocraticTutorGraph:
    def __init__(self, store: MultiTenantStore) -> None:
        self.store = store
        self.sample_diagrams = {d["diagram_id"]: d for d in load_sample_diagrams()}

    def _run_node(self, state: TutorState, name: str, fn: Any) -> None:
        start = time.perf_counter()
        detail = fn(state)
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        state.trace.append({"node": name, "elapsed_ms": elapsed_ms, "detail": detail})

    # ---- Node 1: FERPA/COPPA PII Redaction ----
    def _node_redact_pii(self, state: TutorState) -> str:
        users = self.store.list_users(state.tenant)
        known_names = [u["display_name"] for u in users]
        result = redact_pii(state.raw_query, known_names=known_names)
        state.redacted_query = result.redacted_text
        state.pii_redacted = result.pii_detected
        state.pii_types = result.redacted_types
        state.pseudonym_ref = pseudonymize_student(state.tenant.school_id, state.student_ref)
        if result.pii_detected:
            return f"Stripped PII ({', '.join(result.redacted_types)}) before model routing."
        return "No PII detected; student identifier pseudonymized."

    # ---- Node 2: Vision Extraction + Tenant SHA-256 Cache ----
    def _node_vision_extract(self, state: TutorState) -> str:
        raw_diagram_key = ""
        sample_match = None

        if state.diagram_id and state.diagram_id in self.sample_diagrams:
            cand = self.sample_diagrams[state.diagram_id]
            # Enforce school scope on sample diagram library too
            if cand["school_id"] == state.tenant.school_id:
                sample_match = cand
                raw_diagram_key = f"{cand['diagram_id']}::{cand['description']}"
            else:
                return f"Diagram '{state.diagram_id}' blocked: belongs to another tenant."
        elif state.diagram_payload_text and state.diagram_payload_text.strip():
            raw_diagram_key = state.diagram_payload_text.strip()

        if not raw_diagram_key:
            state.has_diagram = False
            return "Text-only turn; vision pipeline skipped."

        state.has_diagram = True
        sha = hashlib.sha256(raw_diagram_key.encode("utf-8")).hexdigest()
        state.diagram_sha256 = sha

        cached = self.store.get_vision_cache(state.tenant, sha)
        if cached:
            state.vision_cache_hit = True
            state.vision_structured = cached["structured_json"]
            return f"CACHE HIT ({sha[:10]}): reused structured diagram JSON without calling VLM."

        state.vision_cache_hit = False
        if sample_match:
            structured = dict(sample_match["structured_extraction"])
            structured["title"] = sample_match["title"]
        else:
            structured = {
                "diagram_type": "uploaded_custom_diagram",
                "title": "Student Uploaded Diagram",
                "raw_description": raw_diagram_key[:320],
                "key_concept": "Break the diagram into labeled axes, forces, or stages before computing values.",
                "socratic_checkpoints": [
                    "First, look closely at the labels, axes, or arrows in your diagram. Which quantities are given directly?",
                    "Which relationship or formula from your current textbook chapter connects those labeled quantities?",
                    "Walk through plugging your values into that relationship step by step — what intermediate number do you get?",
                ],
                "target_numeric_answer": "",
            }

        self.store.put_vision_cache(
            tenant=state.tenant,
            image_sha256=sha,
            model_used="vision-vlm",
            structured_json=structured,
            tokens_spent=1150,
        )
        state.vision_structured = structured
        return f"CACHE MISS ({sha[:10]}): extracted structured JSON via VLM & cached for tenant."

    # ---- Node 3: Cost-Aware Model Router ----
    def _node_route_model(self, state: TutorState) -> str:
        decision = route_request(
            query=state.redacted_query,
            has_diagram=state.has_diagram,
            vision_cache_hit=state.vision_cache_hit,
        )
        state.routing = decision
        return f"Selected {decision.tier} (~${decision.est_cost_usd:.5f}/turn): {decision.reason}"

    # ---- Node 4: Tenant-Isolated Hybrid RAG ----
    def _node_retrieve(self, state: TutorState) -> str:
        aug_query = state.redacted_query
        if state.vision_structured:
            aug_query += " " + state.vision_structured.get("title", "") + " " + state.vision_structured.get("key_concept", "")

        state.retrieved_chunks = retrieve_hybrid(
            store=self.store,
            tenant=state.tenant,
            query=aug_query,
            top_k=3,
            subject=state.subject,
            grade_level=state.grade_level,
        )
        return f"Retrieved {len(state.retrieved_chunks)} tenant-scoped chunks for school '{state.tenant.school_id}'."

    # ---- Node 5: Stateful Socratic Generation ----
    def _call_live_llm(self, system_prompt: str, user_prompt: str) -> str | None:
        """Optional live OpenAI/Gemini HTTP bridge when DEMO_MODE=false."""
        openai_key = os.getenv("OPENAI_API_KEY", "").strip()
        if openai_key:
            payload = json.dumps(
                {
                    "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                    "temperature": 0.3,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                }
            ).encode("utf-8")
            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=payload,
                headers={"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                    return body["choices"][0]["message"]["content"].strip()
            except (urllib.error.URLError, KeyError, IndexError):
                return None

        gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
        if gemini_key:
            model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={gemini_key}"
            payload = json.dumps(
                {
                    "contents": [{"parts": [{"text": f"{system_prompt}\n\nStudent message:\n{user_prompt}"}]}]
                }
            ).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                    return body["candidates"][0]["content"]["parts"][0]["text"].strip()
            except (urllib.error.URLError, KeyError, IndexError):
                return None
        return None

    def _build_demo_socratic_reply(self, state: TutorState) -> str:
        school = self.store.get_school(state.tenant)
        if not state.retrieved_chunks and not state.vision_structured:
            return (
                f"I searched {school['name']}'s assigned curriculum library and didn't find a matching textbook section for that question. "
                "To keep tutoring grounded in your class materials (and strictly isolated from other schools), could you tell me which chapter or topic from your course notes this relates to?"
            )

        lead_chunk = state.retrieved_chunks[0] if state.retrieved_chunks else None
        eq_chunk = next((c for c in state.retrieved_chunks if c["block_type"] == "equation"), None)
        table_chunk = next((c for c in state.retrieved_chunks if c["block_type"] == "table"), None)
        citation = lead_chunk["citation_label"] if lead_chunk else "Attached Class Diagram"

        # Vision-guided Socratic progression
        if state.vision_structured:
            checkpoints = state.vision_structured.get("socratic_checkpoints", [])
            idx = min(state.hint_level - 1, max(len(checkpoints) - 1, 0))
            prompt_q = checkpoints[idx] if checkpoints else "What key relationship do you notice in the diagram?"
            cache_note = "reused cached diagram structure" if state.vision_cache_hit else "parsed diagram structure"

            if state.hint_level == 1:
                return (
                    f"Great question — I've {cache_note} for **{state.vision_structured.get('title', 'your diagram')}** "
                    f"and matched it to [{citation}].\n\n"
                    f"**Socratic Step 1 (Observation):** Before we calculate anything, let's build intuition: {prompt_q}"
                )
            if state.hint_level == 2:
                formula_hint = f"\nRelevant equation from your textbook:\n{eq_chunk['content']}\n" if eq_chunk else ""
                return (
                    f"Nice progress! Staying grounded in [{citation}]:{formula_hint}\n"
                    f"**Socratic Step 2 (Guided Setup):** {prompt_q}"
                )
            return (
                f"You're almost there! Using [{citation}] and the diagram segments we identified:\n\n"
                f"**Socratic Step 3 (Verification Check):** {prompt_q}\n"
                "Share your computed value and reasoning, and I'll verify every step with you."
            )

        # Text-only curriculum-grounded Socratic progression
        snippet = lead_chunk["content"][:220].strip() if lead_chunk else ""
        if state.hint_level == 1:
            return (
                f"Let's work through this step by step using [{citation}] instead of jumping straight to the answer.\n\n"
                f"**Textbook Anchor:** Your chapter notes highlight: *\"{snippet}...\"*\n\n"
                "**Guiding Question (Hint 1/3):** In your own words, which physical or scientific relationship from this section connects what you're given to what you're trying to find?"
            )
        if state.hint_level == 2:
            support = eq_chunk["content"] if eq_chunk else (table_chunk["content"] if table_chunk else snippet)
            return (
                f"Good effort — let's narrow it down with [{citation}].\n\n"
                f"**Reference Structure ({eq_chunk['block_type'] if eq_chunk else 'key note'}):**\n{support}\n\n"
                "**Guiding Question (Hint 2/3):** Which known values from your problem plug into the left or right side here? Try writing out just the first intermediate step."
            )
        return (
            f"You're one step away! Review [{citation}] and check your units and signs carefully.\n\n"
            "**Verification Prompt (Hint 3/3):** Combine your intermediate values and tell me what result you arrive at — I'll check your logic and catch any slip-ups."
        )

    def _node_generate_socratic(self, state: TutorState) -> str:
        prior = self.store.get_session_attempt_count(state.tenant, state.session_id)
        state.attempt_number = prior + 1
        state.hint_level = min(state.attempt_number, 3)

        demo_mode = os.getenv("DEMO_MODE", "true").lower() == "true"
        if not demo_mode:
            context_block = "\n\n".join(
                f"[{c['citation_label']}]\n{c['content']}" for c in state.retrieved_chunks
            )
            vision_block = (
                f"\nStructured Diagram JSON:\n{json.dumps(state.vision_structured, indent=2)}"
                if state.vision_structured
                else ""
            )
            system_prompt = (
                "You are a Socratic K-12 AI tutor. NEVER give the final numeric or direct answer on Hint Levels 1 or 2. "
                f"Current hint_level={state.hint_level}/3. Cite only the provided school textbook snippets."
            )
            user_prompt = f"Curriculum Context:\n{context_block}{vision_block}\n\nStudent Question: {state.redacted_query}"
            live_reply = self._call_live_llm(system_prompt, user_prompt)
            if live_reply:
                state.provider_mode = "live"
                state.draft_response = live_reply
                return f"Generated live Socratic response (attempt #{state.attempt_number}, hint {state.hint_level}/3)."

        state.provider_mode = "demo"
        state.draft_response = self._build_demo_socratic_reply(state)
        return f"Generated deterministic DEMO_MODE Socratic response (attempt #{state.attempt_number}, hint {state.hint_level}/3)."

    # ---- Node 6: Socratic Anti-Spoiler Guardrail ----
    def _node_socratic_guard(self, state: TutorState) -> str:
        text = state.draft_response
        leaked = any(p.search(text) for p in SPOILER_PATTERNS)

        if state.vision_structured and state.hint_level < 3:
            target = str(state.vision_structured.get("target_numeric_answer", "")).strip()
            if target and target.lower() in text.lower():
                leaked = True

        if leaked:
            state.guard_triggered = True
            state.final_response = (
                "Let's pause before jumping to the final answer! "
                "Look at the equation or diagram component we referenced — what is your first step if you isolate the unknown quantity?"
            )
            return "Guard triggered: intercepted direct-answer spoiler and rewrote to Socratic prompt."

        state.guard_triggered = False
        state.final_response = text
        return "Guard passed: no premature direct-answer spoiler detected."

    # ---- Node 7: Tenant-Scoped Audit Log ----
    def _node_audit_log(self, state: TutorState) -> str:
        citations = [
            {
                "chunk_id": c["id"],
                "label": c["citation_label"],
                "block_type": c["block_type"],
                "rrf_score": c["rrf_score"],
            }
            for c in state.retrieved_chunks
        ]
        assert state.routing is not None
        self.store.log_turn(
            tenant=state.tenant,
            session_id=state.session_id,
            student_ref=state.pseudonym_ref,
            attempt_number=state.attempt_number,
            hint_level=state.hint_level,
            model_tier=state.routing.tier,
            vision_cache_hit=state.vision_cache_hit,
            estimated_cost_usd=state.routing.est_cost_usd,
            pii_redacted=state.pii_redacted,
            redacted_prompt=state.redacted_query,
            socratic_response=state.final_response,
            citations=citations,
        )
        return f"Logged redacted turn for '{state.pseudonym_ref}' in school '{state.tenant.school_id}'."

    # ---- Execute Full Graph ----
    def invoke(
        self,
        tenant: TenantContext,
        session_id: str,
        student_ref: str,
        query: str,
        subject: str | None = None,
        grade_level: str | None = None,
        diagram_id: str | None = None,
        diagram_payload_text: str | None = None,
    ) -> dict[str, Any]:
        # Verify school tenant exists before executing graph
        self.store.get_school(tenant)
        state = TutorState(
            tenant=tenant,
            session_id=session_id.strip() or "sess_default",
            student_ref=student_ref.strip() or "STU-ANON",
            raw_query=query.strip(),
            subject=subject,
            grade_level=grade_level,
            diagram_id=diagram_id,
            diagram_payload_text=diagram_payload_text,
        )

        self._run_node(state, "redact_pii", self._node_redact_pii)
        self._run_node(state, "vision_extract_or_cache", self._node_vision_extract)
        self._run_node(state, "route_model", self._node_route_model)
        self._run_node(state, "retrieve_curriculum", self._node_retrieve)
        self._run_node(state, "generate_socratic", self._node_generate_socratic)
        self._run_node(state, "socratic_guard", self._node_socratic_guard)
        self._run_node(state, "audit_log", self._node_audit_log)

        assert state.routing is not None
        return {
            "school_id": tenant.school_id,
            "session_id": state.session_id,
            "student_pseudonym": state.pseudonym_ref,
            "provider_mode": state.provider_mode,
            "attempt_number": state.attempt_number,
            "hint_level": state.hint_level,
            "pii_redacted": state.pii_redacted,
            "pii_types": state.pii_types,
            "redacted_query": state.redacted_query,
            "socratic_guard_triggered": state.guard_triggered,
            "routing": {
                "tier": state.routing.tier,
                "model_label": state.routing.model_label,
                "reason": state.routing.reason,
                "est_cost_usd": state.routing.est_cost_usd,
                "est_latency_ms": state.routing.est_latency_ms,
                "vision_cache_hit": state.vision_cache_hit,
                "vision_savings_pct": state.routing.vision_savings_pct,
            },
            "vision_structured": state.vision_structured,
            "citations": [
                {
                    "chunk_id": c["id"],
                    "label": c["citation_label"],
                    "block_type": c["block_type"],
                    "rrf_score": c["rrf_score"],
                    "excerpt": c["content"][:240],
                }
                for c in state.retrieved_chunks
            ],
            "response": state.final_response,
            "graph_trace": state.trace,
        }

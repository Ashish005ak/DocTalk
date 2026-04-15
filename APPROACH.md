# Medical Consultation AI Agent — Remodel Approach

## Decision Record

**Date:** 2026-04-07
**Status:** Approved
**Scope:** Full rewrite of backend into a LangGraph-based medical consultation agent. Drop transcript replay/simulation. Keep voice input via Whisper. Rebuild frontend to match.

### Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Migration strategy | Clean rewrite in parallel package | Current `context_engine.py` (950 lines) is too entangled to refactor incrementally |
| Graph framework | LangGraph | Future cycles likely (re-explore on new red flags, multi-pass reasoning) |
| Session persistence | In-memory only | No database yet; sessions are ephemeral per server lifetime |
| Hypothesis scoring | Pure Python arithmetic | Counting `supporting_keys ∩ gathered_facts` is math, not reasoning — LLM not needed |
| LLM provider | Keep multi-provider support from current `llm_client.py` | Already built; wrap existing client behind new thin interface |
| Voice input | Keep Faster Whisper | Already working; reuse `audio/transcriber.py` as-is |
| Domain config | YAML files | Clinicians can review; testable; no Python changes to add specialties |

---

## Guiding Principles

1. **Code owns logic, LLM owns language** — flow, state, gaps, phase transitions are never delegated to the LLM
2. **Smallest possible LLM calls** — each call has one job, gets only what it needs
3. **Every LLM call is replaceable** — if it fails, there's a fallback
4. **State is the source of truth** — everything observable, loggable, testable
5. **Domain is configuration** — no clinical knowledge hardcoded in Python
6. **Fail safe** — any failure defaults to patient safety, never to silence

---

## What Gets Deleted vs Kept vs Rewritten

### Deleted (no longer needed)
```
backend/simulation/           # replay_engine, preview_buffer, speed_controller, transcript_validator
backend/suggestions/          # suggestion_engine, suggestion_models, feedback_logger
backend/transcripts/          # sample JSON transcripts
backend/domains/legal.py      # non-medical domains
backend/domains/hr.py
backend/domains/journalism.py
backend/domains/ux_research.py
backend/domains/custom.py
backend/domains/loader.py     # replaced by YAML loader
backend/domains/models.py     # replaced by new models
backend/context/              # context_engine.py, context_models.py (the 950-line monolith)
backend/models/utterance.py   # replaced by new state models

frontend/src/components/SimulationControls.tsx
frontend/src/components/TranscriptPanel.tsx
frontend/src/components/PreviewBubble.tsx
frontend/src/components/SuggestionCards.tsx
frontend/src/components/SessionSetup.tsx    # rewritten for chat-only
```

### Kept as-is
```
backend/audio/transcriber.py       # Faster Whisper — works, no changes needed
backend/config.py                  # extend with new settings, keep LLM provider config
backend/websocket/manager.py       # WebSocket broadcast infra — reuse
```

### Rewritten
```
backend/main.py                    # new API routes, simplified WS protocol
backend/context/llm_client.py      # thin wrapper extracted, multi-provider kept
frontend/src/App.tsx               # chat-only layout
frontend/src/components/ChatPanel.tsx   # enhanced with phase indicators
frontend/src/components/ContextPanel.tsx # adapted for new state shape
frontend/src/types/index.ts        # new type definitions
frontend/src/hooks/useWebSocket.ts # simplified protocol
```

---

## Target Repository Structure

```
backend/
├── agent/                          # LangGraph wiring
│   ├── graph.py                    # graph definition + compilation
│   ├── state.py                    # ClinicalState TypedDict
│   ├── nodes/
│   │   ├── intake.py               # intent classification + two-layer fact extraction
│   │   ├── reason.py               # fact merge + hypothesis + gaps + phase
│   │   ├── flow_control.py         # red flags + move decision
│   │   ├── response_gen.py         # natural language generation (+ inline explanation for MIXED)
│   │   ├── safety.py               # post-generation validation
│   │   └── crisis.py               # emergency response
│   └── routing.py                  # conditional edge: crisis vs linear path
│
├── clinical/                       # pure Python, zero LLM
│   ├── red_flag_guard.py           # rule-based red flag detection
│   ├── hypothesis.py               # scoring arithmetic
│   ├── block_manager.py            # symptom block progression
│   ├── fact_merger.py              # merge extracted facts into state
│   └── phase_computer.py           # phase transition logic
│
├── llm/                            # focused LLM callers
│   ├── client.py                   # thin async wrapper (reuse multi-provider)
│   ├── intent_classifier.py        # 10-token intent classification
│   ├── fact_extractor.py           # two-layer: targeted slot fill + volunteer detection
│   ├── explainer.py                # explanation + bridge generation (called by response_gen)
│   ├── response_generator.py       # question/clarify/acknowledge generation
│   └── summarizer.py               # final consultation summary
│
├── safety/                         # deterministic post-processing
│   ├── validator.py                # banned openings, empty response guard
│   ├── jargon_replacer.py          # lookup table substitution
│   └── dedup_checker.py            # question deduplication
│
├── domain/
│   ├── loader.py                   # YAML → DomainProfile parser
│   ├── models.py                   # DomainProfile, SymptomBlock, RedFlagRule, etc.
│   └── configs/
│       └── general_medicine.yaml   # all clinical knowledge lives here
│
├── models/                         # shared dataclasses and enums
│   ├── state.py                    # Phase, Confidence, PatientIntent, MoveType, etc.
│   ├── utterance.py                # Utterance (simplified)
│   ├── hypothesis.py               # HypothesisEntry, Hypothesis
│   ├── move.py                     # ConversationMove
│   ├── facts.py                    # ClinicalFact, RawFact, IntakeResult
│   └── red_flag.py                 # RedFlagRule
│
├── session/
│   └── manager.py                  # session lifecycle (in-memory)
│
├── audio/
│   └── transcriber.py              # kept as-is (Faster Whisper)
│
├── websocket/
│   └── manager.py                  # kept as-is (broadcast infra)
│
├── api/
│   ├── routes.py                   # FastAPI REST endpoints
│   └── websocket.py                # WS handler (simplified protocol)
│
├── tests/
│   ├── unit/
│   │   ├── test_fact_merger.py
│   │   ├── test_red_flag_guard.py
│   │   ├── test_phase_computer.py
│   │   ├── test_block_manager.py
│   │   ├── test_hypothesis.py
│   │   └── test_safety_validator.py
│   └── integration/
│       ├── test_graph_flow.py
│       └── test_full_conversation.py
│
├── config.py                       # extended Settings
└── main.py                         # FastAPI app entry point
```

---

## Phased Implementation Plan

Each phase ends with a **manual test checkpoint** — a concrete scenario you run
by hand before moving to the next phase. No phase begins until the previous
checkpoint passes.

---

### Phase 0: Foundation — Models, Domain, Config
**Goal:** All data structures and domain configuration exist. Nothing runs yet, but everything compiles and type-checks.

**Tasks:**
1. Create `models/state.py` — all enums: `Phase`, `Confidence`, `PatientIntent`, `MoveType`, `EmotionalTone`
2. Create `models/facts.py` — `ClinicalFact`, `RawFact`, `IntakeResult`
3. Create `models/hypothesis.py` — `HypothesisEntry`, `Hypothesis`
4. Create `models/move.py` — `ConversationMove`
5. Create `models/utterance.py` — simplified `Utterance` (speaker: `"patient"` | `"doctor"`, text, turn, optional intent)
6. Create `models/red_flag.py` — `RedFlagRule` dataclass
7. Create `domain/models.py` — `DomainProfile`, `SymptomBlock`, `SymptomField`, `HypothesisConfig`, `RedFlagConfig`, confidence thresholds
8. Create `domain/configs/general_medicine.yaml` — full YAML with symptom blocks, hypotheses, red flags, jargon map, thresholds
9. Create `domain/loader.py` — parse YAML into `DomainProfile`, validate required fields
10. Create `agent/state.py` — `ClinicalState` TypedDict with all fields and LangGraph reducers
11. Update `config.py` — add new agent-specific settings (keep existing LLM provider config)
12. Add `FactConfidence` enum to `models/facts.py` with values `HIGH`, `MEDIUM`, `UNCLEAR`. Update `RawFact.confidence` to use this enum instead of a raw string.
13. Add `is_supporting_key: bool` field to `SymptomField` in `domain/models.py`. This flag indicates whether the field is a supporting key for any hypothesis in the domain. Used by the block manager revisit hook to decide if an uncertain field is clinically relevant enough to revisit.
14. Add three new fields to `ClinicalState` in `agent/state.py`: `unconfirmed_facts` (medium-confidence extractions awaiting confirmation), `uncertain_fields` (low-confidence extractions that exhausted clarification attempts), and `clarification_attempts` (per-field attempt counter, max 2). All default to empty dicts.
15. Annotate every field in `general_medicine.yaml` with `is_supporting_key: true` or `is_supporting_key: false` based on whether the field appears as a supporting key in any hypothesis definition.
16. Add `TARGETED_CLARIFY` to the `MoveType` enum in `models/state.py`. This move type is used by candidate red flags to trigger targeted clarification rather than warnings.

**Manual Test Checkpoint:**
```python
# In a Python REPL or test script:
from domain.loader import load_domain
profile = load_domain("general_medicine")
assert len(profile.symptom_blocks) > 0
assert len(profile.red_flags) > 0
assert profile.get_field_hint("Fever") is not None

# Verify new Phase 0 additions
from backend.agent.state import create_initial_state
state = create_initial_state("general_medicine")
assert state["unconfirmed_facts"] == {}
assert state["uncertain_fields"] == {}
assert state["clarification_attempts"] == {}

from backend.models.facts import FactConfidence, RawFact
assert FactConfidence.HIGH.value == "high"
fact = RawFact(key="test", value="val")
assert fact.confidence == FactConfidence.HIGH

fever_field = profile.get_field("Fever")
assert fever_field.is_supporting_key is True
age_field = profile.get_field("Age")
assert age_field.is_supporting_key is False

print("Phase 0: PASS")
```

**No LLM calls. No graph. No API. Just data structures that compile.**

---

### Phase 1: Clinical Logic — Pure Python, No LLM
**Goal:** All rule-based clinical logic works and is unit tested. These modules have zero LLM dependency.

**Tasks:**
1. Implement `clinical/fact_merger.py`
   - `merge_facts(existing, new_facts, fact_confidence, turn_count, unconfirmed_facts, clarification_attempts, uncertain_fields) → (updated_dict, new_denied_set, updated_confidence, updated_unconfirmed, updated_attempts, updated_uncertain)`
   - Handles: new facts, denied symptoms, overwrites, empty keys
   - **Three-way confidence routing:**
     - `FactConfidence.HIGH` — merged into `information_gathered` (confirmed). If the key was in `unconfirmed_facts`, it is promoted out.
     - `FactConfidence.MEDIUM` — merged into `unconfirmed_facts` only (NOT `information_gathered`). The field is stored but not confirmed. Confidence recorded as `"medium"`.
     - `FactConfidence.UNCLEAR` — not merged anywhere. Increments `clarification_attempts[key]`. If attempts reach 2, the field is moved to `uncertain_fields` with its attempt count and no further clarification is attempted.
   - Updates `fact_confidence` dict on state with each merge operation
2. Implement `clinical/hypothesis.py`
   - `score_hypothesis(config, facts, denied) → float` — pure arithmetic. **RESTRICTION:** `facts` must be `information_gathered` (confirmed facts only). Unconfirmed facts must never be passed to scoring functions to avoid inflating hypothesis scores.
   - `score_all_hypotheses(domain, facts, denied) → Hypothesis` — returns leading + differential + ruled_out. Same restriction: reads exclusively from confirmed facts.
   - `compute_overall_confidence(leading_score, domain) → Confidence`
3. Implement `clinical/phase_computer.py`
   - `compute_phase(hypothesis, remaining_gaps, turn_count, domain) → Phase`
   - Handles: first turn → INTAKE, high confidence + no gaps → SUMMARY, etc.
4. Implement `clinical/block_manager.py`
   - `get_relevant_blocks(domain, hypothesis, completed_ids) → list[SymptomBlock]`
   - `compute_remaining_gaps(block, info_gathered, denied) → list[str]`
   - `should_advance_block(remaining_gaps) → bool`
   - `advance_block(state, domain) → (next_block | None, updated_completed_ids)`
   - `compute_revisit_gaps(uncertain_fields, unconfirmed_facts, domain, hypothesis) → (revisit_gaps, pruned_uncertain, pruned_unconfirmed)` — Revisit hook that surfaces clinically relevant uncertain/unconfirmed fields as open gaps during block advancement. For each field, checks if `is_supporting_key` is true AND any hypothesis listing the field as a supporting key has score > 0.3. If both conditions met, the field is surfaced as a gap. If either fails, the field is permanently discarded.
5. Implement `clinical/red_flag_guard.py`
   - `RedFlagGuard.__init__(domain)` — loads rules
   - `RedFlagGuard.check(state) → list[RedFlagRule]` — evaluates required_keys + at_least_one_of + qualifiers
   - Respects `last_rf_check_fact_snapshot` to skip unchanged states
   - Skips already-confirmed flag IDs
   - `RedFlagGuard.check_with_candidates(info_gathered, denied, confirmed_ids, snapshot) → (confirmed, candidates)` — Three-state evaluation per rule:
     - **confirmed**: all required_keys present, at_least_one_of satisfied, qualifiers pass
     - **candidate**: partial match — some evidence exists but the rule is not fully satisfied. Candidates trigger `TARGETED_CLARIFY` moves, not warnings.
     - **clear**: no supporting evidence at all

**Unit Tests (write alongside each module):**
```
tests/unit/test_fact_merger.py       — merge, deny, overwrite, empty input, three-way confidence routing (HIGH→info_gathered, MEDIUM→unconfirmed, UNCLEAR→attempts), max-two clarification enforcement, promotion from unconfirmed on HIGH confirmation
tests/unit/test_hypothesis.py        — scoring, ruled_out, edge cases
tests/unit/test_phase_computer.py    — each phase transition path
tests/unit/test_block_manager.py     — block relevance, gap computation, advancement
tests/unit/test_red_flag_guard.py    — each red flag rule, qualifier matching, dedup, candidate vs confirmed vs clear
```

**Manual Test Checkpoint:**
```bash
pytest tests/unit/ -v
# ALL tests pass. Zero LLM calls made.
```

**This phase is the safety foundation. Every test here is a guardrail that prevents clinical errors. Take the time to get it right.**

---

### Phase 2: Safety Layer — Deterministic Post-Processing
**Goal:** All output validation logic works independently of LLM generation.

**Tasks:**
1. Implement `safety/validator.py`
   - `strip_banned_openings(text) → text` — regex-based, removes "I understand", "Thank you for sharing", etc.
   - `has_acknowledgment_opener(text) → bool`
   - `strip_first_sentence(text) → text`
   - `empty_response_guard(text) → text` — returns fallback if empty
2. Implement `safety/jargon_replacer.py`
   - `replace_jargon(text, jargon_map) → (text, list[str])` — case-insensitive lookup-table substitution
3. Implement `safety/dedup_checker.py`
   - `is_duplicate_question(response, questions_asked) → bool` — keyword overlap scoring
   - `extract_question_sentences(text) → list[str]` — pulls out sentences ending in `?`

**Unit Tests:**
```
tests/unit/test_safety_validator.py  — banned opening removal, opener throttle, empty guard
tests/unit/test_jargon_replacer.py   — substitution, case handling, no false positives
tests/unit/test_dedup_checker.py     — overlap detection, threshold tuning
```

**Manual Test Checkpoint:**
```python
from safety.validator import strip_banned_openings
assert strip_banned_openings("I understand your concern. How long has the fever lasted?") == "How long has the fever lasted?"
from safety.jargon_replacer import replace_jargon
text, found = replace_jargon("You may have dyspnea and myalgia", {"dyspnea": "difficulty breathing", "myalgia": "muscle aches"})
assert "difficulty breathing" in text
assert "muscle aches" in text
print("Phase 2: PASS")
```

---

### Phase 3: LLM Client + Focused Callers
**Goal:** Each LLM caller works in isolation with a known input → expected output shape.

**Tasks:**
1. Create `llm/client.py`
   - Thin `LLMClient` wrapper with `complete(system, user, max_tokens) → str` and `complete_json(system, user, max_tokens, retries) → dict`
   - Reuse the multi-provider logic from existing `backend/context/llm_client.py` (Claude/OpenAI/Gemini/Groq)
   - Add retry with backoff, JSON fence stripping, parse error handling
2. Create `llm/intent_classifier.py`
   - `classify_intent(llm, message, last_gap) → PatientIntent`
   - Max 10 tokens, single word return
   - Fallback: `PatientIntent.ANSWERING`
3. Create `llm/fact_extractor.py` — **two-layer extraction design**
   - **Layer 1 — Targeted slot filling:** `extract_targeted(llm, message, target_keys, field_hints) → list[RawFact]`
     - For fields the doctor just asked about (via `last_question_asked` on state), supply the key names and hints to the LLM. The LLM classifies the value — it never invents key names.
     - Max 256 tokens, JSON array return.
   - **Layer 2 — Volunteer detection:** `detect_volunteered(llm, message, taxonomy_keys) → list[RawFact]`
     - For facts the patient mentions unprompted, run a binary detection pass against the known field taxonomy from the active block.
     - Max 256 tokens, JSON array return.
   - **Post-extraction validation:** `validate_facts(raw_facts, domain) → list[RawFact]`
     - Pure Python validates each `RawFact` against `field_type`/`valid_values` from the `SymptomField` schema. Rejects nonsensical values before they reach the merger.
   - Each `RawFact` carries a `FactConfidence` value (`HIGH` / `MEDIUM` / `UNCLEAR`). The extractor determines confidence but does NOT decide routing — downstream routing into `information_gathered`, `unconfirmed_facts`, or `clarification_attempts` is determined by the fact merger in the reason node.
   - Fallback: empty list
4. Create `llm/explainer.py`
   - `generate_explanation(llm, state, domain) → str`
   - Max 256 tokens, includes bridge to next gap
   - Fallback: "I'm sorry, could you repeat your question?"
5. Create `llm/response_generator.py`
   - `generate_question(llm, state, domain, move) → str` — handles QUESTION, CLARIFY, RED_FLAG_FOLLOWUP, ACKNOWLEDGE_CONCERN
   - Max 200 tokens per call
   - Fallback: generic "Can you tell me more about that?"
6. Create `llm/summarizer.py`
   - `generate_summary(llm, state, domain) → str`
   - Max 1024 tokens, structured with sections
   - Hardcoded disclaimer that cannot be skipped

**Manual Test Checkpoint:**
```python
# Test each caller independently with a real LLM call:
from llm.client import LLMClient
from llm.intent_classifier import classify_intent
from models.state import PatientIntent

client = LLMClient()  # uses config provider

intent = asyncio.run(classify_intent(client, "I've had a headache for 3 days", "Chief_Complaint"))
assert isinstance(intent, PatientIntent)
print(f"Intent: {intent}")

from llm.fact_extractor import extract_targeted, detect_volunteered, validate_facts
from domain.loader import load_domain
domain = load_domain("general_medicine")

# Targeted: doctor asked about Chief_Complaint
targeted = asyncio.run(extract_targeted(client, "I've had a headache for 3 days and a fever since yesterday", ["Chief_Complaint"], {"Chief_Complaint": "Primary symptom"}))
assert len(targeted) >= 1

# Volunteered: patient also mentioned fever unprompted
volunteered = asyncio.run(detect_volunteered(client, "I've had a headache for 3 days and a fever since yesterday", ["Fever", "Cough", "Nausea"]))
all_facts = validate_facts(targeted + volunteered, domain)
for f in all_facts:
    print(f"  {f.key}: {f.value} (denied={f.denied}, confidence={f.confidence})")

print("Phase 3: PASS")
```

**Run each caller 5 times with the same input. If results are inconsistent, tighten the prompt before moving on.**

---

### Phase 4: LangGraph Nodes + Wiring
**Goal:** The graph runs end-to-end for a single turn. No API yet — invoked directly from Python.

**Tasks:**
1. Implement `agent/nodes/intake.py`
   - Calls `classify_intent` + two-layer `extract_facts` (targeted + volunteered) in parallel via `asyncio.gather`
   - When intent is `MIXED`, sets `pending_explanation` on state with the patient's question text. Facts are still extracted — nothing is dropped.
   - When intent is `ASKING_EXPLANATION` (pure explanation, no facts), sets `pending_explanation` and skips extraction.
   - Updates `last_question_asked` on state from the previous turn's `conversation_move.target_gap`
   - Returns `IntakeResult` on state
2. Implement `agent/nodes/reason.py`
   - Calls `merge_facts` (code) → `score_all_hypotheses` (code) → `compute_remaining_gaps` (code) → `advance_block` (code) → `compute_phase` (code)
   - **No LLM calls** — hypothesis scoring is pure Python per our decision
   - **Always runs**, regardless of intent. For MIXED turns, facts are merged before any explanation is generated — the explanation is never based on stale state.
   - Returns updated clinical picture on state
3. Implement `agent/nodes/flow_control.py`
   - Calls `RedFlagGuard.check` (code) → decides `ConversationMove` based on priority: crisis > red_flag > vague > summary > concern > question
   - Candidate red flags from `RedFlagGuard.check_with_candidates` produce `TARGETED_CLARIFY` moves. A safety backup LLM call sits between red flag detection and response generation — it consumes candidate flags, confirms or downgrades them, and either escalates to a warning or converts to a targeted clarify move.
   - Returns `conversation_move` on state
4. Implement `agent/nodes/response_gen.py`
   - Routes to `generate_question` / `generate_summary` based on `conversation_move.type`
   - **MIXED/explanation handling:** If `pending_explanation` is set on state, calls `generate_explanation` (LLM) and blends the explanation with the next clinical question into one natural response. Clears `pending_explanation` after use.
   - For pure `ASKING_EXPLANATION` turns (no facts extracted), generates explanation with bridge back to the next gap.
   - Returns `doctor_response`
5. Implement `agent/nodes/safety.py`
   - Calls `strip_banned_openings` → `replace_jargon` → opener throttle → `is_duplicate_question` → `empty_response_guard`
   - Appends `Utterance` entries (patient + doctor) to state
   - Increments `turn_count`
   - Sets `last_question_asked` from current `conversation_move.target_gap` (for next turn's targeted extraction)
   - Returns cleaned `doctor_response` + updated tracking
6. Implement `agent/nodes/crisis.py`
   - Returns hardcoded emergency response — no LLM call
   - "Please call emergency services immediately. If you're having chest pain, difficulty breathing, or feel you're in danger, call 911 (or your local emergency number) right now."
7. Implement `agent/routing.py`
   - `route_after_intake(state) → str` — intent is metadata, not a routing key
   - `CRISIS` → crisis node (only hard route)
   - All other intents (including `MIXED`) → reason node. The graph stays linear: intake → reason → flow_control → response_gen → safety → END
   - `explain.py` is removed as a separate common-path node. Explanation logic lives in `response_gen` where it has access to fresh post-reason state.
8. Implement `agent/graph.py`
   - Wire all nodes with `StateGraph(ClinicalState)`
   - Single conditional edge after intake: crisis vs everything else
   - Linear edges: reason → flow_control → response_gen → safety → END
   - Compile with `MemorySaver` checkpointer

**Manual Test Checkpoint:**
```python
from agent.graph import build_graph
from agent.state import create_initial_state

graph = build_graph()
state = create_initial_state(domain_id="general_medicine")

# Turn 1: patient opens
state["patient_message"] = "I've had a bad headache and fever for two days"
result = asyncio.run(graph.ainvoke(state, config={"configurable": {"thread_id": "test-1"}}))

print(f"Phase: {result['phase']}")
print(f"Facts: {list(result['information_gathered'].keys())}")
print(f"Doctor: {result['doctor_response']}")
assert result["doctor_response"]  # not empty
assert "Headache" in result["information_gathered"] or "Fever" in result["information_gathered"]

# Turn 2: patient answers
result["patient_message"] = "It started suddenly two days ago, worst headache I've ever had"
result2 = asyncio.run(graph.ainvoke(result, config={"configurable": {"thread_id": "test-1"}}))

print(f"Phase: {result2['phase']}")
print(f"Red flags: {result2['confirmed_red_flag_ids']}")
print(f"Doctor: {result2['doctor_response']}")
# "worst ever headache" should trigger subarachnoid red flag
# Doctor should mention seeking urgent care

print("Phase 4: PASS")
```

**This is the critical integration point. Spend time here. Run at least 5 different multi-turn scenarios manually.**

---

### Phase 5: Session Manager + API Layer
**Goal:** The agent is accessible via HTTP/WebSocket. No frontend yet — test with curl/wscat.

**Tasks:**
1. Implement `session/manager.py`
   - `create_session(domain_id) → session_id` — initializes full `ClinicalState`
   - `send_message(session_id, message) → doctor_response` — invokes graph
   - `get_session_state(session_id) → dict` — returns observable state for frontend
   - `get_phase(session_id) → Phase`
   - Opening message: when session is created, store the domain's static `opening_message` and return it
2. Implement `api/routes.py`
   - `POST /api/session` — create session, returns `{session_id, opening_message}`
   - `GET /api/session/{session_id}/state` — returns current clinical state (for ContextPanel)
   - `POST /api/transcribe` — keep existing Whisper endpoint
   - `GET /api/health` — liveness check
3. Implement `api/websocket.py`
   - `WS /ws/{session_id}` — accepts connection, loops on `receive_text`
   - On message: sends `{"type": "thinking"}`, invokes `send_message`, sends `{"type": "response", "text": ..., "phase": ..., "state": ...}`
   - On disconnect: cleanup
4. Implement new `main.py`
   - Wire FastAPI app with routes + WebSocket + CORS
   - Startup: load domain configs, initialize LLM client
   - Keep Whisper transcription endpoint

**Manual Test Checkpoint:**
```bash
# Terminal 1: start server
uvicorn backend.main:app --reload --port 8000

# Terminal 2: create session
curl -X POST http://localhost:8000/api/session?domain_id=general_medicine
# → {"session_id": "abc-123", "opening_message": "Hello, I'm your AI health assistant..."}

# Terminal 3: connect WebSocket (using wscat or similar)
wscat -c ws://localhost:8000/ws/abc-123
> I've had a headache and fever for two days
# ← {"type": "thinking"}
# ← {"type": "response", "text": "When did the headache start?...", "phase": "exploring"}

> It came on suddenly, worst headache of my life
# ← {"type": "thinking"}
# ← {"type": "response", "text": "...", "phase": "..."}
# Should see red flag handling

> Actually what does that mean? Why are you asking about my neck?
# ← {"type": "response", "text": "...", "phase": "..."}
# Should see explanation with bridge back
```

**Test the full WebSocket flow with at least 3 different conversation paths:**
1. Normal symptom gathering → summary
2. Red flag triggered mid-conversation
3. Patient asks explanation mid-flow

---

### Phase 6: Frontend Rewrite — Chat-Only UI
**Goal:** The React frontend works with the new agent API. Clean, chat-focused interface.

**Tasks:**
1. Delete unused components: `SimulationControls.tsx`, `TranscriptPanel.tsx`, `PreviewBubble.tsx`, `SuggestionCards.tsx`
2. Rewrite `types/index.ts`
   - New types: `ClinicalStateView` (what the API returns), `WSAgentMessage`, `Phase`, `ConversationMove`
   - Remove: `ReplayState`, `Speed`, `TranscriptMeta`, `Transcript`, `Suggestion`, simulation-related types
3. Rewrite `SessionSetup.tsx`
   - Simple: domain selector (just "General Medicine" for now) + "Start Consultation" button
   - Calls `POST /api/session`, receives `session_id` + `opening_message`
4. Rewrite `App.tsx`
   - Two-panel layout: chat (left) + clinical state (right)
   - No simulation controls, no transcript panel, no suggestion cards
   - State: `sessionId`, `messages[]`, `clinicalState`, `phase`
5. Rewrite `ChatPanel.tsx`
   - Chat messages with patient/doctor styling
   - Voice input (keep MediaRecorder → `/api/transcribe` → text)
   - Show "thinking" indicator when waiting
   - Phase indicator badge (INTAKE / EXPLORING / NARROWING / SUMMARY)
   - Auto-scroll to latest message
6. Rewrite `ContextPanel.tsx`
   - Sections: Information Gathered, Active Hypotheses, Current Phase, Red Flags, Remaining Gaps
   - Live-updates from `state` field in WebSocket responses
   - Collapsible sections for dense state
7. Simplify `useWebSocket.ts`
   - New message types: `thinking`, `response`, `error`
   - Remove: `utterance_preview`, `utterance_commit`, `replay_state`, `suggestions_updated`

**Manual Test Checkpoint:**
```
1. Open http://localhost:5173
2. Click "Start Consultation"
3. See opening message from AI doctor
4. Type "I've had a sore throat and fever for 3 days"
5. See thinking indicator → doctor response
6. See ContextPanel update with extracted facts
7. Continue for 5-6 turns
8. Verify: no repeated questions, no jargon, phase progresses
9. Reach summary phase → see structured summary with disclaimer
10. Voice input: click mic, speak, see transcription appear, send
```

---

### Phase 7: Cleanup + Polish
**Goal:** Remove all dead code, ensure production readiness.

**Tasks:**
1. Delete old backend modules:
   - `backend/simulation/` (entire directory)
   - `backend/suggestions/` (entire directory)
   - `backend/transcripts/` (entire directory)
   - `backend/domains/legal.py`, `hr.py`, `journalism.py`, `ux_research.py`, `custom.py`
   - `backend/domains/loader.py` (old), `backend/domains/models.py` (old)
   - `backend/context/` (entire directory — the monolith)
   - `backend/models/utterance.py` (old)
2. Update `requirements.txt`
   - Add: `langgraph`, `pyyaml`
   - Remove: anything unused
3. Update `README.md` with new architecture description
4. Add logging throughout:
   - Each LLM call: log prompt size, response time, success/failure
   - Each phase transition: log from → to
   - Each red flag trigger: log flag ID + evidence
   - Safety node: log every correction applied
5. Error handling sweep:
   - LLM timeouts → fallback responses
   - Invalid session ID → 404
   - WebSocket disconnect → graceful cleanup
6. Run full integration test: 10-turn conversation covering all paths

**Manual Test Checkpoint:**
```
Full conversation test — run 3 scenarios end-to-end:

Scenario A: "Common Cold"
- Patient reports: sore throat, runny nose, mild fever, cough
- Expected: URTI hypothesis, no red flags, summary after ~8 turns
- Verify: disclaimer present, no jargon, no repeated questions

Scenario B: "Meningitis Red Flag"
- Patient reports: severe headache, high fever, neck stiffness
- Expected: red flag triggered, urgent warning issued
- Verify: warning appears within 1-2 turns of neck stiffness mention

Scenario C: "Patient Asks Questions"
- Patient gives symptoms but asks "why are you asking about that?"
- Expected: explanation with bridge back to consultation
- Verify: no clinical reasoning skipped, flow resumes naturally
```

---

## Phase Dependencies (what blocks what)

```
Phase 0: Foundation
   │
   ├──→ Phase 1: Clinical Logic     (needs models + domain)
   │       │
   │       ├──→ Phase 2: Safety      (needs models, independent of clinical)
   │       │
   │       └──→ Phase 3: LLM Callers (needs models + domain)
   │               │
   │               └──→ Phase 4: Graph Nodes + Wiring  (needs everything above)
   │                       │
   │                       └──→ Phase 5: API Layer      (needs working graph)
   │                               │
   │                               └──→ Phase 6: Frontend  (needs working API)
   │                                       │
   │                                       └──→ Phase 7: Cleanup
```

Note: **Phases 1, 2, and 3 can be worked on in parallel** after Phase 0 completes.
Phase 2 (safety) has no dependency on Phase 1 (clinical) or Phase 3 (LLM).

---

## LLM Call Budget Per Turn (Reference)

| Call | Purpose | Max Tokens | When |
|------|---------|-----------|------|
| `intent_classifier` | classify patient intent | 10 | every turn |
| `extract_targeted` | slot-fill facts for asked fields | 256 | ANSWERING or MIXED turns |
| `detect_volunteered` | binary detect unprompted facts | 256 | ANSWERING or MIXED turns |
| `response_generator` | natural language response | 200 | every turn |
| `explainer` | explanation blended into response | 256 | MIXED or ASKING_* turns (called within response_gen) |
| `summarizer` | final consultation summary | 1024 | summary phase only |

**Normal turn:** 4 calls (~720 tokens total) — intent + targeted + volunteered + response
**MIXED turn:** 5 calls (~980 tokens total) — intent + targeted + volunteered + explainer + response
**Pure explain turn:** 3 calls (~470 tokens total) — intent + explainer + response
**Summary turn:** 2 calls (~1040 tokens total) — intent + summarizer
**Current system:** 1 call (~2000-3000 tokens every turn)

---

## Key Differences From Current System

| Aspect | Current (`context_engine.py`) | New (agent/) |
|--------|-------------------------------|-------------|
| Architecture | 950-line monolith | 12+ focused modules |
| LLM calls per turn | 1 mega-call (2000-3000 tokens) | 3 small calls (~750 tokens) |
| Clinical logic | Embedded in LLM prompts | Pure Python, unit tested |
| Domain knowledge | Hardcoded in `medical.py` as Python | YAML configuration |
| Hypothesis scoring | LLM does the math | Python arithmetic |
| Red flag detection | LLM every 2 turns | Deterministic rules every turn |
| Phase transitions | LLM reports phase | `compute_phase()` in code |
| Safety checks | Prompt instructions (unreliable) | Code enforcement (deterministic) |
| Question dedup | None | Keyword overlap detection |
| Jargon handling | Prompt instruction | Regex lookup table |
| Session model | Global singleton | Per-session state in memory |
| Testability | Integration tests only (need LLM) | Unit tests for all logic (no LLM) |
| Transcript replay | Supported | Removed (chat-only) |
| Multi-domain | 6 domains | Medical only (extensible via YAML) |

---

## Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| LangGraph learning curve | Slows Phase 4 | Keep graph simple — linear with one branch. Avoid advanced features until needed |
| Fact extraction quality | Wrong facts → wrong hypothesis | Constrain extraction to known field keys from active block. Unit test edge cases |
| Intent classification errors | Wrong routing (e.g., explanation treated as answer) | Safe fallback to ANSWERING. Log misclassifications for prompt tuning |
| Server restart loses sessions | Patient loses mid-consultation | Accept for now. Add Redis/Postgres in future phase |
| YAML config errors | Runtime crashes | Validate YAML on load with schema. Fail fast with clear error messages |
| Token costs during development | Expensive testing | Use cheapest model (Groq/Gemini Flash) for dev. Switch to Claude for production |
| Unconfirmed facts inflating scores | Wrong hypothesis leads to wrong clinical path | Scoring functions read exclusively from `information_gathered`. `unconfirmed_facts` is a separate dict never passed to `score_hypothesis`. Enforced by code structure and explicit comments. |
| Clarification loop stalling consultation | Patient stuck in repeated clarification questions | `clarification_attempts` enforces max-two attempts per field in the merger. After 2 attempts, the field is moved to `uncertain_fields` and the consultation moves forward. |

---

## Success Criteria

The remodel is complete when:

1. A patient can have a 10+ turn medical consultation via text or voice
2. The AI doctor never repeats a question already answered
3. Red flags (meningitis, MI, stroke, SAH, PE) trigger within 1 turn of evidence
4. The consultation ends with a structured summary including disclaimer
5. All clinical logic is covered by unit tests that run without LLM calls
6. The safety node catches and corrects banned openings, jargon, and duplicates
7. Token usage per turn is under 1000 tokens (normal turns)
8. The system gracefully handles: vague answers, patient questions, emotional distress, crisis

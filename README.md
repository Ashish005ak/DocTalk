# DocTalk — AI Medical Consultation Agent
 
An AI-powered medical history-taking assistant built with a **LangGraph** agent backend and a **React** chat frontend. The agent conducts structured clinical interviews, extracts facts, scores hypotheses, detects red flags, and produces a consultation summary — all with deterministic safety guardrails.
 
---
 
## Quick Start
 
### 1. Backend (FastAPI)
 
```bash
pip install -r requirements.txt
 
# Copy env file (once) and fill in your LLM API key
copy .env.example .env              # Windows
# cp .env.example .env              # macOS / Linux
 
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```
 
- API: `http://localhost:8000`
- Interactive docs: `http://localhost:8000/docs`
 
### 2. Frontend (React + Vite)
 
```bash
cd frontend
npm install
copy .env.example .env              # once
npm run dev
```
 
- UI: `http://localhost:5173`
 
---
 
## Environment Variables
 
### Backend (`.env` in project root)
 
```bash
WS_PORT=8000
 
# CORS — add your frontend origin if it runs on a different port
# CORS_ORIGINS=["http://localhost:5173","http://localhost:3000"]
 
# Speech-to-text model (faster-whisper): tiny | base | small | medium | large-v3
WHISPER_MODEL=medium
 
# LLM provider: claude | openai | gemini | groq
LLM_PROVIDER=claude
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
GOOGLE_API_KEY=
GROQ_API_KEY=
```
 
Additional settings available via env (with sensible defaults in `config.py`):
 
| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_MODEL` | `claude-sonnet-4-20250514` | Anthropic model |
| `OPENAI_MODEL` | `gpt-4.1-mini` | OpenAI model |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Google model |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Groq model |
| `LLM_TEMPERATURE` | `0.2` | Generation temperature |
| `LLM_MAX_OUTPUT_TOKENS` | `8192` | Max output tokens |
| `LLM_MAX_RETRIES` | `3` | Retry count on LLM failure |
| `DEFAULT_DOMAIN` | `general_medicine` | Domain config loaded at session start |
| `MAX_CONVERSATION_TURNS` | `30` | Turn limit per session |
| `WHISPER_LANGUAGE` | `en` | Whisper transcription language |
 
### Frontend (`frontend/.env`)
 
```bash
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000/ws
```
 
---
 
## Architecture
 
```
Patient (text / voice)
        │
        ▼
   ┌─────────┐     POST /api/transcribe
   │ Frontend │────────────────────────────► Faster Whisper
   │ React 19 │◄───────────────────────────  { text }
   │ Vite 7   │
   │ Tailwind │     WS /ws/{session_id}
   │          │◄══════════════════════════► FastAPI WebSocket
   └─────────┘                                   │
                                                 ▼
                                         ┌──────────────┐
                                         │  LangGraph   │
                                         │  Agent Loop  │
                                         │              │
                                         │ intake ──┐   │
                                         │          │   │
                                         │  crisis ◄┤   │
                                         │          │   │
                                         │ reason ◄─┘   │
                                         │    │         │
                                         │ flow_ctrl   │
                                         │    │         │
                                         │ response_gen│
                                         │    │         │
                                         │ safety      │
                                         └──────────────┘
                                           │         │
                                    YAML Domain   LLM Providers
                                    (red flags,   (Claude, OpenAI,
                                     symptoms,    Gemini, Groq)
                                     hypotheses)
```
 
---
 
## Project Structure
 
```
DocTalk/
├── backend/
│   ├── main.py                        # FastAPI app, CORS, lifespan, routers
│   ├── config.py                      # Pydantic settings (env-driven)
│   │
│   ├── agent/                         # LangGraph wiring
│   │   ├── graph.py                   # StateGraph definition + compilation
│   │   ├── state.py                   # ClinicalState TypedDict + reducers
│   │   ├── routing.py                 # Conditional edge: crisis vs linear path
│   │   └── nodes/
│   │       ├── intake.py              # Intent classification + two-layer fact extraction
│   │       ├── reason.py              # Fact merge → hypothesis → gaps → phase (pure Python)
│   │       ├── flow_control.py        # Red flags + conversation move decision
│   │       ├── response_gen.py        # Natural language generation
│   │       ├── safety.py              # Post-generation validation pipeline
│   │       └── crisis.py              # Emergency response (hardcoded, no LLM)
│   │
│   ├── clinical/                      # Pure Python logic, zero LLM
│   │   ├── red_flag_guard.py          # Rule-based red flag detection
│   │   ├── fact_merger.py             # Three-way confidence routing
│   │   └── readiness.py              # Readiness checks
│   │
│   ├── llm/                           # Focused LLM callers (one job each)
│   │   ├── client.py                  # AgentLLMClient wrapper + cost logging
│   │   ├── intent_classifier.py       # 10-token intent classification
│   │   ├── fact_extractor.py          # Two-layer: targeted slot fill + volunteer detection
│   │   ├── response_generator.py      # Question / clarify / acknowledge generation
│   │   ├── clinical_reasoner.py       # Clinical reasoning
│   │   ├── explainer.py               # Explanation + bridge generation
│   │   └── summarizer.py             # Final consultation summary
│   │
│   ├── safety/                        # Deterministic post-processing
│   │   ├── validator.py               # Banned openings, empty response guard
│   │   ├── jargon_replacer.py         # Lookup-table substitution from domain config
│   │   └── dedup_checker.py           # Question deduplication
│   │
│   ├── domain/
│   │   ├── loader.py                  # YAML → DomainProfile parser + validation
│   │   ├── models.py                  # DomainProfile, SymptomBlock, RedFlagRule, etc.
│   │   └── configs/
│   │       └── general_medicine.yaml  # Symptoms, hypotheses, red flags, jargon map
│   │
│   ├── models/                        # Shared data types
│   │   ├── state.py                   # Phase, Confidence, PatientIntent, MoveType enums
│   │   ├── utterance.py               # Utterance (speaker, text, turn)
│   │   ├── hypothesis.py              # HypothesisEntry, Hypothesis
│   │   ├── move.py                    # ConversationMove
│   │   ├── facts.py                   # ClinicalFact, RawFact, IntakeResult
│   │   └── red_flag.py               # RedFlagRule dataclass
│   │
│   ├── session/
│   │   └── manager.py                 # In-memory session lifecycle + graph invocation
│   │
│   ├── cost/
│   │   ├── tracker.py                 # Per-call CSV logging (costs/run.csv, costs/cost.csv)
│   │   └── context.py                 # contextvars for session/caller tracking
│   │
│   ├── audio/
│   │   └── transcriber.py            # Faster Whisper speech-to-text
│   │
│   ├── context/
│   │   └── llm_client.py             # Low-level multi-provider LLM client + retries
│   │
│   ├── api/
│   │   ├── routes.py                  # REST endpoints
│   │   └── websocket.py              # WebSocket handler
│   │
│   └── tests/
│       └── unit/                      # pytest unit tests (no LLM required)
│
├── frontend/                          # React 19 + Vite 7 + TypeScript + Tailwind 4
│   └── src/
│       ├── App.tsx                    # Two-panel layout: chat + clinical context
│       ├── index.css
│       ├── components/
│       │   ├── ChatPanel.tsx          # Chat messages + voice input + phase badge
│       │   ├── ContextPanel.tsx       # Live clinical state (hypotheses, gaps, red flags)
│       │   └── SessionSetup.tsx       # Domain selector + start consultation
│       ├── hooks/
│       │   └── useWebSocket.ts        # WS connection with exponential backoff
│       └── types/
│           └── index.ts              # ClinicalStateView, WSAgentMessage, Phase types
│
├── costs/                             # Auto-generated at runtime
│   ├── run.csv                        # Per-LLM-call cost log
│   └── cost.csv                       # Per-session cost summary
│
├── APPROACH.md                        # Architecture decision record
├── requirements.txt
├── .env.example
└── frontend/.env.example
```
 
---
 
## API Reference
 
### Session
 
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/session` | Create a new consultation session. Query param: `domain_id` (default: `general_medicine`). Returns `{session_id, opening_message}` |
| GET | `/api/session/{session_id}/state` | Current clinical state snapshot (phase, facts, gaps, hypotheses, red flags) |
 
### Audio
 
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/transcribe` | Upload an audio file, returns `{text}` via Faster Whisper |
 
### System
 
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Liveness check + active session count |
 
### WebSocket
 
| Method | Endpoint | Description |
|--------|----------|-------------|
| WS | `/ws/{session_id}` | Real-time consultation stream |
 
---
 
## WebSocket Protocol
 
**Client → Server:**
```json
{ "text": "I've had a headache for 3 days" }
```
 
**Server → Client:**
 
| Type | Description |
|------|-------------|
| `connected` | Connection confirmed with `session_id` |
| `thinking` | Agent is processing the message |
| `response` | Agent reply with `text`, `phase`, `state`, `consultation_ended` |
| `error` | Error message |
 
---
 
## Agent Graph
 
The consultation runs through a **LangGraph** state machine on every patient turn:
 
1. **Intake** — Classifies patient intent (answering, asking, mixed, crisis) and extracts clinical facts using two-layer extraction (targeted slot-fill + volunteer detection)
2. **Crisis** (conditional) — If crisis intent detected, returns hardcoded emergency response
3. **Reason** — Merges facts, scores hypotheses, computes gaps and phase transitions (pure Python, no LLM)
4. **Flow Control** — Evaluates red flag rules, decides next conversation move (question, clarify, red flag follow-up, summary)
5. **Response Generation** — LLM generates natural language for the decided move; blends explanations when patient asks questions
6. **Safety** — Strips banned openings, replaces jargon, throttles acknowledgments, deduplicates questions, runs escalation check
 
---
 
## Domain Configuration
 
Clinical knowledge lives in **YAML files** under `backend/domain/configs/`. Currently ships with `general_medicine.yaml`, which includes:
 
- **Symptom blocks** with fields, types, valid values, and hints
- **Hypothesis definitions** with supporting keys and scoring
- **Red flag rules** (meningitis triad, MI pattern, PE, stroke, SAH, etc.)
- **Jargon map** for plain-language replacements
- **Thresholds** (`max_turns`, `max_gap_asks`, `watch_turns_limit`)
- **Dedup fallback** templates and **placeholder values**
 
New specialties can be added by creating a new YAML file — no Python changes required.
 
---
 
## LLM Providers
 
Four providers supported through a unified async interface. Switch via `LLM_PROVIDER` in `.env`:
 
| Provider | Env Key | Default Model |
|----------|---------|---------------|
| `claude` | `ANTHROPIC_API_KEY` | `claude-sonnet-4-20250514` |
| `openai` | `OPENAI_API_KEY` | `gpt-4.1-mini` |
| `gemini` | `GOOGLE_API_KEY` | `gemini-2.5-flash` |
| `groq` | `GROQ_API_KEY` | `llama-3.3-70b-versatile` |
 
Features:
- Async-first design with retry and exponential backoff
- Auto-strips markdown JSON fences from LLM responses
- Per-call latency, token usage, and cost logging to CSV
- `complete()` returns raw text; `complete_json()` auto-parses with retry on malformed JSON
- Factory pattern with client caching
 
---
 
## LLM Call Budget Per Turn
 
| Call | Purpose | Max Tokens | When |
|------|---------|------------|------|
| `intent_classifier` | Classify patient intent | 10 | Every turn |
| `extract_targeted` | Slot-fill facts for asked fields | 256 | ANSWERING or MIXED turns |
| `detect_volunteered` | Detect unprompted facts | 256 | ANSWERING or MIXED turns |
| `response_generator` | Natural language response | 200 | Every turn |
| `explainer` | Explanation blended into response | 256 | MIXED or ASKING turns |
| `summarizer` | Final consultation summary | 1024 | Summary phase only |
 
**Normal turn:** ~4 calls, ~720 tokens | **MIXED turn:** ~5 calls, ~980 tokens | **Summary turn:** ~2 calls, ~1040 tokens
 
---
 
## Safety Guarantees
 
- **Red flag detection** — Deterministic rule evaluation every turn (meningitis, MI, stroke, SAH, PE)
- **Banned opener removal** — Regex strips empathetic filler ("I understand your concern…")
- **Jargon replacement** — Lookup-table substitution ensures plain language
- **Question deduplication** — Keyword overlap scoring prevents repeated questions
- **Acknowledgment throttling** — Consecutive opener suppression
- **Empty response guard** — Fallback text if generation returns empty
- **LLM escalation check** — Safety node runs a YES/NO escalation prompt; appends urgent-care warning if YES
- **Crisis path** — Hardcoded emergency response with no LLM dependency
 
---
 
## Cost Tracking
 
Every LLM call is logged to `costs/run.csv` with timestamp, session ID, caller, model, token counts, and estimated USD cost. When a session ends (WebSocket disconnect or shutdown), a summary row is appended to `costs/cost.csv`.
 
---
 
## Tech Stack
 
| Layer | Technologies |
|-------|-------------|
| Backend | Python, FastAPI, Uvicorn, Pydantic v2, pydantic-settings |
| Agent | LangGraph (StateGraph, MemorySaver) |
| LLM | Anthropic, OpenAI, Google Generative AI, Groq |
| Speech | Faster Whisper |
| Domain | PyYAML |
| Frontend | React 19, Vite 7, TypeScript, Tailwind CSS 4 |
| Testing | pytest |
 
---
 
## Design Principles
 
1. **Code owns logic, LLM owns language** — flow, state, gaps, and phase transitions are never delegated to the LLM
2. **Smallest possible LLM calls** — each call has one job and gets only what it needs
3. **Every LLM call is replaceable** — if it fails, there's a deterministic fallback
4. **State is the source of truth** — everything is observable, loggable, and testable
5. **Domain is configuration** — no clinical knowledge hardcoded in Python
6. **Fail safe** — any failure defaults to patient safety, never to silence
 
 
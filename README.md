# ConvoNudge — Real-Time Conversation Intelligence

Phases completed: **1** (Transcript Simulation), **2.1-2.5** (LLM Abstraction, Domain Profiles, Context Engine, Prompt Optimisation, Context Panel)

---

## Quick Start

### 1. Backend (FastAPI)

```bash
# Install dependencies (run again after pulling new changes)
pip install -r requirements.txt

# Copy env files (once)
copy .env.example .env              # Windows
# cp .env.example .env              # macOS / Linux

# Start the server
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

- API: `http://localhost:8000`
- Interactive docs: `http://localhost:8000/docs`

### 2. Frontend (React + Vite)

```bash
cd frontend
npm install                         # once
copy .env.example .env              # once
npm run dev
```

- UI: `http://localhost:5173`

---

## Environment Variables

### Backend (`.env` in project root)

```bash
# Server
WS_PORT=8000
DEFAULT_SPEED=1.0
TRANSCRIPTS_DIR=backend/transcripts

# CORS — add your frontend origin if it runs on a different port
# CORS_ORIGINS=["http://localhost:5173","http://localhost:5174"]

# LLM provider: claude | openai | gemini | groq
LLM_PROVIDER=gemini
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
GOOGLE_API_KEY=your-key-here
GROQ_API_KEY=

# Context engine tuning (optional — sensible defaults)
# CONTEXT_ANALYSIS_INTERVAL=2           # analyse every N responder turns
# CONTEXT_TOKEN_THRESHOLD_FULL=4000     # below this: full transcript
# CONTEXT_TOKEN_THRESHOLD_SUMMARY=8000  # above this: LLM summarisation
# CONTEXT_WINDOW_SIZE=10                # recent utterances kept verbatim
```

### Frontend (`frontend/.env`)

```bash
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000/ws
```

---

## Project Structure

```
ConvoNude_1/
├── backend/
│   ├── main.py                     # FastAPI app, routes, WebSocket handler
│   ├── config.py                   # Pydantic settings (env-driven)
│   ├── context/
│   │   ├── __init__.py
│   │   ├── llm_client.py           # LLMClient ABC, Claude/OpenAI/Gemini/Groq clients, factory
│   │   ├── context_models.py       # ContextObject, InformationItem, Signal models
│   │   └── context_engine.py       # ContextEngine — three-tier prompt optimisation
│   ├── domains/
│   │   ├── __init__.py
│   │   ├── models.py               # DomainProfile Pydantic model
│   │   ├── loader.py               # DomainLoader registry
│   │   ├── custom.py               # Custom profile loader + generic fallback
│   │   ├── medical.py              # SOCRATES framework
│   │   ├── legal.py                # Evidence Chain framework
│   │   ├── hr.py                   # STAR (Behavioural Competency)
│   │   ├── journalism.py           # 5W1H + Impact framework
│   │   └── ux_research.py          # Pain Point Mapping framework
│   ├── models/
│   │   └── utterance.py            # Utterance, Transcript, SessionConfig, SessionState
│   ├── simulation/
│   │   ├── replay_engine.py        # Asyncio transcript replay with timing
│   │   ├── speed_controller.py     # Timestamp math + speed scaling
│   │   ├── preview_buffer.py       # 0.8s preview bubble simulation
│   │   └── transcript_validator.py # JSON schema + structural validation
│   ├── websocket/
│   │   └── manager.py              # Multi-client WebSocket manager
│   └── transcripts/                # Sample transcripts
│       ├── medical_chest_pain.json
│       ├── legal_auto_accident.json
│       └── hr_software_engineer.json
├── frontend/                       # React + Vite + TypeScript + Tailwind
│   └── src/
│       ├── App.tsx
│       ├── index.css               # Global styles + fadeIn animation
│       ├── components/
│       │   ├── TranscriptPanel.tsx
│       │   ├── SimulationControls.tsx
│       │   ├── SessionSetup.tsx     # Domain selector dropdown
│       │   ├── ContextPanel.tsx     # Live context panel (Phase 2.5)
│       │   └── PreviewBubble.tsx
│       ├── hooks/
│       │   └── useWebSocket.ts
│       └── types/
│           └── index.ts            # DomainProfile, ContextObject, Signal types
├── docs/
│   └── CONTEXT_OPTIMIZATION.md     # How three-tier prompt optimisation works
├── requirements.txt
├── .env.example
├── frontend/.env.example
└── implementation_plan.md
```

---

## API Reference

### Transcripts

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/transcripts` | List all transcripts with metadata |
| GET | `/api/transcripts/{id}` | Get full transcript by id |
| POST | `/api/transcripts/upload` | Upload a `.json` transcript file |
| POST | `/api/transcripts/upload-json` | Upload transcript as JSON body |

### Session

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/session/configure` | Configure session (transcript, domain, speed) |
| GET | `/api/session/state` | Current session state |

### Context (Phase 2.3)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/context` | Current context object (for late-joining clients or page refresh) |

### Domains (Phase 2.2)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/domains` | List all domain profiles with full details |
| GET | `/api/domains/{id}` | Get a single domain profile |

### LLM (Phase 2.1)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/llm/status` | Configured provider, key status, available providers |

### WebSocket

| Method | Endpoint | Description |
|--------|----------|-------------|
| WS | `/ws` | Real-time event stream |

---

## Domain Profiles

Six profiles are loaded at startup. Each includes a framework, gap categories, signal types, priority rules, and a system prompt fragment for the LLM.

| ID | Name | Framework | Gaps | Role Labels |
|----|------|-----------|------|-------------|
| `medical` | Medical — SOCRATES | SOCRATES | Site, Onset, Character, Radiation, Associations, Time course, Exacerbating/relieving, Severity | Doctor / Patient |
| `legal` | Legal — Evidence Chain | Evidence Chain | Incident details, Timeline, Witnesses, Damages, Prior incidents, Insurance, Documentation, Opposing party | Attorney / Client |
| `hr` | HR — Behavioural Competency | STAR | Situation, Task, Action, Result, Leadership, Conflict resolution, Technical depth, Cultural fit | Interviewer / Candidate |
| `journalism` | Journalism — Story Angle | 5W1H + Impact | Who, What, When, Where, Why, How, Impact, Sources | Reporter / Source |
| `ux_research` | UX Research — Pain Point Mapping | Pain Point Mapping | Current workflow, Pain points, Workarounds, Frequency, Impact, Ideal state, Emotional response, Context of use | Researcher / Participant |
| `custom` | Custom | General | Topic coverage, Detail depth, Follow-up needed | Interviewer / Responder |

---

## LLM Client Abstraction

The system supports four LLM providers through a unified interface. Switch providers by changing `LLM_PROVIDER` in `.env`:

| Provider | Env Key | Default Model |
|----------|---------|---------------|
| `claude` | `ANTHROPIC_API_KEY` | `claude-sonnet-4-20250514` |
| `openai` | `OPENAI_API_KEY` | `gpt-4o` |
| `gemini` | `GOOGLE_API_KEY` | `gemini-2.5-flash` |
| `groq` | `GROQ_API_KEY` | `llama-3.3-70b-versatile` |

Features:
- Async-first design (`AsyncAnthropic`, `AsyncOpenAI`, `AsyncGroq`, `generate_content_async`)
- Retry with exponential backoff (1s → 2s → 4s) on transient errors
- Auto-strips markdown JSON fences from LLM responses
- Per-call latency + token usage logging
- `analyze()` returns raw text; `analyze_json()` auto-parses with retry on malformed JSON
- Factory pattern with client caching — instantiate once, reuse across requests

---

## WebSocket Protocol

**Server → Client:**
- `utterance_preview` — partial utterance (is_preview: true)
- `utterance_commit` — final committed utterance
- `replay_state` — state update (playing / paused / finished)
- `context_updated` — updated ContextObject after LLM analysis (Phase 2.3)
- `session_start` — session configured
- `session_end` — session stopped
- `connection_ack` — connection confirmed

**Client → Server:**
- `{ action: "start" }`
- `{ action: "pause" }`
- `{ action: "resume" }`
- `{ action: "stop" }`
- `{ action: "set_speed", speed: 0.5 | 1.0 | 2.0 | 4.0 }`
- `{ action: "load_transcript", transcript_id: "..." }`

---

## Phase Status

- [x] **Phase 1** — Transcript Simulation Engine
- [x] **Phase 2.1** — LLM Client Abstraction (Claude / OpenAI / Gemini)
- [x] **Phase 2.2** — Domain Profile Loader (5 built-in + custom)
- [x] **Phase 2.3** — Context Engine Core (LLM analysis after responder turns, domain selector)
- [x] **Phase 2.4** — Incremental Prompt Optimisation (three-tier: FULL / WINDOW / SUMMARY)
- [x] **Phase 2.5** — Frontend: Context Panel (live sidebar with gaps, signals, info)
- [ ] **Phase 3** — Next Question Suggestion Engine
- [ ] **Phase 4** — Live Audio Integration
- [ ] **Phase 5** — Post-Session Intelligence

See [docs/CONTEXT_OPTIMIZATION.md](docs/CONTEXT_OPTIMIZATION.md) for details on how the three-tier prompt system works.

# Implementation Plan — ConvoNude

## Real-Time Conversation Intelligence System

**Phased, feature-by-feature build plan.**
Each phase is self-contained — it delivers testable value before the next phase begins.

---

## Project Structure (Target)

```
ConvoNude_1/
├── backend/                    # Python + FastAPI
│   ├── main.py                 # FastAPI app entry point
│   ├── config.py               # Global config, env vars, API keys
│   ├── simulation/
│   │   ├── replay_engine.py    # Transcript replay with timing
│   │   ├── speed_controller.py # Playback speed logic (0.5x–4x)
│   │   └── preview_buffer.py   # 0.8s preview bubble before commit
│   ├── context/
│   │   ├── context_engine.py   # Running context object management
│   │   ├── context_models.py   # Pydantic models for context state
│   │   └── llm_client.py       # LLM API abstraction (Claude/GPT-4/Gemini)
│   ├── suggestions/
│   │   ├── suggestion_engine.py  # Trigger + ranking logic
│   │   ├── suggestion_models.py  # Pydantic models for suggestions
│   │   └── feedback_logger.py    # Tracks used/ignored suggestions
│   ├── domains/
│   │   ├── loader.py           # Domain profile loader
│   │   ├── medical.py          # SOCRATES framework profile
│   │   ├── legal.py            # Evidence chain profile
│   │   ├── hr.py               # Behavioural competency profile
│   │   ├── journalism.py       # Story angle profile
│   │   ├── ux_research.py      # Pain point mapping profile
│   │   └── custom.py           # Custom profile handler
│   ├── audio/                  # Phase 4
│   │   ├── pipeline.py         # Audio orchestration
│   │   ├── vad.py              # Silero VAD wrapper
│   │   ├── transcriber.py      # Faster-Whisper via RealtimeSTT
│   │   ├── diarizer.py         # Diart streaming wrapper
│   │   ├── merger.py           # Timestamp-aligned chunk merge
│   │   └── enrollment.py       # Speaker enrollment at session start
│   ├── postsession/            # Phase 5
│   │   ├── whisperx_runner.py  # High-accuracy post-session pass
│   │   ├── artifact_generator.py # Domain-specific output generation
│   │   └── templates/          # Artifact templates per domain
│   ├── websocket/
│   │   └── manager.py          # WebSocket connection management
│   └── transcripts/            # Sample transcript JSON files
│       ├── medical_chest_pain.json
│       ├── legal_auto_accident.json
│       └── hr_software_engineer.json
├── frontend/                   # React + Electron
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── TranscriptPanel.tsx    # Live transcript display
│   │   │   ├── SuggestionCards.tsx    # 2–3 ranked suggestions
│   │   │   ├── ContextPanel.tsx       # Running context sidebar
│   │   │   ├── SimulationControls.tsx # Play/pause/speed/load
│   │   │   ├── SessionSetup.tsx       # Domain + role config
│   │   │   ├── PreviewBubble.tsx      # 0.8s partial result indicator
│   │   │   └── PostSessionView.tsx    # Artifacts display
│   │   ├── hooks/
│   │   │   ├── useWebSocket.ts        # WS connection management
│   │   │   └── useSession.ts          # Session state management
│   │   └── types/
│   │       └── index.ts               # Shared TypeScript types
│   └── electron/
│       └── main.ts                    # Electron shell (Phase 4+)
├── requirements.txt
├── package.json
├── .env.example
└── implementation_plan.md
```

---

## Shared Data Contracts

These are defined first and never change. Everything downstream consumes them.

### Utterance (the universal unit)

```json
{
  "id": "utt_001",
  "timestamp": "00:00:06.500",
  "speaker": "responder",
  "text": "I've been having chest pain for three days now.",
  "is_preview": false
}
```

### Context Object

```json
{
  "session_id": "sess_abc123",
  "core_topic": "Chest pain evaluation",
  "information_gathered": [
    { "key": "chief_complaint", "value": "Chest pain × 3 days", "source_utt": "utt_001" }
  ],
  "questions_asked": ["utt_002"],
  "gaps": ["radiation", "associated symptoms", "cardiac history"],
  "signals": [
    { "type": "red_flag", "detail": "Exertional chest pain", "source_utt": "utt_005" }
  ],
  "turn_count": 6
}
```

### Suggestion Output

```json
{
  "trigger_utt": "utt_007",
  "context_summary": "Patient reports 3-day chest pain with exertion-related onset.",
  "gaps": ["radiation", "associated symptoms", "cardiac history"],
  "suggestions": [
    {
      "id": "sug_001",
      "priority": "high",
      "question": "Does the pain spread to your arm, jaw, or back?",
      "rationale": "Radiation not yet established — critical for cardiac differential"
    }
  ]
}
```

---

## Phase 1 — Transcript Simulation Engine

**Goal:** Build and validate the replay infrastructure that every downstream component depends on. No audio, no LLM calls — pure data plumbing.

### Feature 1.1 — Transcript Data Model & Sample Transcripts

**What:** Define the canonical transcript JSON schema and create 3 domain transcripts (medical, legal, HR) that serve as test fixtures for all future phases.

**Tasks:**
1. Define Pydantic models: `Utterance`, `Transcript`, `SessionConfig`
2. Write `medical_chest_pain.json` — 20–30 turns, realistic SOCRATES-style history taking
3. Write `legal_auto_accident.json` — 20–30 turns, client intake for a car accident claim
4. Write `hr_software_engineer.json` — 20–30 turns, behavioural interview for a senior engineer role
5. Add a JSON schema validation utility that verifies any transcript before it enters the pipeline

**Files:**
- `backend/context/context_models.py` — Pydantic models
- `backend/transcripts/*.json` — Sample transcripts
- `backend/simulation/transcript_validator.py` — Schema validation

**Acceptance Criteria:**
- [ ] All 3 transcripts pass schema validation
- [ ] Each transcript has accurate timestamps with realistic inter-turn gaps (2–8 seconds)
- [ ] Speaker roles alternate correctly (interviewer asks, responder answers)
- [ ] Transcripts are rich enough to test gap detection in Phase 2

---

### Feature 1.2 — Replay Engine Core

**What:** A Python engine that reads a transcript JSON file and emits utterances on a timer, respecting the timestamps in the file. This is the simulation backbone.

**Tasks:**
1. Build `ReplayEngine` class with methods: `load(transcript_path)`, `start()`, `pause()`, `resume()`, `stop()`, `set_speed(multiplier)`
2. Compute inter-utterance delays from timestamps, scaled by speed multiplier
3. Use `asyncio` for non-blocking timer-based emission
4. Emit each utterance as a structured event (not raw text) through a callback/event system
5. Track replay state: `idle`, `playing`, `paused`, `finished`

**Files:**
- `backend/simulation/replay_engine.py`
- `backend/simulation/speed_controller.py`

**Acceptance Criteria:**
- [ ] Engine replays a 30-turn transcript at 1× speed with correct inter-utterance timing (±50ms)
- [ ] Speed changes (0.5×, 1×, 2×, 4×) apply immediately to the next utterance delay
- [ ] Pause/resume preserves position correctly
- [ ] Engine emits events in the canonical `Utterance` format

---

### Feature 1.3 — Preview Bubble (Partial Result Simulation)

**What:** Before each utterance fully commits, a preview appears 0.8 seconds early — simulating the partial-result behaviour of real STT systems. This trains the UI to handle the two-stage pattern (preview → commit) that live audio will produce.

**Tasks:**
1. Build `PreviewBuffer` that intercepts replay engine output
2. 0.8s before commit time, emit a `preview` event with the first ~60% of the utterance text
3. At commit time, emit the full `committed` event
4. Preview events carry `is_preview: true` so the UI can style them differently
5. Handle edge case: if speed is 4× and gap between utterances < 0.8s, skip preview

**Files:**
- `backend/simulation/preview_buffer.py`

**Acceptance Criteria:**
- [ ] Every utterance at 1× speed shows a preview before commit
- [ ] Preview text is a realistic prefix (not random truncation)
- [ ] At 4× speed, previews gracefully degrade (skip if no time)
- [ ] Preview → commit transition produces no duplicates

---

### Feature 1.4 — WebSocket Server for Real-Time Streaming

**What:** A FastAPI WebSocket endpoint that streams replay engine events to connected clients in real time. This is the bridge between backend and frontend.

**Tasks:**
1. Set up FastAPI application with CORS and WebSocket support
2. Build `WebSocketManager` — handles multiple client connections, broadcasts events
3. Define WebSocket message protocol:
   - Server → Client: `utterance_preview`, `utterance_commit`, `replay_state_change`, `session_start`, `session_end`
   - Client → Server: `start`, `pause`, `resume`, `stop`, `set_speed`, `load_transcript`
4. Wire replay engine events to WebSocket broadcasts
5. Add connection lifecycle handling (connect, disconnect, reconnect)

**Files:**
- `backend/main.py` — FastAPI app with WS endpoint
- `backend/websocket/manager.py` — Connection manager

**Acceptance Criteria:**
- [ ] Client connects via WebSocket and receives utterance events in real time
- [ ] Client can send control commands (start/pause/speed) and engine responds immediately
- [ ] Multiple clients receive the same stream (shared session)
- [ ] Clean disconnect handling — no orphaned tasks

---

### Feature 1.5 — REST Endpoints for Session Management

**What:** HTTP endpoints for operations that don't need real-time streaming: listing available transcripts, loading a transcript, configuring a session.

**Tasks:**
1. `GET /api/transcripts` — list available transcript files with metadata
2. `GET /api/transcripts/{id}` — return full transcript JSON
3. `POST /api/transcripts/upload` — accept and validate a custom transcript JSON
4. `POST /api/session/configure` — set domain profile, role labels, speed
5. `GET /api/session/state` — current session state (playing, paused, turn count, etc.)
6. `GET /api/domains` — list available domain profiles

**Files:**
- `backend/main.py` — Route definitions
- `backend/config.py` — Session configuration model

**Acceptance Criteria:**
- [ ] All endpoints return proper JSON responses with appropriate status codes
- [ ] Uploaded custom transcripts are validated against schema before acceptance
- [ ] Session config persists across WebSocket reconnects

---

### Feature 1.6 — Frontend: Transcript Panel & Simulation Controls

**What:** The React UI that displays the live transcript stream and lets the user control the simulation.

**Tasks:**
1. Set up React project with TypeScript, Tailwind CSS
2. Build `TranscriptPanel` — scrolling list of utterances, auto-scrolls, distinguishes speakers by colour
3. Build `PreviewBubble` — renders partial text with a typing indicator, transitions to committed state
4. Build `SimulationControls` — play/pause button, speed selector (0.5×/1×/2×/4×), transcript picker dropdown
5. Build `useWebSocket` hook — connects to backend, dispatches messages, handles reconnection
6. Build `SessionSetup` — domain selector, role label configuration, transcript loader (file upload or preset)
7. Layout: transcript on the left (60% width), controls at the top, right panel reserved for Phase 2/3

**Files:**
- `frontend/src/App.tsx`
- `frontend/src/components/TranscriptPanel.tsx`
- `frontend/src/components/PreviewBubble.tsx`
- `frontend/src/components/SimulationControls.tsx`
- `frontend/src/components/SessionSetup.tsx`
- `frontend/src/hooks/useWebSocket.ts`
- `frontend/src/types/index.ts`

**Acceptance Criteria:**
- [ ] Transcript renders in real time as events arrive over WebSocket
- [ ] Interviewer and Responder utterances are visually distinct (different colours/alignment)
- [ ] Preview bubbles appear and transition smoothly to committed text
- [ ] Speed controls change replay speed without restart
- [ ] Custom transcript upload works end-to-end
- [ ] UI is responsive and doesn't scroll-jank on fast replay speeds

---

### Feature 1.7 — Custom Transcript Loader

**What:** Paste or upload any JSON transcript in the standard utterance format and replay it instantly. This makes the system testable with any conversation.

**Tasks:**
1. Add a JSON text area in `SessionSetup` where users can paste raw transcript JSON
2. Client-side validation against the utterance schema before sending to backend
3. Backend validates, stores temporarily, and makes it available to the replay engine
4. Error messaging: clear feedback if JSON is malformed or missing required fields

**Files:**
- `frontend/src/components/SessionSetup.tsx` (extend)
- `backend/main.py` (extend upload endpoint)

**Acceptance Criteria:**
- [ ] Pasted JSON with valid schema loads and replays correctly
- [ ] Invalid JSON shows a specific, helpful error message
- [ ] Custom transcripts appear in the transcript picker after upload

---

### Phase 1 — Integration Test

**End-to-end validation before moving to Phase 2:**
- [ ] Load the medical transcript via the UI
- [ ] Press play — utterances stream at 1× with correct timing
- [ ] Preview bubbles appear 0.8s before each commit
- [ ] Switch to 2× speed mid-replay — timing adjusts immediately
- [ ] Pause and resume — position preserved
- [ ] Stop and reload a different transcript — clean reset
- [ ] Upload a custom JSON transcript — it replays correctly
- [ ] Open a second browser tab — both receive the same stream
- [ ] End-to-end latency (event emission → UI render) < 100ms

---

## Phase 2 — Conversation Context Tracking

**Goal:** After every Responder turn, the system updates a running understanding of the conversation — what's been covered, what's missing, and what signals deserve follow-up.

### Feature 2.1 — LLM Client Abstraction

**What:** A unified interface for calling Claude, GPT-4, or Gemini. The rest of the system never knows which LLM is behind the call.

**Tasks:**
1. Define `LLMClient` abstract interface: `async analyze(prompt, context) -> dict`
2. Implement `ClaudeClient` using Anthropic SDK
3. Implement `OpenAIClient` using OpenAI SDK
4. Implement `GeminiClient` using Google GenAI SDK
5. Config-driven selection: `.env` file specifies which provider + API key
6. Add retry logic with exponential backoff (3 retries, 1s/2s/4s)
7. Add response parsing — LLM returns JSON, client validates and extracts structured output
8. Measure and log latency per call

**Files:**
- `backend/context/llm_client.py`
- `backend/config.py` (extend)
- `.env.example`

**Acceptance Criteria:**
- [ ] Can swap between Claude/GPT-4/Gemini by changing one env var
- [ ] Invalid or malformed LLM responses are caught and retried
- [ ] Latency per call is logged
- [ ] API keys are never hardcoded

---

### Feature 2.2 — Domain Profile Loader

**What:** Load a domain profile (structured prompt fragment) at session start. The profile defines the framework, gap logic, and signal types for the conversation domain.

**Tasks:**
1. Define `DomainProfile` model: `name`, `framework`, `gap_categories`, `signal_types`, `priority_rules`, `role_labels`, `system_prompt_fragment`
2. Write the 5 built-in profiles as structured Python objects:
   - Medical (SOCRATES)
   - Legal (Evidence Chain)
   - HR (Behavioural Competency)
   - Journalism (Story Angle)
   - UX Research (Pain Point Mapping)
3. Build `DomainLoader` that reads built-in profiles and custom profiles from config files
4. Inject the profile into the LLM system prompt at session start

**Files:**
- `backend/domains/loader.py`
- `backend/domains/medical.py`
- `backend/domains/legal.py`
- `backend/domains/hr.py`
- `backend/domains/journalism.py`
- `backend/domains/ux_research.py`
- `backend/domains/custom.py`

**Acceptance Criteria:**
- [ ] All 5 built-in profiles load correctly and produce valid system prompts
- [ ] Custom domain profile can be loaded from a JSON/YAML config file
- [ ] Profile switch at session start does not require restart
- [ ] Profile content is visible in the session setup UI

---

### Feature 2.3 — Context Engine Core

**What:** The brain of the system. After every Responder utterance, sends the full transcript + domain profile to the LLM and receives an updated context object.

**Tasks:**
1. Build `ContextEngine` class that subscribes to utterance commit events
2. Filter: only trigger on `speaker: "responder"` utterances
3. Construct LLM prompt: system prompt (domain profile) + full transcript so far + instruction to return updated context JSON
4. Parse LLM response into `ContextObject` (Pydantic model)
5. Maintain context state across turns — each update builds on the previous
6. Emit `context_updated` event with the new context object
7. Handle LLM failures gracefully — retain last valid context, retry once, log error

**Files:**
- `backend/context/context_engine.py`
- `backend/context/context_models.py` (extend)

**Acceptance Criteria:**
- [ ] Context updates within 2 seconds of each Responder turn
- [ ] `information_gathered` grows incrementally — new facts are added, not duplicated
- [ ] `gaps` shrink as topics are covered
- [ ] `signals` correctly identify red flags / emotionally significant statements
- [ ] Context object is valid JSON matching the schema after every update

---

### Feature 2.4 — Incremental Prompt Optimisation

**What:** Sending the full transcript every turn is expensive and slow as conversations grow. This feature optimises the prompt to reduce token usage without losing accuracy.

**Tasks:**
1. Track token count of the full transcript
2. Below 4K tokens: send full transcript (no optimisation needed)
3. 4K–8K tokens: send full transcript + previous context object (gives LLM a head start)
4. Above 8K tokens: send previous context object + last 10 utterances + summary of earlier turns
5. Add configurable thresholds per LLM provider (Claude has larger context than GPT-4 Turbo)
6. A/B test accuracy: compare full-transcript vs optimised-prompt outputs on sample conversations

**Files:**
- `backend/context/context_engine.py` (extend)
- `backend/context/prompt_optimizer.py` (new)

**Acceptance Criteria:**
- [ ] Token usage scales sub-linearly with conversation length
- [ ] Context accuracy degrades < 5% when using optimised prompts vs full transcript
- [ ] Prompt strategy auto-switches based on transcript length

---

### Feature 2.5 — Frontend: Context Panel

**What:** A live sidebar that displays the running context object — what the system understands about the conversation at any moment.

**Tasks:**
1. Build `ContextPanel` component in the right sidebar
2. Sections: Core Topic, Information Gathered (key-value list), Gaps (checklist with uncovered items highlighted), Signals (tagged cards)
3. Subscribe to `context_updated` WebSocket events
4. Animate updates: new items fade in, resolved gaps get a strikethrough
5. Collapsible sections for long conversations
6. Add "Context updated" timestamp indicator

**Files:**
- `frontend/src/components/ContextPanel.tsx`
- `frontend/src/hooks/useSession.ts` (extend)

**Acceptance Criteria:**
- [ ] Context panel updates in real time as the conversation progresses
- [ ] Gaps visually distinguish covered vs uncovered items
- [ ] Signals show type labels (red flag, contradiction, vague, emotional)
- [ ] Panel is scrollable and collapsible for long conversations
- [ ] Panel is useful as a standalone conversation guide even without suggestions

---

### Phase 2 — Integration Test

- [ ] Start a medical simulation session
- [ ] Context panel is empty at start, shows the SOCRATES framework as the gap checklist
- [ ] After the first Responder turn: core topic populated, first information item added
- [ ] After 5 turns: 3–5 information items gathered, some gaps resolved
- [ ] Red flag signal appears when patient mentions exertional chest pain
- [ ] Switch to legal transcript — context resets, legal framework appears
- [ ] Context update latency consistently < 2 seconds
- [ ] No duplicate information items across turns

---

## Phase 3 — Next Question Suggestion Engine

**Goal:** The moment the Responder finishes speaking, surface 2–3 ranked suggested questions for the Interviewer.

### Feature 3.1 — Suggestion Engine Core

**What:** Consumes the context object and generates ranked suggestions. This is the core product value.

**Tasks:**
1. Build `SuggestionEngine` that triggers on every `context_updated` event
2. Construct suggestion prompt: context object + domain profile priority rules + instruction to return 1–3 ranked suggestions
3. Each suggestion includes: `priority` (high/medium/low), `question` (plain text), `rationale` (one sentence)
4. Ranking logic varies by domain:
   - Medical: red flag follow-up > gap coverage > depth
   - Legal: evidence gap > chronology > witness detail
   - HR: behavioural depth > specific examples > cultural fit
5. Deduplicate: never suggest a question that's already been asked (check against `questions_asked`)
6. Parse and validate LLM response into `SuggestionOutput` model

**Files:**
- `backend/suggestions/suggestion_engine.py`
- `backend/suggestions/suggestion_models.py`

**Acceptance Criteria:**
- [ ] 2–3 suggestions generated within 1 second of context update
- [ ] Suggestions never repeat questions already asked
- [ ] Priority ranking matches domain-specific rules
- [ ] Each suggestion has a clear, non-generic rationale
- [ ] Suggestions are phrased as natural questions (not clinical instructions)

---

### Feature 3.2 — Combined LLM Call (Context + Suggestions)

**What:** Instead of two sequential LLM calls (one for context, one for suggestions), combine them into a single call that returns both. Cuts latency roughly in half.

**Tasks:**
1. Modify the LLM prompt to request both context update AND suggestions in one response
2. Define combined response schema: `{ context: {...}, suggestions: [...] }`
3. Parse both outputs from a single LLM response
4. Fallback: if combined call fails, fall back to two sequential calls
5. Measure latency improvement vs two-call approach

**Files:**
- `backend/context/context_engine.py` (modify)
- `backend/suggestions/suggestion_engine.py` (modify)

**Acceptance Criteria:**
- [ ] Single LLM call produces both valid context and valid suggestions
- [ ] End-to-end latency (Responder turn → suggestions visible) < 3 seconds
- [ ] Fallback to two-call mode works transparently

---

### Feature 3.3 — Suggestion Feedback Logger

**What:** Track which suggestions the Interviewer uses, adapts, or ignores. This data is essential for future quality improvement.

**Tasks:**
1. Each suggestion card has: "Use" button (copies question verbatim), "Adapt" indicator (Interviewer asks something similar), "Ignore" (default if neither)
2. Log every suggestion with its outcome: `{ suggestion_id, outcome: "used"|"adapted"|"ignored", timestamp }`
3. Store feedback in session log
4. Calculate per-session relevance rate: (used + adapted) / total
5. Include feedback summary in post-session artifacts

**Files:**
- `backend/suggestions/feedback_logger.py`
- `frontend/src/components/SuggestionCards.tsx` (extend)

**Acceptance Criteria:**
- [ ] "Use" button copies the question text and logs the action
- [ ] Adapted detection: if the Interviewer's next utterance is semantically similar to a suggestion, mark it as adapted
- [ ] Per-session relevance rate is calculated and stored
- [ ] Feedback data is included in post-session output

---

### Feature 3.4 — Frontend: Suggestion Cards

**What:** The Interviewer-facing UI element that displays ranked suggestions with rationale.

**Tasks:**
1. Build `SuggestionCards` component — appears below/beside the transcript panel
2. Show up to 3 cards, ranked by priority (high = red/orange accent, medium = yellow, low = blue)
3. Each card shows: the question (large, readable), the rationale (smaller, muted), a "Use" button
4. Cards animate in when new suggestions arrive, animate out when replaced
5. Old suggestions fade/collapse when new ones arrive (don't accumulate)
6. Suggestion history: expandable "Previous suggestions" section at the bottom

**Files:**
- `frontend/src/components/SuggestionCards.tsx`

**Acceptance Criteria:**
- [ ] Suggestions appear within 500ms of WebSocket event
- [ ] Maximum 3 cards visible at any time
- [ ] Priority is visually clear through colour coding
- [ ] Cards don't cause layout shift in the transcript panel
- [ ] Suggestion text is large enough to scan at a glance during a conversation

---

### Phase 3 — Integration Test

- [ ] Run a full medical simulation end-to-end
- [ ] After first Responder turn: suggestions appear within 3 seconds
- [ ] Suggestions are medically relevant (ask a doctor to review)
- [ ] Red flag follow-up is always priority "high" when present
- [ ] Suggestions don't repeat questions the Interviewer has already asked
- [ ] Clicking "Use" logs the action and the suggestion is tracked
- [ ] Run a full legal simulation — suggestions match legal framework priorities
- [ ] Run a full HR simulation — suggestions probe for behavioural depth
- [ ] >80% of suggestions rated relevant by domain-aware reviewer across all 3 domains

---

## Phase 4 — Live Audio Integration

**Goal:** Replace the simulator with real microphone input. Same pipeline, same output format. This is an input swap, not a rebuild.

### Feature 4.1 — Audio Capture & VAD

**What:** Capture audio from the microphone and strip silence using Silero VAD before any processing.

**Tasks:**
1. Set up audio capture using `sounddevice` or `pyaudio` — configurable sample rate (16kHz), chunk size
2. Integrate Silero VAD — CPU only, no VRAM
3. VAD filters out silence and non-speech noise
4. Only speech-containing chunks are forwarded to STT and diarization
5. Add audio level indicator for the UI (helps user verify mic is working)

**Files:**
- `backend/audio/pipeline.py`
- `backend/audio/vad.py`

**Acceptance Criteria:**
- [ ] Audio captured cleanly from default microphone
- [ ] Silero VAD correctly identifies speech vs silence (tested with sample recordings)
- [ ] Non-speech chunks are discarded before hitting downstream models
- [ ] CPU usage for VAD < 5% on an 8-core machine

---

### Feature 4.2 — Streaming Transcription (Faster-Whisper)

**What:** Real-time speech-to-text using Faster-Whisper via RealtimeSTT.

**Tasks:**
1. Install and configure `RealtimeSTT` with `faster-whisper` backend
2. Feed VAD-filtered audio chunks to the transcriber
3. Emit partial results (preview) as they're generated
4. Emit final result (committed utterance) when the model finalises
5. Map partial → preview and final → commit to match the simulation format exactly
6. Handle GPU memory allocation: Faster-Whisper large-v3 needs ~10GB VRAM

**Files:**
- `backend/audio/transcriber.py`

**Acceptance Criteria:**
- [ ] Transcription latency < 500ms from end of speech to final text
- [ ] Partial results stream in real time (word-by-word or phrase-by-phrase)
- [ ] Output format matches simulation `Utterance` schema exactly
- [ ] VRAM usage stable at ~10GB for Faster-Whisper large-v3

---

### Feature 4.3 — Streaming Diarization (Diart)

**What:** Real-time speaker identification — determines whether the Interviewer or Responder is speaking.

**Tasks:**
1. Install and configure Diart for streaming diarization
2. Run Diart in parallel with Faster-Whisper on the same audio chunks
3. Diart outputs speaker labels per chunk (Speaker A / Speaker B)
4. Handle ~1s lag in speaker label confirmation
5. VRAM allocation: Diart needs ~2–3GB

**Files:**
- `backend/audio/diarizer.py`

**Acceptance Criteria:**
- [ ] Speaker labels assigned to each audio chunk within ~1 second
- [ ] Two-speaker separation accuracy > 88% in single-mic setup
- [ ] Labels are consistent across the session (Speaker A stays Speaker A)
- [ ] VRAM usage stable at ~2–3GB

---

### Feature 4.4 — Speaker Enrollment & Role Mapping

**What:** At session start, each speaker says one sentence. The system maps Diart's abstract labels (Speaker A/B) to semantic roles (Interviewer/Responder).

**Tasks:**
1. Build enrollment flow: UI prompts "Interviewer, please say a sentence" → records → "Responder, please say a sentence" → records
2. Extract voice fingerprints from enrollment samples
3. Map Diart's Speaker A/B labels to Interviewer/Responder by matching against fingerprints
4. Add manual role-flip button in UI for rare misattributions
5. Store enrollment data for the session duration only (no persistent voice storage)

**Files:**
- `backend/audio/enrollment.py`
- `frontend/src/components/SessionSetup.tsx` (extend)

**Acceptance Criteria:**
- [ ] Enrollment completes in < 15 seconds
- [ ] Role mapping is correct > 95% of the time for distinct voices
- [ ] Manual flip button instantly corrects misattribution
- [ ] Enrollment data is discarded at session end

---

### Feature 4.5 — Chunk-Aligned Timestamp Merge

**What:** Merge Faster-Whisper transcription output with Diart diarization output by aligning timestamps from both models.

**Tasks:**
1. Both models process the same audio chunks with shared timestamps
2. Merger aligns transcription text with speaker labels by overlapping time windows
3. Handle edge cases: speaker change mid-sentence, overlapping speech, one model lagging
4. Output: canonical `Utterance` objects with `speaker`, `text`, `timestamp`
5. Feed merged utterances into the same pipeline the simulation engine uses

**Files:**
- `backend/audio/merger.py`

**Acceptance Criteria:**
- [ ] Merged output matches `Utterance` schema exactly
- [ ] Speaker labels are assigned to correct text segments > 90% of the time
- [ ] Overlapping speech is handled gracefully (attributed to dominant speaker or flagged)
- [ ] Merged output enters the context/suggestion pipeline identically to simulation output

---

### Feature 4.6 — Audio Pipeline Orchestration

**What:** Wire all audio components together: mic → VAD → STT + diarization (parallel) → merge → pipeline.

**Tasks:**
1. Build `AudioPipeline` class that orchestrates all components
2. Manage GPU memory allocation across models
3. Handle startup sequence: enrollment → pipeline start → streaming
4. Graceful degradation: if diarization fails, continue with transcription only (label all as "unknown")
5. Add pipeline health monitoring: latency per component, VRAM usage, error rates
6. UI toggle: switch between simulation mode and live audio mode

**Files:**
- `backend/audio/pipeline.py`

**Acceptance Criteria:**
- [ ] Full pipeline runs stably for 30+ minute sessions
- [ ] End-to-end latency (end of speech → suggestions visible) < 3 seconds
- [ ] No VRAM leaks over time
- [ ] Graceful degradation when one component fails
- [ ] Switching between simulation and live mode is seamless

---

### Phase 4 — Integration Test

- [ ] Conduct a real 10-minute medical conversation with two speakers
- [ ] Transcript appears in real time with correct speaker labels
- [ ] Context panel and suggestions behave identically to simulation
- [ ] End-to-end latency stays under 3 seconds throughout the session
- [ ] No crashes or memory leaks during the full session
- [ ] Manually trigger a role-flip — suggestions adjust to the correct speaker roles
- [ ] Single-mic test: accuracy > 88% speaker separation
- [ ] Two-mic test (if available): accuracy > 98% speaker separation

---

## Phase 5 — Post-Session Intelligence

**Goal:** When the session ends, produce a structured, domain-appropriate record from the full conversation.

### Feature 5.1 — WhisperX Post-Session Transcription

**What:** Run WhisperX over the full session recording for a higher-accuracy transcript than the real-time pass produced.

**Tasks:**
1. Save full session audio as WAV during recording
2. When session ends, run WhisperX with word-level timestamps and diarization
3. Compare WhisperX output to the real-time transcript — log accuracy delta
4. Store the WhisperX transcript as the canonical session record
5. Handle long sessions: chunk audio if needed for memory constraints

**Files:**
- `backend/postsession/whisperx_runner.py`

**Acceptance Criteria:**
- [ ] WhisperX transcript is measurably more accurate than real-time transcript
- [ ] Word-level timestamps enable precise quote extraction
- [ ] Processing completes within 2× real-time (30-min session → < 60 min processing)
- [ ] Output stored in the canonical `Transcript` format

---

### Feature 5.2 — Artifact Generation Engine

**What:** LLM generates domain-specific structured output from the final transcript.

**Tasks:**
1. Build `ArtifactGenerator` that takes a `Transcript` + `DomainProfile` and produces artifacts
2. Define artifact templates per domain:
   - Medical: SOAP note, symptom timeline, differential diagnosis list, uncovered gaps
   - Legal: Intake summary, key facts, follow-up actions, evidence status
   - HR: Candidate summary, competency map, red flags, recommendation
   - Journalism: Source summary, key quotes, story angles, verification checklist
   - UX Research: Insight summary, pain points, direct quotes, feature gaps
3. LLM generates each artifact from the transcript using domain-specific prompts
4. Output as structured JSON + human-readable Markdown
5. Include the "Gaps Not Covered" section from the final context object

**Files:**
- `backend/postsession/artifact_generator.py`
- `backend/postsession/templates/`

**Acceptance Criteria:**
- [ ] Medical SOAP note is complete and clinically reasonable
- [ ] All domains produce their specified artifacts
- [ ] "Gaps Not Covered" section accurately reflects questions never asked
- [ ] Artifacts are available in both JSON and Markdown formats
- [ ] Generation completes within 30 seconds of session end

---

### Feature 5.3 — Frontend: Post-Session View

**What:** A dedicated UI screen that displays all generated artifacts after the session ends.

**Tasks:**
1. Build `PostSessionView` component with tabs for each artifact type
2. Show full transcript (WhisperX version) with search and highlighting
3. Show generated artifacts in formatted Markdown
4. Add export buttons: copy to clipboard, download as Markdown, download as JSON
5. Show session metadata: duration, turn count, suggestion relevance rate, domain used

**Files:**
- `frontend/src/components/PostSessionView.tsx`

**Acceptance Criteria:**
- [ ] All artifacts render correctly with proper formatting
- [ ] Transcript is searchable with keyword highlighting
- [ ] Export to Markdown and JSON works correctly
- [ ] Session metadata is accurate
- [ ] View is accessible immediately after session ends (no manual trigger)

---

### Feature 5.4 — Session Storage & History

**What:** Persist session data so users can review past sessions.

**Tasks:**
1. Store each completed session: transcript, context history, suggestions log, artifacts, feedback data
2. Build session list view: sorted by date, filterable by domain
3. Each session is re-openable with full artifact view
4. Local storage (SQLite or file-based) for privacy — no cloud storage by default
5. Optional: export entire session as a single ZIP archive

**Files:**
- `backend/postsession/session_store.py`
- `frontend/src/components/SessionHistory.tsx`

**Acceptance Criteria:**
- [ ] Sessions persist across app restarts
- [ ] Session list shows date, domain, duration, turn count
- [ ] Full session data is re-viewable
- [ ] ZIP export includes transcript, artifacts, and session metadata

---

### Phase 5 — Integration Test

- [ ] Complete a full live session (or simulation) end-to-end
- [ ] Session ends → WhisperX processes audio → artifacts generate automatically
- [ ] Post-session view shows all artifacts immediately
- [ ] SOAP note (medical) is clinically reasonable and includes gap section
- [ ] Export to Markdown produces a clean, readable document
- [ ] Session appears in history and is re-openable
- [ ] Feedback summary shows suggestion relevance rate

---

## Dependency & Environment Setup

### Python Dependencies (`requirements.txt`)

```
# Core
fastapi>=0.109.0
uvicorn>=0.27.0
websockets>=12.0
pydantic>=2.6.0
python-dotenv>=1.0.0

# LLM Clients
anthropic>=0.18.0
openai>=1.12.0
google-generativeai>=0.4.0

# Audio (Phase 4+)
# sounddevice>=0.4.6
# silero-vad>=4.0
# RealtimeSTT>=0.1.0
# faster-whisper>=0.10.0
# diart>=0.8.0
# whisperx>=3.1.0

# Utilities
aiofiles>=23.2.0
```

### Node Dependencies (`package.json` — frontend)

```
react, react-dom, typescript,
tailwindcss, @headlessui/react,
electron (Phase 4+)
```

### Environment Variables (`.env.example`)

```
LLM_PROVIDER=claude          # claude | openai | gemini
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
GOOGLE_API_KEY=
DEFAULT_DOMAIN=medical
SIMULATION_SPEED=1.0
WS_PORT=8000
```

---

## Implementation Order Summary

| Order | Feature | Phase | Depends On | Estimated Effort |
|-------|---------|-------|------------|-----------------|
| 1 | Transcript Data Model & Samples | P1 | — | 1 day |
| 2 | Replay Engine Core | P1 | #1 | 2 days |
| 3 | Preview Buffer | P1 | #2 | 0.5 day |
| 4 | WebSocket Server | P1 | #2 | 1 day |
| 5 | REST Endpoints | P1 | #1 | 0.5 day |
| 6 | Frontend: Transcript + Controls | P1 | #4 | 2 days |
| 7 | Custom Transcript Loader | P1 | #5, #6 | 0.5 day |
| 8 | LLM Client Abstraction | P2 | — | 1 day |
| 9 | Domain Profile Loader | P2 | — | 1.5 days |
| 10 | Context Engine Core | P2 | #8, #9 | 2 days |
| 11 | Incremental Prompt Optimisation | P2 | #10 | 1 day |
| 12 | Frontend: Context Panel | P2 | #10, #6 | 1.5 days |
| 13 | Suggestion Engine Core | P3 | #10 | 1.5 days |
| 14 | Combined LLM Call | P3 | #10, #13 | 1 day |
| 15 | Suggestion Feedback Logger | P3 | #13 | 0.5 day |
| 16 | Frontend: Suggestion Cards | P3 | #13, #6 | 1 day |
| 17 | Audio Capture & VAD | P4 | — | 1.5 days |
| 18 | Streaming Transcription | P4 | #17 | 2 days |
| 19 | Streaming Diarization | P4 | #17 | 2 days |
| 20 | Speaker Enrollment | P4 | #19 | 1 day |
| 21 | Chunk-Aligned Merge | P4 | #18, #19 | 1.5 days |
| 22 | Audio Pipeline Orchestration | P4 | #17–#21 | 2 days |
| 23 | WhisperX Post-Session | P5 | #22 | 1 day |
| 24 | Artifact Generation | P5 | #10, #23 | 2 days |
| 25 | Frontend: Post-Session View | P5 | #24 | 1.5 days |
| 26 | Session Storage & History | P5 | #24, #25 | 1.5 days |

**Total estimated effort: ~33 developer-days**

- **Phase 1 (Simulation):** ~7.5 days
- **Phase 2 (Context):** ~7 days
- **Phase 3 (Suggestions):** ~4 days
- **Phase 4 (Audio):** ~10 days
- **Phase 5 (Post-Session):** ~6 days

---

## Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| LLM latency spikes exceed 3s budget | Suggestions feel stale | Pre-warm connections, cache domain prompts, use streaming LLM responses |
| Diart speaker separation < 88% single mic | Wrong speaker triggers suggestions | Manual flip button, two-mic option, post-session WhisperX correction |
| Combined LLM call returns malformed JSON | Pipeline stalls | Fallback to two-call mode, structured output mode (Claude/GPT-4) |
| Long conversations exceed context window | Context tracking degrades | Incremental prompt optimisation (Feature 2.4), summarise early turns |
| GPU VRAM exhaustion during live session | Models crash | Pre-allocate budgets, monitor usage, offload Silero VAD to CPU |
| Electron packaging complexity | Deployment delays | Start with browser-only (Phase 1–3), Electron only needed for Phase 4+ |

---

## What "Done" Looks Like Per Phase

| Phase | Definition of Done |
|-------|-------------------|
| **Phase 1** | A user can load any transcript, watch it replay in real time with preview bubbles, control speed, and see the utterance stream — all in the browser. |
| **Phase 2** | A context panel updates live during replay, showing what's been covered, what's missing, and what signals appeared — validated against domain expert review. |
| **Phase 3** | 2–3 ranked suggestions appear after every Responder turn, >80% rated relevant by domain-aware reviewer, with feedback tracking. |
| **Phase 4** | Two people speak into a microphone, and the system produces the same transcript stream and suggestions as simulation — latency < 3s. |
| **Phase 5** | Session ends and a complete structured record is generated automatically — SOAP notes, intake summaries, candidate profiles — with no manual effort. |

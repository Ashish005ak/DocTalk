# Context Engine — Prompt Optimisation

This document explains how ConvoNudge's Context Engine manages LLM token usage as conversations grow longer.

---

## The Problem

Every time the Context Engine analyses a conversation, it sends the transcript to an LLM. For short conversations this is fine, but a 60-minute interview can produce 200+ utterances and 15,000+ tokens of raw text. Sending the full transcript every time wastes money, increases latency, and can exceed model context windows.

## Solution: Three-Tier Prompt Strategy

The engine estimates the token count of the full transcript (`len(text) // 4`) before every analysis call, then picks one of three modes:

```
                         Token estimate
                              |
              < 4,000 tokens? |
             +----YES---------+--------NO-----+
             |                                 |
         FULL MODE                  < 8,000 tokens?
     (all utterances                      |
       verbatim)           +----YES-------+------NO------+
                           |                              |
                      WINDOW MODE                   SUMMARY MODE
                  (last 10 verbatim,          (LLM-generated summary
                   older turns covered         of old turns + last 10
                   by previous context)          verbatim)
```

### Tier 1: FULL (< 4,000 tokens)

Every utterance is included verbatim in the prompt. This is the simplest and most accurate mode, used for the majority of conversations (a typical 28-turn transcript is ~650 tokens).

**Prompt structure:**
```
## Transcript
[utt_001] Interviewer: ...
[utt_002] Responder: ...
... (all utterances) ...

## Previous context
{ ... last ContextObject ... }
```

### Tier 2: WINDOW (4,000 - 8,000 tokens)

Only the last 10 utterances are included verbatim. Older turns are **not** sent — instead, the prompt tells the LLM that earlier information is captured in the "Previous context" section (which contains the full ContextObject from the last analysis, including all previously gathered information, gaps, and signals).

This works because the ContextObject already acts as a running summary. The LLM only needs the recent utterances to detect new information and update the context.

**Prompt structure:**
```
## Transcript
[28 earlier utterances omitted — their information is captured
in the Previous context section below]

[utt_029] Responder: ...
[utt_030] Interviewer: ...
... (last 10 utterances) ...

## Previous context
{ ... last ContextObject with all accumulated data ... }
```

**Token savings:** ~50-70% reduction compared to FULL mode.

### Tier 3: SUMMARY (> 8,000 tokens)

For very long conversations, an LLM call is made to summarise all utterances except the last 10 into a compact paragraph (~200 words). This summary is cached and only regenerated when 10+ new utterances accumulate beyond what the cache covers.

**Prompt structure:**
```
## Summary of earlier conversation (utterances 1-58)
The patient presented with chest pain that started 2 hours ago...
[~200 word factual summary]

## Recent utterances (verbatim)
[utt_059] Interviewer: ...
[utt_060] Responder: ...
... (last 10 utterances) ...

## Previous context
{ ... last ContextObject ... }
```

**Token savings:** ~70-85% reduction compared to FULL mode.

**Cache refresh logic:** The summary is regenerated when `total_utterances - 10 > cached_count + 10`. This means the summary stays fresh without being regenerated on every call.

---

## Analysis Frequency

By default, the Context Engine analyses every **2nd responder turn** instead of every single one. This halves the number of LLM calls with minimal impact on context freshness — in a typical conversation, a responder turn happens every 5-10 seconds at 1x speed, so the context updates roughly every 10-20 seconds.

The first responder turn always triggers analysis so the context panel isn't empty at the start.

This is configurable via the `CONTEXT_ANALYSIS_INTERVAL` environment variable.

---

## Configuration

All thresholds are configurable in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `CONTEXT_ANALYSIS_INTERVAL` | `2` | Analyse every N-th responder turn |
| `CONTEXT_TOKEN_THRESHOLD_FULL` | `4000` | Below this: FULL mode |
| `CONTEXT_TOKEN_THRESHOLD_SUMMARY` | `8000` | Above this: SUMMARY mode (in between: WINDOW) |
| `CONTEXT_WINDOW_SIZE` | `10` | Number of recent utterances kept verbatim |

---

## Logging

The engine logs which mode was selected on every analysis call. Look for these in the backend terminal:

```
INFO  Prompt mode: FULL  (est. 650 tokens, 28 utterances)
INFO  Prompt mode: WINDOW  (est. 5200 tokens, 42 utterances, last 10 verbatim, 32 omitted)
INFO  Prompt mode: SUMMARY  (est. 9800 tokens, 68 utterances, summarised up to utt 58, last 10 verbatim)
INFO  Summarising 58 old utterances (previous cache covered 0)
INFO  Summary refreshed: 312 chars covering 58 utterances
```

When a responder turn is skipped due to the interval setting:
```
DEBUG  Skipping analysis (responder turn 3, next at 4)
```

---

## Data Flow

```
ReplayEngine
    |
    v  (utterance_commit)
PreviewBuffer
    |
    v  (non-preview utterances only)
main.py bridge -----> WebSocket broadcast to frontend
    |
    v  (asyncio.create_task)
ContextEngine.on_utterance()
    |
    |-- interviewer turn: track question, no analysis
    |-- responder turn (not interval): skip
    |-- responder turn (interval match):
          |
          v
        _build_user_prompt()
          |
          +-- est. < 4K tokens --> FULL mode
          +-- est. 4K-8K tokens -> WINDOW mode
          +-- est. > 8K tokens --> SUMMARY mode (may trigger _maybe_refresh_summary)
          |
          v
        LLMClient.analyze_json()
          |
          v
        _parse_and_merge()
          |
          v
        Emit context_updated --> WebSocket broadcast --> ContextPanel
```

---

## Cost Estimates

Assuming Gemini 2.5 Flash (free tier: 15 req/min):

| Conversation | Utterances | Mode | Est. Input Tokens | LLM Calls (at 2x interval) |
|-------------|-----------|------|-------------------|---------------------------|
| Short (5 min) | 20 | FULL | ~500 | ~5 |
| Medium (15 min) | 60 | WINDOW | ~1,200 | ~15 |
| Long (45 min) | 180 | SUMMARY | ~1,500 | ~45 + 4 summary calls |

Without optimisation, the long conversation would send ~15,000 tokens per call x 90 calls = 1.35M input tokens. With optimisation: ~1,500 x 45 + 4 summary calls = ~72K input tokens. That is a **~95% reduction**.

# Fix: Two-Bucket Clinical Observations

## Problem

Red flag keys like `"Neck stiffness"`, `"Photophobia"`, `"Altered consciousness"` didn't match any schema field name. When the LLM extracted these from patient messages, `validate_facts` rejected them (unknown key), so they never entered `information_gathered`. The red flag condition was never satisfied, and `flow_control` looped on `TARGETED_CLARIFY` forever.

Additionally, any out-of-schema fact the patient mentioned was silently dropped — never acknowledged, never summarized, never checked for safety escalation.

## Solution: Two-Bucket Architecture

Two complementary fixes applied together:

### Part D — Normalize Red Flag & Hypothesis Keys to Schema Fields

For clinically important concepts that the system *should* formally track, proper schema fields were added and all red flag / hypothesis definitions were updated to reference those field names.

### Part 2 — `clinical_observations` Bucket

For facts the LLM extracts that genuinely don't match any schema field, they are routed into a bounded `clinical_observations` dict instead of being silently dropped. This bucket feeds:
- Response generation (acknowledgment)
- Summarization (completeness)
- LLM safety review (escalation check)

It does **not** feed hypothesis scoring, gap computation, or directly trigger deterministic red flags.

---

## File Changes

### `backend/domain/configs/general_medicine.yaml`

**D1 — Added 14 new schema fields to `common_symptoms` block:**

| Field | Hint |
|---|---|
| `Neck_Stiffness` | Any stiffness or difficulty moving your neck? |
| `Photophobia` | Any sensitivity to light? |
| `Altered_Consciousness` | Any confusion, drowsiness, or altered awareness? |
| `Arm_Pain` | Any pain in your arms? |
| `Jaw_Pain` | Any pain in your jaw? |
| `Sweating` | Any unusual or excessive sweating? |
| `Syncope` | Any fainting or near-fainting episodes? |
| `Leg_Swelling` | Any swelling in your legs? |
| `Calf_Pain` | Any pain in your calves? |
| `Abdominal_Pain` | Any abdominal or stomach pain? |
| `Flank_Pain` | Any pain in your side or flank area? |
| `Dysuria` | Any pain or burning when urinating? |
| `Vomiting` | Any vomiting? |
| `Palpitations` | Any awareness of your heart beating fast or irregularly? |

All are `field_type: text`, `required: false`, `is_supporting_key: true`.

**D2 — Normalized all 9 red flag rules:**

All `required_keys`, `at_least_one_of`, and `qualifiers` keys now use exact schema field names (e.g., `"Neck_Stiffness"` instead of `"Neck stiffness"`).

**D3 — Normalized all hypothesis keys:**

All `supporting_keys` and `contradicting_keys` now reference schema field names only, so hypothesis scoring actually matches facts in `information_gathered`.

---

### `backend/agent/state.py`

- Added `clinical_observations: Annotated[dict[str, str], _merge_dict]` to `ClinicalState`.
- Initialized as `{}` in `create_initial_state`.

---

### `backend/llm/fact_extractor.py`

- Added `ValidationResult` dataclass with `schema_facts` and `observations` lists.
- Refactored `validate_facts` to return `ValidationResult` instead of `list[RawFact]`.
- Unknown-key facts are now routed to `observations` instead of being silently dropped.
- Placeholder values and type-mismatch facts are still hard-dropped.

**New logging:**
- `VALIDATE_OBSERVATION` — logged when a fact is routed to observations (unknown key).
- `VALIDATE_DROP` — logged when a fact is dropped (placeholder value).
- `VALIDATE_REJECT` — logged when a fact fails type check.
- `VALIDATE_ACCEPT` — logged when a fact passes all checks.
- `VALIDATE_FACTS` — summary line with `schema_accepted`, `observations`, `dropped` counts.

---

### `backend/agent/nodes/intake.py`

- Updated to handle `ValidationResult` from `validate_facts`.
- Schema facts go through the existing path into `intake_facts`.
- Observations are formatted as `{key: value}` and returned as the `clinical_observations` state update.

**New logging:**
- `INTAKE_VALIDATED` — now logs `schema_facts` and `observations` counts.
- `INTAKE_OBSERVATION_BUCKET` — logged per observation routed to the bucket.
- `INTAKE_OBSERVATIONS` — summary of all observations in this turn.

---

### `backend/llm/response_generator.py`

- `_build_prompt` now reads `clinical_observations` from state.
- When non-empty, appends an "Additional observations noted" block to the user prompt so the LLM can naturally acknowledge what the patient mentioned.

**New logging:**
- `RESPONSE_PROMPT` — logged when observations are included in the prompt.

---

### `backend/llm/summarizer.py`

- `generate_summary` now reads `clinical_observations` from state.
- When non-empty, includes a "Additional patient-reported observations (not formally assessed)" section in the summary prompt.

**New logging:**
- `SUMMARY_OBSERVATIONS` — logged when observations are included in the summary.

---

### `backend/agent/nodes/safety.py`

- Added LLM escalation check (step 5) between dedup check and empty response guard.
- When `clinical_observations` is non-empty, calls the LLM with a focused safety prompt asking whether anything warrants immediate medical escalation.
- If the LLM replies YES, appends an escalation warning to the doctor's response.
- This is a bounded LLM call — small prompt, short response, only fires when observations exist.

**New logging:**
- `SAFETY_ESCALATION_CHECK` — logged when the escalation check fires.
- `SAFETY_ESCALATION_RESULT` — logged with the LLM's decision (YES/NO) and reason.
- `SAFETY_ESCALATION_TRIGGERED` — logged when a warning is appended.
- `SAFETY_ESCALATION_FAIL` — logged if the LLM call fails (check is skipped).

---

### `backend/agent/nodes/flow_control.py`

- Applied `gap_ask_counts` / `skipped_gaps` retry mechanism to the `TARGETED_CLARIFY` (candidate red flag) path.
- Before emitting a `TARGETED_CLARIFY` move, checks if the target gap has exceeded `max_gap_asks`.
- If exhausted, skips that candidate and moves to the next candidate or falls through to normal flow.
- Prevents infinite loops on candidates whose required keys can never be gathered.

**New logging:**
- `FLOW_SKIP_RF_CANDIDATE` — logged when a red flag candidate target is skipped (retry limit exceeded).
- `FLOW_RF_CANDIDATES_EXHAUSTED` — logged when all candidates are skipped.

---

## Data Flow Summary

```
Patient message
  → fact_extractor (LLM extraction)
    → validate_facts
      ├── Schema match + type OK → schema_facts → information_gathered
      ├── Unknown key, non-placeholder → observations → clinical_observations
      └── Placeholder / type mismatch → dropped (logged)

clinical_observations used by:
  1. response_generator → acknowledge in doctor response
  2. summarizer → include in final summary
  3. safety_node → LLM escalation check for urgent signals

Red flag evaluation:
  - Deterministic rules check information_gathered (schema facts only)
  - LLM safety backup checks clinical_observations for unexpected escalation signals
  - Candidate red flags have retry/skip limits to prevent infinite loops
```

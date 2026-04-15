from __future__ import annotations
 
import json
import logging
from typing import Any, Awaitable, Callable
 
from backend.config import settings
from backend.context.context_models import ContextObject, InformationItem, Signal
from backend.context.llm_client import LLMClient, LLMError
from backend.domains.models import DomainProfile
from backend.models.utterance import Utterance
from backend.suggestions.suggestion_models import SuggestionOutput
 
logger = logging.getLogger(__name__)
 
ContextCallback = Callable[[ContextObject], Awaitable[None]]
SuggestionCallback = Callable[[SuggestionOutput], Awaitable[None]]
 
WINDOW_SIZE = settings.context_window_size
 
# ---------------------------------------------------------------------------
# Prompt templates — context-only mode (fallback)
# ---------------------------------------------------------------------------
 
_CONTEXT_ONLY_FIRST_PROMPT = """\
Below is the conversation transcript so far.
Analyze the conversation and return a context object as a JSON object.
 
## Transcript
{transcript}
 
## Instructions
Return a JSON object with these fields:
- "core_topic" (string): the main subject/complaint/issue being discussed
- "information_gathered" (array of {{"key": string, "value": string, "source_utt": string}}): \
key facts extracted from the responder's answers. "source_utt" is the utterance id.
- "gaps" (array of strings): important areas from the domain framework that have NOT yet been \
adequately covered. Use the domain's gap categories as a guide. Only list gaps that are still open.
- "signals" (array of {{"type": string, "detail": string, "source_utt": string}}): \
notable signals — type must be one of "red_flag", "contradiction", "vague", "emotional"
 
Respond ONLY with valid JSON, no markdown fences or extra text.
"""
 
_CONTEXT_ONLY_UPDATE_PROMPT = """\
Below is the conversation transcript so far, followed by the previous context analysis.
Analyze the conversation and return an UPDATED context object as a JSON object.
 
## Transcript
{transcript}
 
## Previous context
{previous_context}
 
## Instructions
Return a JSON object with ONLY these fields (do NOT include core_topic):
- "information_gathered" (array of {{"key": string, "value": string, "source_utt": string}}): \
key facts extracted from the responder's answers. "source_utt" is the utterance id.
- "gaps" (array of strings): important areas from the domain framework that have NOT yet been \
adequately covered. Use the domain's gap categories as a guide. Only list gaps that are still open.
- "signals" (array of {{"type": string, "detail": string, "source_utt": string}}): \
notable signals — type must be one of "red_flag", "contradiction", "vague", "emotional"
 
Respond ONLY with valid JSON, no markdown fences or extra text.
"""
 
# ---------------------------------------------------------------------------
# Prompt templates — combined mode (context + suggestions in one call)
# ---------------------------------------------------------------------------
 
_COMBINED_FIRST_PROMPT = """\
Below is the conversation transcript so far.
Analyze the conversation and return BOTH a context analysis AND suggested next questions.
 
## Transcript
{transcript}
 
## Questions Already Asked by the Interviewer
{questions_asked}
 
## Instructions
Return a JSON object with TWO top-level keys: "context" and "suggestions".
 
"context" must contain:
- "core_topic" (string): the main subject/complaint/issue being discussed
- "information_gathered" (array of {{"key": string, "value": string, "source_utt": string}}): \
key facts extracted from the responder's answers. "source_utt" is the utterance id.
- "gaps" (array of strings): important areas from the domain framework that have NOT yet been \
adequately covered. Use the domain's gap categories as a guide. Only list gaps that are still open.
- "signals" (array of {{"type": string, "detail": string, "source_utt": string}}): \
notable signals — type must be one of "red_flag", "contradiction", "vague", "emotional"
 
"suggestions" must be an array of up to {max_suggestions} objects, each with:
- "priority" ("high" | "medium" | "low"): ranked per the domain priority rules
- "question" (string): a natural question the interviewer should ask next
- "rationale" (string): one sentence explaining why this question matters now
 
Suggestion rules:
- NEVER suggest a question already asked (see "Questions Already Asked" above)
- Rank by domain priority rules: {priority_rules}
- Phrase questions naturally
 
Respond ONLY with valid JSON, no markdown fences or extra text.
"""
 
_COMBINED_UPDATE_PROMPT = """\
Below is the conversation transcript so far, followed by the previous context analysis.
Analyze the conversation and return BOTH an updated context AND suggested next questions.
 
## Transcript
{transcript}
 
## Previous context
{previous_context}
 
## Questions Already Asked by the Interviewer
{questions_asked}
 
## Instructions
Return a JSON object with TWO top-level keys: "context" and "suggestions".
 
"context" must contain (do NOT include core_topic):
- "information_gathered" (array of {{"key": string, "value": string, "source_utt": string}}): \
key facts extracted from the responder's answers. "source_utt" is the utterance id.
- "gaps" (array of strings): important areas from the domain framework that have NOT yet been \
adequately covered. Use the domain's gap categories as a guide. Only list gaps that are still open.
- "signals" (array of {{"type": string, "detail": string, "source_utt": string}}): \
notable signals — type must be one of "red_flag", "contradiction", "vague", "emotional"
 
"suggestions" must be an array of up to {max_suggestions} objects, each with:
- "priority" ("high" | "medium" | "low"): ranked per the domain priority rules
- "question" (string): a natural question the interviewer should ask next
- "rationale" (string): one sentence explaining why this question matters now
 
Suggestion rules:
- NEVER suggest a question already asked (see "Questions Already Asked" above)
- Rank by domain priority rules: {priority_rules}
- Phrase questions naturally
 
Respond ONLY with valid JSON, no markdown fences or extra text.
"""
 
# ---------------------------------------------------------------------------
# Prompt templates — chat mode (context + doctor_response + suggestions)
# ---------------------------------------------------------------------------
 
_CHAT_FIRST_PROMPT = """\
You are conducting a live medical consultation. Below is the conversation so far.
 
## Transcript
{transcript}
 
## Domain gap categories (from the framework)
{gap_categories}
 
## Instructions
Carefully analyze every patient utterance. Then return a JSON object with TWO keys: \
"context" and "doctor_response".
 
### "context" (object)
- "core_topic" (string): the primary symptom, complaint, or reason for the visit.
- "information_gathered" (array of {{"key": string, "value": string, "source_utt": string}}): \
concrete facts the patient has provided. Each key should map to a domain category when possible \
(e.g. "Site", "Onset"). "source_utt" is the utterance id that provided this info. \
Be thorough — extract EVERY piece of clinical information the patient mentions. \
CRITICAL NEGATIVE EXTRACTION: If the patient says "no", "none", or denies a symptom (e.g. no fever), you MUST extract this as a gathered fact with value "Denied" so it is removed from gaps.
- "gaps" (array of strings): domain framework categories that are BOTH clinically relevant \
for this case AND have NOT yet been covered. Only list gaps still open — do NOT include \
categories irrelevant to this presentation. NEVER include categories already in \
information_gathered.
- "active_categories" (array of strings): Tier 1 categories plus relevant Tier 2 categories \
based on symptoms described.
- "signals" (array of {{"type": string, "detail": string, "source_utt": string}}): \
notable clinical signals. Types: "red_flag", "contradiction", "vague", "emotional". \
Be aggressive — better to over-flag than miss something critical.
- "conversation_phase" (string): "gathering" while gaps remain. "summary" when all gaps covered.
 
### "doctor_response" (string)
Your next reply as the doctor. Rules:
1. Ask TWO focused questions targeting DIFFERENT gap categories. Combine them naturally \
(e.g. "Have you noticed any rash? Also, have you traveled recently?"). \
If only one gap remains, ask just one. If red flags exist, one question MUST address the red flag.
2. If a previous answer was flagged as "vague", ask for clarification BEFORE moving on.
3. ONLY ask about categories in the "gaps" array. Topics in "information_gathered" are DONE.
4. If the patient says "no"/"nothing"/"not really" → accept it, move on.
 
BANNED OPENINGS (never use): "I understand", "I see that", "I note that", \
"Thank you for sharing", "Based on what you've told me"
GOOD OPENINGS (vary these): "That sounds tough.", "Got it.", "Okay.", "Right.", \
"That's helpful to know.", or jump straight to the question with no preamble.
 
Respond ONLY with valid JSON, no markdown fences or extra text.
"""
 
_CHAT_UPDATE_PROMPT = """\
You are conducting a live medical consultation. Below is the conversation so far, \
along with the current analysis state.
 
## Transcript
{transcript}
 
## Current context (what you know so far)
{current_context}
 
## Domain gap categories (from the framework)
{gap_categories}
 
## Instructions
The patient has just responded. Analyze their latest message against the current context above. \
Update the context and produce your next doctor response.
 
Return a JSON object with TWO keys: "context" and "doctor_response".
 
### "context" (object — do NOT include core_topic, it is already set)
- "information_gathered" (array of {{"key": string, "value": string, "source_utt": string}}): \
ALL facts gathered so far — carry forward everything from the current context, plus \
add NEW information from the latest patient message. Be thorough. \
CRITICAL NEGATIVE EXTRACTION: If the patient says "no", "none", or denies a symptom (e.g. no fever), you MUST extract this as a gathered fact with value "Denied" so it is removed from gaps.
- "gaps" (array of strings): categories in active_categories that still have no clear answer. \
Remove any gap now covered. NEVER list categories already in information_gathered.
- "active_categories" (array of strings): clinically relevant gap categories. Carry forward \
and update if new information changes relevance.
- "conversation_phase" (string): "summary" if ALL gaps covered, otherwise "gathering".
- "signals" (array of {{"type": string, "detail": string, "source_utt": string}}): \
ALL signals — carry forward previous ones AND add new ones. Types: "red_flag", \
"contradiction", "vague", "emotional". Be aggressive — better to over-flag than miss.
 
### "doctor_response" (string)
Your next reply as the doctor. Rules:
1. Ask TWO focused questions targeting DIFFERENT gap categories. Combine them naturally \
(e.g. "Have you noticed any rash? Also, have you traveled recently?"). \
If only one gap remains, ask just one. If red flags exist, one question MUST address the red flag.
2. If a previous answer was flagged as "vague", ask for clarification BEFORE moving on.
3. ONLY ask about categories in the "gaps" array. Topics in "information_gathered" are DONE.
4. If the patient says "no"/"nothing"/"not really" → accept it, move on.
5. If ALL gaps are covered, set conversation_phase to "summary".
 
BANNED OPENINGS (never use): "I understand", "I see that", "I note that", \
"Thank you for sharing", "Based on what you've told me"
GOOD OPENINGS (vary these): "That sounds tough.", "Got it.", "Okay.", "Right.", \
"That's helpful to know.", or jump straight to the question with no preamble.
 
Respond ONLY with valid JSON, no markdown fences or extra text.
"""
 
_CHAT_SUMMARY_PROMPT = """\
You are concluding a live medical consultation. Below is the full conversation \
and the final analysis state.
 
## Transcript
{transcript}
 
## Final context (all information gathered)
{current_context}
 
## Instructions
All relevant clinical history has been gathered. Produce a comprehensive \
summary and clinical assessment.
 
Return a JSON object with TWO keys: "context" and "doctor_response".
 
### "context" (object — do NOT include core_topic, it is already set)
- "information_gathered": carry forward ALL existing information unchanged.
- "gaps": empty array (all gaps are resolved).
- "active_categories": carry forward from current context unchanged.
- "conversation_phase": "summary"
- "signals": carry forward ALL existing signals unchanged.
 
### "doctor_response" (string)
Produce a warm, professional closing message that includes:
1. A brief, clean summary of the key findings (presenting complaint, relevant history, \
key positives and negatives)
2. A differential diagnosis list ordered from most likely to least likely (use "possible" / \
"could be" — NEVER diagnose definitively)
3. Suggested investigations (blood tests, imaging, specialist referrals) if appropriate
4. Red flags to watch for at home and when to seek emergency care
5. A safety disclaimer: "This is an AI-assisted assessment and does not replace \
professional medical advice. Please consult a qualified healthcare provider."
 
Use clear, empathetic language. Format with line breaks for readability.
 
Respond ONLY with valid JSON, no markdown fences or extra text.
"""
 
_SUMMARY_SYSTEM_PROMPT = (
    "You are a factual conversation summariser. "
    "Condense the dialogue below into a concise paragraph (max 200 words). "
    "Preserve all key facts, names, dates, numbers, and decisions. "
    "Do not add opinions or analysis."
)
 
_RED_FLAG_CHECK_PROMPT = """\
You are a medical safety checker. Review the patient symptoms below and check \
for dangerous combinations.
 
## Symptoms collected so far
{symptoms}
 
## Red flag combinations to check
- Fever + neck stiffness/photophobia -> meningitis
- Fever >103F + headache -> needs meningitis screening (ask about neck stiffness)
- Fever + rash + bleeding -> dengue/meningococcaemia
- Chest pain + arm/jaw radiation + sweating -> acute MI
- Sudden worst-ever headache -> subarachnoid haemorrhage
- Abdominal pain + rigidity -> surgical abdomen
- SOB + pleuritic pain + leg swelling -> PE
- Syncope + exertional symptoms -> cardiac
- Unilateral weakness + speech difficulty -> stroke
 
Return a JSON object:
{{
  "red_flags_found": [{{"flag": "description", "urgency": "high|medium",
                        "follow_up_question": "question to ask patient"}}],
  "warning_message": "message to append to doctor response, or empty string"
}}
Respond ONLY with valid JSON.
"""
 
_BANNED_PREFIXES = [
    "i understand",
    "i see that",
    "i note that",
    "thank you for sharing",
    "based on what you've told me",
    "based on what you're telling me",
]
 
 
def _estimate_tokens(text: str) -> int:
    """Rough token estimate: 1 token ~ 4 characters."""
    return len(text) // 4
 
 
class ContextEngine:
    """Analyzes conversation context and generates suggestions via LLM.
 
    Supports two modes controlled by ``settings.suggestion_combined_mode``:
      - **Combined**: single LLM call returns both context + suggestions
      - **Separate**: context-only call, suggestions handled by SuggestionEngine
 
    Includes three-tier prompt optimisation:
      - FULL:    all utterances verbatim  (< 4K tokens)
      - WINDOW:  last N utterances + previous context as implicit summary (4K-8K)
      - SUMMARY: LLM-generated summary of old turns + last N utterances (> 8K)
    """
 
    def __init__(
        self,
        domain_profile: DomainProfile,
        llm_client: LLMClient,
        session_id: str,
        mode: str = "simulation",
    ) -> None:
        self._profile = domain_profile
        self._llm = llm_client
        self._session_id = session_id
        self._mode = mode
        self._utterances: list[Utterance] = []
        self._questions: list[str] = []
        self._context: ContextObject = ContextObject(session_id=session_id)
        self._subscribers: list[ContextCallback] = []
        self._suggestion_subscribers: list[SuggestionCallback] = []
        self._analyzing = False
 
        self._responder_count: int = 0
        self._exchange_count: int = 0
        self._resolved_gaps: set[str] = set()
 
        self._cached_summary: str = ""
        self._summary_utt_count: int = 0
 
        # Lazy-loaded fallback suggestion engine
        self._suggestion_engine: Any = None
 
        logger.info(
            "ContextEngine created: session='%s' domain='%s' provider='%s' "
            "mode='%s' analysis_interval=%d window=%d combined_mode=%s",
            session_id,
            domain_profile.id,
            llm_client.provider,
            mode,
            settings.context_analysis_interval,
            WINDOW_SIZE,
            settings.suggestion_combined_mode,
        )
 
    @property
    def current_context(self) -> ContextObject:
        return self._context
 
    @property
    def latest_suggestions(self) -> SuggestionOutput | None:
        if self._suggestion_engine is not None:
            return self._suggestion_engine.latest
        return None
 
    def subscribe(self, callback: ContextCallback) -> None:
        self._subscribers.append(callback)
 
    def subscribe_suggestions(self, callback: SuggestionCallback) -> None:
        self._suggestion_subscribers.append(callback)
 
    # ------------------------------------------------------------------
    # Utterance ingestion + interval gating
    # ------------------------------------------------------------------
 
    async def on_utterance(self, utt: Utterance) -> None:
        """Called on every committed (non-preview) utterance."""
        if utt.is_preview:
            return
 
        self._utterances.append(utt)
 
        if utt.speaker == "interviewer":
            self._questions.append(utt.text)
 
        if utt.speaker == "responder":
            self._responder_count += 1
            interval = settings.context_analysis_interval
            if self._responder_count == 1 or self._responder_count % interval == 0:
                await self._analyze()
            else:
                logger.debug(
                    "Skipping analysis (responder turn %d, next at %d)",
                    self._responder_count,
                    self._responder_count + (interval - self._responder_count % interval),
                )
 
    # ------------------------------------------------------------------
    # Core analysis
    # ------------------------------------------------------------------
 
    async def _analyze(self) -> None:
        if self._analyzing:
            logger.debug("Skipping overlapping analysis — previous call still in-flight")
            return
        self._analyzing = True
        try:
            system_prompt = self._build_system_prompt()
 
            if settings.suggestion_combined_mode:
                await self._analyze_combined(system_prompt)
            else:
                await self._analyze_context_only(system_prompt)
 
        except LLMError as exc:
            logger.error("LLM analysis failed (retaining last context): %s", exc)
        except Exception:
            logger.exception("Unexpected error during context analysis")
        finally:
            self._analyzing = False
 
    async def _analyze_context_only(self, system_prompt: str) -> None:
        """Original two-call path: context only, suggestions via fallback engine."""
        user_prompt = await self._build_user_prompt(combined=False)
 
        raw: dict[str, Any] = await self._llm.analyze_json(
            system_prompt, user_prompt,
            max_tokens=settings.llm_max_output_tokens,
        )
 
        new_ctx = self._parse_and_merge(raw)
        self._context = new_ctx
        self._log_context_update(new_ctx)
        await self._emit_context(new_ctx)
 
        await self._generate_suggestions_fallback(new_ctx)
 
    async def _analyze_combined(self, system_prompt: str) -> None:
        """Single-call path: context + suggestions in one LLM response."""
        user_prompt = await self._build_user_prompt(combined=True)
 
        raw: dict[str, Any] = await self._llm.analyze_json(
            system_prompt, user_prompt,
            max_tokens=settings.llm_max_output_tokens,
        )
 
        # The LLM should return { "context": {...}, "suggestions": [...] }
        # but may return flat context fields if it ignores the wrapper
        context_raw = raw.get("context", None)
        suggestions_raw = raw.get("suggestions", None)
 
        if context_raw is not None and isinstance(context_raw, dict):
            new_ctx = self._parse_and_merge(context_raw)
        else:
            new_ctx = self._parse_and_merge(raw)
 
        self._context = new_ctx
        self._log_context_update(new_ctx)
        await self._emit_context(new_ctx)
 
        if suggestions_raw and isinstance(suggestions_raw, list):
            engine = self._get_suggestion_engine()
            context_summary = ""
            if context_raw and isinstance(context_raw, dict):
                context_summary = str(context_raw.get("core_topic", new_ctx.core_topic))
            output = engine.parse_from_combined(
                suggestions_raw, new_ctx, context_summary=context_summary,
            )
            logger.info(
                "Combined suggestions parsed: %d suggestions",
                len(output.suggestions),
            )
            await self._emit_suggestions(output)
        else:
            logger.warning("Combined call missing suggestions — falling back to standalone call")
            await self._generate_suggestions_fallback(new_ctx)
 
    async def _generate_suggestions_fallback(self, context: ContextObject) -> None:
        """Generate suggestions via a separate SuggestionEngine LLM call."""
        try:
            engine = self._get_suggestion_engine()
            output = await engine.generate(context)
            logger.info(
                "Fallback suggestions generated: %d suggestions",
                len(output.suggestions),
            )
            await self._emit_suggestions(output)
        except LLMError as exc:
            logger.error("Fallback suggestion generation failed: %s", exc)
        except Exception:
            logger.exception("Unexpected error in fallback suggestion generation")
 
    # ------------------------------------------------------------------
    # Chat mode — single-call context + doctor response + suggestions
    # ------------------------------------------------------------------
 
    async def chat_reply(self, patient_utt: Utterance) -> str:
        """Process a patient message and return the doctor's response.
 
        Flow: LLM call → strip banned openings → dedup check (max 1 retry)
        → parse/merge context → red flag check every 2 exchanges → emit.
        """
        self._utterances.append(patient_utt)
        self._exchange_count += 1
        logger.debug(
            "chat_reply called: session='%s' patient_text_len=%d "
            "total_utterances=%d exchange=%d",
            self._session_id, len(patient_utt.text),
            len(self._utterances), self._exchange_count,
        )
 
        use_summary = self._should_use_summary_prompt()
 
        system_prompt = self._build_system_prompt(chat=True)
        user_prompt = await self._build_user_prompt(
            combined=True, chat=True, summary=use_summary,
        )
 
        raw: dict[str, Any] = await self._llm.analyze_json(
            system_prompt, user_prompt,
            max_tokens=settings.llm_max_output_tokens,
        )
 
        context_raw = raw.get("context", None)
        doctor_response = raw.get("doctor_response", "")
 
        if not doctor_response:
            doctor_response = "Could you tell me more about that?"
            logger.warning("Chat LLM call returned empty doctor_response — using fallback")
 
        doctor_response = self._strip_banned_openings(doctor_response)
 
        if context_raw is not None and isinstance(context_raw, dict):
            new_ctx = self._parse_and_merge(context_raw)
        else:
            logger.warning("Chat LLM response missing 'context' key — parsing from top-level object")
            new_ctx = self._parse_and_merge(raw)
 
        self._context = new_ctx
        self._log_context_update(new_ctx)
        await self._emit_context(new_ctx)
 
        if self._exchange_count % 2 == 0:
            try:
                rf_signals, warning = await self._check_red_flags()
                if rf_signals:
                    self._context.signals.extend(rf_signals)
                    await self._emit_context(self._context)
                if warning:
                    doctor_response += "\n\n" + warning
            except LLMError:
                logger.error("Red flag check failed (non-critical)")
            except Exception:
                logger.exception("Unexpected error in red flag check")
 
        self._questions.append(doctor_response)
 
        logger.info(
            "Chat reply generated: session='%s' response_len=%d phase='%s'",
            self._session_id, len(doctor_response), new_ctx.conversation_phase,
        )
        return doctor_response
 
    # ------------------------------------------------------------------
    # Post-processing helpers
    # ------------------------------------------------------------------
 
    @staticmethod
    def _strip_banned_openings(response: str) -> str:
        """Remove robotic 'I understand...' openings."""
        for prefix in _BANNED_PREFIXES:
            if response.lower().startswith(prefix):
                for i, ch in enumerate(response):
                    if ch in ".!?" and i > 10:
                        response = response[i + 1:].strip()
                        break
        return response
 
    async def _check_red_flags(self) -> tuple[list[Signal], str]:
        """Lightweight LLM call checking accumulated symptoms for red flags."""
        symptoms = {
            item.key: item.value
            for item in self._context.information_gathered
        }
        prompt = _RED_FLAG_CHECK_PROMPT.format(
            symptoms=json.dumps(symptoms, indent=2),
        )
        system = (
            "You are a medical safety checker. Be thorough — "
            "flag anything concerning."
        )
        raw = await self._llm.analyze_json(system, prompt, max_tokens=1024)
 
        signals: list[Signal] = []
        for rf in raw.get("red_flags_found", []):
            signals.append(Signal(
                type="red_flag",
                detail=str(rf.get("flag", "")),
                source_utt="system",
            ))
 
        warning = str(raw.get("warning_message", ""))
        return signals, warning
 
    def _should_use_summary_prompt(self) -> bool:
        """Check if we should switch to the summary prompt."""
        if self._context.conversation_phase == "summary":
            return True
        if (
            self._context.active_categories
            and self._context.gaps == []
            and self._context.turn_count > 0
        ):
            return True
        return False
 
    def _get_suggestion_engine(self) -> Any:
        if self._suggestion_engine is None:
            from backend.suggestions.suggestion_engine import SuggestionEngine
            self._suggestion_engine = SuggestionEngine(self._profile, self._llm)
        return self._suggestion_engine
 
    def _log_context_update(self, ctx: ContextObject) -> None:
        logger.info(
            "Context updated: session='%s' topic='%s' info_items=%d gaps=%d signals=%d",
            self._session_id,
            ctx.core_topic[:50] if ctx.core_topic else "(none)",
            len(ctx.information_gathered),
            len(ctx.gaps),
            len(ctx.signals),
        )
 
    # ------------------------------------------------------------------
    # Prompt construction (three-tier)
    # ------------------------------------------------------------------
 
    def _build_system_prompt(self, *, chat: bool = False) -> str:
        if chat:
            hard_rules = (
                "=== HARD RULES (you MUST follow these) ===\n"
                "1. NEVER start your response with \"I understand\", \"I see that\", "
                "\"I note that\", \"Thank you for sharing\", or \"Based on what you've told me\". "
                "Vary your openings.\n"
                "2. Ask exactly TWO focused questions per turn, targeting DIFFERENT gap categories. "
                "Combine them naturally (e.g. \"Have you noticed any rash? Also, have you traveled recently?\"). "
                "If only one gap remains, ask just one.\n"
                "3. ONLY ask about categories listed in the \"gaps\" array. Topics already in "
                "\"information_gathered\" are DONE — NEVER revisit them.\n"
                "4. If the patient says \"no\" / \"nothing\" / \"not really\" → accept it and move on. "
                "Mark that category as covered.\n"
                "5. Use everyday language ONLY. Say \"blood test\" not \"CBC\". "
                "Say \"spread\" not \"radiate\". No medical jargon.\n"
                "6. Keep responses to 2-4 sentences maximum.\n"
                "7. Do NOT restate the patient's history. Acknowledge ONLY their latest answer briefly.\n"
                "8. If a red flag is detected, include a brief warning about seeking urgent care.\n"
                "=== END HARD RULES ===\n\n"
            )
 
            framework = (
                f"{self._profile.system_prompt_fragment}\n\n"
                f"Gap categories for this domain: {json.dumps(self._profile.gap_categories)}\n"
                f"Signal types to watch for: {json.dumps(self._profile.signal_types)}\n"
            )
 
            priority_section = "\nPriority for question selection:\n"
            for i, rule in enumerate(self._profile.priority_rules, 1):
                priority_section += f"  {i}. {rule}\n"
 
            recap = (
                "\n=== RULES RECAP ===\n"
                "REMEMBER: No \"I understand\" openings. TWO questions per turn. "
                "ONLY ask about gaps, NEVER about information_gathered topics. "
                "Accept \"no\" answers. No jargon. No history recaps.\n"
            )
 
            return hard_rules + framework + priority_section + recap
 
        base = (
            "You are an expert conversation analyst specializing in "
            f"the {self._profile.name} domain.\n\n"
            f"{self._profile.system_prompt_fragment}\n\n"
            f"Gap categories for this domain: {json.dumps(self._profile.gap_categories)}\n"
            f"Signal types to watch for: {json.dumps(self._profile.signal_types)}\n"
        )
        if settings.suggestion_combined_mode:
            base += (
                f"\nPriority rules for suggestions: "
                f"{json.dumps(self._profile.priority_rules)}\n"
            )
        return base
 
    async def _build_user_prompt(
        self, *, combined: bool, chat: bool = False, summary: bool = False,
    ) -> str:
        is_first_run = self._context.turn_count == 0
 
        all_lines = [
            f"[{u.id}] {u.speaker.capitalize()}: {u.text}" for u in self._utterances
        ]
        full_text = "\n".join(all_lines)
        est_tokens = _estimate_tokens(full_text)
        total_utts = len(self._utterances)
 
        if chat:
            if summary:
                template = _CHAT_SUMMARY_PROMPT
            elif is_first_run:
                template = _CHAT_FIRST_PROMPT
            else:
                template = _CHAT_UPDATE_PROMPT
        elif combined:
            template = _COMBINED_FIRST_PROMPT if is_first_run else _COMBINED_UPDATE_PROMPT
        else:
            template = _CONTEXT_ONLY_FIRST_PROMPT if is_first_run else _CONTEXT_ONLY_UPDATE_PROMPT
 
        prev_ctx = json.dumps(self._context.model_dump(), indent=2)
        questions_json = json.dumps(self._questions)
        priority_rules = ", ".join(self._profile.priority_rules) if self._profile.priority_rules else "general relevance"
 
        gap_categories_json = json.dumps(self._profile.gap_categories)
 
        def _format(transcript: str) -> str:
            kwargs: dict[str, Any] = {"transcript": transcript}
            if chat:
                kwargs["gap_categories"] = gap_categories_json
                if not is_first_run or summary:
                    kwargs["current_context"] = prev_ctx
            else:
                if not is_first_run:
                    kwargs["previous_context"] = prev_ctx
                if combined:
                    kwargs["questions_asked"] = questions_json
                    kwargs["max_suggestions"] = settings.suggestion_max_count
                    kwargs["priority_rules"] = priority_rules
            return template.format(**kwargs)
 
        # --- Tier 1: FULL (below 4K tokens) ---
        if est_tokens < settings.context_token_threshold_full:
            logger.info(
                "Prompt mode: FULL  (est. %d tokens, %d utterances, first_run=%s, combined=%s)",
                est_tokens, total_utts, is_first_run, combined,
            )
            return _format(full_text)
 
        # --- Tier 2: WINDOW (4K-8K tokens) ---
        recent_lines = all_lines[-WINDOW_SIZE:]
        recent_text = "\n".join(recent_lines)
        omitted = total_utts - len(recent_lines)
 
        if est_tokens < settings.context_token_threshold_summary:
            logger.info(
                "Prompt mode: WINDOW  (est. %d tokens, %d utterances, "
                "last %d verbatim, %d omitted, first_run=%s, combined=%s)",
                est_tokens, total_utts, len(recent_lines), omitted, is_first_run, combined,
            )
            transcript_section = (
                f"[{omitted} earlier utterances omitted — their information is captured "
                f"in the Previous context section below]\n\n"
                f"{recent_text}"
            )
            return _format(transcript_section)
 
        # --- Tier 3: SUMMARY (above 8K tokens) ---
        await self._maybe_refresh_summary()
        logger.info(
            "Prompt mode: SUMMARY  (est. %d tokens, %d utterances, "
            "summarised up to utt %d, last %d verbatim, first_run=%s, combined=%s)",
            est_tokens, total_utts, self._summary_utt_count, len(recent_lines),
            is_first_run, combined,
        )
        transcript_section = (
            f"## Summary of earlier conversation (utterances 1-{self._summary_utt_count})\n"
            f"{self._cached_summary}\n\n"
            f"## Recent utterances (verbatim)\n"
            f"{recent_text}"
        )
        return _format(transcript_section)
 
    # ------------------------------------------------------------------
    # Summarisation
    # ------------------------------------------------------------------
 
    async def _maybe_refresh_summary(self) -> None:
        """Re-summarise old turns if the cache is stale (>= WINDOW_SIZE new utterances since last)."""
        old_boundary = len(self._utterances) - WINDOW_SIZE
        if old_boundary <= 0:
            return
        if old_boundary <= self._summary_utt_count + WINDOW_SIZE and self._cached_summary:
            return
 
        old_utts = self._utterances[:old_boundary]
        dialogue = "\n".join(
            f"{u.speaker.capitalize()}: {u.text}" for u in old_utts
        )
        logger.info(
            "Summarising %d old utterances (previous cache covered %d)",
            len(old_utts), self._summary_utt_count,
        )
        try:
            self._cached_summary = await self._llm.analyze(
                _SUMMARY_SYSTEM_PROMPT,
                dialogue,
                max_tokens=512,
            )
            self._summary_utt_count = len(old_utts)
            logger.info(
                "Summary refreshed: %d chars covering %d utterances",
                len(self._cached_summary), self._summary_utt_count,
            )
        except LLMError as exc:
            logger.error("Summary generation failed (keeping stale cache): %s", exc)
 
    # ------------------------------------------------------------------
    # Response parsing & merging
    # ------------------------------------------------------------------
 
    def _parse_and_merge(self, raw: dict[str, Any]) -> ContextObject:
        info_items: list[InformationItem] = []
        for item in raw.get("information_gathered", []):
            if isinstance(item, dict):
                info_items.append(InformationItem(
                    key=str(item.get("key", "")),
                    value=str(item.get("value", "")),
                    source_utt=str(item.get("source_utt", "")),
                ))
 
        existing_keys = {i.key for i in self._context.information_gathered}
        merged_info = list(self._context.information_gathered)
        for item in info_items:
            if item.key not in existing_keys:
                merged_info.append(item)
                existing_keys.add(item.key)
            else:
                for i, existing in enumerate(merged_info):
                    if existing.key == item.key:
                        merged_info[i] = item
                        break
 
        signals: list[Signal] = []
        for sig in raw.get("signals", []):
            if isinstance(sig, dict):
                signals.append(Signal(
                    type=str(sig.get("type", "vague")),
                    detail=str(sig.get("detail", "")),
                    source_utt=str(sig.get("source_utt", "")),
                ))
 
        new_gaps_raw: list[str] = raw.get("gaps", self._context.gaps)
        old_gaps = set(self._context.gaps)
        newly_resolved = old_gaps - set(new_gaps_raw)
        if newly_resolved:
            self._resolved_gaps.update(newly_resolved)
            logger.debug("Gaps newly resolved (locked): %s", newly_resolved)
        merged_gaps = [g for g in new_gaps_raw if g not in self._resolved_gaps]
 
        core_topic = self._context.core_topic
        if "core_topic" in raw and raw["core_topic"]:
            core_topic = str(raw["core_topic"])
 
        active_categories: list[str] = raw.get(
            "active_categories", self._context.active_categories,
        )
        if not isinstance(active_categories, list):
            active_categories = self._context.active_categories
 
        conversation_phase: str = raw.get(
            "conversation_phase", self._context.conversation_phase,
        )
        if conversation_phase not in ("gathering", "summary"):
            conversation_phase = self._context.conversation_phase
 
        return ContextObject(
            session_id=self._session_id,
            core_topic=core_topic,
            information_gathered=merged_info,
            questions_asked=self._questions[:],
            gaps=merged_gaps,
            signals=signals if signals else self._context.signals,
            turn_count=len(self._utterances),
            active_categories=active_categories,
            conversation_phase=conversation_phase,
        )
 
    # ------------------------------------------------------------------
    # Event emission
    # ------------------------------------------------------------------
 
    async def _emit_context(self, ctx: ContextObject) -> None:
        for cb in self._subscribers:
            try:
                await cb(ctx)
            except Exception:
                logger.exception("Error in context subscriber callback")
 
    async def _emit_suggestions(self, output: SuggestionOutput) -> None:
        for cb in self._suggestion_subscribers:
            try:
                await cb(output)
            except Exception:
                logger.exception("Error in suggestion subscriber callback")
 
    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------
 
    def reset(self) -> None:
        """Clear all state for a new session."""
        self._utterances.clear()
        self._questions.clear()
        self._context = ContextObject(session_id=self._session_id)
        self._analyzing = False
        self._responder_count = 0
        self._exchange_count = 0
        self._resolved_gaps.clear()
        self._cached_summary = ""
        self._summary_utt_count = 0
        if self._suggestion_engine is not None:
            self._suggestion_engine.reset()
        logger.info("ContextEngine reset: session='%s'", self._session_id)
 
 
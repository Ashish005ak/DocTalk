from __future__ import annotations

import logging

from backend.clinical.readiness import is_ready_to_land
from backend.clinical.red_flag_guard import RedFlagGuard
from backend.domain.models import DomainProfile
from backend.llm.client import AgentLLMClient
from backend.models.move import ConversationMove
from backend.models.state import ConsultationEnding, MoveType, PatientIntent, Phase

logger = logging.getLogger(__name__)

_ZERO_FACT_WINDOW = 3
_MAX_EMERGENCY_QA_TURNS = 1


async def flow_control_node(
    state: dict,
    *,
    client: AgentLLMClient,
    domain: DomainProfile,
) -> dict:
    """Decide the next conversation move based on red flags, phase, intent, and LLM-chosen question."""
    phase = state.get("phase", Phase.EXPLORING)
    intent_str = state.get("intake_intent", PatientIntent.ANSWERING.value)
    info_gathered = state.get("information_gathered", {})
    denied_symptoms = set(state.get("denied_symptoms", set()))
    confirmed_ids = set(state.get("confirmed_red_flag_ids", set()))
    snapshot = state.get("last_rf_check_fact_snapshot", {})
    remaining_gaps = list(state.get("remaining_gaps", []))
    pending_explanation = state.get("pending_explanation")
    unconfirmed = state.get("unconfirmed_facts", {})
    gap_ask_counts = dict(state.get("gap_ask_counts", {}))
    skipped_gaps = set(state.get("skipped_gaps", set()))
    new_volunteered = state.get("new_volunteered_keys", [])
    turn_count = state.get("turn_count", 0)
    consultation_ending = state.get("consultation_ending", ConsultationEnding.NONE)
    closing_turn_count = state.get("closing_turn_count", 0)
    summary_generated = state.get("summary_generated", False)

    max_gap_asks = domain.thresholds.max_gap_asks
    max_turns = domain.thresholds.max_turns

    remaining_gaps = [g for g in remaining_gaps if g not in skipped_gaps]

    logger.info(
        "FLOW_ENTRY  phase=%s  intent=%s  info_count=%d  gaps=%d  confirmed_rf=%d  ending=%s  closing_turn=%d",
        phase.value if hasattr(phase, "value") else phase,
        intent_str,
        len(info_gathered),
        len(remaining_gaps),
        len(confirmed_ids),
        consultation_ending.value if hasattr(consultation_ending, "value") else consultation_ending,
        closing_turn_count,
    )

    # ===================================================================
    # PRE-CHECK: Ending state handling (runs before any other logic)
    # ===================================================================

    if consultation_ending in (ConsultationEnding.LANDING, ConsultationEnding.EMERGENCY):
        guard = RedFlagGuard(domain)
        override_confirmed, _ = guard.check_with_candidates(
            info_gathered, denied_symptoms, confirmed_ids, snapshot,
        )
        new_rf_ids = {f.id for f in override_confirmed} - confirmed_ids
        if new_rf_ids and consultation_ending == ConsultationEnding.LANDING:
            logger.warning("FLOW_EMERGENCY_OVERRIDE  new_rf=%s  upgrading LANDING->EMERGENCY", new_rf_ids)
            consultation_ending = ConsultationEnding.EMERGENCY
            closing_turn_count = 0
            summary_generated = False

    if consultation_ending == ConsultationEnding.CLOSED:
        logger.info("FLOW_CLOSED  session already terminated")
        move = ConversationMove(type=MoveType.TERMINATE, reason="Session closed")
        return {"conversation_move": move}

    if consultation_ending in (ConsultationEnding.LANDING, ConsultationEnding.EMERGENCY):
        closing_turn_count += 1

        if not summary_generated:
            move_type = MoveType.URGENT_CLOSE if consultation_ending == ConsultationEnding.EMERGENCY else MoveType.SUMMARIZE
            logger.info("FLOW_LANDING_SUMMARY  ending=%s  move=%s", consultation_ending.value, move_type.value)
            return {
                "conversation_move": ConversationMove(type=move_type, reason="Generating closing summary"),
                "closing_turn_count": closing_turn_count,
                "consultation_ending": consultation_ending,
            }

        is_emergency = consultation_ending == ConsultationEnding.EMERGENCY
        qa_cap = _MAX_EMERGENCY_QA_TURNS if is_emergency else 2

        if intent_str == PatientIntent.TERMINATE.value or closing_turn_count > qa_cap:
            logger.info("FLOW_TERMINATE  intent=%s  closing_turn=%d  cap=%d", intent_str, closing_turn_count, qa_cap)
            return {
                "conversation_move": ConversationMove(type=MoveType.TERMINATE, reason="Patient done or Q&A cap reached"),
                "closing_turn_count": closing_turn_count,
                "consultation_ending": ConsultationEnding.CLOSED,
            }

        if intent_str in (PatientIntent.ASKING_EXPLANATION.value, PatientIntent.MIXED.value):
            logger.info("FLOW_LANDING_EXPLAIN  closing_turn=%d", closing_turn_count)
            return {
                "conversation_move": ConversationMove(type=MoveType.EXPLAIN, reason="Q&A during landing"),
                "closing_turn_count": closing_turn_count,
            }

        logger.info("FLOW_LANDING_GRACEFUL_EXIT  closing_turn=%d  intent=%s", closing_turn_count, intent_str)
        return {
            "conversation_move": ConversationMove(type=MoveType.TERMINATE, reason="Patient acknowledged summary"),
            "closing_turn_count": closing_turn_count,
            "consultation_ending": ConsultationEnding.CLOSED,
        }

    # ===================================================================
    # ENDING TRIGGERS (only when consultation_ending == NONE)
    # ===================================================================

    # --- TERMINATE intent: patient wants to end the conversation ---
    if intent_str == PatientIntent.TERMINATE.value:
        if is_ready_to_land(state, "fatigue"):
            logger.info("FLOW_TERMINATE_WITH_SUMMARY  intent=terminate  ending=LANDING")
            return {
                "conversation_move": ConversationMove(
                    type=MoveType.SUMMARIZE,
                    reason="Patient requested termination -- summarizing first",
                ),
                "consultation_ending": ConsultationEnding.LANDING,
                "closing_turn_count": 0,
                "remaining_gaps": [],
                "last_rf_check_fact_snapshot": dict(info_gathered),
                "watch_flags": dict(state.get("watch_flags", {})),
            }
        else:
            logger.info("FLOW_TERMINATE_EARLY  intent=terminate  no_summary")
            return {
                "conversation_move": ConversationMove(
                    type=MoveType.TERMINATE,
                    reason="Patient requested termination -- too early for summary",
                ),
                "consultation_ending": ConsultationEnding.CLOSED,
            }

    guard = RedFlagGuard(domain)
    watch_turns_limit = domain.thresholds.watch_turns_limit
    prev_watch = dict(state.get("watch_flags", {}))

    confirmed_flags, candidate_flags = guard.check_with_candidates(
        info_gathered, denied_symptoms, confirmed_ids, snapshot,
    )

    alert_flags, watch_statuses, _clear = guard.check_with_states(
        info_gathered=info_gathered,
        denied_symptoms=denied_symptoms,
        confirmed_red_flag_ids=confirmed_ids,
        current_turn=turn_count,
        prev_watch_flags=prev_watch,
    )

    timeout_promoted: list = []
    for ws in list(watch_statuses):
        since = ws.watch_since_turn
        if since is not None and (turn_count - since) >= watch_turns_limit:
            logger.info(
                "FLOW_WATCH_TIMEOUT  flag=%s  turns_in_watch=%d  promoting_to_alert",
                ws.rule.id, turn_count - since,
            )
            ws.state = "alert"
            alert_flags.append(ws)
            watch_statuses.remove(ws)
            timeout_promoted.append(ws.rule.id)

    for ws in watch_statuses:
        logger.info(
            "FLOW_WATCH_PASS  flag=%s  score=%d/%d  llm_drives",
            ws.rule.id, ws.score, ws.hard_threshold,
        )

    new_watch_flags: dict[str, dict] = {}
    for ws in watch_statuses:
        new_watch_flags[ws.rule.id] = {
            "score": ws.score,
            "since_turn": ws.watch_since_turn if ws.watch_since_turn is not None else turn_count,
            "missing_keys": ws.missing_keys,
        }

    new_confirmed_ids = set()
    for flag in confirmed_flags:
        new_confirmed_ids.add(flag.id)

    if confirmed_flags:
        logger.warning("FLOW_RED_FLAGS  confirmed=%s", [f.id for f in confirmed_flags])
    if alert_flags:
        logger.info("FLOW_RED_FLAGS  alert=%s", [a.rule.id for a in alert_flags])

    updated_snapshot = dict(info_gathered)

    # --- EMERGENCY trigger: first-time red flag confirmation ---
    if confirmed_flags:
        if is_ready_to_land(state, "emergency"):
            logger.warning("FLOW_EMERGENCY_TRIGGER  confirmed_rf=%s", [f.id for f in confirmed_flags])
            move = ConversationMove(
                type=MoveType.URGENT_CLOSE,
                red_flag_id=confirmed_flags[0].id,
                reason=confirmed_flags[0].message,
            )
            return {
                "conversation_move": move,
                "confirmed_red_flag_ids": new_confirmed_ids,
                "last_rf_check_fact_snapshot": updated_snapshot,
                "consultation_ending": ConsultationEnding.EMERGENCY,
                "closing_turn_count": 0,
                "watch_flags": new_watch_flags,
            }
        else:
            flag = confirmed_flags[0]
            move = ConversationMove(
                type=MoveType.RED_FLAG_FOLLOWUP,
                red_flag_id=flag.id,
                reason=flag.message,
            )
            logger.info("FLOW_MOVE  type=%s  red_flag=%s  (not ready to land)", move.type.value, flag.id)
            return {
                "conversation_move": move,
                "confirmed_red_flag_ids": new_confirmed_ids,
                "last_rf_check_fact_snapshot": updated_snapshot,
                "watch_flags": new_watch_flags,
            }

    # --- FATIGUE trigger ---
    _consecutive_zero = state.get("_consecutive_zero_fact_turns", 0)
    if turn_count >= max_turns or _consecutive_zero >= _ZERO_FACT_WINDOW:
        trigger = "fatigue"
        if is_ready_to_land(state, trigger):
            logger.info("FLOW_FATIGUE_TRIGGER  turn=%d  max=%d  zero_streak=%d", turn_count, max_turns, _consecutive_zero)
            move = ConversationMove(type=MoveType.SUMMARIZE, reason="Conversation fatigue — landing")
            return {
                "conversation_move": move,
                "last_rf_check_fact_snapshot": updated_snapshot,
                "consultation_ending": ConsultationEnding.LANDING,
                "closing_turn_count": 0,
                "watch_flags": new_watch_flags,
                "remaining_gaps": [],
            }
        else:
            logger.info("FLOW_FATIGUE_NOT_READY  turn=%d  emitting reorienting question", turn_count)
            move = ConversationMove(
                type=MoveType.QUESTION,
                target_gap="chief_complaint",
                reason="Reorienting — fatigue but not ready to land",
            )
            return {
                "conversation_move": move,
                "last_rf_check_fact_snapshot": updated_snapshot,
                "watch_flags": new_watch_flags,
            }

    # ===================================================================
    # NORMAL FLOW (unchanged from original)
    # ===================================================================

    # --- Alert-state red flags: override LLM and force targeted clarify ---
    if alert_flags:
        selected_status = None
        selected_target = None
        newly_skipped_rf: set[str] = set()

        for af in alert_flags:
            target = _find_missing_key_for_candidate(af.rule, info_gathered, denied_symptoms)
            if target is None:
                continue
            count = gap_ask_counts.get(target, 0)
            if count >= max_gap_asks:
                logger.info(
                    "FLOW_SKIP_RF_ALERT  flag=%s  target=%s  ask_count=%d  max=%d",
                    af.rule.id, target, count, max_gap_asks,
                )
                newly_skipped_rf.add(target)
                continue
            selected_status = af
            selected_target = target
            break

        if selected_status and selected_target:
            gap_ask_counts[selected_target] = gap_ask_counts.get(selected_target, 0) + 1
            move = ConversationMove(
                type=MoveType.TARGETED_CLARIFY,
                target_gap=selected_target,
                red_flag_id=selected_status.rule.id,
                reason=f"Alert red flag: {selected_status.rule.name}",
            )
            logger.info(
                "FLOW_ALERT_OVERRIDE  flag=%s  score=%d/%d  target=%s",
                selected_status.rule.id, selected_status.score,
                selected_status.hard_threshold, selected_target,
            )
            result: dict = {
                "conversation_move": move,
                "last_rf_check_fact_snapshot": updated_snapshot,
                "gap_ask_counts": gap_ask_counts,
                "watch_flags": new_watch_flags,
            }
            if newly_skipped_rf:
                result["skipped_gaps"] = newly_skipped_rf
            return result

        if newly_skipped_rf:
            skipped_gaps |= newly_skipped_rf

    # --- Summary phase ---
    if phase == Phase.SUMMARY:
        move = ConversationMove(type=MoveType.SUMMARIZE, reason="Summary phase reached")
        logger.info("FLOW_MOVE  type=%s  reason=summary_phase", move.type.value)
        return {
            "conversation_move": move,
            "last_rf_check_fact_snapshot": updated_snapshot,
            "watch_flags": new_watch_flags,
        }

    # --- Patient expressing concern ---
    if intent_str == PatientIntent.EXPRESSING_CONCERN.value:
        next_gap = remaining_gaps[0] if remaining_gaps else None
        move = ConversationMove(
            type=MoveType.ACKNOWLEDGE_CONCERN,
            target_gap=next_gap,
            reason="Patient expressed concern",
        )
        logger.info("FLOW_MOVE  type=%s  target=%s", move.type.value, next_gap)
        return {
            "conversation_move": move,
            "last_rf_check_fact_snapshot": updated_snapshot,
            "watch_flags": new_watch_flags,
        }

    # --- Explanation request ---
    if pending_explanation and intent_str in (
        PatientIntent.ASKING_EXPLANATION.value,
        PatientIntent.MIXED.value,
    ):
        next_gap = remaining_gaps[0] if remaining_gaps else None
        move = ConversationMove(
            type=MoveType.EXPLAIN,
            target_gap=next_gap,
            reason="Patient asked for explanation",
        )
        logger.info("FLOW_MOVE  type=%s  target=%s", move.type.value, next_gap)
        return {
            "conversation_move": move,
            "last_rf_check_fact_snapshot": updated_snapshot,
            "watch_flags": new_watch_flags,
        }

    # --- Unconfirmed facts ---
    if unconfirmed:
        first_unconfirmed = next(iter(unconfirmed))
        move = ConversationMove(
            type=MoveType.CLARIFY,
            target_gap=first_unconfirmed,
            reason=f"Unconfirmed fact needs clarification: {first_unconfirmed}",
        )
        logger.info("FLOW_MOVE  type=%s  target=%s", move.type.value, first_unconfirmed)
        return {
            "conversation_move": move,
            "last_rf_check_fact_snapshot": updated_snapshot,
            "watch_flags": new_watch_flags,
        }

    # --- LLM's chosen next question ---
    if remaining_gaps:
        target = remaining_gaps[0]
        count = gap_ask_counts.get(target, 0)
        if count >= max_gap_asks:
            logger.info("FLOW_SKIP_GAP  gap=%s  ask_count=%d  max=%d", target, count, max_gap_asks)
            skipped_gaps.add(target)
        else:
            gap_ask_counts[target] = count + 1
            move = ConversationMove(
                type=MoveType.QUESTION,
                target_gap=target,
                reason="LLM-selected discriminating question",
            )
            logger.info("FLOW_MOVE  type=%s  target=%s  ask_count=%d", move.type.value, target, gap_ask_counts[target])
            return {
                "conversation_move": move,
                "last_rf_check_fact_snapshot": updated_snapshot,
                "gap_ask_counts": gap_ask_counts,
                "watch_flags": new_watch_flags,
            }

    # --- No gaps — trigger natural completion ---
    if is_ready_to_land(state, "natural"):
        logger.info("FLOW_NATURAL_COMPLETION  no gaps, ready to land")
        move = ConversationMove(type=MoveType.SUMMARIZE, reason="Natural completion — no remaining gaps")
        return {
            "conversation_move": move,
            "last_rf_check_fact_snapshot": updated_snapshot,
            "skipped_gaps": skipped_gaps,
            "consultation_ending": ConsultationEnding.LANDING,
            "closing_turn_count": 0,
            "watch_flags": new_watch_flags,
        }

    move = ConversationMove(
        type=MoveType.SUMMARIZE,
        reason="No remaining gaps -- transitioning to summary",
    )
    logger.info("FLOW_MOVE  type=%s  reason=no_gaps_fallback", move.type.value)
    return {
        "conversation_move": move,
        "last_rf_check_fact_snapshot": updated_snapshot,
        "skipped_gaps": skipped_gaps,
        "watch_flags": new_watch_flags,
        "consultation_ending": ConsultationEnding.LANDING,
        "closing_turn_count": 0,
        "remaining_gaps": [],
    }


def _find_missing_key_for_candidate(
    flag,
    info_gathered: dict[str, str],
    denied_symptoms: set[str] | None = None,
) -> str | None:
    """Find the first required key missing from gathered facts for a candidate flag.

    Keys that have been denied are skipped — there is no point asking about them.
    """
    denied = denied_symptoms or set()
    for key in flag.required_keys:
        key_lower = key.lower()
        found = any(k.lower() == key_lower for k in info_gathered)
        if not found and not any(d.lower() == key_lower for d in denied):
            return key
    for key in flag.at_least_one_of:
        key_lower = key.lower()
        found = any(k.lower() == key_lower for k in info_gathered)
        if not found and not any(d.lower() == key_lower for d in denied):
            return key
    return None

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from backend.domain.models import DomainProfile, RedFlagConfig
from backend.models.red_flag import RedFlagRule

logger = logging.getLogger(__name__)


@dataclass
class RedFlagStatus:
    """Per-flag state produced by the scoring engine."""

    rule: RedFlagRule
    score: int
    soft_threshold: int
    hard_threshold: int
    state: str  # "clear", "watch", "alert"
    missing_keys: list[str] = field(default_factory=list)
    watch_since_turn: int | None = None


def _fact_present(key: str, info_gathered: dict[str, str]) -> bool:
    """Case-insensitive check: is *key* present as a key in gathered facts?"""
    key_lower = key.lower()
    for k in info_gathered:
        if key_lower == k.lower():
            return True
    return False


def _get_fact_value(key: str, info_gathered: dict[str, str]) -> str | None:
    """Case-insensitive lookup of fact value."""
    key_lower = key.lower()
    for k, v in info_gathered.items():
        if key_lower == k.lower():
            return v
    return None


def _key_denied(key: str, denied_symptoms: set[str]) -> bool:
    """Case-insensitive check: is *key* in the denied set?"""
    key_lower = key.lower()
    return any(d.lower() == key_lower for d in denied_symptoms)


def _qualifier_passes(
    qualifier_key: str,
    qualifier_values: list[str],
    info_gathered: dict[str, str],
) -> bool:
    """Check if the fact value for *qualifier_key* contains any of the qualifier values."""
    fact_value = _get_fact_value(qualifier_key, info_gathered)
    if fact_value is None:
        return False
    val_lower = fact_value.lower()
    return any(qv.lower() in val_lower for qv in qualifier_values)


def _config_to_rule(config: RedFlagConfig) -> RedFlagRule:
    return RedFlagRule(
        id=config.id,
        name=config.name,
        required_keys=config.required_keys,
        at_least_one_of=config.at_least_one_of,
        qualifiers=config.qualifiers,
        message=config.message,
        severity=config.severity,
        soft_threshold=config.soft_threshold,
        hard_threshold=config.hard_threshold,
    )


class RedFlagGuard:
    """Deterministic red-flag evaluation against gathered facts."""

    def __init__(self, domain: DomainProfile) -> None:
        self._rules: list[RedFlagConfig] = domain.red_flags

    # ------------------------------------------------------------------
    # Legacy interface (kept for backward compatibility)
    # ------------------------------------------------------------------

    def check(
        self,
        info_gathered: dict[str, str],
        denied_symptoms: set[str],
        confirmed_red_flag_ids: set[str],
        last_rf_check_fact_snapshot: dict[str, str],
    ) -> list[RedFlagRule]:
        """Evaluate all rules. Return newly triggered rules (not already confirmed)."""
        if info_gathered == last_rf_check_fact_snapshot:
            return []

        triggered: list[RedFlagRule] = []

        for rule in self._rules:
            if rule.id in confirmed_red_flag_ids:
                continue

            if not self._evaluate_rule(rule, info_gathered, denied_symptoms):
                continue

            triggered.append(_config_to_rule(rule))

        return triggered

    @staticmethod
    def _evaluate_rule(
        rule: RedFlagConfig,
        info_gathered: dict[str, str],
        denied_symptoms: set[str],
    ) -> bool:
        for key in rule.required_keys:
            if _key_denied(key, denied_symptoms):
                return False
            if not _fact_present(key, info_gathered):
                return False

        if rule.at_least_one_of:
            if not any(_fact_present(k, info_gathered) for k in rule.at_least_one_of):
                return False

        for qual_key, qual_values in rule.qualifiers.items():
            if _fact_present(qual_key, info_gathered):
                if not _qualifier_passes(qual_key, qual_values, info_gathered):
                    return False

        return True

    @staticmethod
    def _evaluate_rule_partial(
        rule: RedFlagConfig,
        info_gathered: dict[str, str],
        denied_symptoms: set[str],
    ) -> str:
        """Three-state evaluation of a red flag rule (legacy).

        Returns:
          "confirmed"  - fully satisfied
          "candidate"  - partially matched
          "clear"      - no supporting evidence
        """
        required_present = 0
        required_denied = 0
        for key in rule.required_keys:
            if _key_denied(key, denied_symptoms):
                required_denied += 1
            elif _fact_present(key, info_gathered):
                required_present += 1

        if required_denied > 0 and required_present == 0:
            return "clear"

        at_least_one_met = True
        all_at_least_one_denied = False
        if rule.at_least_one_of:
            alo_present = 0
            alo_denied = 0
            for k in rule.at_least_one_of:
                if _fact_present(k, info_gathered):
                    alo_present += 1
                elif _key_denied(k, denied_symptoms):
                    alo_denied += 1
            at_least_one_met = alo_present > 0
            all_at_least_one_denied = (
                alo_present == 0
                and alo_denied > 0
                and alo_denied + alo_present == len(rule.at_least_one_of)
            )

        if all_at_least_one_denied:
            return "clear"

        qualifiers_pass = True
        for qual_key, qual_values in rule.qualifiers.items():
            if _fact_present(qual_key, info_gathered):
                if not _qualifier_passes(qual_key, qual_values, info_gathered):
                    qualifiers_pass = False

        total_required = len(rule.required_keys)
        all_required_met = (total_required == 0) or (required_present == total_required)

        if all_required_met and at_least_one_met and qualifiers_pass:
            return "confirmed"

        has_any_evidence = required_present > 0 or (
            not rule.required_keys and rule.at_least_one_of and at_least_one_met
        )
        if has_any_evidence:
            return "candidate"

        return "clear"

    def check_with_candidates(
        self,
        info_gathered: dict[str, str],
        denied_symptoms: set[str],
        confirmed_red_flag_ids: set[str],
        last_rf_check_fact_snapshot: dict[str, str],
    ) -> tuple[list[RedFlagRule], list[RedFlagRule]]:
        """Evaluate all rules. Return (newly_confirmed, candidates). (Legacy)"""
        if info_gathered == last_rf_check_fact_snapshot:
            return [], []

        confirmed: list[RedFlagRule] = []
        candidates: list[RedFlagRule] = []

        for rule in self._rules:
            if rule.id in confirmed_red_flag_ids:
                continue

            result = self._evaluate_rule_partial(rule, info_gathered, denied_symptoms)

            if result == "confirmed":
                confirmed.append(_config_to_rule(rule))
            elif result == "candidate":
                candidates.append(_config_to_rule(rule))

        return confirmed, candidates

    # ------------------------------------------------------------------
    # New Clear / Watch / Alert interface
    # ------------------------------------------------------------------

    @staticmethod
    def score_rule(
        rule: RedFlagConfig,
        info_gathered: dict[str, str],
        denied_symptoms: set[str],
    ) -> tuple[int, list[str]]:
        """Compute a numeric evidence score for *rule*.

        Returns (score, missing_keys) where missing_keys are all keys from
        required_keys and at_least_one_of that haven't been gathered or denied.

        Scoring:
          +1  per required_key present
          +1  per qualifier that passes
          +2  per at_least_one_of key present

        A score of -1 signals the rule is conclusively clear (a required key
        was denied, making the flag impossible).
        """
        missing: list[str] = []

        for key in rule.required_keys:
            if _key_denied(key, denied_symptoms):
                return -1, []

        if rule.at_least_one_of:
            all_denied = all(
                _key_denied(k, denied_symptoms) for k in rule.at_least_one_of
            )
            if all_denied:
                return -1, []

        score = 0

        for key in rule.required_keys:
            if _fact_present(key, info_gathered):
                score += 1
            else:
                missing.append(key)

        for qual_key, qual_values in rule.qualifiers.items():
            if _fact_present(qual_key, info_gathered):
                if _qualifier_passes(qual_key, qual_values, info_gathered):
                    score += 1

        for key in rule.at_least_one_of:
            if _fact_present(key, info_gathered):
                score += 2
            elif not _key_denied(key, denied_symptoms):
                missing.append(key)

        return score, missing

    def check_with_states(
        self,
        info_gathered: dict[str, str],
        denied_symptoms: set[str],
        confirmed_red_flag_ids: set[str],
        current_turn: int = 0,
        prev_watch_flags: dict[str, dict] | None = None,
    ) -> tuple[list[RedFlagStatus], list[RedFlagStatus], list[RedFlagStatus]]:
        """Score every rule and bucket into (alert, watch, clear).

        *prev_watch_flags* carries persisted Watch metadata from prior turns
        (keyed by flag id), each entry having ``since_turn``.

        Returns three lists: (alert_flags, watch_flags, clear_flags).
        """
        prev = prev_watch_flags or {}

        alert_flags: list[RedFlagStatus] = []
        watch_flags: list[RedFlagStatus] = []
        clear_flags: list[RedFlagStatus] = []

        for rule in self._rules:
            if rule.id in confirmed_red_flag_ids:
                continue

            score, missing = self.score_rule(rule, info_gathered, denied_symptoms)

            if score == -1:
                status = RedFlagStatus(
                    rule=_config_to_rule(rule),
                    score=0,
                    soft_threshold=rule.soft_threshold,
                    hard_threshold=rule.hard_threshold,
                    state="clear",
                    missing_keys=[],
                )
                clear_flags.append(status)
                logger.info(
                    "RF_SCORE  flag=%s  score=denied  soft=%d  hard=%d  state=clear",
                    rule.id, rule.soft_threshold, rule.hard_threshold,
                )
                continue

            since_turn = prev.get(rule.id, {}).get("since_turn")

            if score >= rule.hard_threshold:
                state = "alert"
            elif score >= rule.soft_threshold:
                state = "watch"
                if since_turn is None:
                    since_turn = current_turn
            else:
                state = "clear"
                since_turn = None

            logger.info(
                "RF_SCORE  flag=%s  score=%d  soft=%d  hard=%d  state=%s",
                rule.id, score, rule.soft_threshold, rule.hard_threshold, state,
            )

            prev_state = "clear"
            if rule.id in prev:
                prev_state = "watch"

            if state != prev_state:
                logger.info(
                    "RF_TRANSITION  flag=%s  %s->%s  trigger=%s",
                    rule.id, prev_state, state,
                    _summarise_trigger(rule, info_gathered),
                )

            status = RedFlagStatus(
                rule=_config_to_rule(rule),
                score=score,
                soft_threshold=rule.soft_threshold,
                hard_threshold=rule.hard_threshold,
                state=state,
                missing_keys=missing,
                watch_since_turn=since_turn,
            )

            if state == "alert":
                alert_flags.append(status)
            elif state == "watch":
                watch_flags.append(status)
            else:
                clear_flags.append(status)

        return alert_flags, watch_flags, clear_flags


def _summarise_trigger(rule: RedFlagConfig, info_gathered: dict[str, str]) -> str:
    """Build a short human-readable summary of which evidence is present."""
    parts: list[str] = []
    for key in rule.required_keys:
        if _fact_present(key, info_gathered):
            parts.append(f"{key}_present")
    for key in rule.at_least_one_of:
        if _fact_present(key, info_gathered):
            parts.append(f"{key}_present")
    return ",".join(parts) if parts else "no_trigger"

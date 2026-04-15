from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from backend.agent.graph import build_graph
from backend.agent.state import create_initial_state
from backend.config import settings
from backend.cost.context import current_session_id
from backend.cost.tracker import cost_tracker
from backend.domain.loader import load_domain
from backend.domain.models import DomainProfile
from backend.llm.client import AgentLLMClient
from backend.models.state import ConsultationEnding

logger = logging.getLogger(__name__)


@dataclass
class _SessionRecord:
    """Internal bookkeeping for a single consultation session."""

    session_id: str
    domain_id: str
    domain: DomainProfile
    graph: Any  # CompiledStateGraph (avoid import for lighter coupling)
    turn_count: int = 0
    last_state: dict = field(default_factory=dict)


class SessionManager:
    """In-memory session store that owns compiled LangGraph instances.

    One ``AgentLLMClient`` is shared across all sessions (stateless wrapper).
    ``DomainProfile`` objects are cached per ``domain_id``.
    Each session gets its own ``CompiledStateGraph`` with a private
    ``MemorySaver`` checkpointer keyed by the session id.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, _SessionRecord] = {}
        self._domain_cache: dict[str, DomainProfile] = {}
        self._client: AgentLLMClient | None = None

    # -- helpers --------------------------------------------------------

    def _get_client(self) -> AgentLLMClient:
        if self._client is None:
            self._client = AgentLLMClient()
            logger.info("SESSION_CLIENT_INIT  provider=%s", self._client.provider)
        return self._client

    def _get_domain(self, domain_id: str) -> DomainProfile:
        if domain_id not in self._domain_cache:
            self._domain_cache[domain_id] = load_domain(domain_id)
            logger.info("SESSION_DOMAIN_CACHED  domain_id=%s", domain_id)
        return self._domain_cache[domain_id]

    def _lookup(self, session_id: str) -> _SessionRecord:
        rec = self._sessions.get(session_id)
        if rec is None:
            logger.warning("SESSION_UNKNOWN  session_id=%s", session_id)
            raise KeyError(f"Unknown session: {session_id}")
        return rec

    # -- public API -----------------------------------------------------

    @property
    def active_count(self) -> int:
        return len(self._sessions)

    def has_session(self, session_id: str) -> bool:
        return session_id in self._sessions

    def create_session(self, domain_id: str | None = None) -> tuple[str, str]:
        """Create a new consultation session.

        Returns ``(session_id, opening_message)``.
        """
        domain_id = domain_id or settings.default_domain
        domain = self._get_domain(domain_id)
        client = self._get_client()
        compiled = build_graph(client, domain)

        session_id = uuid.uuid4().hex
        rec = _SessionRecord(
            session_id=session_id,
            domain_id=domain_id,
            domain=domain,
            graph=compiled,
        )
        self._sessions[session_id] = rec
        cost_tracker.register_session(session_id, domain_id)
        logger.info(
            "SESSION_CREATE  session_id=%s  domain_id=%s  active=%d",
            session_id,
            domain_id,
            self.active_count,
        )
        return session_id, domain.opening_message

    async def send_message(self, session_id: str, message: str) -> dict[str, Any]:
        """Invoke the graph for one conversation turn.

        Returns a dict with ``text``, ``phase``, and ``state`` keys.
        """
        rec = self._lookup(session_id)
        current_session_id.set(session_id)

        config = {"configurable": {"thread_id": session_id}}

        if rec.turn_count == 0:
            init = create_initial_state(rec.domain_id)
            init["patient_message"] = message
            result = await rec.graph.ainvoke(init, config=config)
        else:
            result = await rec.graph.ainvoke(
                {"patient_message": message}, config=config
            )

        rec.turn_count += 1
        rec.last_state = dict(result)

        phase_val = result.get("phase")
        phase_str = phase_val.value if hasattr(phase_val, "value") else str(phase_val)

        logger.info(
            "SESSION_MESSAGE  session_id=%s  message_len=%d  "
            "response_len=%d  phase=%s  turn=%d",
            session_id,
            len(message),
            len(result.get("doctor_response", "")),
            phase_str,
            rec.turn_count,
        )

        ending_val = result.get("consultation_ending", ConsultationEnding.NONE)
        is_ended = ending_val == ConsultationEnding.CLOSED or (
            hasattr(ending_val, "value") and ending_val.value == "closed"
        )

        if is_ended:
            cost_tracker.finalize_session(session_id)

        return {
            "text": result.get("doctor_response", ""),
            "phase": phase_str,
            "state": self._build_state_snapshot(result),
            "consultation_ended": is_ended,
        }

    def get_session_state(self, session_id: str) -> dict[str, Any]:
        """Return the observable clinical state for the frontend."""
        rec = self._lookup(session_id)
        logger.info("SESSION_STATE  session_id=%s", session_id)

        if not rec.last_state:
            init = create_initial_state(rec.domain_id)
            return self._build_state_snapshot(init)

        return self._build_state_snapshot(rec.last_state)

    def get_phase(self, session_id: str) -> str:
        """Return the current phase as a string."""
        rec = self._lookup(session_id)
        if not rec.last_state:
            return "intake"
        phase_val = rec.last_state.get("phase")
        return phase_val.value if hasattr(phase_val, "value") else str(phase_val)

    def delete_session(self, session_id: str) -> None:
        """Remove a session from the store."""
        if session_id in self._sessions:
            cost_tracker.finalize_session(session_id)
            del self._sessions[session_id]
            logger.info(
                "SESSION_DELETE  session_id=%s  active=%d",
                session_id,
                self.active_count,
            )
        else:
            logger.warning("SESSION_DELETE_UNKNOWN  session_id=%s", session_id)

    # -- snapshot builder -----------------------------------------------

    @staticmethod
    def _build_state_snapshot(state: dict) -> dict[str, Any]:
        """Extract the subset of state the frontend needs."""
        phase_val = state.get("phase")
        phase_str = phase_val.value if hasattr(phase_val, "value") else str(phase_val)

        confidence_val = state.get("confidence")
        confidence_str = (
            confidence_val.value
            if hasattr(confidence_val, "value")
            else str(confidence_val)
        )

        hypothesis = state.get("hypothesis")
        hyp_dict: dict[str, Any] | None = None
        if hypothesis is not None:
            leading_dict = None
            if hypothesis.leading is not None:
                leading_dict = {
                    "name": hypothesis.leading.name,
                    "score": hypothesis.leading.score,
                    "supporting_evidence": hypothesis.leading.supporting_evidence,
                    "missing_evidence": hypothesis.leading.missing_evidence,
                }
            hyp_dict = {
                "leading": leading_dict,
                "differential": [
                    {"name": h.name, "score": h.score}
                    for h in hypothesis.differential
                ],
                "ruled_out": [
                    {"name": h.name, "score": h.score}
                    for h in hypothesis.ruled_out
                ],
            }

        denied = state.get("denied_symptoms", set())
        confirmed_rf = state.get("confirmed_red_flag_ids", set())

        ending_val = state.get("consultation_ending", ConsultationEnding.NONE)
        ending_str = ending_val.value if hasattr(ending_val, "value") else str(ending_val)

        return {
            "phase": phase_str,
            "turn_count": state.get("turn_count", 0),
            "information_gathered": dict(state.get("information_gathered", {})),
            "denied_symptoms": sorted(denied) if isinstance(denied, set) else list(denied),
            "hypothesis": hyp_dict,
            "confidence": confidence_str,
            "remaining_gaps": list(state.get("remaining_gaps", [])),
            "confirmed_red_flag_ids": sorted(confirmed_rf) if isinstance(confirmed_rf, set) else list(confirmed_rf),
            "conversation_history": [
                {"speaker": u.speaker, "text": u.text}
                for u in state.get("conversation_history", [])
            ],
            "consultation_ending": ending_str,
        }

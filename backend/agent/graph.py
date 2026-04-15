from __future__ import annotations

import logging
from functools import partial

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from backend.agent.nodes.crisis import crisis_node
from backend.agent.nodes.flow_control import flow_control_node
from backend.agent.nodes.intake import intake_node
from backend.agent.nodes.reason import reason_node
from backend.agent.nodes.response_gen import response_gen_node
from backend.agent.nodes.safety import safety_node
from backend.agent.routing import route_after_intake
from backend.agent.state import ClinicalState
from backend.domain.models import DomainProfile
from backend.llm.client import AgentLLMClient

logger = logging.getLogger(__name__)


def build_graph(
    client: AgentLLMClient,
    domain: DomainProfile,
) -> CompiledStateGraph:
    """Construct and compile the clinical consultation StateGraph.

    Each node receives ``client`` and ``domain`` via functools.partial so
    the graph only needs to pass the state dict at invocation time.
    """
    graph = StateGraph(ClinicalState)

    graph.add_node("intake", partial(intake_node, client=client, domain=domain))
    graph.add_node("reason", partial(reason_node, client=client, domain=domain))
    graph.add_node("flow_control", partial(flow_control_node, client=client, domain=domain))
    graph.add_node("response_gen", partial(response_gen_node, client=client, domain=domain))
    graph.add_node("safety", partial(safety_node, client=client, domain=domain))
    graph.add_node("crisis", partial(crisis_node, client=client, domain=domain))

    graph.set_entry_point("intake")
    graph.add_conditional_edges(
        "intake",
        route_after_intake,
        {"crisis": "crisis", "reason": "reason"},
    )
    graph.add_edge("reason", "flow_control")
    graph.add_edge("flow_control", "response_gen")
    graph.add_edge("response_gen", "safety")
    graph.add_edge("safety", END)
    graph.add_edge("crisis", END)

    logger.info(
        "GRAPH_BUILD  nodes=6  domain=%s  checkpointer=MemorySaver",
        domain.id,
    )

    serde = JsonPlusSerializer(allowed_msgpack_modules=[
        ("backend.models.state", "Phase"),
        ("backend.models.state", "Confidence"),
        ("backend.models.state", "MoveType"),
        ("backend.models.state", "EmotionalTone"),
        ("backend.models.state", "ConsultationEnding"),
        ("backend.models.hypothesis", "HypothesisEntry"),
        ("backend.models.hypothesis", "Hypothesis"),
        ("backend.models.utterance", "Utterance"),
        ("backend.models.move", "ConversationMove"),
    ])
    return graph.compile(checkpointer=MemorySaver(serde=serde))

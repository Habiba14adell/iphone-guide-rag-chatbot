import logging

from langgraph.graph import END, START, StateGraph
from ..config.logging_config import setup_logging
from .nodes import generate_answer_node, retrieve_node
from .state import AgentState


logger = logging.getLogger(__name__)


def build_state_graph():
    setup_logging()
    builder = StateGraph(AgentState)
    builder.add_edge(START, "retrieve")
    builder.add_edge("retrieve", "generate_answer")
    builder.add_edge("generate_answer", END)

    builder.add_node("retrieve", retrieve_node)
    builder.add_node("generate_answer", generate_answer_node)

    graph = builder.compile()
    logger.info("RAG workflow ready")
    return graph

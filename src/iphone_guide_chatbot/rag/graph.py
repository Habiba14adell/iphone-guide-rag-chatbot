"""LangGraph workflow for retrieving guide excerpts and generating an answer."""

from langgraph.graph import END, START, StateGraph

from .nodes import generate_answer_node, retrieve_node
from .state import AgentState


def build_state_graph():
    builder = StateGraph(AgentState)
    builder.add_edge(START, "retrieve")
    builder.add_edge("retrieve", "generate_answer")
    builder.add_edge("generate_answer", END)

    builder.add_node("retrieve", retrieve_node)
    builder.add_node("generate_answer", generate_answer_node)

    return builder.compile()

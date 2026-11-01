
from functools import partial
from langgraph.graph import END, START, StateGraph
from .nodes import RelevanceEvaluator, relevance_node, retrieve_node
from .state import AgentState


def route_after_retrieval(state: AgentState) -> str:
    return "stop" if state.get("status") == "error" else "evaluate"


def route_after_relevance(state: AgentState) -> str:
    if state.get("status") != "evaluated":
        return "stop"
    if state.get("is_relevant") is True:
        return "relevant"
    if state.get("is_relevant") is False:
        return "not_relevant"
    return "stop"


def pending_stage(state: AgentState, *, status: str) -> dict:
    """Mark an unimplemented stage; do not generate an answer or fallback."""
    return {"status": status}


def build_state_graph(evaluator: RelevanceEvaluator | None = None):
    builder = StateGraph(AgentState)
    builder.add_node("retrieve", retrieve_node)
    builder.add_node("relevance_judge", partial(relevance_node, evaluator=evaluator))

    builder.add_node("generate_answer", partial(pending_stage, status="answer_generation_pending"))
    builder.add_node("fallback", partial(pending_stage, status="fallback_pending"))

    builder.add_edge(START, "retrieve")
    builder.add_conditional_edges("retrieve", route_after_retrieval,
                                  {"evaluate": "relevance_judge", "stop": END})
    builder.add_conditional_edges("relevance_judge", route_after_relevance, {
        "relevant": "generate_answer", "not_relevant": "fallback", "stop": END,
    })
    builder.add_edge("generate_answer", END)
    builder.add_edge("fallback", END)
    return builder.compile()

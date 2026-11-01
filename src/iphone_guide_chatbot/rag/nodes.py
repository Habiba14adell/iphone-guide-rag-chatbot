



import logging
from collections.abc import Callable

from ..config.logging_config import setup_logging
from ..retrieval.retriever import retrieve_chunks
from .state import AgentState


logger = logging.getLogger(__name__)

RelevanceEvaluator = Callable[[str, list[dict]], dict]


def retrieve_node(state: AgentState) -> dict:
    setup_logging()
    try:
        chunks = retrieve_chunks(state["question"])
        return {"retrieved_chunks": chunks, "status": "evaluating"}
    except Exception as error:
        logger.error("Retrieval node failed (%s)", type(error).__name__)
        return {"retrieved_chunks": [], "status": "error"}


def relevance_node(state: AgentState, evaluator: RelevanceEvaluator | None = None) -> dict:
    setup_logging()
    if state.get("status") == "error":
        return {"status": "error", "relevance_reason": "Retrieval failed; evaluation was not run."}

    if evaluator is None:
        logger.info("Relevance evaluation pending: no evaluator configured")
        # Omit the optional boolean rather than inventing a relevance decision.
        # Routing checks status first, so a previous turn's boolean is ignored.
        return {
            "status": "evaluation_pending",
            "relevance_reason": "Relevance evaluation is pending: no evaluator is configured.",
        }

    try:
        question = state["question"]
        chunks = state["retrieved_chunks"]
        if not isinstance(question, str) or not question.strip():
            raise ValueError("A nonempty question is required")
        if not isinstance(chunks, list) or any(not isinstance(chunk, dict) for chunk in chunks):
            raise ValueError("Retrieved chunks must be a list of dictionaries")

        result = evaluator(question, chunks)
        if not isinstance(result, dict) or type(result.get("is_relevant")) is not bool:
            raise ValueError("Evaluator must return a boolean is_relevant")
        reason = result.get("relevance_reason")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("Evaluator must return a nonempty relevance_reason")

        logger.info("Relevance evaluation completed: relevant=%s", result["is_relevant"])
        return {
            "is_relevant": result["is_relevant"],
            "relevance_reason": reason,
            "status": "evaluated",
        }
    except Exception as error:
        logger.error("Relevance evaluation failed (%s)", type(error).__name__)
        return {"status": "error", "relevance_reason": "Relevance evaluation failed."}

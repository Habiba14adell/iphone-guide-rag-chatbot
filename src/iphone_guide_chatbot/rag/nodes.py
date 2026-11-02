"""LangGraph nodes for guide retrieval and grounded answer generation."""

import logging
from functools import lru_cache

from ..config.logging_config import setup_logging
from ..llm.gemini_client import GeminiClient
from ..retrieval.retriever import retrieve_chunks
from .prompts import UNSUPPORTED_ANSWER, build_answer_prompt
from .state import AgentState


logger = logging.getLogger(__name__)
RETRIEVAL_ERROR_ANSWER = "I couldn't retrieve excerpts from the iPhone User Guide. Please try again."
GENERATION_ERROR_ANSWER = "I couldn't generate an answer right now. Please try again."
setup_logging()


@lru_cache(maxsize=1)
def _get_gemini_client() -> GeminiClient:
    """Create one Gemini client per process and reuse it across graph calls."""
    return GeminiClient()

def _citations_for_chunks(chunks: list[dict]) -> list[dict]:
    citation_fields = (
        "source", "chapter", "section", "pdf_pages", "printed_pages", "point_id",
    )
    citations = []
    for rank, chunk in enumerate(chunks, start=1):
        citation = {"source_number": rank}
        citation.update({key: chunk[key] for key in citation_fields if key in chunk})
        citations.append(citation)
    return citations

def retrieve_node(state: AgentState) -> dict:
    try:
        chunks = retrieve_chunks(state["question"])
        return {"retrieved_chunks": chunks, "status": "retrieved"}
    except Exception as error:
        logger.error("Retrieval node failed (%s)", type(error).__name__)
        return {
            "retrieved_chunks": [],
            "citations": [],
            "answer": RETRIEVAL_ERROR_ANSWER,
            "status": "error",
        }


def generate_answer_node(state: AgentState) -> dict:
    """Generate an answer grounded exclusively in this turn's retrieved excerpts."""
    setup_logging()
    if state.get("status") == "error":
        return {
            "answer": state.get("answer") or RETRIEVAL_ERROR_ANSWER,
            "citations": [],
            "status": "error",
        }

    question = state.get("question")
    chunks = state.get("retrieved_chunks") or []
    if not chunks:
        return {
            "answer": UNSUPPORTED_ANSWER,
            "citations": [],
            "status": "completed",
        }

    citations = _citations_for_chunks(chunks)
    try:
        if not isinstance(question, str) or not question.strip():
            raise ValueError("A nonempty question is required")
        if any(not isinstance(chunk.get("content"), str) for chunk in chunks):
            raise ValueError("Each retrieved chunk must contain text content")

        prompt = build_answer_prompt(question, chunks)
        answer = _get_gemini_client().generate_text(prompt)
        return {"answer": answer, "citations": citations, "status": "completed"}
    except Exception as error:
        logger.error("Answer generation failed (%s)", type(error).__name__)
        return {
            "answer": GENERATION_ERROR_ANSWER,
            "citations": citations,
            "status": "error",
        }

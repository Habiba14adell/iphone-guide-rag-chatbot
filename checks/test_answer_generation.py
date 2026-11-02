"""Offline checks for the grounded answer-generation workflow."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

from iphone_guide_chatbot.rag.graph import build_state_graph
from iphone_guide_chatbot.rag import graph as graph_module
from iphone_guide_chatbot.rag import nodes
from iphone_guide_chatbot.rag.nodes import generate_answer_node
from iphone_guide_chatbot.rag.prompts import UNSUPPORTED_ANSWER


def make_state(question="How do I connect to Wi-Fi?", chunks=None, **overrides):
    state = {
        "messages": [],
        "conversation_history": [],
        "retrieved_chunks": chunks or [],
        "question": question,
        "answer": "",
        "status": "retrieved",
    }
    state.update(overrides)
    return state


def make_chunk(content="Open Settings and tap Wi-Fi."):
    return {
        "content": content,
        "source": "iPhone User Guide",
        "chapter": "Connect to the internet",
        "section": "Connect iPhone to a Wi-Fi network",
        "pdf_pages": [12],
        "printed_pages": [10],
        "point_id": "chunk-1",
    }


def test_supported_answer_returns_metadata_citations():
    gemini = Mock()
    gemini.generate_text.return_value = "Open Settings and tap Wi-Fi. [PDF p. 12]"
    with patch.object(nodes, "_get_gemini_client", return_value=gemini):
        result = generate_answer_node(make_state(chunks=[make_chunk()]))

    assert result["status"] == "completed"
    assert "PDF p. 12" in result["answer"]
    assert result["citations"] == [{
        "source_number": 1,
        "source": "iPhone User Guide",
        "chapter": "Connect to the internet",
        "section": "Connect iPhone to a Wi-Fi network",
        "pdf_pages": [12],
        "printed_pages": [10],
        "point_id": "chunk-1",
    }]
    prompt = gemini.generate_text.call_args.args[0]
    assert "Open Settings and tap Wi-Fi." in prompt
    assert '"pdf_pages": [12]' in prompt


def test_unsupported_answer_uses_required_fallback():
    gemini = Mock()
    gemini.generate_text.return_value = UNSUPPORTED_ANSWER
    with patch.object(nodes, "_get_gemini_client", return_value=gemini):
        result = generate_answer_node(make_state(
            question="Does the guide explain how to repair a cracked screen?",
            chunks=[make_chunk()],
        ))

    assert result["answer"] == UNSUPPORTED_ANSWER
    assert result["status"] == "completed"
    assert UNSUPPORTED_ANSWER in gemini.generate_text.call_args.args[0]


def test_empty_retrieval_does_not_call_gemini():
    with patch.object(nodes, "_get_gemini_client") as get_client:
        result = generate_answer_node(make_state(chunks=[]))

    get_client.assert_not_called()
    assert result["answer"] == UNSUPPORTED_ANSWER
    assert result["citations"] == []
    assert result["status"] == "completed"


def test_gemini_error_returns_safe_error_state(caplog):
    gemini = Mock()
    gemini.generate_text.side_effect = RuntimeError("private provider response")
    with patch.object(nodes, "_get_gemini_client", return_value=gemini):
        result = generate_answer_node(make_state(chunks=[make_chunk()]))

    assert result["status"] == "error"
    assert "private provider response" not in result["answer"]
    assert "private provider response" not in str(result["citations"])
    assert "private provider response" not in caplog.text
    assert "Answer generation failed (RuntimeError)" in caplog.text


def test_previous_assistant_answer_is_not_sent_as_evidence():
    gemini = Mock()
    gemini.generate_text.return_value = "The excerpts do not say."
    history = [
        {"role": "assistant", "content": "Invented claim: the iPhone has a hidden setting."},
        {"role": "user", "content": "Where is that setting?"},
    ]
    with patch.object(nodes, "_get_gemini_client", return_value=gemini):
        generate_answer_node(make_state(
            question="Where is that setting?",
            chunks=[make_chunk()],
            conversation_history=history,
        ))

    prompt = gemini.generate_text.call_args.args[0]
    assert "Invented claim" not in prompt
    assert "hidden setting" not in prompt
    assert "Open Settings and tap Wi-Fi." in prompt


def test_graph_runs_retrieval_then_generation():
    call_order = []

    def retrieve(state):
        call_order.append("retrieve")
        return {"retrieved_chunks": [make_chunk()], "status": "retrieved"}

    def generate(state):
        call_order.append("generate")
        return {"answer": "Generated.", "citations": [], "status": "completed"}

    with patch.object(graph_module, "retrieve_node", side_effect=retrieve), patch.object(
        graph_module, "generate_answer_node", side_effect=generate
    ):
        result = build_state_graph().invoke(make_state(chunks=[]))

    assert call_order == ["retrieve", "generate"]
    assert result["answer"] == "Generated."
    assert result["status"] == "completed"

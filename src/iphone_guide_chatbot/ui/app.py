"""Chainlit interface for inspecting the iPhone guide retrieval workflow."""

import asyncio
import logging
import sys
from pathlib import Path

import chainlit as cl

# Chainlit loads this entry point by filename rather than as an installed package.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from iphone_guide_chatbot.config.logging_config import setup_logging
from iphone_guide_chatbot.rag.graph import build_state_graph
from iphone_guide_chatbot.rag.prompts import UNSUPPORTED_ANSWER
from iphone_guide_chatbot.ui.presentation import format_answer, format_source


logger = logging.getLogger(__name__)
APP_NAME = "iPhone Guide Assistant"
WELCOME_MESSAGE = """# iPhone Guide Assistant

Explore the supplied **iPhone User Guide**.

Ask a question about the guide. Answers are grounded in retrieved passages and
include PDF page references.

Try: *How can I connect my iPhone to a Wi-Fi network?*
"""


@cl.on_chat_start
async def start_chat():
    setup_logging()
    cl.user_session.set("graph", build_state_graph())
    cl.user_session.set("conversation_history", [])
    cl.user_session.set("message_lock", asyncio.Lock())
    await cl.Message(content=WELCOME_MESSAGE, author=APP_NAME).send()


@cl.on_message
async def on_message(message: cl.Message):
    question = message.content.strip()
    if not question:
        await cl.Message(content="Please enter a question about the iPhone guide.", author=APP_NAME).send()
        return

    # The lock and history belong to this session, never to the whole server.
    async with cl.user_session.get("message_lock"):
        history = list(cl.user_session.get("conversation_history", []))
        history.append({"role": "user", "content": question})
        cl.user_session.set("conversation_history", history)
        graph = cl.user_session.get("graph")
        elements = []
        try:
            async with cl.Step(name="Searching the iPhone User Guide", type="tool", show_input=False) as step:
                result = await graph.ainvoke({
                    "question": question,
                    "conversation_history": history,
                    "messages": history,
                    "retrieved_chunks": [],
                    "answer": "",
                    "status": "retrieving",
                })
                cl.user_session.set("last_result", result)
                chunks = result.get("retrieved_chunks", [])
                citations = result.get("citations", [])
                answer = result.get("answer", "")
                if result.get("status") == "error" or answer.strip() == UNSUPPORTED_ANSWER:
                    citations = []
                content = format_answer(answer, citations)
                cited_sources = {citation["source_number"] for citation in citations}
                elements = [
                    cl.Text(name=f"Source {rank}", content=format_source(chunk, rank), display="side")
                    for rank, chunk in enumerate(chunks, start=1)
                    if rank in cited_sources
                ]
                if result.get("status") == "error":
                    step.is_error = True
                    step.output = "The guide search or answer generation failed."
                else:
                    step.output = f"Retrieved {len(chunks)} excerpts and generated an answer."
        except Exception as error:
            logger.error("UI request failed (%s)", type(error).__name__)
            content = "I couldn't retrieve the guide excerpts or generate an answer. Please try again."

        if not elements:
            await cl.ElementSidebar.set_elements([])
        await cl.Message(content=content, author=APP_NAME, elements=elements).send()
        history.append({"role": "assistant", "content": content})
        cl.user_session.set("conversation_history", history)

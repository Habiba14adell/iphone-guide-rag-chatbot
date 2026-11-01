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
from iphone_guide_chatbot.ui.presentation import format_response, format_source


logger = logging.getLogger(__name__)
APP_NAME = "iPhone Guide Assistant"
WELCOME_MESSAGE = """# iPhone Guide Assistant

Explore the supplied **iPhone User Guide**.

Ask a question to inspect passages from the guide and their PDF page references.
**Answer generation is not configured yet** — retrieved excerpts are shown for
inspection, not as generated answers.

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
                if result.get("status") == "error":
                    step.is_error = True
                    step.output = "The guide search could not be completed."
                    content = "I couldn't retrieve the guide excerpts. Please try again. Answer generation is not configured yet."
                else:
                    chunks = result.get("retrieved_chunks", [])
                    step.output = f"Retrieved {len(chunks)} excerpts."
                    content = format_response(chunks)
                    elements = [cl.Text(name=f"Source {rank}", content=format_source(chunk, rank), display="side")
                                for rank, chunk in enumerate(chunks, start=1)]
        except Exception as error:
            logger.error("UI request failed (%s)", type(error).__name__)
            content = "The guide search could not be completed. Please try again. Answer generation is not configured yet."

        await cl.Message(content=content, author=APP_NAME, elements=elements).send()
        history.append({"role": "assistant", "content": content})
        cl.user_session.set("conversation_history", history)

from typing import Any
from typing_extensions import TypedDict, NotRequired

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from typing import Annotated


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    conversation_history: list[dict[str, str]]
    retrieved_chunks: list[dict[str, Any]]
    question: str
    is_relevant: NotRequired[bool]
    relevance_reason: NotRequired[str]
    answer: str
    status: str
    citations: NotRequired[list[dict[str, Any]]]




    



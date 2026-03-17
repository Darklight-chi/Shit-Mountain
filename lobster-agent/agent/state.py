"""Agent state definition for LangGraph."""

from typing import TypedDict, Optional


class AgentState(TypedDict):
    message: str
    channel: str
    session_id: str
    user_id: str
    history: list[dict]
    locale: str
    intent: str
    risk_level: str
    tool_results: str
    reply: str
    needs_handoff: bool
    conversation_id: Optional[int]

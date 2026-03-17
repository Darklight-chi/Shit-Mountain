"""Escalation / handoff tool."""

from conversation.escalation import EscalationManager

esc_mgr = EscalationManager()


def escalate(conversation_id: int, reason: str, summary: str,
             priority: str = "high", locale: str = "zh") -> str:
    """Create ticket and return handoff message."""
    esc_mgr.create_ticket(conversation_id, reason, summary, priority)
    return esc_mgr.handoff_message(locale)

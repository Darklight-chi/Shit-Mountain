"""Human handoff / escalation logic."""

from database.repository import TicketRepo
from loguru import logger

ticket_repo = TicketRepo()


class EscalationManager:
    def create_ticket(self, conversation_id: int, reason: str,
                      summary: str, priority: str = "high") -> int:
        tid = ticket_repo.create(conversation_id, reason, summary, priority)
        logger.warning(f"Ticket #{tid} created — reason: {reason}, priority: {priority}")
        return tid

    @staticmethod
    def handoff_message(locale: str = "zh") -> str:
        if locale == "zh":
            return "您的问题已记录，我现在为您转接人工客服，请稍等。"
        return "Your issue has been noted. Let me transfer you to a human agent. Please hold on."

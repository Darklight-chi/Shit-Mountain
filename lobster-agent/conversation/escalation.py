"""Human handoff / escalation logic."""

from loguru import logger

from database.repository import ConversationRepo, TicketRepo

ticket_repo = TicketRepo()
conversation_repo = ConversationRepo()


class EscalationManager:
    def create_ticket(self, conversation_id: int, reason: str,
                      summary: str, priority: str = "high") -> int:
        tid = ticket_repo.create(conversation_id, reason, summary, priority)
        logger.warning(f"Ticket #{tid} created — reason: {reason}, priority: {priority}")
        return tid

    def accept_ticket(self, session_id: str) -> dict | None:
        conversation = conversation_repo.get_by_session_id(session_id)
        if not conversation:
            return None

        ticket = ticket_repo.get_latest_by_conversation(conversation["id"])
        if ticket:
            ticket_repo.update_status(ticket["id"], "in_progress")

        conversation_repo.update(
            session_id,
            status="escalated",
            needs_handoff=True,
        )
        return {
            "session": conversation,
            "ticket": ticket_repo.get_latest_by_conversation(conversation["id"]),
        }

    def resolve_ticket(self, session_id: str, resolution_note: str = "") -> dict | None:
        conversation = conversation_repo.get_by_session_id(session_id)
        if not conversation:
            return None

        ticket = ticket_repo.get_latest_by_conversation(conversation["id"])
        updated_summary = conversation.get("summary", "") or ""
        if resolution_note:
            updated_summary = (
                f"{updated_summary} | resolution={resolution_note}"
                if updated_summary else f"resolution={resolution_note}"
            )

        if ticket:
            ticket_repo.update_status(ticket["id"], "resolved", updated_summary or None)

        conversation_repo.update(
            session_id,
            status="resolved",
            needs_handoff=False,
            summary=updated_summary or conversation.get("summary"),
        )
        return {
            "session": conversation_repo.get_by_session_id(session_id),
            "ticket": ticket_repo.get_latest_by_conversation(conversation["id"]),
        }

    def list_escalated(self) -> list[dict]:
        sessions = conversation_repo.list_by_status("escalated")
        result = []
        for session in sessions:
            ticket = ticket_repo.get_latest_by_conversation(session["id"])
            result.append({"session": session, "ticket": ticket})
        return result

    @staticmethod
    def handoff_message(locale: str = "zh") -> str:
        if locale == "zh":
            return "您的问题已记录，我现在为您转接人工客服，请稍等。"
        return "Your issue has been noted. Let me transfer you to a human agent. Please hold on."

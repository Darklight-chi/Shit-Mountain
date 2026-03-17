"""Simple handoff operations CLI for live support follow-up."""

import sys

from conversation.escalation import EscalationManager

esc_mgr = EscalationManager()


def run_handoff_cli(argv: list[str]):
    if not argv or argv[0] in {"help", "-h", "--help"}:
        _print_usage()
        return

    command = argv[0]

    if command == "list":
        escalated = esc_mgr.list_escalated()
        if not escalated:
            print("No escalated sessions.")
            return
        for item in escalated:
            session = item["session"]
            ticket = item.get("ticket") or {}
            print(
                f"{session['session_id']} | {session['channel']} | "
                f"ticket={ticket.get('id', '-')} | status={ticket.get('status', '-')} | "
                f"{session.get('summary', '') or '-'}"
            )
        return

    if len(argv) < 2:
        _print_usage()
        return

    session_id = argv[1]

    if command == "accept":
        result = esc_mgr.accept_ticket(session_id)
        if not result:
            print(f"Session not found: {session_id}")
            return
        ticket = result.get("ticket") or {}
        print(
            f"Accepted session {session_id}. "
            f"ticket={ticket.get('id', '-')} status={ticket.get('status', '-')}"
        )
        return

    if command == "resolve":
        note = " ".join(argv[2:]).strip()
        result = esc_mgr.resolve_ticket(session_id, note)
        if not result:
            print(f"Session not found: {session_id}")
            return
        ticket = result.get("ticket") or {}
        print(
            f"Resolved session {session_id}. "
            f"ticket={ticket.get('id', '-')} status={ticket.get('status', '-')}"
        )
        return

    _print_usage()


def _print_usage():
    print("Usage:")
    print("  python -m app.main handoff list")
    print("  python -m app.main handoff accept <session_id>")
    print("  python -m app.main handoff resolve <session_id> [resolution note]")


if __name__ == "__main__":
    run_handoff_cli(sys.argv[1:])

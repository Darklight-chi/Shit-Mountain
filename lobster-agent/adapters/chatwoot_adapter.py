"""Chatwoot bridge adapter backed by local JSONL inbox/outbox files."""

from adapters.jsonl_channel_adapter import JsonlChannelAdapter
from config.settings import CHATWOOT_INBOX_PATH, CHATWOOT_OUTBOX_PATH


class ChatwootAdapter(JsonlChannelAdapter):
    channel_name = "chatwoot"

    def __init__(self):
        super().__init__(
            inbox_path=CHATWOOT_INBOX_PATH,
            outbox_path=CHATWOOT_OUTBOX_PATH,
            channel_name=self.channel_name,
        )

"""Shopify bridge adapter backed by local JSONL inbox/outbox files."""

from adapters.jsonl_channel_adapter import JsonlChannelAdapter
from config.settings import SHOPIFY_INBOX_PATH, SHOPIFY_OUTBOX_PATH


class ShopifyChatAdapter(JsonlChannelAdapter):
    channel_name = "shopify"

    def __init__(self):
        super().__init__(
            inbox_path=SHOPIFY_INBOX_PATH,
            outbox_path=SHOPIFY_OUTBOX_PATH,
            channel_name=self.channel_name,
        )

"""Message deduplication to prevent double-processing."""

import time


class Deduplicator:
    def __init__(self, ttl: int = 300):
        self._seen: dict[str, float] = {}
        self._ttl = ttl

    def is_duplicate(self, channel: str, session_id: str, content: str) -> bool:
        key = f"{channel}:{session_id}:{hash(content)}"
        now = time.time()
        # Clean expired
        self._seen = {k: v for k, v in self._seen.items() if now - v < self._ttl}
        if key in self._seen:
            return True
        self._seen[key] = now
        return False

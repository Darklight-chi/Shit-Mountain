"""Message deduplication to prevent double-processing."""

import time
import hashlib


class Deduplicator:
    def __init__(self, ttl: int = 300):
        self._seen: dict[str, float] = {}
        self._ttl = ttl

    def is_duplicate(
        self,
        channel: str,
        session_id: str,
        content: str,
        message_id: str = "",
        timestamp: str = "",
        author: str = "",
    ) -> bool:
        basis = message_id.strip() or f"{author.strip()}|{timestamp.strip()}|{content.strip()}"
        digest = hashlib.sha1(basis.encode("utf-8")).hexdigest()
        key = f"{channel}:{session_id}:{digest}"
        now = time.time()
        # Clean expired
        self._seen = {k: v for k, v in self._seen.items() if now - v < self._ttl}
        if key in self._seen:
            return True
        self._seen[key] = now
        return False

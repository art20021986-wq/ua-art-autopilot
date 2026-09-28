"""Bounded, thread-safe per-process admission control; no network dependency."""
from collections import OrderedDict
from threading import Lock
import time


class RateLimit:
    def __init__(self, limit, *, seconds=60, capacity=4096, clock=time.monotonic):
        if min(limit, seconds, capacity) <= 0:
            raise ValueError('Positive rate-limit settings required')
        self.limit, self.seconds, self.capacity = limit, seconds, capacity
        self.clock = clock
        self._entries = OrderedDict()
        self._lock = Lock()

    def allow(self, key):
        now = self.clock()
        with self._lock:
            while self._entries:
                oldest, (expires, _) = next(iter(self._entries.items()))
                if expires > now:
                    break
                del self._entries[oldest]
            current = self._entries.get(key)
            if current is None:
                # Refuse new identities at capacity; do not evict a live limit.
                if len(self._entries) >= self.capacity:
                    return False
                self._entries[key] = (now + self.seconds, 1)
                return True
            expires, count = current
            if count >= self.limit:
                return False
            self._entries[key] = (expires, count + 1)
            return True

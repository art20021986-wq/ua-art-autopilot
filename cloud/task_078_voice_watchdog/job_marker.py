"""Bounded job-marker store (no text/audio/PII persisted).

Stores only: chat_id, message_id, file_unique_id, card_id, field, attempt,
state, created_at, updated_at. Used so a restart can safely replay exactly
once and so failures release the marker instead of poisoning
`crm_voice_seen` forever.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from typing import Dict, Optional


class JobState(str, Enum):
    PENDING = "pending"
    ATTEMPT_1 = "attempt_1"
    ATTEMPT_2 = "attempt_2"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class JobMarker:
    chat_id: int
    message_id: int
    file_unique_id: str
    card_id: Optional[str]
    field: Optional[str]
    attempt: int = 0
    state: JobState = JobState.PENDING
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class JobMarkerStore:
    """In-memory bounded store keyed by (chat_id, file_unique_id).

    A real deployment should back this with a small bounded table (e.g. a
    row per marker with TTL cleanup), never raw audio/text.
    """

    def __init__(self):
        self._lock = Lock()
        self._markers: Dict[tuple, JobMarker] = {}
        self._tombstones: Dict[tuple, float] = {}  # success idempotency

    @staticmethod
    def _key(chat_id: int, file_unique_id: str) -> tuple:
        return (chat_id, file_unique_id)

    def start_or_get(self, chat_id: int, message_id: int, file_unique_id: str,
                      card_id: Optional[str], field_name: Optional[str]) -> JobMarker:
        key = self._key(chat_id, file_unique_id)
        with self._lock:
            if key in self._tombstones:
                # already succeeded once -> exactly-once replay guard
                m = JobMarker(chat_id, message_id, file_unique_id, card_id, field_name,
                               attempt=0, state=JobState.SUCCESS)
                return m
            existing = self._markers.get(key)
            if existing and existing.state not in (JobState.FAILED,):
                return existing
            m = JobMarker(chat_id, message_id, file_unique_id, card_id, field_name)
            self._markers[key] = m
            return m

    def mark_attempt(self, chat_id: int, file_unique_id: str, attempt: int) -> None:
        key = self._key(chat_id, file_unique_id)
        with self._lock:
            m = self._markers.get(key)
            if not m:
                return
            m.attempt = attempt
            m.state = JobState.ATTEMPT_1 if attempt == 1 else JobState.ATTEMPT_2
            m.updated_at = time.time()

    def mark_success(self, chat_id: int, file_unique_id: str) -> None:
        key = self._key(chat_id, file_unique_id)
        with self._lock:
            m = self._markers.pop(key, None)
            self._tombstones[key] = time.time()

    def release_failure(self, chat_id: int, file_unique_id: str) -> None:
        """Marker becomes retryable; NOT persisted as permanent seen."""
        key = self._key(chat_id, file_unique_id)
        with self._lock:
            m = self._markers.get(key)
            if m:
                m.state = JobState.FAILED
                m.updated_at = time.time()

    def already_succeeded(self, chat_id: int, file_unique_id: str) -> bool:
        key = self._key(chat_id, file_unique_id)
        with self._lock:
            return key in self._tombstones

    def is_retryable(self, chat_id: int, file_unique_id: str) -> bool:
        key = self._key(chat_id, file_unique_id)
        with self._lock:
            m = self._markers.get(key)
            return bool(m and m.state == JobState.FAILED)

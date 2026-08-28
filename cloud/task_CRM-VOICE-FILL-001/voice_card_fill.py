"""
CRM-VOICE-FILL-001

Voice-to-card autofill service for the CRM bot.

This module is a self-contained, dependency-free implementation of the
business logic requested in task_CRM-VOICE-FILL-001. It does NOT touch
crm.db, the site, or UA-0009 directly. It defines an abstraction
(CardRepository) that the real bot integration layer must implement on
top of the existing CRM data access code. Wiring this module into the
live Telegram bot and restarting the bot process is a deployment step
that must be performed through the existing owner-approved deployment
pipeline, not by writing directly to production from this repository.

Requirements implemented:

1. Voice from an OPEN card modifies ONLY that card's card_id.
2. Without an open card, voice does NOT create a new card; the bot asks
   the user to select a card first.
3. Empty fields are filled. Already-filled fields are changed only when
   the transcript contains an explicit overwrite intent keyword
   ("измени", "исправь", "замени", "поменяй").
4. Exactly one transcription call per voice message, capped at a 15
   second recognition budget. Zero LLM tokens are used -- field
   extraction is done with deterministic keyword/pattern matching, not
   with a language model.
5. Re-processing the same Telegram message_id does not re-apply the
   write; the cached result is returned instead.
6. After a successful write, the last voice-driven change can be
   undone with undo_last().
7. Leaving to the card list or the main menu resets the active card
   for that user (handle_list_navigation / handle_menu_navigation).

The field-name mapping in _DEFAULT_FIELD_KEYWORDS is an example mapping
for demonstration and tests ("привод" -> "drive_type"). The production
keyword-to-CRM-field mapping must be reviewed against the actual UA ART
CRM field schema before this module is wired into the bot; that review
is outside the scope of this code delivery and does not require any
production or crm.db write to perform.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Protocol


# ---------------------------------------------------------------------------
# Abstractions the real bot/CRM integration layer must provide.
# ---------------------------------------------------------------------------

class Transcriber(Protocol):
    def transcribe(self, audio_bytes: bytes, timeout_seconds: int) -> Optional[str]:
        """Return the recognized text, or None if recognition failed or
        exceeded the timeout. Must be called at most once per voice
        message by the caller (VoiceCardFillService enforces this via
        message_id deduplication).
        """
        ...


class CardRepository(Protocol):
    def get_card(self, card_id: str) -> Dict[str, Optional[str]]:
        ...

    def update_card(self, card_id: str, fields: Dict[str, str]) -> None:
        ...


# ---------------------------------------------------------------------------
# Deterministic, zero-LLM field extraction.
# ---------------------------------------------------------------------------

# Example keyword -> (field_name, value_extractor) mapping.
# This is illustrative; the production mapping must match the real CRM
# schema and should be reviewed before deployment.
_DEFAULT_FIELD_KEYWORDS: Dict[str, str] = {
    "привод передний": "drive_type",
    "привод задний": "drive_type",
    "полный привод": "drive_type",
}

_OVERWRITE_KEYWORDS = ("измени", "исправь", "замени", "поменяй")


def default_parse_fields(text: str) -> Dict[str, str]:
    """Deterministic keyword-based extraction. No LLM calls, no tokens."""
    low = text.lower().strip()
    result: Dict[str, str] = {}
    for phrase, field_name in _DEFAULT_FIELD_KEYWORDS.items():
        if phrase in low:
            result[field_name] = phrase.split(" ", 1)[-1] if " " in phrase else phrase
            # store the full recognized phrase as the value, e.g. "передний"
            parts = phrase.split(" ")
            result[field_name] = parts[-1]
    return result


def is_overwrite_intent(text: str) -> bool:
    low = text.lower()
    return any(k in low for k in _OVERWRITE_KEYWORDS)


# ---------------------------------------------------------------------------
# Core service
# ---------------------------------------------------------------------------

@dataclass
class UndoEntry:
    user_id: str
    card_id: str
    prev_fields: Dict[str, Optional[str]]
    applied_fields: Dict[str, str]


@dataclass
class VoiceCardFillService:
    transcriber: Transcriber
    card_repo: CardRepository
    parse_fields: Callable[[str], Dict[str, str]] = default_parse_fields
    recognition_timeout_seconds: int = 15

    _active_card: Dict[str, str] = field(default_factory=dict)
    _processed_messages: Dict[str, dict] = field(default_factory=dict)
    _undo_stack: Dict[str, List[UndoEntry]] = field(default_factory=dict)

    # -- active card lifecycle -------------------------------------------------

    def open_card(self, user_id: str, card_id: str) -> None:
        """Called when the user opens a specific card in the bot UI."""
        self._active_card[user_id] = card_id

    def get_active_card(self, user_id: str) -> Optional[str]:
        return self._active_card.get(user_id)

    def reset_active_card(self, user_id: str) -> None:
        self._active_card.pop(user_id, None)

    def handle_list_navigation(self, user_id: str) -> None:
        """Called when the user goes back to the card list."""
        self.reset_active_card(user_id)

    def handle_menu_navigation(self, user_id: str) -> None:
        """Called when the user goes back to the main menu."""
        self.reset_active_card(user_id)

    # -- voice handling ----------------------------------------------------

    def handle_voice_message(
        self, user_id: str, message_id: str, audio_bytes: bytes
    ) -> dict:
        """Process one Telegram voice message.

        Returns a dict describing the outcome. Guarantees:
        - at most one transcription call per message_id
        - re-delivery of the same message_id never re-applies a write
        - without an active card, no card is created; user is asked to
          pick one
        """
        if message_id in self._processed_messages:
            cached = dict(self._processed_messages[message_id])
            cached["deduplicated"] = True
            return cached

        card_id = self._active_card.get(user_id)
        if not card_id:
            result = {
                "status": "no_active_card",
                "message": "Сначала откройте карточку, к которой нужно добавить голосовую запись.",
            }
            self._processed_messages[message_id] = result
            return result

        transcript = self._transcribe_once(audio_bytes)
        if transcript is None:
            result = {
                "status": "transcription_failed",
                "message": "Не удалось распознать голос за 15 секунд.",
            }
            self._processed_messages[message_id] = result
            return result

        force_overwrite = is_overwrite_intent(transcript)
        parsed_fields = self.parse_fields(transcript)

        if not parsed_fields:
            result = {
                "status": "no_fields_recognized",
                "card_id": card_id,
                "transcript": transcript,
            }
            self._processed_messages[message_id] = result
            return result

        card = self.card_repo.get_card(card_id)
        prev_fields: Dict[str, Optional[str]] = {}
        applied: Dict[str, str] = {}
        for field_name, value in parsed_fields.items():
            current_value = card.get(field_name)
            is_empty = current_value is None or str(current_value).strip() == ""
            if force_overwrite or is_empty:
                prev_fields[field_name] = current_value
                applied[field_name] = value

        if applied:
            self.card_repo.update_card(card_id, applied)
            entry = UndoEntry(
                user_id=user_id,
                card_id=card_id,
                prev_fields=prev_fields,
                applied_fields=applied,
            )
            self._undo_stack.setdefault(user_id, []).append(entry)
            status = "applied"
        else:
            status = "no_change"

        result = {
            "status": status,
            "card_id": card_id,
            "applied_fields": applied,
            "transcript": transcript,
        }
        self._processed_messages[message_id] = result
        return result

    def _transcribe_once(self, audio_bytes: bytes) -> Optional[str]:
        start = time.monotonic()
        text = self.transcriber.transcribe(
            audio_bytes, timeout_seconds=self.recognition_timeout_seconds
        )
        elapsed = time.monotonic() - start
        if elapsed > self.recognition_timeout_seconds:
            return None
        return text

    # -- undo ----------------------------------------------------------------

    def undo_last(self, user_id: str) -> dict:
        stack = self._undo_stack.get(user_id)
        if not stack:
            return {"status": "nothing_to_undo"}
        entry = stack.pop()
        self.card_repo.update_card(entry.card_id, entry.prev_fields)
        return {"status": "undone", "card_id": entry.card_id}

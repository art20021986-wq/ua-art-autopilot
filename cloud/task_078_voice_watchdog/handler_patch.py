"""Reference-contract implementation of the patched voice branch.

This is NOT a blind in-place patch of an unseen production file. It is the
target behavior that `installer.py` will diff/apply against the *actually
fetched* `cars_ui.py::catch_message`, once Gate A confirms the real source.
Any operator applying this must confirm the handler order (voice/audio,
text, photo, buttons) and the exact card-write (CAS) call signature against
the real file first.

Contract implemented here (task_078):
1. timeout from voice_object.duration via killable_stt_worker.compute_stt_timeout
2. STT in killable subprocess (killable_stt_worker.KillableSTTWorker)
3. max 2 attempts, one automatic restart, transcription cannot write fields itself
4. exactly one CAS write, only after exactly one successful transcription
5. bounded job marker before/after processing (job_marker.py)
6. after 2 failures: one failure message + "Повторить голосовое" button;
   bot stays responsive for text/buttons (no blocking wait here)
7. full-process restart is out of scope of this handler (see controller.py)
8. circuit breaker consulted before starting any new STT job
9. crm_voice_seen: released on failure, tombstoned only on success
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from .circuit_breaker import STTCircuitBreaker
from .job_marker import JobMarkerStore
from .killable_stt_worker import (
    KillableSTTWorker,
    compute_download_timeout,
    compute_stt_timeout,
)

RETRY_BUTTON_TEXT = "Повторить голосовое"


class VoiceWatchdogHandler:
    """Drop-in replacement logic for the voice/audio branch of catch_message.

    `transcribe_fn` must be a pure function: bytes/path -> text. It must NOT
    touch the CRM card. `write_card_fn` performs the single CAS write and is
    only called once, after one successful transcription.
    """

    def __init__(
        self,
        transcribe_fn: Callable[..., str],
        write_card_fn: Callable[[int, str, str, str], None],
        send_message_fn: Callable[[int, str, Optional[list]], None],
        marker_store: Optional[JobMarkerStore] = None,
        breaker: Optional[STTCircuitBreaker] = None,
    ):
        self._worker = KillableSTTWorker(transcribe_fn)
        self._write_card_fn = write_card_fn
        self._send_message_fn = send_message_fn
        self._markers = marker_store or JobMarkerStore()
        self._breaker = breaker or STTCircuitBreaker()

    def handle_voice(
        self,
        chat_id: int,
        message_id: int,
        file_unique_id: str,
        card_id: Optional[str],
        field_name: Optional[str],
        duration_seconds: Optional[float],
        audio_ref: Any,
    ) -> str:
        """Returns a short status string for tests: 'success' | 'failed' |
        'duplicate_success' | 'breaker_open'.
        """
        if self._markers.already_succeeded(chat_id, file_unique_id):
            # exactly-once replay guard: do not re-run STT or re-write card
            return "duplicate_success"

        if self._breaker.is_open():
            self._send_message_fn(
                chat_id,
                "Голосовой ввод временно недоступен, попробуйте текстом.",
                None,
            )
            return "breaker_open"

        marker = self._markers.start_or_get(
            chat_id, message_id, file_unique_id, card_id, field_name
        )

        timeout = compute_stt_timeout(duration_seconds)
        outcome = self._worker.run_with_single_restart(timeout, args=(audio_ref,))

        if outcome.status == "timeout":
            self._breaker.record_hang()

        if outcome.status != "ok":
            self._markers.release_failure(chat_id, file_unique_id)
            self._send_message_fn(
                chat_id,
                "Не удалось распознать голосовое сообщение.",
                [RETRY_BUTTON_TEXT],
            )
            return "failed"

        text = outcome.payload
        self._markers.mark_success(chat_id, file_unique_id)
        if card_id and field_name:
            self._write_card_fn(chat_id, card_id, field_name, text)
        self._send_message_fn(chat_id, "Готово.", None)
        return "success"

"""
Offline unit tests for voice_card_fill.py (CRM-VOICE-FILL-001).

These tests use in-memory fakes only. No crm.db, no network, no
production access.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from voice_card_fill import VoiceCardFillService  # noqa: E402


class FakeTranscriber:
    def __init__(self, script=None):
        self.script = script or {}
        self.calls = 0

    def transcribe(self, audio_bytes, timeout_seconds):
        self.calls += 1
        return self.script.get(audio_bytes)


class FakeCardRepo:
    def __init__(self, cards):
        self.cards = cards
        self.update_calls = []

    def get_card(self, card_id):
        return dict(self.cards.get(card_id, {}))

    def update_card(self, card_id, fields):
        self.update_calls.append((card_id, dict(fields)))
        self.cards.setdefault(card_id, {}).update(fields)


class VoiceCardFillTests(unittest.TestCase):
    def setUp(self):
        self.cards = {"UA-0009": {"drive_type": None, "engine": "2.0"}}
        self.repo = FakeCardRepo(self.cards)

    def test_no_active_card_does_not_create_card(self):
        transcriber = FakeTranscriber({b"audio1": "привод передний"})
        service = VoiceCardFillService(transcriber=transcriber, card_repo=self.repo)

        result = service.handle_voice_message("user1", "msg1", b"audio1")

        self.assertEqual(result["status"], "no_active_card")
        self.assertEqual(len(self.repo.cards), 1)
        self.assertEqual(self.repo.update_calls, [])

    def test_voice_fills_only_open_card(self):
        self.cards["UA-0010"] = {"drive_type": None}
        transcriber = FakeTranscriber({b"audio1": "привод передний"})
        service = VoiceCardFillService(transcriber=transcriber, card_repo=self.repo)

        service.open_card("user1", "UA-0009")
        result = service.handle_voice_message("user1", "msg1", b"audio1")

        self.assertEqual(result["status"], "applied")
        self.assertEqual(result["card_id"], "UA-0009")
        self.assertEqual(self.repo.cards["UA-0009"]["drive_type"], "передний")
        self.assertIsNone(self.repo.cards["UA-0010"]["drive_type"])
        self.assertEqual(len(self.repo.cards), 2)  # no new card created

    def test_filled_field_not_overwritten_without_keyword(self):
        self.cards["UA-0009"]["drive_type"] = "задний"
        transcriber = FakeTranscriber({b"audio1": "привод передний"})
        service = VoiceCardFillService(transcriber=transcriber, card_repo=self.repo)
        service.open_card("user1", "UA-0009")

        result = service.handle_voice_message("user1", "msg1", b"audio1")

        self.assertEqual(result["status"], "no_change")
        self.assertEqual(self.repo.cards["UA-0009"]["drive_type"], "задний")

    def test_overwrite_keyword_changes_filled_field(self):
        self.cards["UA-0009"]["drive_type"] = "задний"
        transcriber = FakeTranscriber({b"audio1": "исправь привод передний"})
        service = VoiceCardFillService(transcriber=transcriber, card_repo=self.repo)
        service.open_card("user1", "UA-0009")

        result = service.handle_voice_message("user1", "msg1", b"audio1")

        self.assertEqual(result["status"], "applied")
        self.assertEqual(self.repo.cards["UA-0009"]["drive_type"], "передний")

    def test_duplicate_message_id_does_not_reapply(self):
        transcriber = FakeTranscriber({b"audio1": "привод передний"})
        service = VoiceCardFillService(transcriber=transcriber, card_repo=self.repo)
        service.open_card("user1", "UA-0009")

        first = service.handle_voice_message("user1", "msg1", b"audio1")
        second = service.handle_voice_message("user1", "msg1", b"audio1")

        self.assertEqual(first["status"], "applied")
        self.assertEqual(second["status"], "applied")
        self.assertTrue(second["deduplicated"])
        self.assertEqual(transcriber.calls, 1)
        self.assertEqual(len(self.repo.update_calls), 1)

    def test_undo_last_reverts_change(self):
        transcriber = FakeTranscriber({b"audio1": "привод передний"})
        service = VoiceCardFillService(transcriber=transcriber, card_repo=self.repo)
        service.open_card("user1", "UA-0009")

        service.handle_voice_message("user1", "msg1", b"audio1")
        self.assertEqual(self.repo.cards["UA-0009"]["drive_type"], "передний")

        undo_result = service.undo_last("user1")

        self.assertEqual(undo_result["status"], "undone")
        self.assertIsNone(self.repo.cards["UA-0009"]["drive_type"])

    def test_undo_with_no_history(self):
        transcriber = FakeTranscriber({})
        service = VoiceCardFillService(transcriber=transcriber, card_repo=self.repo)

        result = service.undo_last("user_never_did_anything")

        self.assertEqual(result["status"], "nothing_to_undo")

    def test_list_navigation_resets_active_card(self):
        transcriber = FakeTranscriber({b"audio1": "привод передний"})
        service = VoiceCardFillService(transcriber=transcriber, card_repo=self.repo)
        service.open_card("user1", "UA-0009")

        service.handle_list_navigation("user1")
        result = service.handle_voice_message("user1", "msg1", b"audio1")

        self.assertEqual(result["status"], "no_active_card")

    def test_menu_navigation_resets_active_card(self):
        transcriber = FakeTranscriber({b"audio1": "привод передний"})
        service = VoiceCardFillService(transcriber=transcriber, card_repo=self.repo)
        service.open_card("user1", "UA-0009")

        service.handle_menu_navigation("user1")
        result = service.handle_voice_message("user1", "msg1", b"audio1")

        self.assertEqual(result["status"], "no_active_card")

    def test_transcription_failure_reported(self):
        transcriber = FakeTranscriber({})  # returns None for unknown audio
        service = VoiceCardFillService(transcriber=transcriber, card_repo=self.repo)
        service.open_card("user1", "UA-0009")

        result = service.handle_voice_message("user1", "msg1", b"unrecognized_audio")

        self.assertEqual(result["status"], "transcription_failed")
        self.assertEqual(transcriber.calls, 1)

    def test_acceptance_privod_peredniy_does_not_increase_card_count(self):
        """Acceptance: 'привод передний' in an open UA-0009 augments UA-0009
        and does not increase the number of cards."""
        before_count = len(self.repo.cards)
        transcriber = FakeTranscriber({b"audio1": "привод передний"})
        service = VoiceCardFillService(transcriber=transcriber, card_repo=self.repo)
        service.open_card("user1", "UA-0009")

        result = service.handle_voice_message("user1", "msg1", b"audio1")

        self.assertEqual(result["status"], "applied")
        self.assertEqual(result["card_id"], "UA-0009")
        self.assertEqual(len(self.repo.cards), before_count)
        self.assertEqual(self.repo.cards["UA-0009"]["drive_type"], "передний")


if __name__ == "__main__":
    unittest.main()

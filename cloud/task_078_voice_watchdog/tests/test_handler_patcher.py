#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import sys
import unittest

BASE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

import handler_patcher as p  # noqa: E402


FIXTURE = '''async def catch_message(update, context):
    import asyncio
    import time
    import ai
    msg = update.effective_message
    voice_object = msg.voice or msg.audio or msg.video_note
    wait = context.user_data.get("car_wait")
    input_text = ""
    thinking = None
    voice_elapsed = None
    if voice_object:
        active_id = 19
        marker = "1:2"
        seen = []
        started = time.monotonic()
        hard_deadline = started + 4.65
        thinking = await msg.reply_text("old")
        if not ai.voice_enabled():
            raise ApplicationHandlerStop
        if msg.voice:
            file_id, filename = msg.voice.file_id, "voice.ogg"
        elif msg.audio:
            file_id, filename = msg.audio.file_id, "audio.mp3"
        else:
            file_id, filename = msg.video_note.file_id, "video_note.mp4"
        async def download_voice(fid):
            return b"x"
        input_text = await asyncio.wait_for(
            asyncio.to_thread(ai.transcribe, b"x", filename), timeout=1)
        if not input_text:
            raise ApplicationHandlerStop

    if not wait:
        return
'''


class HandlerPatcherTests(unittest.TestCase):
    def test_replaces_fixed_deadline_and_non_killable_thread(self):
        candidate = p.patch_function_fixture(FIXTURE)
        self.assertNotIn("hard_deadline = started + 4.65", candidate)
        self.assertNotIn("asyncio.to_thread(ai.transcribe", candidate)
        self.assertIn("transcribe_with_restart", candidate)
        self.assertIn("duration_seconds", candidate)
        compile(candidate, "fixture.py", "exec")

    def test_unrelated_suffix_preserved(self):
        candidate = p.patch_function_fixture(FIXTURE)
        self.assertTrue(candidate.endswith("    if not wait:\n        return\n"))

    def test_unknown_fixture_fails_closed(self):
        with self.assertRaises(p.PatchError):
            p.patch_function_fixture(FIXTURE.replace("4.65", "9.99"))

    def test_full_source_sha_gate_fails_on_synthetic(self):
        with self.assertRaisesRegex(p.PatchError, "FULL_SHA_MISMATCH"):
            p.build_candidate(FIXTURE)


if __name__ == "__main__":
    unittest.main()

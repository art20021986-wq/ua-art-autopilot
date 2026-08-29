#!/usr/bin/env python3
"""Exact live-anchored in-memory patch for cars_ui.catch_message.

No file is written by this module.  Gate B must separately back up and install
the returned candidate after verifying both the full-file and function SHA.
"""
from __future__ import annotations

import ast
import hashlib


AUDITED_FULL_SHA256 = "50f1cb15b6e1ec3a35878a3021beb362a87f3607ac46abf3eb44566023b14306"
AUDITED_FUNCTION_SHA256 = "152d00158bcd097f61fad4e795340f45113724217b481d56ab32f358549a4fd5"
START = "        started = time.monotonic()\n        hard_deadline = started + 4.65\n"
END = "\n    if not wait:\n"


class PatchError(RuntimeError):
    pass


NEW_BLOCK = r'''        import crm_voice_watchdog as _v178_voice

        started = time.monotonic()
        duration_seconds = int(getattr(voice_object, "duration", 0) or 0)
        timeout_seconds = _v178_voice.timeout_for_duration(duration_seconds)
        thinking = await msg.reply_text(
            "🎤 Распознаю голосовое. Для этой длины лимит до %d секунд..."
            % timeout_seconds)
        if not ai.voice_enabled():
            if marker in seen:
                seen.remove(marker)
            await thinking.edit_text("Расшифровка голоса не настроена. Карточка не изменена.")
            raise ApplicationHandlerStop
        try:
            import crm_online_guard as _v168_guard
            if not _v168_guard.circuit_allows("stt"):
                if marker in seen:
                    seen.remove(marker)
                await thinking.edit_text(
                    "Сервис распознавания восстанавливается. Карточка не изменена; "
                    "повторите через 15 секунд.")
                raise ApplicationHandlerStop
        except ApplicationHandlerStop:
            raise
        except Exception:
            pass

        if msg.voice:
            file_id, filename = msg.voice.file_id, "voice.ogg"
        elif msg.audio:
            file_id, filename = msg.audio.file_id, "audio.mp3"
        else:
            file_id, filename = msg.video_note.file_id, "video_note.mp4"

        async def download_voice(fid):
            tg_file = await context.bot.get_file(fid)
            return bytes(await tg_file.download_as_bytearray())

        _v178_result = None
        try:
            audio_bytes = await asyncio.wait_for(
                download_voice(file_id),
                timeout=_v178_voice.download_timeout_for_duration(duration_seconds),
            )
            _v178_result = await _v178_voice.transcribe_with_restart(
                audio_bytes, filename, duration_seconds)
            input_text = (_v178_result.text if _v178_result.ok else "").strip()
        except asyncio.CancelledError:
            raise
        except asyncio.TimeoutError:
            input_text = ""
            log.warning("CRM voice download timeout card=%s", active_id)
        except Exception as e:
            input_text = ""
            log.warning("CRM voice watchdog failed card=%s error=%s", active_id, e)
        voice_elapsed = time.monotonic() - started
        try:
            import crm_online_guard as _v168_guard
            _v168_guard.circuit_result("stt", bool(input_text))
            _v168_guard.record_timing(
                "crm_voice", voice_elapsed, "ok" if input_text else "empty",
                card_id=active_id)
        except Exception:
            pass
        if not input_text:
            if marker in seen:
                seen.remove(marker)
            attempts = getattr(_v178_result, "attempts", 0) if _v178_result else 0
            restarts = (getattr(_v178_result, "restarted_workers", 0)
                        if _v178_result else 0)
            await thinking.edit_text(
                "Голосовое не распознано. Попыток: %d; автоматических "
                "перезапусков: %d. Карточка не изменена; отправьте голосовое ещё раз."
                % (max(attempts, 1), restarts),
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                    "🎤 Повторить голосовое", callback_data="car_open:%d" % active_id)]]))
            raise ApplicationHandlerStop
'''


def sha_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _function_span(source: str, name: str) -> tuple[int, int, str]:
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    matches = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]
    if len(matches) != 1:
        raise PatchError("FUNCTION_COUNT:%s:%d" % (name, len(matches)))
    node = matches[0]
    start = offsets[node.lineno - 1]
    end = offsets[node.end_lineno]
    return start, end, source[start:end]


def build_candidate(source: str, *, require_full_sha: bool = True) -> str:
    if "crm_voice_watchdog as _v178_voice" in source:
        compile(source, "cars_ui.py", "exec")
        return source
    if require_full_sha and sha_text(source) != AUDITED_FULL_SHA256:
        raise PatchError("FULL_SHA_MISMATCH")
    start, end, function = _function_span(source, "catch_message")
    if sha_text(function) != AUDITED_FUNCTION_SHA256:
        raise PatchError("FUNCTION_SHA_MISMATCH")
    if function.count(START) != 1 or function.count(END) != 1:
        raise PatchError("VOICE_BLOCK_ANCHOR_MISMATCH")
    block_start = function.index(START)
    block_end = function.index(END, block_start)
    patched_function = function[:block_start] + NEW_BLOCK + function[block_end:]
    if "asyncio.to_thread(ai.transcribe" in patched_function:
        raise PatchError("NON_KILLABLE_STT_REMAINS")
    if "hard_deadline = started + 4.65" in patched_function:
        raise PatchError("FIXED_DEADLINE_REMAINS")
    candidate = source[:start] + patched_function + source[end:]
    compile(candidate, "cars_ui.py", "exec")
    return candidate


def patch_function_fixture(function_source: str) -> str:
    """Test helper: patch an exact function fixture without full-file SHA."""
    if function_source.count(START) != 1 or function_source.count(END) != 1:
        raise PatchError("VOICE_BLOCK_ANCHOR_MISMATCH")
    begin = function_source.index(START)
    finish = function_source.index(END, begin)
    return function_source[:begin] + NEW_BLOCK + function_source[finish:]

#!/usr/bin/env python3
"""Fail-closed source patch for TASK 072's Telegram description route."""
from __future__ import annotations

import hashlib


EXPECTED_LIVE_SHA256 = "862baea2ca0794f5e0d83bc04169f6d2fdec401f86f384ef4376e373c02a776b"
PATCH_MARKER = "CRM-DESCRIPTION-SAVE-072-V2"


DESCRIPTION_ANCHOR = '''    if wait and input_text:
        context.user_data.pop("car_wait", None)
        field = wait["field"]
'''


DESCRIPTION_REPLACEMENT = '''    # CRM-DESCRIPTION-SAVE-072-V2: a selected existing card only.
    if wait and input_text and wait.get("field") in ("condition_text", "description"):
        import crm_description_writer as _ua072_description
        _ua072_card_id = int(wait["card_id"])
        _ua072_chat_id = getattr(msg, "chat_id", None) or update.effective_chat.id
        _ua072_operation_id = "%s:%s" % (_ua072_chat_id, msg.message_id)
        try:
            _ua072_result = await asyncio.to_thread(
                _ua072_description.save_or_enqueue,
                db.DB_FILE,
                db.DB_FILE + ".description_queue.sqlite3",
                _ua072_card_id,
                input_text,
                user_id,
                _ua072_operation_id,
            )
        except Exception as _ua072_exc:
            log.warning(
                "CRM description save failed card=%s type=%s",
                _ua072_card_id,
                type(_ua072_exc).__name__,
            )
            _ua072_answer = _ua072_description.safe_user_message(_ua072_exc)
            _ua072_rows = [[InlineKeyboardButton(
                "Отмена", callback_data="car_open:%d" % _ua072_card_id)]]
        else:
            _ua072_status = _ua072_result["status"]
            if _ua072_status == "saved":
                context.user_data.pop("car_wait", None)
                _ua072_answer = (
                    "✅ Описание сохранено · %d пунктов, %d знаков"
                    % (_ua072_result["lines"], _ua072_result["characters"])
                )
                _ua072_rows = [[InlineKeyboardButton(
                    "Изменить снова",
                    callback_data="car_setf:%d:condition_text" % _ua072_card_id)]]
            elif _ua072_status == "superseded":
                _ua072_answer = (
                    "Более новое описание уже принято. Эта старая отправка не перезаписала карточку."
                )
                _ua072_rows = [[InlineKeyboardButton(
                    "← Вернуться к карточке",
                    callback_data="car_open:%d" % _ua072_card_id)]]
            else:
                # The durable queue owns the text.  Keep the edit mode until a
                # confirmed CRM read-back; the user does not need to resend it.
                _ua072_answer = (
                    "⏳ Описание принято и сохранится автоматически. "
                    "Повторно отправлять текст не нужно."
                )
                _ua072_rows = [[InlineKeyboardButton(
                    "← Вернуться к карточке",
                    callback_data="car_open:%d" % _ua072_card_id)]]
        _ua072_rows.append([InlineKeyboardButton(
            "← К карточке авто", callback_data="car_open:%d" % _ua072_card_id)])
        if thinking:
            await thinking.edit_text(
                _ua072_answer, reply_markup=InlineKeyboardMarkup(_ua072_rows))
        else:
            await msg.reply_text(
                _ua072_answer, reply_markup=InlineKeyboardMarkup(_ua072_rows))
        raise ApplicationHandlerStop

    if wait and input_text:
        context.user_data.pop("car_wait", None)
        field = wait["field"]
'''


DIAG_ANCHOR = '''        if ok and field in ("condition_text", "diag_text"):
            zapisano = input_text
            punktov = len([s for s in zapisano.split("\\n") if s.strip()])
            answer = ("Описание сохранено · %d пунктов, %d знаков\\n\\n%s"
                      % (punktov, len(zapisano), zapisano))
            rows.insert(0, [InlineKeyboardButton(
                "Изменить снова",
                callback_data="car_setf:%d:condition_text" % wait["card_id"])])
'''


DIAG_REPLACEMENT = '''        if ok and field == "diag_text":
            zapisano = input_text
            punktov = len([s for s in zapisano.split("\\n") if s.strip()])
            answer = ("Диагностика сохранена · %d пунктов, %d знаков"
                      % (punktov, len(zapisano)))
            rows.insert(0, [InlineKeyboardButton(
                "Изменить снова",
                callback_data="car_setf:%d:diag_text" % wait["card_id"])])
'''


class PatchRefused(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise PatchRefused("%s_anchor_count_%d" % (label, count))
    return source.replace(old, new, 1)


def patch_source(data: bytes, *, require_live_sha: bool = True) -> bytes:
    actual = sha256_bytes(data)
    if require_live_sha and actual != EXPECTED_LIVE_SHA256:
        raise PatchRefused("live_sha_drift")
    source = data.decode("utf-8")
    if PATCH_MARKER in source:
        raise PatchRefused("already_patched")
    source = _replace_once(
        source, DESCRIPTION_ANCHOR, DESCRIPTION_REPLACEMENT, "description"
    )
    source = _replace_once(source, DIAG_ANCHOR, DIAG_REPLACEMENT, "diagnostic")
    compile(source, "cars_ui.py", "exec")
    return source.encode("utf-8")


if __name__ == "__main__":
    raise SystemExit("Import patch_source from the guarded Gate A/Gate B controller.")


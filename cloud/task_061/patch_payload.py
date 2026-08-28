#!/usr/bin/env python3
"""Exact owner-intake function replacement for CRM-AI-CARD-001."""


RUN_AI_DRAFT_SOURCE = r'''async def run_ai_draft(update, context, inbox_id, kind, text, file_id):
    """Open a schema-closed CRM draft from photo, text, or voice."""
    import asyncio
    import time
    import ai_fast_schema as fast
    import local_ocr

    msg = update.message
    if ai.is_stopped():
        await msg.reply_text("🛑 ИИ остановлен. Включите ИИ в главном меню.")
        return

    started = time.monotonic()
    hard_deadline = started + 15.0
    data = {}
    thinking = None
    allowed = fast.car_fields(ai_filter)

    async def download_bytes(fid):
        tg_file = await context.bot.get_file(fid)
        return bytes(await tg_file.download_as_bytearray())

    if kind in ("voice", "audio", "video_note") and file_id:
        thinking = await msg.reply_text("🎤 ИИ распознаёт, до 15 секунд...")
        if not ai.voice_enabled():
            await thinking.edit_text("🎤 Расшифровка голоса не настроена.")
            return
        try:
            remaining = max(0.1, hard_deadline - time.monotonic())
            audio = await asyncio.wait_for(download_bytes(file_id), timeout=min(3.0, remaining))
            remaining = max(0.1, hard_deadline - time.monotonic())
            text = await asyncio.wait_for(
                asyncio.to_thread(ai.transcribe, audio), timeout=remaining
            )
        except asyncio.TimeoutError:
            text = ""
            logging.warning("AI voice hard timeout inbox=%s", inbox_id)
        except Exception as exc:
            text = ""
            logging.error("Voice recognition failed inbox=%s error=%s", inbox_id, exc)
        if text:
            data.update(local_ocr.fields_from_text(text, allowed))
            data.update(fast.fast_text_data(text, ai_filter))

    elif kind in ("photo", "document") and file_id:
        if kind == "document":
            mime = (msg.document.mime_type or "") if msg.document else ""
            if not mime.startswith("image/"):
                await msg.reply_text("📎 Нужен файл-изображение.")
                return
        if msg.media_group_id:
            marker = "ai_mg_%s" % msg.media_group_id
            if context.chat_data.get(marker):
                return
            context.chat_data[marker] = True
        thinking = await msg.reply_text("🖼 ИИ распознаёт, до 15 секунд...")
        try:
            remaining = max(0.1, hard_deadline - time.monotonic())
            image = await asyncio.wait_for(download_bytes(file_id), timeout=remaining)
            remaining = max(0.5, hard_deadline - time.monotonic())
            image_data = await asyncio.wait_for(
                asyncio.to_thread(local_ocr.fields_from_image, image, allowed, remaining),
                timeout=remaining,
            )
            data.update(image_data)
            # A caption is explicit owner input and wins over an OCR ambiguity.
            if (text or "").strip():
                data.update(local_ocr.fields_from_text(text, allowed))
                data.update(fast.fast_text_data(text, ai_filter))
        except asyncio.TimeoutError:
            data = {}
            logging.warning("Local OCR hard timeout inbox=%s", inbox_id)
        except Exception as exc:
            data = {}
            logging.error("Local OCR failed inbox=%s error=%s", inbox_id, exc)

    elif (text or "").strip():
        thinking = await msg.reply_text("🧠 ИИ распознаёт, до 15 секунд...")
        data.update(local_ocr.fields_from_text(text, allowed))
        data.update(fast.fast_text_data(text, ai_filter))

    if data:
        parsed = fast.parsed_from_data(data)
        data = fast.clean_car(parsed, ai_filter, "")
    if data:
        parsed = fast.parsed_from_data(data)
        context.user_data["ai_draft"] = {
            "inbox_id": inbox_id,
            "parsed": parsed,
            "clean_data": data,
            "source_text": "",
            "review": None,
        }
        rows = [[InlineKeyboardButton("✅ Сохранить карточку", callback_data="ai_ok")], [
            InlineKeyboardButton("✏️ Дополнить", callback_data="ai_edit"),
            InlineKeyboardButton("❌ Отменить", callback_data="ai_no"),
        ]]
        elapsed = time.monotonic() - started
        if thinking is None:
            thinking = await msg.reply_text("🧠 ИИ распознаёт, до 15 секунд...")
        await thinking.edit_text(
            "✅ Новая карточка открыта\n\n" + ai_filter.render(data)
            + "\n\n⏱ %.1f с · локально · 0 AI-токенов" % elapsed,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(rows),
        )
        return

    if thinking is None:
        thinking = await msg.reply_text("🧠 ИИ распознаёт, до 15 секунд...")
    await thinking.edit_text(
        "Поля CRM не распознаны. Пришлите более чёткое фото, текст или голос."
    )
'''

#!/usr/bin/env python3
"""Exact production function replacements for TASK 060."""

SHOW_MENU_SOURCE = r'''async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, staff, text=None):
    msg = update.effective_message
    header = text or (
        f"{db.ROLE_LABELS.get(staff['role'], staff['role'])}\n"
        f"Здравствуйте, {staff.get('full_name') or 'коллега'}!"
    )
    if is_owner(staff):
        header += ("\n\nОтправьте текст, фото, скриншот, голосовое или документ. "
                   "ИИ сам распознает только поля CRM и покажет предпросмотр.")
    await msg.reply_text(cars_ui.menu_header(header), parse_mode="HTML",
                         reply_markup=cars_ui.with_stats_button(main_menu(staff)))
'''


INTAKE_SOURCE = r'''async def intake(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner intake is processed by AI only; no staff handoff."""
    staff = who(update)
    msg = update.message

    if not staff:
        if msg.text and await try_invite_code(update, context):
            return
        await msg.reply_text(
            "Нет доступа. Отправьте код приглашения или обратитесь к руководителю."
        )
        return

    if not is_owner(staff) and msg.text:
        await do_search(update, context, msg.text)
        return
    if not is_owner(staff):
        await msg.reply_text("Входящую информацию в систему добавляет владелец.")
        return

    kind, file_id = detect_kind(msg)
    text = msg.text or msg.caption
    if msg.contact:
        text = f"Контакт: {msg.contact.first_name} {msg.contact.phone_number}"

    inbox_id = db.add_inbox(
        from_user_id=staff["user_id"],
        kind=kind,
        text=text,
        file_id=file_id,
        media_group=msg.media_group_id,
        tg_chat_id=msg.chat_id,
        tg_message_id=msg.message_id,
    )
    await run_ai_draft(update, context, inbox_id, kind, text, file_id)
'''


RUN_AI_DRAFT_SOURCE = r'''async def run_ai_draft(update, context, inbox_id, kind, text, file_id):
    """Token-free photo/text parser; voice uses existing transcription only."""
    import asyncio
    import time
    import ai_fast_schema as fast
    import local_ocr

    msg = update.message
    if ai.is_stopped():
        await msg.reply_text("🛑 ИИ остановлен. Включите ИИ в главном меню.")
        return

    started = time.monotonic()
    data = {}
    thinking = None
    allowed = fast.car_fields(ai_filter)

    async def download_bytes(fid):
        tg_file = await context.bot.get_file(fid)
        return bytes(await tg_file.download_as_bytearray())

    if kind in ("voice", "audio", "video_note") and file_id:
        thinking = await msg.reply_text("🎤 ИИ распознаёт голос...")
        if not ai.voice_enabled():
            await thinking.edit_text("🎤 Расшифровка голоса не настроена.")
            return
        try:
            audio = await asyncio.wait_for(download_bytes(file_id), timeout=2.5)
            text = await asyncio.wait_for(
                asyncio.to_thread(ai.transcribe, audio), timeout=7.0
            )
        except asyncio.TimeoutError:
            text = ""
            logging.warning("AI voice hard timeout inbox=%s", inbox_id)
        except Exception as exc:
            text = ""
            logging.error("Не распознал голос: %s", exc)
        if text:
            data.update(local_ocr.fields_from_text(text, allowed))
            data.update(fast.fast_text_data(text, ai_filter))

    elif kind in ("photo", "document") and file_id:
        mime = "image/jpeg"
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
        thinking = await msg.reply_text("🖼 ИИ распознаёт, до 7 секунд...")
        deadline = started + 7.0
        try:
            image = await asyncio.wait_for(
                download_bytes(file_id), timeout=max(0.1, deadline - time.monotonic())
            )
            remaining = max(0.5, deadline - time.monotonic())
            data = await asyncio.wait_for(
                asyncio.to_thread(local_ocr.fields_from_image, image, allowed, remaining),
                timeout=remaining,
            )
        except asyncio.TimeoutError:
            data = {}
            logging.warning("Local OCR hard timeout inbox=%s", inbox_id)
        except Exception as exc:
            data = {}
            logging.error("Local OCR failed inbox=%s error=%s", inbox_id, exc)

    elif (text or "").strip():
        thinking = await msg.reply_text("🧠 ИИ распознаёт...")
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
        rows = [[InlineKeyboardButton("✅ Разместить", callback_data="ai_ok")], [
            InlineKeyboardButton("✏️ Поправить", callback_data="ai_edit"),
            InlineKeyboardButton("❌ Отменить", callback_data="ai_no"),
        ]]
        elapsed = time.monotonic() - started
        if thinking is None:
            thinking = await msg.reply_text("🧠 ИИ распознаёт...")
        await thinking.edit_text(
            ai_filter.render(data) + "\n\n⏱ %.1f с · локально · 0 AI-токенов" % elapsed,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(rows),
        )
        return

    if thinking is None:
        thinking = await msg.reply_text("🧠 ИИ распознаёт...")
    await thinking.edit_text(
        "ИИ не нашёл читаемых полей CRM. Пришлите более чёткое фото или текст. "
        "Сотруднику запись не передана."
    )
'''

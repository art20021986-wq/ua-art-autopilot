#!/usr/bin/env python3
"""Exact replacement functions for the production ``team_bot.py`` candidate."""

RUN_AI_DRAFT_SOURCE = r'''async def run_ai_draft(update, context, inbox_id, kind, text, file_id):
    """Fast schema-closed intake. No card write before owner confirmation."""
    import asyncio
    import time
    import ai_fast_schema as fast

    if not ai.enabled():
        return
    msg = update.message
    if ai.is_stopped():
        await msg.reply_text(
            "🛑 ИИ остановлен. Запись сохранена в «Необработанное» и ждёт ручной обработки."
        )
        return

    fast.install_prompt(ai, ai_filter)
    started = time.monotonic()
    parsed = None
    data = {}
    thinking = None

    async def download_bytes(fid):
        tg_file = await context.bot.get_file(fid)
        return bytes(await tg_file.download_as_bytearray())

    if kind in ("voice", "audio", "video_note") and file_id:
        if not ai.voice_enabled():
            await msg.reply_text("🎤 Голос сохранён, но расшифровка не настроена.")
            return
        thinking = await msg.reply_text("🎤 Распознаю...")
        try:
            audio = await asyncio.wait_for(download_bytes(file_id), timeout=2.5)
            text = await asyncio.wait_for(
                asyncio.to_thread(ai.transcribe, audio),
                timeout=fast.VOICE_TRANSCRIBE_SECONDS,
            )
        except asyncio.TimeoutError:
            text = ""
            logging.warning("AI voice hard timeout inbox=%s", inbox_id)
        except Exception as exc:
            text = ""
            logging.error("Не распознал голос: %s", exc)
        if not text:
            await thinking.edit_text("🎤 Запись сохранена. За 10 секунд поля CRM не распознаны.")
            return
        with db.connect() as connection:
            connection.execute("UPDATE inbox SET text=? WHERE id=?", ("[расшифровка] " + text, inbox_id))

    if kind in ("photo", "document") and file_id:
        mime = "image/jpeg"
        if kind == "document":
            mime = (msg.document.mime_type or "") if msg.document else ""
            if not mime.startswith("image/"):
                await msg.reply_text("📎 Файл сохранён. Для быстрого разбора пришлите изображение.")
                return
        if msg.media_group_id:
            marker = "ai_mg_%s" % msg.media_group_id
            if context.chat_data.get(marker):
                return
            context.chat_data[marker] = True
        thinking = await msg.reply_text("🖼 Распознаю, до 7 секунд...")
        deadline = started + fast.PHOTO_HARD_SECONDS
        try:
            image = await asyncio.wait_for(
                download_bytes(file_id),
                timeout=max(0.1, deadline - time.monotonic()),
            )
            parsed = await asyncio.wait_for(
                asyncio.to_thread(ai.parse_image, image, caption=text, mime=mime),
                timeout=max(0.1, deadline - time.monotonic()),
            )
        except asyncio.TimeoutError:
            parsed = None
            logging.warning("AI photo hard timeout inbox=%s", inbox_id)
        except Exception as exc:
            parsed = None
            logging.error("Не распознал изображение: %s", exc)
        parsed = fast.sanitize_parsed(parsed, ai_filter, db)
        data = fast.clean_car(parsed, ai_filter, text or "")
        if not data:
            await thinking.edit_text(
                "🖼 Изображение сохранено. За 7 секунд поля CRM не найдены. "
                "Пришлите данные текстом или голосом."
            )
            return

    if parsed is None and (text or "").strip():
        if thinking is None:
            thinking = await msg.reply_text("🧠 Распознаю...")
        quick = fast.fast_text_data(text, ai_filter)
        try:
            parsed = await asyncio.wait_for(
                asyncio.to_thread(ai.parse_message, text),
                timeout=fast.TEXT_HARD_SECONDS,
            )
        except asyncio.TimeoutError:
            parsed = None
            logging.warning("AI text hard timeout inbox=%s", inbox_id)
        except Exception as exc:
            parsed = None
            logging.error("Не распознал текст: %s", exc)
        safe = fast.sanitize_parsed(parsed, ai_filter, db)
        if safe and safe.get("type") == "car":
            data = fast.clean_car(safe, ai_filter, text)
        elif quick:
            data = quick
            safe = fast.parsed_from_data(data)
        parsed = safe

    if data:
        parsed = fast.parsed_from_data(data)
        issues = ai.validate(parsed)
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
        await thinking.edit_text(
            ai_filter.render(data) + "\n\n⏱ %.1f с" % elapsed,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(rows),
        )
        return

    if parsed and parsed.get("type") == "client":
        safe = fast.sanitize_parsed(parsed, ai_filter, db)
        clean_data = ai.to_card_data(safe) if safe else {}
        context.user_data["ai_draft"] = {
            "inbox_id": inbox_id, "parsed": safe, "clean_data": clean_data,
            "source_text": "", "review": None,
        }
        await thinking.edit_text(
            ai_filter.render_from(safe, ai.validate(safe)),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Сохранить", callback_data="ai_ok"),
                InlineKeyboardButton("❌ Отменить", callback_data="ai_no"),
            ]]),
        )
        return

    if thinking is None:
        thinking = await msg.reply_text("🧠 Распознаю...")
    await thinking.edit_text(
        "Запись сохранена. Поля действующей формы CRM не найдены — "
        "пришлите данные автомобиля текстом, фотографией или голосом."
    )
'''


AI_SAVE_SOURCE = r'''async def ai_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import ai_fast_schema as fast

    query = update.callback_query
    await query.answer()
    staff = who(update)
    draft = context.user_data.get("ai_draft")
    if not draft or not staff:
        await query.message.reply_text("Черновик потерялся. Отправьте сообщение заново.")
        return

    parsed = draft.get("parsed") or {}
    table = "cars" if parsed.get("type") == "car" else "clients"
    actor = staff["user_id"]
    if table == "cars":
        data = {
            key: value for key, value in (draft.get("clean_data") or {}).items()
            if key in fast.car_fields(ai_filter)
        }
        if not data:
            await query.message.reply_text("Нет полей автомобиля для сохранения.")
            return
        card_id, number, new_card = ai_filter.store(
            data, actor, draft.get("inbox_id"), card_id=None
        )
        if not card_id:
            await query.message.reply_text("Для новой карточки нужен VIN.")
            return
        db.set_card_review("cars", card_id, db.ST_APPROVED_OWNER, actor, publish=True)
        db.add_comment(
            "cars", card_id, actor,
            "Создано распознаванием из входящего #%s; сохранены только поля CRM."
            % draft.get("inbox_id"),
        )
    else:
        allowed = set(getattr(db, "CLIENT_FIELDS", ()))
        data = {key: value for key, value in (draft.get("clean_data") or {}).items() if key in allowed}
        card_id = db.create_card("clients", data, actor)
        db.link_inbox_card(draft.get("inbox_id"), "clients", card_id, actor)
        db.set_inbox_status(draft.get("inbox_id"), db.ST_APPROVED_OWNER, actor)

    card = db.get_card(table, card_id)
    note = "\nОпубликовано в клиентском каталоге." if table == "cars" else ""
    await query.message.edit_reply_markup(reply_markup=None)
    await query.message.reply_text(
        "✅ Сохранено: %s%s" % (db.card_title(table, card), note),
        reply_markup=main_menu(staff),
    )
    context.user_data.pop("ai_draft", None)
'''


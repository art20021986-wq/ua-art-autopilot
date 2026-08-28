#!/usr/bin/env python3
"""Exact production function replacements for CRM-VOICE-FILL-001."""


VOICE_PLAN_SOURCE = r'''def voice_change_plan(card, data, allowed, override=False):
    """Return bounded field updates; filled values change only by explicit request."""
    changes = []
    skipped = []
    permitted = set(allowed or ())
    for field, value in (data or {}).items():
        if field not in permitted or value in (None, "", []):
            continue
        old = card.get(field)
        if old not in (None, "", 0, []) and not override:
            skipped.append(field)
            continue
        if str(old or "") != str(value):
            changes.append((field, old, value))
    return changes, skipped
'''


VOICE_UNDO_SOURCE = r'''async def voice_undo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Undo only the latest matching voice fill and never create a card."""
    q = update.callback_query
    try:
        _, cid_raw, token = q.data.split(":", 2)
        cid = int(cid_raw)
    except Exception:
        await q.answer("Некорректная команда", show_alert=True)
        raise ApplicationHandlerStop

    saved = context.user_data.get("voice_undo") or {}
    if saved.get("card_id") != cid or str(saved.get("token")) != token:
        await q.answer("Это изменение уже недоступно", show_alert=True)
        raise ApplicationHandlerStop

    card = card_of(cid)
    if not card:
        context.user_data.pop("voice_undo", None)
        await q.answer("Карточка не найдена", show_alert=True)
        raise ApplicationHandlerStop

    restored = []
    for change in saved.get("changes") or []:
        field = change.get("field")
        current = card.get(field)
        if str(current or "") != str(change.get("new") or ""):
            continue
        db.update_card_field("cars", cid, field, change.get("old"), q.from_user.id)
        restored.append(LABELS_ALL.get(field, field))
    context.user_data.pop("voice_undo", None)
    if restored:
        await q.answer("Изменение отменено")
        await q.message.reply_text(
            "↩️ %s: восстановлено — %s" % (
                card.get("auto_number") or "#%d" % cid, ", ".join(restored)),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                "← Вернуться к карточке", callback_data="car_open:%d" % cid)]])
        )
    else:
        await q.answer("Поля уже менялись позже — отмена не выполнена", show_alert=True)
    raise ApplicationHandlerStop
'''


OPEN_CARD_SOURCE = r'''async def open_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    drop_wait(context)
    staff = db.get_staff(q.from_user.id)
    cid = q.data.split(":")[-1]
    card = card_of(cid)
    if not card:
        await q.message.reply_text("Карточка не найдена.")
        raise ApplicationHandlerStop

    await CR.send_photos(q.message, card)
    await q.message.reply_text(render(card, staff), parse_mode="HTML",
                               reply_markup=card_kb(card, staff),
                               disable_web_page_preview=True)
    await CR.send_videos(q.message, card)
    context.user_data["car_last"] = int(cid)
    context.user_data["car_voice_active"] = int(cid)
    raise ApplicationHandlerStop
'''


CARS_LIST_SOURCE = r'''async def cars_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    drop_wait(context)
    context.user_data.pop("car_last", None)
    context.user_data.pop("car_voice_active", None)
    context.user_data.pop("voice_undo", None)
    staff = db.get_staff(q.from_user.id)
    try:
        cards = db.list_cards("cars", limit=30)
    except Exception as e:
        log.warning("Список машин: %s", e)
        return
    if not cards:
        await q.message.reply_text(
            "Автомобилей пока нет. Откройте явное создание новой карточки.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("← Назад", callback_data="menu")]]))
        raise ApplicationHandlerStop

    lines = ["<b>Автомобили</b>", "Нажмите на машину — откроется карточка для правки.", ""]
    rows = []
    for card in cards:
        card = card_of(card["id"]) or card
        nomer = card.get("auto_number") or "#%d" % card["id"]
        name = " ".join(str(x) for x in (card.get("brand"), card.get("model"),
                                         card.get("year")) if x) or "без названия"
        miss = S.missing_required(card)
        sostoyanie = ("черновик, не хватает %d" % len(miss)) if miss else "заполнена"
        etap = S.status_label(card.get("status")) if card.get("status") else "этап не задан"
        lines.append("<b>%s</b> · %s" % (nomer, name))
        lines.append("   %s · %s" % (etap, sostoyanie))
        rows.append([InlineKeyboardButton("%s · %s" % (nomer, name[:28]),
                                          callback_data="car_open:%d" % card["id"])])
    rows.append([InlineKeyboardButton("← Назад", callback_data="menu")])
    await q.message.reply_text("\n".join(lines), parse_mode="HTML",
                               reply_markup=InlineKeyboardMarkup(rows))
    raise ApplicationHandlerStop
'''


MENU_CB_SOURCE = r'''async def menu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.pop("car_last", None)
    context.user_data.pop("car_voice_active", None)
    context.user_data.pop("voice_undo", None)
    staff = who(update)
    if staff:
        await show_menu(update, context, staff)
'''


CATCH_MESSAGE_SOURCE = r'''async def catch_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """CRM-VOICE-FILL-001: voice fills only the explicitly open card."""
    import asyncio
    import time
    import ai
    import ai_fast_schema as fast
    import ai_filter
    import local_ocr

    msg = update.effective_message
    if not msg:
        return
    user_id = update.effective_user.id

    wait = context.user_data.get("car_media_wait")
    if wait:
        target = wait["target"]
        tag = ""
        card = card_of(wait["card_id"])
        if not card:
            context.user_data.pop("car_media_wait", None)
            return
        file_id = None
        if msg.photo:
            file_id = msg.photo[-1].file_id
        elif msg.video:
            file_id = msg.video.file_id
            if target in ("videos", "video_h", "video_v"):
                target = "videos"
                slot = _orient(msg.video)
                tag = {"video_h": "гориз", "video_v": "вертик"}.get(slot, "")
        elif msg.video_note:
            file_id = msg.video_note.file_id
        elif msg.document:
            file_id = msg.document.file_id
        if file_id:
            answer = save_media(card, target, file_id, user_id, tag)
            if answer:
                await msg.reply_text(
                    answer,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("← Вернуться к карточке",
                                              callback_data="car_open:%d" % card["id"])],
                        [InlineKeyboardButton("Фото и видео",
                                              callback_data="car_media:%d" % card["id"])]]))
            raise ApplicationHandlerStop
        if msg.text and target == "diag_report":
            pass
        return

    voice_object = msg.voice or msg.audio or msg.video_note
    input_text = (msg.text or "").strip()
    wait = context.user_data.get("car_wait")
    thinking = None
    voice_elapsed = None

    if voice_object:
        active_id = wait.get("card_id") if wait else context.user_data.get("car_voice_active")
        active_card = card_of(active_id) if active_id else None
        if not active_card:
            context.user_data.pop("car_last", None)
            context.user_data.pop("car_voice_active", None)
            await msg.reply_text(
                "Откройте нужную карточку автомобиля и повторите голосовое. "
                "Новая карточка автоматически не создаётся."
            )
            raise ApplicationHandlerStop

        chat_id = getattr(msg, "chat_id", None) or update.effective_chat.id
        marker = "%s:%s" % (chat_id, msg.message_id)
        seen = context.chat_data.get("crm_voice_seen")
        if not isinstance(seen, list):
            seen = []
            context.chat_data["crm_voice_seen"] = seen
        if marker in seen:
            await msg.reply_text("Это голосовое уже обработано.")
            raise ApplicationHandlerStop
        seen.append(marker)
        del seen[:-20]
        context.user_data.pop("voice_undo", None)

        started = time.monotonic()
        hard_deadline = started + 15.0
        thinking = await msg.reply_text("🎤 Распознаю, до 15 секунд...")
        if not ai.voice_enabled():
            if marker in seen:
                seen.remove(marker)
            await thinking.edit_text("Расшифровка голоса не настроена. Карточка не изменена.")
            raise ApplicationHandlerStop

        if msg.voice:
            file_id, filename = msg.voice.file_id, "voice.ogg"
        elif msg.audio:
            file_id, filename = msg.audio.file_id, "audio.mp3"
        else:
            file_id, filename = msg.video_note.file_id, "video_note.mp4"

        async def download_voice(fid):
            tg_file = await context.bot.get_file(fid)
            return bytes(await tg_file.download_as_bytearray())

        try:
            remaining = max(0.1, hard_deadline - time.monotonic())
            audio_bytes = await asyncio.wait_for(
                download_voice(file_id), timeout=min(3.0, remaining))
            remaining = max(0.1, hard_deadline - time.monotonic())
            input_text = await asyncio.wait_for(
                asyncio.to_thread(ai.transcribe, audio_bytes, filename),
                timeout=remaining,
            )
            input_text = (input_text or "").strip()
        except asyncio.TimeoutError:
            input_text = ""
            log.warning("CRM voice timeout card=%s", active_id)
        except Exception as e:
            input_text = ""
            log.warning("CRM voice recognition failed card=%s error=%s", active_id, e)
        voice_elapsed = time.monotonic() - started
        if not input_text:
            if marker in seen:
                seen.remove(marker)
            await thinking.edit_text(
                "Голос не распознан за 15 секунд. Карточка не изменена; повторите короче."
            )
            raise ApplicationHandlerStop

    if not wait:
        cid = (context.user_data.get("car_voice_active") if voice_object
               else context.user_data.get("car_last"))
        card = card_of(cid) if cid else None
        if card and voice_object:
            allowed = fast.car_fields(ai_filter)
            data = {}
            data.update(local_ocr.fields_from_text(input_text, allowed))
            data.update(fast.fast_text_data(input_text, ai_filter))
            if data:
                data = fast.clean_car(fast.parsed_from_data(data), ai_filter, "")
            data = {key: value for key, value in (data or {}).items()
                    if key in allowed and value not in (None, "", [])}
            folded = input_text.casefold()
            override = any(word in folded for word in (
                "измени", "исправь", "замени", "поменяй", "скорректируй"))
            changes, skipped = voice_change_plan(card, data, allowed, override)
            applied = []
            for field, old, new in changes:
                try:
                    db.update_card_field("cars", card["id"], field, new, user_id)
                    applied.append((field, old, new))
                except Exception as e:
                    log.warning("CRM voice write failed card=%s field=%s error=%s",
                                card["id"], field, e)

            number = card.get("auto_number") or "#%d" % card["id"]
            if applied:
                token = str(msg.message_id)
                context.user_data["voice_undo"] = {
                    "card_id": card["id"], "token": token,
                    "changes": [{"field": f, "old": old, "new": new}
                                for f, old, new in applied],
                }
                value_names = {
                    "fwd": "передний", "rwd": "задний", "4wd": "полный",
                    "automatic": "автомат", "manual": "механика",
                    "gasoline": "бензин", "diesel": "дизель",
                    "hybrid": "гибрид", "electric": "электро", "LPG": "газ",
                }
                lines = []
                for field, _, value in applied:
                    shown = value_names.get(str(value), str(value))
                    lines.append("• %s — %s" % (LABELS_ALL.get(field, field), shown))
                await thinking.edit_text(
                    "✅ %s дополнена:\n%s\n\n⏱ %.1f с · 1 расшифровка · 0 LLM-токенов"
                    % (number, "\n".join(lines), voice_elapsed or 0.0),
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("↩️ Отменить изменение",
                                              callback_data="car_vundo:%d:%s" % (
                                                  card["id"], token))],
                        [InlineKeyboardButton("← Вернуться к карточке",
                                              callback_data="car_open:%d" % card["id"])],
                    ]),
                )
            elif data and skipped and not override:
                await thinking.edit_text(
                    "%s: распознанные поля уже заполнены. "
                    "Для замены скажите: «измени …». Новая карточка не создана." % number
                )
            elif data:
                await thinking.edit_text("%s: новых значений нет. Карточка не изменена." % number)
            else:
                await thinking.edit_text(
                    "Не распознал поле CRM. Назовите поле и значение, например: "
                    "«привод передний». Карточка не изменена."
                )
            raise ApplicationHandlerStop

        if card:
            done = await auto_catch(msg, card, user_id, context)
            if done:
                raise ApplicationHandlerStop

    wait = context.user_data.get("car_wait")
    if wait and input_text and wait.get("client"):
        context.user_data.pop("car_wait", None)
        card = card_of(wait["card_id"])
        klient = client_of(card)
        if klient:
            db.update_card_field("clients", klient["id"], wait["field"],
                                 input_text, user_id)
        answer = "Записано."
        if voice_object:
            answer += " · %.1f с · 1 расшифровка · 0 LLM-токенов" % (voice_elapsed or 0.0)
        if thinking:
            await thinking.edit_text(
                answer,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                    "← К покупателю", callback_data="car_client:%d" % wait["card_id"])],
                    [InlineKeyboardButton("← К карточке авто",
                                          callback_data="car_open:%d" % wait["card_id"])]]))
        else:
            await msg.reply_text(
                answer,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                    "← К покупателю", callback_data="car_client:%d" % wait["card_id"])],
                    [InlineKeyboardButton("← К карточке авто",
                                          callback_data="car_open:%d" % wait["card_id"])]]))
        raise ApplicationHandlerStop

    if wait and input_text:
        context.user_data.pop("car_wait", None)
        field = wait["field"]
        nizhny = input_text.lower()
        if field not in ("price_uah", "condition_text", "diag_text", "diag_link") \
                and ("$" in nizhny or "цена" in nizhny or "стоимость" in nizhny):
            field = "price_uah"
        elif field == "eta_days" and _re.search(r"\d{4,}", nizhny):
            field = "price_uah"
        ok, answer = apply_value(wait["card_id"], field, input_text, user_id)
        card = card_of(wait["card_id"])
        if ok and field == "price_uah" and card:
            remember_price(card, user_id)
            answer = "%s · цена этапа «%s»: %s" % (
                card.get("auto_number") or "", S.status_label(card.get("status")),
                S.money(_int(card.get("price_uah"))))
        rows = [[InlineKeyboardButton("← Вернуться к карточке",
                                      callback_data="car_open:%d" % wait["card_id"])]]
        if ok and field in ("condition_text", "diag_text"):
            zapisano = input_text
            punktov = len([s for s in zapisano.split("\n") if s.strip()])
            answer = ("Описание сохранено · %d пунктов, %d знаков\n\n%s"
                      % (punktov, len(zapisano), zapisano))
            rows.insert(0, [InlineKeyboardButton(
                "Изменить снова",
                callback_data="car_setf:%d:condition_text" % wait["card_id"])])
        if voice_object:
            answer += "\n\n⏱ %.1f с · 1 расшифровка · 0 LLM-токенов" % (voice_elapsed or 0.0)
        if not ok:
            wait["field"] = field
            context.user_data["car_wait"] = wait
            rows.insert(0, [InlineKeyboardButton(
                "Отмена", callback_data="car_open:%d" % wait["card_id"])])
        if thinking:
            await thinking.edit_text(answer, reply_markup=InlineKeyboardMarkup(rows))
        else:
            await msg.reply_text(answer, reply_markup=InlineKeyboardMarkup(rows))
        raise ApplicationHandlerStop
'''


REGISTER_SOURCE = r'''def register(app):
    ensure_columns()
    try:
        import ai_filter
        ai_filter.register(app)
    except Exception as e:
        log.warning("ai_filter не подключён: %s", e)
    try:
        import photo_hide
        photo_hide.register(app)
    except Exception as e:
        log.warning("photo_hide не подключён: %s", e)
    g = -1
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, catch_message), group=g)
    app.add_handler(CallbackQueryHandler(voice_undo, pattern=r"^car_vundo:"), group=g)
    app.add_handler(CallbackQueryHandler(open_card, pattern=r"^card_open:cars:"), group=g)
    app.add_handler(CallbackQueryHandler(open_card, pattern=r"^car_open:"), group=g)
    app.add_handler(CallbackQueryHandler(clear_field, pattern=r"^car_clr:"), group=g)
    app.add_handler(CallbackQueryHandler(diag_clear, pattern=r"^diag_clr:"), group=g)
    app.add_handler(CallbackQueryHandler(cars_list, pattern=r"^cards_cars$"), group=g)
    app.add_handler(CallbackQueryHandler(cars_list, pattern=r"^cars_cards$"), group=g)
    app.add_handler(CallbackQueryHandler(edit_menu, pattern=r"^car_edit:"), group=g)
    app.add_handler(CallbackQueryHandler(edit_ask, pattern=r"^car_setf:"), group=g)
    app.add_handler(CallbackQueryHandler(media_screen, pattern=r"^car_media:"), group=g)
    app.add_handler(CallbackQueryHandler(video_remove_all, pattern=r"^car_vidvseok:"), group=g)
    app.add_handler(CallbackQueryHandler(video_remove_all_ask, pattern=r"^car_vidvse:"), group=g)
    app.add_handler(CallbackQueryHandler(diag_photo_show, pattern=r"^car_dgal:"), group=g)
    app.add_handler(CallbackQueryHandler(diag_video_show, pattern=r"^car_dvid:"), group=g)
    app.add_handler(CallbackQueryHandler(gallery, pattern=r"^car_gal:"), group=g)
    app.add_handler(CallbackQueryHandler(video_gallery, pattern=r"^car_vid:"), group=g)
    app.add_handler(CallbackQueryHandler(photo_remove_menu, pattern=r"^car_rmphoto:"), group=g)
    app.add_handler(CallbackQueryHandler(photo_remove, pattern=r"^car_rmpok:"), group=g)
    app.add_handler(CallbackQueryHandler(
        photo_remove_all_ask, pattern=r"^car_rmvse:"), group=g)
    app.add_handler(CallbackQueryHandler(
        photo_remove_all, pattern=r"^car_rmvse2:"), group=g)
    app.add_handler(CallbackQueryHandler(add_media_start, pattern=r"^car_add:"), group=g)
    app.add_handler(CallbackQueryHandler(condition_screen, pattern=r"^car_cond:"), group=g)
    app.add_handler(CallbackQueryHandler(diag_clear_ask, pattern=r"^diag_ask:"), group=g)
    app.add_handler(CallbackQueryHandler(stage_menu, pattern=r"^car_stage:"), group=g)
    app.add_handler(CallbackQueryHandler(stage_set, pattern=r"^car_setstage:"), group=g)
    app.add_handler(CallbackQueryHandler(price_screen, pattern=r"^car_price:"), group=g)
    app.add_handler(CallbackQueryHandler(keep_price, pattern=r"^car_keepprice:"), group=g)
    app.add_handler(CallbackQueryHandler(save_ai_text, pattern=r"^car_saveai:"), group=g)
    app.add_handler(CallbackQueryHandler(preview, pattern=r"^car_preview:"), group=g)
    app.add_handler(CallbackQueryHandler(preview_demo, pattern=r"^car_demo:"), group=g)
    app.add_handler(CallbackQueryHandler(ad_screen, pattern=r"^car_ad:"), group=g)
    app.add_handler(CallbackQueryHandler(client_screen, pattern=r"^car_client:"), group=g)
    app.add_handler(CallbackQueryHandler(client_ask, pattern=r"^car_setc:"), group=g)
    app.add_handler(CallbackQueryHandler(client_unlink, pattern=r"^car_unclient:"), group=g)
    app.add_handler(CallbackQueryHandler(toggle_publish, pattern=r"^car_pub:"), group=g)
    app.add_handler(CallbackQueryHandler(mark_sold, pattern=r"^car_sold:"), group=g)
    app.add_handler(CallbackQueryHandler(mark_sold_ok, pattern=r"^car_soldok:"), group=g)
    app.add_handler(CallbackQueryHandler(delete_ask, pattern=r"^car_del:"), group=g)
    app.add_handler(CallbackQueryHandler(delete_ok, pattern=r"^car_delok:"), group=g)
    app.add_handler(CallbackQueryHandler(crm_stats, pattern=r"^crm_stats$"), group=g)
    app.add_handler(CallbackQueryHandler(clients_screen, pattern=r"^cards_clients$"), group=g)
    app.add_handler(CallbackQueryHandler(crm_leads, pattern=r"^crm_leads$"), group=g)
    app.add_handler(CallbackQueryHandler(more_screen, pattern=r"^crm_more$"), group=g)
    app.add_handler(CallbackQueryHandler(optimize_screen, pattern=r"^crm_optimize$"), group=g)
    app.add_handler(CallbackQueryHandler(svodka_screen, pattern=r"^crm_svodka$"), group=g)
    app.add_handler(CallbackQueryHandler(crm_stats_week, pattern=r"^crm_stats_week$"), group=g)
    try:
        import konteyner
        konteyner.register(app, -2)
    except Exception as e:
        log.warning("konteyner не подключён: %s", e)
    log.info("cars_ui подключён")
'''

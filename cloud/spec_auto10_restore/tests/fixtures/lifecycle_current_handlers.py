"""Exact observed CRM handler excerpts; no credentials or application state.
These pinned legacy bodies reproduce the actual missing withdrawal paths.
"""
from __future__ import annotations


async def delete_ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await _v168_ack(q,)
    cid = int(q.data.split(":")[-1])
    card = card_of(cid)
    name = "%s %s" % (card.get("auto_number") or "",
                      " ".join(str(x) for x in (card.get("brand"),
                                                card.get("model")) if x))
    await q.message.reply_text(
        "Удалить карточку %s?\nВернуть её будет нельзя. Фото, видео и история "
        "пропадут вместе с ней." % name.strip(),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Да, удалить", callback_data="car_delok:%d" % cid)],
            [InlineKeyboardButton("← Отмена", callback_data="car_open:%d" % cid)]]))
    raise ApplicationHandlerStop

async def delete_ok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await _v168_ack(q,)
    cid = int(q.data.split(":")[-1])
    card = card_of(cid)
    nomer = card.get("auto_number") if card else "#%d" % cid
    try:
        with db.connect() as c:
            c.execute("DELETE FROM cars WHERE id=?", (cid,))
        db.log_action(q.from_user.id, "card_delete", "cars", cid, "auto_number",
                      nomer, None)
    except Exception as e:
        log.warning("Не удалил карточку: %s", e)
        await q.message.reply_text("Не получилось удалить: %s" % e)
        raise ApplicationHandlerStop
    context.user_data.pop("car_last", None)
    await q.message.reply_text(
        "Карточка %s удалена." % nomer,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
            "← Все автомобили", callback_data="cards_cars")]]))
    raise ApplicationHandlerStop

async def mark_sold_ok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await _v168_ack(q,)
    cid = int(q.data.split(":")[-1])
    set_field(cid, "status", "sold", q.from_user.id)
    db.update_card_field("cars", cid, "published", 0, q.from_user.id)
    await q.message.reply_text(
        "Отмечено: продана. Из каталога убрана.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
            "← Вернуться к карточке", callback_data="car_open:%d" % cid)]]))
    raise ApplicationHandlerStop

async def toggle_publish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await _v168_ack(q,)
    cid = int(q.data.split(":")[-1])
    card = card_of(cid)
    actor_id = q.from_user.id
    preimage = _ua083_publish_preimage(card)
    novoe = 0 if card.get("published") else 1
    back = InlineKeyboardMarkup([[InlineKeyboardButton(
        "← Вернуться к карточке", callback_data="car_open:%d" % cid)]])

    if novoe:
        miss = S.missing_required(card)
        if miss:
            await q.message.reply_text(
                "Для показа клиентам не хватает: %s" % ", ".join(miss),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Дозаполнить", callback_data="car_edit:%d" % cid)],
                    [InlineKeyboardButton("← Вернуться к карточке",
                                          callback_data="car_open:%d" % cid)]]))
            raise ApplicationHandlerStop

    try:
        import asyncio as _ua083_asyncio
        import publikaciya as _ua083_publisher

        db.update_card_field("cars", cid, "published", novoe, actor_id)
        if novoe:
            ok, detail = await _ua083_asyncio.to_thread(
                _ua083_publisher.opublikovat, card.get("auto_number"))
            success_text = "Машина видна клиентам в каталоге."
        else:
            ok, detail = await _ua083_asyncio.to_thread(_ua083_publisher.obnovit_katalog)
            success_text = "Машина скрыта от клиентов."
        if ok is not True:
            restored = _ua083_restore_publish_preimage(cid, preimage, actor_id)
            text = str(detail or "Публикация не прошла проверку.")
            if not restored:
                text += " КРИТИЧНО: состояние CRM не удалось восстановить автоматически."
            await q.message.reply_text(text, reply_markup=back)
            raise ApplicationHandlerStop
        await q.message.reply_text(success_text, reply_markup=back)
        raise ApplicationHandlerStop
    except ApplicationHandlerStop:
        raise
    except Exception as exc:
        restored = _ua083_restore_publish_preimage(cid, preimage, actor_id)
        log.exception("TASK083 publication exception for car %s", cid)
        text = "Публикация отменена: %s. Выполнен откат." % exc
        if not restored:
            text += " КРИТИЧНО: состояние CRM не удалось восстановить автоматически."
        await q.message.reply_text(text, reply_markup=back)
        raise ApplicationHandlerStop

"""Function templates inserted into the exact reviewed cars_ui source by the builder."""

async def ad_screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q, staff = await _ua099_require_staff(update)
    cid = int(q.data.split(':')[-1])
    card = _ua099_card(cid)
    miss = S.missing_required(card)
    from ua_delivery_status import stage_number
    if miss or not stage_number(card.get('status')):
        text = ('Сначала заполните: ' + ', '.join(miss)) if miss else (
            'Выберите действующий этап доставки перед публикацией.')
        await q.message.reply_text(text, reply_markup=_ua099_back(cid))
        raise ApplicationHandlerStop
    if context.application.job_queue is None:
        await q.message.reply_text('Публикация не запущена: служба уведомлений недоступна.',
                                   reply_markup=_ua099_back(cid))
        raise ApplicationHandlerStop
    progress = await q.message.reply_text('Запускаю публикацию…', reply_markup=_ua099_back(cid))
    context.application.create_task(
        _ua_oneclick_submit(cid, q.from_user.id, card, progress), update=update)
    raise ApplicationHandlerStop


def _ua_oneclick_prepare(cid, actor_id, expected, chat_id, message_id):
    from ua_crm_public_sync import ROOT, snapshot, start, notify
    from ua_publish_requests import enqueue
    from ua_delivery_status import stage_number
    card = _ua099_card(cid)
    if (card.get('status') != expected.get('status') or
            (expected.get('published') == 1 and card.get('published') != 1)):
        raise ValueError('CARD_CHANGED_BEFORE_REQUEST')
    if S.missing_required(card) or not stage_number(card.get('status')):
        raise ValueError('CARD_NOT_READY')
    # Use the existing audited DB API. Publication intent is never a toggle.
    if card.get('published') != 1:
        db.update_card_field('cars', cid, 'published', 1, actor_id)
    revision = snapshot().get(str(cid))
    if not revision or revision['delivery_status'] == 'hidden':
        raise ValueError('CARD_NO_LONGER_PUBLIC')
    token = enqueue(ROOT, cid, revision, chat_id, message_id)
    start()
    notify()
    return token


async def _ua_oneclick_submit(cid, actor_id, expected, progress):
    import asyncio
    try:
        await asyncio.to_thread(_ua_oneclick_prepare, cid, actor_id, expected,
                                progress.chat_id, progress.message_id)
        # Completion is delivered by the persistent receipt job. Do not edit here:
        # a fast worker may already have delivered its final result.
    except Exception:
        log.exception('One-click publication request failed for %s', cid)
        await progress.edit_text(
            'Не удалось подтвердить запуск публикации. Данные сохранены. '
            'Откройте карточку и повторите «Разместить объявление».',
            reply_markup=_ua099_back(cid))


def _ua_oneclick_verified(receipt):
    from ua_crm_public_sync import snapshot
    from ua_public_freshness import verify_public
    revision = snapshot().get(receipt['identity'])
    if not revision or revision['delivery_status'] == 'hidden':
        return False
    if revision['sha256'] != receipt['verified_revision']:
        return False
    verify_public(receipt['code'])
    return snapshot().get(receipt['identity']) == revision


async def _ua_oneclick_receipts(context):
    import asyncio
    from ua_crm_public_sync import ROOT, snapshot, notify, start
    import ua_publish_requests as requests
    start()
    for receipt in await asyncio.to_thread(requests.receipts, ROOT):
        try:
            live = await asyncio.to_thread(requests.current, ROOT, receipt['token'])
            if live != receipt:
                continue
            if receipt['state'] == 'verified':
                try:
                    fresh = await asyncio.to_thread(_ua_oneclick_verified, receipt)
                except Exception:
                    fresh = False
                if not fresh:
                    revision = (await asyncio.to_thread(snapshot)).get(receipt['identity'])
                    if revision and revision['delivery_status'] != 'hidden':
                        await asyncio.to_thread(requests.enqueue, ROOT, receipt['identity'],
                            revision, receipt['chat_id'], receipt['message_id'])
                        notify()
                        continue
                    text = 'Публикация отменена: карточка удалена, скрыта или перенесена в архив.'
                else:
                    text = ('✅ Объявление опубликовано на сайте.\n'
                            'https://www.uaart.com.ua/video/%s.html' % receipt['code'])
            else:
                text = 'Публикация отменена: карточка удалена, скрыта или перенесена в архив.'
            # Recheck after network verification so a newer request is not acknowledged.
            if await asyncio.to_thread(requests.current, ROOT, receipt['token']) != receipt:
                continue
            try:
                await context.bot.edit_message_text(text=text,
                    chat_id=receipt['chat_id'], message_id=receipt['message_id'],
                    reply_markup=_ua099_back(int(receipt['identity'])),
                    disable_web_page_preview=True)
            except Exception as exc:
                if 'message is not modified' not in str(exc).lower():
                    raise
            await asyncio.to_thread(requests.delivered, ROOT, receipt['token'])
            if receipt['state'] == 'verified' and fresh:
                _ua_emergency_schedule_spec(receipt['code'])
        except Exception:
            # A Telegram outage never undoes a publication or loses its receipt.
            log.exception('Publication receipt delivery will retry')


async def preview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q, staff = await _ua099_require_staff(update)
    cid = int(q.data.split(':')[-1])
    await q.message.reply_text('Предпросмотр убран. Откройте карточку автомобиля.',
                               reply_markup=_ua099_back(cid))
    raise ApplicationHandlerStop

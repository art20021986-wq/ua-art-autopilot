"""Auction clients in the CRM bot (JPAUTO-KOREA-001, owner 2026-11-10/11): «🔨 Клиенты аукциона» in the main menu
(statistics, «➕ Создать клиента», «👥 Клиенты с доступом · N», «📋 Ставки по датам»); the first two also stay in
«👤 Клиенты → 🔨 Аукционы онлайн → 🇰🇷 Корея». A client's card lists the client's bids by date.

Telegram glue only: records in ua_auction_clients, texts in ua_auction_clients_view, access rules and buttons from
ua_crm_orders (the same staff as «Клиенты»). Multi-step input keeps a draft in context.user_data[WAIT]; any menu button
cancels it, as in the rest of the bot.
Owner 2026-11-12: «🔨 Ставка за клиента» in the client card (lot, amount, the same checks as a bid from the site;
the manager opens the lot and places the bid themselves on the auction, then «✅ Поставил» records it with the
manager — nothing is sent to the auction from the server, variant А) and «👔 По менеджерам» on the home screen.
The draft is taken before recording, so a second tap records nothing.
"""
import asyncio
import re

import ua_auction_bids as bids
import ua_auction_clients as store
import ua_auction_clients_view as view
import ua_auction_stats as stats
import ua_crm_orders as orders

WAIT = 'auction_client'
BACK = view.HOME[1]  # «Назад» from the client list: the «🔨 Клиенты аукциона» screen


def folder_rows():
    """Rows the «🇰🇷 Корея» folder shows above its back button."""
    return [[view.NEW], [('👥 Клиенты с доступом · %d' % len(store.all_clients()), view.LIST)]]


def _markup(rows):
    """Inline buttons: (label, callback data), or (label, 'https://…') for a link."""
    from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as M
    return M([[B(label, url=data) if data.startswith('https://') else B(label, callback_data=data) for label, data in row]
              for row in rows if row])


async def _show(message, screen, edit=None):
    from telegram.error import BadRequest
    markup = _markup(screen['buttons']) if screen['buttons'] else None
    if edit is not None:
        try:
            await edit.edit_message_text(screen['text'], parse_mode='HTML', reply_markup=markup)
            return
        except BadRequest as exc:
            if 'not modified' in str(exc).lower():
                return
    await message.reply_text(screen['text'], parse_mode='HTML', reply_markup=markup)


async def _created(message, screen, forward):
    await _show(message, screen)
    await message.reply_text(forward)  # plain text: ready to forward to the client


def _staff():
    """Telegram id -> the staff member's name (former staff included, so old bids keep their names)."""
    import db
    return {s['user_id']: s.get('full_name') or ('@' + s['username'] if s.get('username') else str(s['user_id']))
            for s in db.list_staff(active_only=False)}


def _names(people):
    return {c['phone']: '%s %s' % (c['surname'], c['name']) for c in people}


def _client_screen(phone):
    client = store.get(phone)
    if client is None:
        raise store.ClientError('not_found')
    return view.card(client, stats.of_client(phone), _staff())


def _day_screen(day):
    if not re.fullmatch(r'\d{4}-\d\d-\d\d', day):
        return view.days_view(stats.days())
    return view.day_view(day, stats.on_day(day), _names(store.all_clients()), _staff())


def _managers_screen():
    return view.managers_view(stats.managers(), _staff())


def _manager_screen(arg):
    if not re.fullmatch(r'[0-9]{1,20}', arg):
        return _managers_screen()
    manager, people = int(arg), store.all_clients()
    own = sum(1 for c in people if c['created_by'] == manager)
    return view.manager_view(manager, own, stats.of_manager(manager, people), _names(people), _staff())


def _bidder(phone):
    """The client a manager may bid for, or ClientError / BidError('blocked')."""
    client = store.get(phone)
    if client is None:
        raise store.ClientError('not_found')
    if client['blocked']:
        raise bids.BidError('blocked')
    return client


def _record(phone, bid, manager):
    """A manager's bid for the client, placed by them on the auction."""
    return bids.by_manager(_bidder(phone), bid, manager)


async def callback(update, context):
    from telegram.ext import ApplicationHandlerStop
    query = update.callback_query
    if not await asyncio.to_thread(orders.allowed, update):
        await query.answer('Недостаточно прав', show_alert=True)
        raise ApplicationHandlerStop
    await query.answer()
    parts = query.data.split(':', 2)
    action, arg = parts[1], (parts[2] if len(parts) > 2 else '')
    draft = context.user_data.get(WAIT)
    try:
        if action == 'home':
            context.user_data.pop(WAIT, None)
            await _show(query.message, view.home(await asyncio.to_thread(stats.summary)), query)
        elif action == 'days':
            context.user_data.pop(WAIT, None)
            await _show(query.message, view.days_view(await asyncio.to_thread(stats.days)), query)
        elif action == 'day':
            context.user_data.pop(WAIT, None)
            await _show(query.message, await asyncio.to_thread(_day_screen, arg), query)
        elif action == 'new':
            context.user_data[WAIT] = {'step': 0, 'values': {}}
            await _show(query.message, view.ask(0))
        elif action == 'city' and draft and view.STEPS[draft.get('step', 0)][0] == 'city':
            await _answer(update, context, arg)
        elif action == 'ok' and draft and draft.get('ready'):
            context.user_data.pop(WAIT, None)
            v = draft['values']
            client, password = await asyncio.to_thread(
                store.create, v['surname'], v['name'], v['phone'], v['email'], v['city'], v['deposit_usd'],
                update.effective_user.id)
            await _created(query.message, *view.created(client, password))
        elif action in ('cancel', 'list'):
            context.user_data.pop(WAIT, None)
            await _show(query.message, view.list_view(await asyncio.to_thread(store.all_clients), BACK), query)
        elif action == 'c':
            context.user_data.pop(WAIT, None)
            await _show(query.message, await asyncio.to_thread(_client_screen, arg), query)
        elif action == 'pw':
            context.user_data.pop(WAIT, None)
            password = await asyncio.to_thread(store.reset_password, arg)
            await _created(query.message, *view.password_changed(await asyncio.to_thread(store.get, arg), password))
        elif action in ('block', 'unblock'):
            context.user_data.pop(WAIT, None)
            await asyncio.to_thread(store.set_blocked, arg, action == 'block')
            screen = await asyncio.to_thread(_client_screen, arg)
            screen['text'] = ('⛔ Доступ закрыт.\n\n' if action == 'block' else '✅ Доступ открыт.\n\n') + screen['text']
            await _show(query.message, screen, query)
        elif action == 'mgrs':
            context.user_data.pop(WAIT, None)
            await _show(query.message, await asyncio.to_thread(_managers_screen), query)
        elif action == 'mgr':
            context.user_data.pop(WAIT, None)
            await _show(query.message, await asyncio.to_thread(_manager_screen, arg), query)
        elif action == 'bid':
            client = await asyncio.to_thread(_bidder, arg)
            context.user_data[WAIT] = {'bid_for': client['phone'], 'lot': None}
            await _show(query.message, view.bid_lot_prompt(client))
        elif action == 'bidok':
            draft = context.user_data.get(WAIT)
            if not (isinstance(draft, dict) and draft.get('bid')):
                await query.message.reply_text('Ставка уже отмечена или отменена.')
                raise ApplicationHandlerStop
            context.user_data.pop(WAIT, None)  # taken before recording: a second tap finds nothing
            from telegram.error import BadRequest
            try:  # the confirm buttons go away; if Telegram refuses, the draft is already taken anyway
                await query.edit_message_reply_markup(reply_markup=None)
            except BadRequest:
                pass
            await asyncio.to_thread(_record, draft['bid_for'], draft['bid'], update.effective_user.id)
            screen = await asyncio.to_thread(_client_screen, draft['bid_for'])
            screen['text'] = view.BID_RECORDED + screen['text']
            await _show(query.message, screen)
        elif action == 'dep':
            client = await asyncio.to_thread(store.get, arg)
            if client is None:
                raise store.ClientError('not_found')
            context.user_data[WAIT] = {'deposit_for': client['phone']}
            await _show(query.message, view.deposit_prompt(client))
    except store.ClientError as error:
        context.user_data.pop(WAIT, None)
        await query.message.reply_text(view.FIELD_ERRORS.get(str(error), 'Ошибка: ' + str(error)))
    except bids.BidError as error:
        context.user_data.pop(WAIT, None)
        await query.message.reply_text(view.BID_ERRORS.get(str(error), 'Ошибка: ' + str(error)))
    raise ApplicationHandlerStop


async def _answer(update, context, text):
    """One answer of the creation dialogue (or the new deposit, or a manager's bid)."""
    draft = context.user_data[WAIT]
    message = update.effective_message
    if 'bid_for' in draft:
        await _bid_answer(context, draft, message, text)
        return
    if 'deposit_for' in draft:
        context.user_data.pop(WAIT, None)
        client = await asyncio.to_thread(store.set_deposit, draft['deposit_for'], text)
        screen = await asyncio.to_thread(_client_screen, client['phone'])
        screen['text'] = '💵 Депозит обновлён.\n\n' + screen['text']
        await _show(message, screen)
        return
    field = view.STEPS[draft['step']][0]
    draft['values'][field] = text.strip()
    draft['step'] += 1
    if draft['step'] < len(view.STEPS):
        await _show(message, view.ask(draft['step']))
        return
    v = draft['values']
    try:
        v['phone'] = store.phone(v['phone'])
        store.deposit(v['deposit_usd'])
    except store.ClientError as error:
        context.user_data.pop(WAIT, None)
        await message.reply_text(view.FIELD_ERRORS.get(str(error), str(error)) + '\nНажмите «➕ Создать клиента» ещё раз.')
        return
    draft['ready'] = True
    await _show(message, view.confirm(v))


async def _bid_answer(context, draft, message, text):
    """The lot, then the amount, of a manager's bid; a wrong answer is asked again, the day limit ends the dialogue."""
    client = await asyncio.to_thread(_bidder, draft['bid_for'])
    answer = re.sub(r'[\s,.₩]', '', text)
    try:
        if draft['lot'] is None:
            if not re.fullmatch(r'[0-9]{6,20}', answer):
                raise bids.BidError('lot')
            lot, _ = await asyncio.to_thread(bids.lot_info, answer)
            draft['lot'] = lot['id']
            await _show(message, view.bid_amount_prompt(client, lot))
            return
        bid = await asyncio.to_thread(bids.check, client, draft['lot'], answer)
    except bids.BidError as error:
        if str(error) == 'day_limit':
            context.user_data.pop(WAIT, None)
        await message.reply_text(view.BID_ERRORS.get(str(error), 'Ошибка: ' + str(error)))
        return
    draft['bid'], draft['ready'] = bid, True
    await _show(message, view.bid_confirm(client, bid, bids.LOT_URL % bid['lot']['id']))


async def text(update, context):
    """The manager's answers while a creation or a deposit change is open; other messages go on."""
    from telegram.ext import ApplicationHandlerStop
    if not isinstance(context.user_data.get(WAIT), dict) or context.user_data[WAIT].get('ready'):
        return
    if not await asyncio.to_thread(orders.allowed, update):
        return
    try:
        await _answer(update, context, update.effective_message.text or '')
    except store.ClientError as error:
        context.user_data.pop(WAIT, None)
        await update.effective_message.reply_text(view.FIELD_ERRORS.get(str(error), str(error)))
    except bids.BidError as error:
        context.user_data.pop(WAIT, None)
        await update.effective_message.reply_text(view.BID_ERRORS.get(str(error), str(error)))
    raise ApplicationHandlerStop


async def cancel(update, context):
    """Any other button or command ends an open dialogue."""
    context.user_data.pop(WAIT, None)


def register(app):
    from telegram.ext import CallbackQueryHandler, MessageHandler, filters
    group = min(app.handlers, default=0) - 1  # an unused group before the bot's own handlers
    app.add_handler(CallbackQueryHandler(callback, pattern=r'^ac:'), group=group)
    try:  # the staff hear about every bid and answer requests (module ua_auction_bids_bot); before the catch-all below
        import ua_auction_bids_bot
        ua_auction_bids_bot.register(app, group)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning('ua_auction_bids_bot не подключён: %s', exc)
    app.add_handler(CallbackQueryHandler(cancel), group=group)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text), group=group)
    app.add_handler(MessageHandler(filters.COMMAND, cancel), group=group)
    return group

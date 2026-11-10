"""Auction clients in the CRM bot (JPAUTO-KOREA-001, owner 2026-11-10): «➕ Создать клиента» and
«👥 Клиенты с доступом · N» in «👤 Клиенты → 🔨 Аукционы онлайн → 🇰🇷 Корея».

Telegram glue only: records in ua_auction_clients, texts in ua_auction_clients_view, access rules and buttons from
ua_crm_orders (the same staff as «Клиенты»). Multi-step input keeps a draft in context.user_data[WAIT]; any menu button
cancels it, as in the rest of the bot.
"""
import asyncio

import ua_auction_clients as store
import ua_auction_clients_view as view
import ua_crm_orders as orders

WAIT = 'auction_client'
BACK = 'co:f:auction_korea'


def folder_rows():
    """Rows the «🇰🇷 Корея» folder shows above its back button."""
    return [[view.NEW], [('👥 Клиенты с доступом · %d' % len(store.all_clients()), view.LIST)]]


async def _show(message, screen, edit=None):
    from telegram.error import BadRequest
    markup = orders.markup(screen['buttons']) if screen['buttons'] else None
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


def _client_screen(phone):
    client = store.get(phone)
    if client is None:
        raise store.ClientError('not_found')
    return view.card(client)


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
        if action == 'new':
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
        elif action == 'cancel':
            context.user_data.pop(WAIT, None)
            await _show(query.message, view.list_view(await asyncio.to_thread(store.all_clients), BACK), query)
        elif action == 'list':
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
            client = await asyncio.to_thread(store.set_blocked, arg, action == 'block')
            screen = view.card(client)
            screen['text'] = ('⛔ Доступ закрыт.\n\n' if action == 'block' else '✅ Доступ открыт.\n\n') + screen['text']
            await _show(query.message, screen, query)
        elif action == 'dep':
            client = await asyncio.to_thread(store.get, arg)
            if client is None:
                raise store.ClientError('not_found')
            context.user_data[WAIT] = {'deposit_for': client['phone']}
            await _show(query.message, view.deposit_prompt(client))
    except store.ClientError as error:
        context.user_data.pop(WAIT, None)
        await query.message.reply_text(view.FIELD_ERRORS.get(str(error), 'Ошибка: ' + str(error)))
    raise ApplicationHandlerStop


async def _answer(update, context, text):
    """One answer of the creation dialogue (or the new deposit)."""
    draft = context.user_data[WAIT]
    message = update.effective_message
    if 'deposit_for' in draft:
        context.user_data.pop(WAIT, None)
        client = await asyncio.to_thread(store.set_deposit, draft['deposit_for'], text)
        screen = view.card(client)
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
        deposit = store.deposit(v['deposit_usd'])
    except store.ClientError as error:
        context.user_data.pop(WAIT, None)
        await message.reply_text(view.FIELD_ERRORS.get(str(error), str(error)) + '\nНажмите «➕ Создать клиента» ещё раз.')
        return
    draft['ready'] = True
    await _show(message, view.confirm(v, store.limit_usd(deposit)))


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
    raise ApplicationHandlerStop


async def cancel(update, context):
    """Any other button or command ends an open dialogue."""
    context.user_data.pop(WAIT, None)


def register(app):
    from telegram.ext import CallbackQueryHandler, MessageHandler, filters
    group = min(app.handlers, default=0) - 1  # an unused group before the bot's own handlers
    app.add_handler(CallbackQueryHandler(callback, pattern=r'^ac:'), group=group)
    app.add_handler(CallbackQueryHandler(cancel), group=group)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text), group=group)
    app.add_handler(MessageHandler(filters.COMMAND, cancel), group=group)
    try:  # JPAUTO-KOREA-001 step В: the staff hear about every client bid (module ua_auction_bids_bot)
        import ua_auction_bids_bot
        ua_auction_bids_bot.register(app)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning('ua_auction_bids_bot не подключён: %s', exc)
    return group

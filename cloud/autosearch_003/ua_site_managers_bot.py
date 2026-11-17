"""Менеджеры сайта в CRM-боте — обработчики (AUTOSEARCH-003, владелец 17.11).

Одна ответственность — Telegram-часть «🧑‍💼 Менеджеры сайта»: список, создание теми же 5 шагами, что клиент, карточка
(пароль, блокировка). Записи — ua_site_managers, тексты — ua_site_managers_view; те же права доступа, что у
«🔨 Клиенты аукциона» (ua_crm_orders.allowed); показ экранов — как у клиентов аукциона (ua_auction_clients_bot._show).
Черновик создания — в context.user_data[WAIT]; любая другая кнопка или команда его отменяет. Регистрируется в группе
раньше обработчиков клиентов аукциона и пропускает дальше всё, что не его.
"""
import asyncio

import ua_crm_orders as orders
import ua_lot_alerts as alerts
import ua_site_managers as managers
import ua_site_managers_view as view

WAIT = 'site_manager'


def _list_screen():
    counts = {}
    for contact in alerts.contacts():
        counts[contact['manager_phone']] = counts.get(contact['manager_phone'], 0) + 1
    return view.list_view(managers.all_managers(), counts)


def _card(phone, maker=None):
    manager = managers.get(phone)
    if manager is None:
        raise managers.ManagerError('not_found')
    import ua_auction_clients_bot as glue
    staff = glue._staff()
    clients = len(alerts.contacts(manager['phone']))
    requests = len(alerts.requests(manager['phone']))
    return (maker or view.card)(manager, clients, requests, staff.get(manager['created_by'], ''))


def _created(manager, password):
    import ua_auction_clients_bot as glue
    return view.created(manager, password, glue._staff().get(manager['created_by'], ''))


async def callback(update, context):
    from telegram.ext import ApplicationHandlerStop
    import ua_auction_clients_bot as glue
    query = update.callback_query
    if not await asyncio.to_thread(orders.allowed, update):
        await query.answer('Недостаточно прав', show_alert=True)
        raise ApplicationHandlerStop
    await query.answer()
    parts = query.data.split(':', 2)
    action, arg = parts[1], (parts[2] if len(parts) > 2 else '')
    draft = context.user_data.get(WAIT)
    try:
        if action == 'list':
            context.user_data.pop(WAIT, None)
            await glue._show(query.message, await asyncio.to_thread(_list_screen), query)
        elif action == 'new':
            context.user_data[WAIT] = {'step': 0, 'values': {}}
            await glue._show(query.message, view.ask(0))
        elif action == 'city' and draft and view.STEPS[draft.get('step', 0)][0] == 'city':
            await _answer(update, context, arg)
        elif action == 'ok' and draft and draft.get('ready'):
            context.user_data.pop(WAIT, None)
            v = draft['values']
            manager, password = await asyncio.to_thread(
                managers.create, v['surname'], v['name'], v['phone'], v['email'], v['city'], update.effective_user.id)
            await glue._created(query.message, *await asyncio.to_thread(_created, manager, password))
        elif action == 'cancel':
            context.user_data.pop(WAIT, None)
            await glue._show(query.message, await asyncio.to_thread(_list_screen), query)
        elif action == 'c':
            context.user_data.pop(WAIT, None)
            await glue._show(query.message, await asyncio.to_thread(_card, arg), query)
        elif action == 'pw':
            context.user_data.pop(WAIT, None)
            password = await asyncio.to_thread(managers.reset_password, arg)
            screen, forward = await asyncio.to_thread(
                _card, arg, lambda m, c, r, s: view.password_changed(m, password, c, r, s))
            await glue._created(query.message, screen, forward)
        elif action in ('block', 'unblock'):
            context.user_data.pop(WAIT, None)
            await asyncio.to_thread(managers.set_blocked, arg, action == 'block')
            await glue._show(query.message, await asyncio.to_thread(_card, arg), query)
    except managers.ManagerError as error:
        context.user_data.pop(WAIT, None)
        await query.message.reply_text(view.ERRORS.get(str(error), 'Ошибка: ' + str(error)))
    raise ApplicationHandlerStop


async def _answer(update, context, text):
    """Один ответ диалога создания менеджера."""
    import ua_auction_clients_bot as glue
    draft = context.user_data[WAIT]
    message = update.effective_message
    draft['values'][view.STEPS[draft['step']][0]] = text.strip()
    draft['step'] += 1
    if draft['step'] < len(view.STEPS):
        await glue._show(message, view.ask(draft['step']))
        return
    v = draft['values']
    try:
        v['phone'] = managers.phone(v['phone'])
    except managers.ManagerError as error:
        context.user_data.pop(WAIT, None)
        await message.reply_text(view.ERRORS.get(str(error), str(error)) + '\nНажмите «➕ Создать менеджера» ещё раз.')
        return
    draft['ready'] = True
    await glue._show(message, view.confirm(v))


async def text(update, context):
    """Ответы, пока открыт диалог создания менеджера; остальные сообщения идут дальше."""
    from telegram.ext import ApplicationHandlerStop
    draft = context.user_data.get(WAIT)
    if not isinstance(draft, dict) or draft.get('ready'):
        return
    if not await asyncio.to_thread(orders.allowed, update):
        return
    await _answer(update, context, update.effective_message.text or '')
    raise ApplicationHandlerStop


async def cancel(update, context):
    """Любая другая кнопка или команда закрывает открытый диалог."""
    context.user_data.pop(WAIT, None)


def register(app, group):
    """Обработчики в группе `group` (раньше обработчиков клиентов аукциона)."""
    from telegram.ext import CallbackQueryHandler, MessageHandler, filters
    app.add_handler(CallbackQueryHandler(callback, pattern=r'^sm:'), group=group)
    app.add_handler(CallbackQueryHandler(cancel), group=group)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text), group=group)
    app.add_handler(MessageHandler(filters.COMMAND, cancel), group=group)

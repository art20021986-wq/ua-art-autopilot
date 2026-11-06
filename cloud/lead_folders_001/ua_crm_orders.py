"""Orders in the CRM bot «👤 Клиенты» (LEAD-FOLDERS-001, owner 2026-11-06): statistics on top, the same ten folders
as the client bot's leads, an order card with the contract and its stages to delivery.

Telegram glue only: orders from ua_order_book, texts from ua_crm_orders_view, contract files from ua_contract_files.
cars_ui's «Клиенты» button calls clients_screen(); register() adds the order buttons. Active staff with the owner,
administrator or manager role may use it.
"""
import asyncio
import logging
import time

import ua_contract_files as files
import ua_crm_orders_view as view
import ua_lead_calendar as cal

log = logging.getLogger(__name__)
WAIT = 'crm_order_note'
_BOOK = None


def _book():
    global _BOOK
    if _BOOK is None:
        import db
        from ua_order_book import OrderBook
        _BOOK = OrderBook(db.connect)
        _BOOK.initialize()
    return _BOOK


def allowed(update):
    import db
    user = update.effective_user
    staff = db.get_staff(user.id) if user else None
    return bool(staff and staff['active'] and staff['role'] in (db.ROLE_OWNER, db.ROLE_ADMIN, db.ROLE_MANAGER))


def _extra_rows():
    rows = [[('Поиск клиента', 'search_start')]]
    try:
        import ua_finance_crm  # FINANCE-001: visits to the finance partners
        rows.append([(ua_finance_crm.BUTTON, ua_finance_crm.CALLBACK)])
    except Exception as exc:
        log.warning('ua_finance_crm: кнопка не добавлена: %s', exc)
    rows.append([('← Назад', 'menu')])
    return rows


def markup(buttons):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    return InlineKeyboardMarkup([[InlineKeyboardButton(b[0], callback_data=b[1]) for b in row] for row in buttons if row])


def home_screen():
    return view.home(_book().all(), time.time(), cal.KYIV, _extra_rows())


async def clients_screen(update, context):
    """«👤 Клиенты»: statistics and the ten folders."""
    from telegram.ext import ApplicationHandlerStop
    query = update.callback_query
    await query.answer()
    context.user_data.pop(WAIT, None)
    if not await asyncio.to_thread(allowed, update):
        raise ApplicationHandlerStop
    screen = await asyncio.to_thread(home_screen)
    await query.message.reply_text(screen['text'], parse_mode='HTML', reply_markup=markup(screen['buttons']))
    raise ApplicationHandlerStop


def _screen(parts, actor):
    action = parts[1]
    if action == 'f':
        if parts[2] not in view.folders.FOLDERS:
            raise LookupError('folder')
        return view.list_view(parts[2], _book().in_folder(parts[2]))
    if action == 'o':
        return view.detail_view(_book().get(int(parts[2])), cal.KYIV)
    if action == 'next':
        return view.detail_view(_book().advance(int(parts[2]), parts[3], actor), cal.KYIV)
    raise LookupError('action')


async def callback(update, context):
    from telegram.ext import ApplicationHandlerStop
    from telegram.error import BadRequest
    query = update.callback_query
    context.user_data.pop(WAIT, None)
    if not await asyncio.to_thread(allowed, update):
        await query.answer('Недостаточно прав', show_alert=True)
        raise ApplicationHandlerStop
    await query.answer()
    parts = query.data.split(':')
    try:
        if parts[1] == 'note':
            _book().get(int(parts[2]))
            context.user_data[WAIT] = int(parts[2])
            await query.message.reply_text(view.NOTE_PROMPT)
            raise ApplicationHandlerStop
        if parts[1] == 'file':
            order = await asyncio.to_thread(_book().get, int(parts[2]))
            with open(files.path(order['contract_file']), 'rb') as handle:
                await query.message.reply_document(handle, filename='Договор %s.%s' % (
                    order['contract_no'], order['contract_file'].rsplit('.', 1)[1]))
            raise ApplicationHandlerStop
        screen = await asyncio.to_thread(_screen, parts, update.effective_user.id)
    except (LookupError, ValueError, IndexError, OSError):
        screen = {'text': 'Заказ не найден', 'buttons': [[('К папкам', view.HOME)]]}
    try:
        await query.edit_message_text(screen['text'], parse_mode='HTML', reply_markup=markup(screen['buttons']))
    except BadRequest as exc:
        if 'not modified' not in str(exc).lower():
            await query.message.reply_text(screen['text'], parse_mode='HTML', reply_markup=markup(screen['buttons']))
    raise ApplicationHandlerStop


async def note(update, context):
    """The next text after «✏️ Заметка» is the note; any other message goes on to the other handlers."""
    from telegram.ext import ApplicationHandlerStop
    order_id = context.user_data.pop(WAIT, None)
    if order_id is None or not await asyncio.to_thread(allowed, update):
        return
    await asyncio.to_thread(_book().set_note, order_id, update.effective_message.text or '')
    screen = await asyncio.to_thread(lambda: view.detail_view(_book().get(order_id), cal.KYIV))
    await update.effective_message.reply_text('✅ Заметка сохранена\n\n' + screen['text'], parse_mode='HTML',
                                              reply_markup=markup(screen['buttons']))
    raise ApplicationHandlerStop


async def cancel(update, context):
    context.user_data.pop(WAIT, None)


def register(app):
    from telegram.ext import CallbackQueryHandler, MessageHandler, filters
    group = min(app.handlers, default=0) - 1  # an unused group before the bot's own handlers
    app.add_handler(CallbackQueryHandler(callback, pattern=r'^co:'), group=group)
    app.add_handler(CallbackQueryHandler(cancel), group=group)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, note), group=group)
    app.add_handler(MessageHandler(filters.COMMAND, cancel), group=group)
    return group

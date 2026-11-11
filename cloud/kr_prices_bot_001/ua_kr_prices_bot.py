"""CRM bot: «💲 Цены Корея» in the owner's main menu — Korea logistics prices per month for the home page
(ORDER-PROCESS-001, owner 2026-11-11).

Telegram glue only; the file and the arithmetic are in ua_kr_prices_store. The owner picks a month (this one or the
next two) and sends six numbers in one message; the site shows them from that month on. Only the owner sees the
button (the same rule as «👥 Сотрудники») and every action checks the owner again. Any other button or command ends
an open input, as in the rest of the bot. A failure only logs; the CRM keeps working.
"""
import asyncio
import logging

import ua_kr_prices_store as store

BUTTON = '💲 Цены Корея'
PREFIX = 'krp:'
HOME = PREFIX + 'home'
BACK = 'menu'  # the bot's main menu
OWNER_MENU_MARK = 'staff_list'  # «👥 Сотрудники» is in the owner's menu only
WAIT = 'kr_prices_month'
log = logging.getLogger(__name__)


def with_button(original, menu):
    """Main menu with the button for the owner (original: the role's menu before the CRM filter)."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    try:
        if any(getattr(b, 'callback_data', None) == OWNER_MENU_MARK for row in original.inline_keyboard for b in row) \
                and not any(getattr(b, 'callback_data', None) == HOME for row in menu.inline_keyboard for b in row):
            return InlineKeyboardMarkup(list(menu.inline_keyboard) + [[InlineKeyboardButton(BUTTON, callback_data=HOME)]])
    except Exception:
        log.exception('kr prices: menu button skipped')
    return menu


def _is_owner(update):
    import db
    user = update.effective_user
    staff = db.get_staff(user.id) if user else None
    return bool(staff) and bool(staff['active']) and staff['role'] == db.ROLE_OWNER


def _label(month):
    return month[5:] + '.' + month[:4]


def _line(prices):
    parts = ['%s %d' % (store.LABELS[k], prices[k]) for k in store.KEYS]
    parts[1] += ' (на авто %d)' % store.per_car(prices)
    return ' · '.join(parts) + '\n<b>Итого за авто: %d $</b>' % store.total(prices)


def home_screen(months, today):
    """{'text', 'buttons'} of the main screen; buttons are (label, callback) rows."""
    live = store.live_month(months, today)
    lines = ['<b>💲 Цены Корея — логистика за 1 авто, $</b>',
             'Сайт показывает цены текущего месяца; следующие месяцы можно задать заранее.', '']
    if live:
        lines += ['<b>Сейчас на сайте (%s):</b>' % _label(live), _line(months[live])]
    else:
        lines += ['<b>Сейчас на сайте (цены страницы):</b>', _line(store.DEFAULTS)]
    future = sorted(m for m in months if live is None or m > live)
    for month in future:
        lines += ['', '<b>%s:</b>' % _label(month), _line(months[month])]
    buttons = [[('✏️ ' + _label(m), PREFIX + 'edit:' + m)] for m in store.months_ahead(today)]
    buttons.append([('В меню', BACK)])
    return {'text': '\n'.join(lines), 'buttons': buttons}


def ask_screen(month, months, today):
    example = months.get(month) or months.get(store.live_month(months, today) or '') or store.DEFAULTS
    order = ', '.join(store.LABELS[k] for k in store.KEYS)
    return {'text': ('<b>Цены на %s</b>\n\nПришлите одним сообщением 6 чисел в долларах через пробел, в таком порядке:\n'
                     '%s.\n\nКонтейнер — цена за весь контейнер (на авто считается 1/%d). Числа без пробелов внутри.\n'
                     'Например:\n<code>%s</code>') % (_label(month), order, store.CARS_PER_CONTAINER,
                                                     ' '.join(str(example[k]) for k in store.KEYS)),
            'buttons': [[('Отмена', HOME)]]}


ERRORS = {'format': 'Нужно ровно 6 целых чисел через пробел. Попробуйте ещё раз или нажмите «Отмена».',
          'limit': 'Слишком большое число (больше 100 000 $). Проверьте и пришлите ещё раз.'}


async def _show(message, screen, edit=None):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    markup = InlineKeyboardMarkup([[InlineKeyboardButton(t, callback_data=d) for t, d in row]
                                   for row in screen['buttons']])
    if edit is not None:
        try:
            await edit.edit_message_text(screen['text'], parse_mode='HTML', reply_markup=markup)
            return
        except Exception:
            pass
    await message.reply_text(screen['text'], parse_mode='HTML', reply_markup=markup)


async def callback(update, context):
    from telegram.ext import ApplicationHandlerStop
    query = update.callback_query
    if not await asyncio.to_thread(_is_owner, update):
        await query.answer('Только для владельца', show_alert=True)
        raise ApplicationHandlerStop
    await query.answer()
    context.user_data.pop(WAIT, None)
    today = store.today_kyiv()
    try:
        months = await asyncio.to_thread(store.load)
        action = query.data[len(PREFIX):]
        if action.startswith('edit:') and action[5:] in store.months_ahead(today):
            context.user_data[WAIT] = action[5:]
            await _show(query.message, ask_screen(action[5:], months, today), query)
        else:
            await _show(query.message, home_screen(months, today), query)
    except Exception:
        log.exception('kr prices: screen failed')
        await query.message.reply_text('Цены временно недоступны, попробуйте позже.')
    raise ApplicationHandlerStop


async def text(update, context):
    """The owner's six numbers while a month is open; other messages go on to the bot."""
    from telegram.ext import ApplicationHandlerStop
    month = context.user_data.get(WAIT)
    if not month or not await asyncio.to_thread(_is_owner, update):
        return
    message = update.effective_message
    try:
        prices = store.parse(message.text or '')
    except store.PriceError as error:
        await message.reply_text(ERRORS.get(str(error), ERRORS['format']))
        raise ApplicationHandlerStop
    context.user_data.pop(WAIT, None)
    try:
        months = await asyncio.to_thread(store.save_month, month, prices)
    except Exception:
        log.exception('kr prices: save failed')
        await message.reply_text('Не удалось сохранить цены, попробуйте позже.')
        raise ApplicationHandlerStop
    screen = home_screen(months, store.today_kyiv())
    screen['text'] = '✅ Цены на %s сохранены.\n\n' % _label(month) + screen['text']
    await _show(message, screen)
    raise ApplicationHandlerStop


async def cancel(update, context):
    """Any other button or command ends an open input."""
    context.user_data.pop(WAIT, None)


def register(app):
    from telegram.ext import CallbackQueryHandler, MessageHandler, filters
    group = min(app.handlers, default=0) - 1  # an unused group before the bot's own handlers
    app.add_handler(CallbackQueryHandler(callback, pattern='^' + PREFIX), group=group)
    app.add_handler(CallbackQueryHandler(cancel), group=group)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text), group=group)
    app.add_handler(MessageHandler(filters.COMMAND, cancel), group=group)
    return group

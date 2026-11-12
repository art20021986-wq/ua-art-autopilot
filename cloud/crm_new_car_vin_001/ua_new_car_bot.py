"""CRM bot: «Создать новое объявление» at the top of «🚗 Автомобили» — a new car card from a typed VIN
(NEW-CAR-VIN-001, owner 2026-11-12).

Telegram glue only. The button asks for the VIN; a valid VIN goes to the installed photo_card module, the same path
as a photo with a VIN: brand from the VIN, the card is created unpublished, an existing VIN creates nothing. Every
staff member who sees «Автомобили» sees the button (owner: managers see the same). Any other button or command ends
the input, as in the rest of the bot. A failure only logs; the CRM keeps working.
"""
import asyncio
import logging
import re

BUTTON = 'Создать новое объявление'
START = 'ncv:start'
WAIT = 'new_car_vin'
ASK = 'Введите VIN-код для создания нового автомобиля'
RETRY = ('VIN-код — 17 латинских букв и цифр (без I, O, Q). Проверьте и введите ещё раз '
         'или откройте другой раздел.')
VIN = re.compile(r'[A-HJ-NPR-Z0-9]{17}')  # ISO 3779 characters
log = logging.getLogger(__name__)


def rows():
    """The button row for the top of the «Автомобили» screen."""
    from telegram import InlineKeyboardButton
    return [[InlineKeyboardButton(BUTTON, callback_data=START)]]


def vin_of(text):
    """The VIN typed by the user (spaces and dashes ignored, any case) or None."""
    value = re.sub(r'[\s-]', '', text or '').upper()
    return value if VIN.fullmatch(value) else None


def _staff(update):
    import db
    user = update.effective_user
    staff = db.get_staff(user.id) if user else None
    return staff if staff and staff['active'] else None


async def start(update, context):
    from telegram.ext import ApplicationHandlerStop
    query = update.callback_query
    if not await asyncio.to_thread(_staff, update):
        await query.answer('Доступ только для сотрудников.', show_alert=True)
        raise ApplicationHandlerStop
    await query.answer()
    context.user_data[WAIT] = True
    await query.message.reply_text(ASK)
    raise ApplicationHandlerStop


async def text(update, context):
    """The VIN while the input is open; other messages go on to the bot."""
    from telegram import InlineKeyboardMarkup
    from telegram.ext import ApplicationHandlerStop
    if not context.user_data.get(WAIT):
        return
    staff = await asyncio.to_thread(_staff, update)
    if not staff:
        return
    message = update.effective_message
    vin = vin_of(message.text)
    if not vin:
        await message.reply_text(RETRY)
        raise ApplicationHandlerStop
    context.user_data.pop(WAIT, None)
    try:
        import photo_card
        data = photo_card.extract(vin)
        answer, buttons, card_id = photo_card.create_card(data, staff['user_id'], None)
    except Exception:
        log.exception('new car by VIN failed')
        await message.reply_text('Не удалось создать карточку, попробуйте позже.')
        raise ApplicationHandlerStop
    if card_id:
        context.user_data['car_last'] = card_id  # as after a photo: the next message goes to this card
    await message.reply_text(answer, parse_mode='HTML',
                             reply_markup=InlineKeyboardMarkup(buttons) if buttons else None)
    raise ApplicationHandlerStop


async def cancel(update, context):
    """Any other button or command ends an open input."""
    context.user_data.pop(WAIT, None)


def register(app):
    from telegram.ext import CallbackQueryHandler, MessageHandler, filters
    group = min(app.handlers, default=0) - 1  # an unused group before the bot's own handlers
    app.add_handler(CallbackQueryHandler(start, pattern='^' + START + '$'), group=group)
    app.add_handler(CallbackQueryHandler(cancel), group=group)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text), group=group)
    app.add_handler(MessageHandler(filters.COMMAND, cancel), group=group)
    return group

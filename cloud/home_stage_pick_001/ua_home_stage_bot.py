"""CRM card button «Разместить на главную» (HOME-STAGE-PICK-001).

One job: the Telegram side. The owner opens a car card that is on the site and
taps the button; the car's main photo goes to the home page tile of the car's
current stage (Київ, Грузія, пором, Корея). The page edit is ua_home_stage_site.
"""
import asyncio
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationHandlerStop, CallbackQueryHandler, ContextTypes

import db
import ua_home_stage_site as site

log = logging.getLogger(__name__)

BUTTON = '🏠 Разместить на главную'
CALLBACK = 'home_stage:%d'
PATTERN = r'^home_stage:[0-9]{1,9}$'
AFTER = 'car_ad:'                 # the button goes right after «Разместить объявление»
STAGE_BY_PREFIX = (('ua_', 'kiev'), ('ge_', 'georgia'), ('sea_', 'sea'), ('kr_', 'korea'))
TILE = {'kiev': '«У Києві»', 'georgia': '«У Грузії»', 'sea': '«На поромі»', 'korea': '«В Кореї»'}


def stage_of(card):
    """Home tile of the car's CRM status (the same prefixes master_card.stage_po_statusu uses)."""
    status = str((card or {}).get('status') or '').strip().lower()
    return next((stage for prefix, stage in STAGE_BY_PREFIX if status.startswith(prefix)), '')


def _is_owner(staff):
    return bool(staff) and bool(staff.get('active')) and staff.get('role') == db.ROLE_OWNER


def eligible(card, staff):
    return _is_owner(staff) and bool(card.get('published')) and bool(card.get('auto_number')) and bool(stage_of(card))


def with_button(markup, card, staff):
    """Card keyboard with the button for the owner on a published car; otherwise unchanged."""
    try:
        if not eligible(card, staff):
            return markup
        rows = [list(row) for row in markup.inline_keyboard]
        button = [InlineKeyboardButton(BUTTON, callback_data=CALLBACK % int(card['id']))]
        at = next((i + 1 for i, row in enumerate(rows)
                   if any(str(getattr(b, 'callback_data', '') or '').startswith(AFTER) for b in row)), len(rows))
        rows.insert(at, button)
        return InlineKeyboardMarkup(rows)
    except Exception:
        log.exception('home stage: card button skipped')
        return markup


async def place(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cid = int(query.data.split(':')[-1])
    back = InlineKeyboardMarkup([[InlineKeyboardButton('← Вернуться к карточке', callback_data='car_open:%d' % cid)]])
    card = db.get_card('cars', cid)
    if not card or not eligible(card, db.get_staff(query.from_user.id)):
        await query.message.reply_text('Разместить на главную может владелец, для авто, опубликованного на сайте.',
                                       reply_markup=back)
        raise ApplicationHandlerStop
    code, stage = card['auto_number'], stage_of(card)
    try:
        await asyncio.to_thread(site.publish, code, stage)
        text = 'Готово: фото %s стоит на главной странице в блоке %s.' % (code, TILE[stage])
    except Exception as e:
        log.exception('home stage: %s not placed', code)
        text = 'Не получилось разместить %s на главной (%s). Главная не изменена.' % (code, e)
    await query.message.reply_text(text, reply_markup=back)
    raise ApplicationHandlerStop


def register(app):
    app.add_handler(CallbackQueryHandler(place, pattern=PATTERN), group=-1)

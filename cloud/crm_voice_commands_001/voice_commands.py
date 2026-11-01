"""Owner voice note in an open CRM card: named fields, the buyer and the delivery stage.

Writes go through the CRM's own functions in cars_ui, the same ones the buttons and typed values
use: _task088_apply_selected_price (prices), apply_value (other card fields), save_stage (stage),
the buyer card as the «Покупатель» screen creates it. Free speech about the 11 vehicle fields
(«бензин, автомат, пробег 120 тысяч») is handed back to the existing voice parser.
"""
import logging
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import voice_fields
import voice_stage

log = logging.getLogger(__name__)
PRICES = ('price_uah', 'price_georgia')
# Words the existing parser reads; text without them has nothing left for it.
VEHICLE_WORDS = re.compile(r'марк|модел|(?<![а-яіїєґa-z])(?:год|рік)(?![а-яіїєґa-z])|vin|вин|топлив|палив|бензин|дизел|'
                           r'(?<![а-яіїєґa-z])газ|гибрид|гібрид|электр|електр|объ?[её]м|об.єм|двигат|двигун|мотор|'
                           r'коробк|кпп|автомат|механ|привод|привід|пробег|пробіг|цвет|колір', re.I)


def _write_car(crm, card_id, field, value, actor):
    if field in PRICES:
        ok, message = crm._task088_apply_selected_price(card_id, field, value, actor)
    else:
        ok, message = crm.apply_value(card_id, field, value, actor)
    return message if not ok or message != 'Записано.' else value


def _write_client(crm, card, field, value, actor):
    client = crm.client_of(crm.card_of(card['id']) or card)
    if not client:  # as the «Покупатель» screen does on first opening
        number = card.get('auto_number') or '#%d' % card['id']
        crm.set_field(card['id'], 'client_id', crm.db.create_card('clients', {'car_interest': number}, actor), actor)
        client = crm.client_of(crm.card_of(card['id']))
    crm.db.update_card_field('clients', client['id'], field, value, actor)
    return value


async def _stage(crm, card, code, actor):
    _, error, note = await crm.save_stage(card['id'], code, actor)
    return error or '%s%s' % (crm.S.status_label(code), '\n  ' + note if note else '')


async def apply(msg, thinking, card, text, actor):
    """Apply what the note names. Return (handled, text left for the existing parser)."""
    import cars_ui as crm
    commands, rest = voice_fields.parse(text)
    stage = voice_stage.stage_code(rest)
    if not commands and not stage:
        return False, text
    lines = []
    for target, field, value in commands:
        try:
            shown = (_write_car(crm, card['id'], field, value, actor) if target == 'car'
                     else _write_client(crm, card, field, value, actor))
        except Exception as error:
            log.warning('Voice command failed card=%s field=%s error=%s', card['id'], field, type(error).__name__)
            shown = 'не записано, повторите'
        label = voice_fields.LABELS[field]
        lines.append('• ' + shown if shown.startswith(label) else '• %s — %s' % (label, shown))
    if stage:
        lines.append('• Этап — %s' % await _stage(crm, card, stage, actor))
    reply = '%s\n%s' % (card.get('auto_number') or '#%d' % card['id'], '\n'.join(lines))
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton('← Вернуться к карточке', callback_data='car_open:%d' % card['id'])]])
    rest = rest if VEHICLE_WORDS.search(rest) else ''
    if rest:
        await msg.reply_text(reply, reply_markup=keyboard)
        return False, rest
    await thinking.edit_text(reply, reply_markup=keyboard)
    return True, ''

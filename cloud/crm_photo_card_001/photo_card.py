"""Owner photo -> new CRM car card (owner rules of 2026-11-01).

1. A VIN is visible and not in the CRM: create the card and fill every recognised CRM field.
2. The VIN is already in the CRM: say so; nothing is created or changed.
3. No VIN: nothing is created.
The card is not published on the site. Recognition reuses the installed modules: local_ocr
(OCR and free-text fields), ai_fast_schema/ai_filter (labelled fields, CRM vocabulary, card
store); screen_fields reads label/value screenshots and vin_brand names the manufacturer.
"""
import asyncio
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import ai_fast_schema as fast
import ai_filter
import db
import local_ocr
import screen_fields
import vin_brand

log = logging.getLogger(__name__)
DOWNLOAD_SECONDS = 2.5
OCR_SECONDS = 11.5
_STORE_LOCK = asyncio.Lock()  # one VIN check + create at a time: a resent photo cannot duplicate a card


def extract(text):
    """CRM fields of the screenshot text, normalised to the CRM vocabulary."""
    allowed = fast.car_fields(ai_filter)
    data = fast.fast_text_data('%s\n%s' % (text, screen_fields.join_labels(text)), ai_filter)
    data.update(local_ocr.fields_from_text(text, allowed))  # OCR-specific parser wins («120 тис. км»)
    if data.get('vin') and not data.get('brand') and 'brand' in allowed:
        data['brand'] = vin_brand.brand(data['vin'])
    data = {key: value for key, value in data.items() if value not in (None, '')}
    return fast.clean_car(fast.parsed_from_data(data), ai_filter, '') if data else {}


def _open(card_id):
    return [InlineKeyboardButton('← Открыть карточку', callback_data='car_open:%d' % card_id)]


def create_card(data, actor, inbox_id):
    """Apply the three rules; return (message, keyboard rows, card id or None)."""
    vin = data.get('vin')
    if not vin:
        return ('VIN на фото не найден — новая карточка не создана.\n'
                'Пришлите фото или скриншот, где виден VIN.'), [], None
    existing = ai_filter.find_by_vin(vin)
    if existing:
        number = existing.get('auto_number') or '#%d' % existing['id']
        return ('Карточка с таким VIN-кодом уже существует: <b>%s</b>.\n'
                'Новая карточка не создана, существующая не изменена.' % number), [_open(existing['id'])], None
    card_id, number, _ = ai_filter.store(data, actor, inbox_id)
    rows = [_open(card_id), [InlineKeyboardButton('Редактировать', callback_data='car_edit:%d' % card_id)]]
    return ('✅ Создана карточка <b>%s</b> (на сайте не опубликована)\n\n%s'
            % (number, ai_filter.render(data))), rows, card_id


async def _image_text(context, file_id):
    tg_file = await asyncio.wait_for(context.bot.get_file(file_id), DOWNLOAD_SECONDS)
    image = bytes(await asyncio.wait_for(tg_file.download_as_bytearray(), DOWNLOAD_SECONDS))
    return await asyncio.wait_for(asyncio.to_thread(local_ocr.image_text, image, OCR_SECONDS), OCR_SECONDS + 1.0)


async def handle(update, context, inbox_id, file_id, caption):
    """Telegram entry point for an owner photo or image document."""
    msg = update.message
    thinking = await msg.reply_text('🖼 Распознаю фото, до 15 секунд...')
    text = ''
    try:
        text = await _image_text(context, file_id)
    except Exception as error:  # timeouts included: answer with what the caption gives
        log.warning('Photo OCR failed inbox=%s error=%s', inbox_id, type(error).__name__)
    data = extract('\n'.join(part for part in (text, caption or '') if part))
    actor = db.get_staff(update.effective_user.id)['user_id']
    async with _STORE_LOCK:
        message, rows, card_id = create_card(data, actor, inbox_id)
    if card_id:
        context.user_data['car_last'] = card_id
    await thinking.edit_text(message, parse_mode='HTML',
                             reply_markup=InlineKeyboardMarkup(rows) if rows else None)

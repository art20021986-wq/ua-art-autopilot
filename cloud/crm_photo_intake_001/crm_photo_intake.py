"""Owner photo intake: bounded existing OCR, explicit fields, atomic draft."""
import asyncio
from collections import deque
import html
import io
import logging
import shutil
import time

from crm_explicit_fields import parse
from crm_intake_store import record_source, save

MAX_BYTES = 10 * 1024 * 1024
STATE = 'explicit_intake_card'
log = logging.getLogger(__name__)


def message_source(msg, picture):
    return dict(chat_id=msg.chat_id, message_id=msg.message_id,
                kind='photo' if msg.photo else 'document' if picture else 'text',
                text=msg.text or msg.caption, file_id=picture.file_id if picture else None,
                media_group=msg.media_group_id)


def photo_text(payload, ocr):
    """One full-page pass preserves label/value rows; no cropped guesses."""
    if not payload or len(payload) > MAX_BYTES:
        raise ValueError('PHOTO_SIZE')
    from PIL import Image, ImageOps  # Already used by local_ocr on the server.
    binary = shutil.which('tesseract')
    if not binary:
        raise RuntimeError('OCR_UNAVAILABLE')
    with Image.open(io.BytesIO(payload)) as source:
        if source.width * source.height > 20_000_000:
            raise ValueError('PHOTO_PIXELS')
        image = ImageOps.exif_transpose(source).convert('RGB')
    deadline = time.monotonic() + 12
    return ocr._ocr_one(image, binary, ocr._languages(binary), deadline, 6)


def register(app, db, ai_filter, ocr, ai):
    """Register before general car text parsing; preserve all explicit editors."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import ApplicationHandlerStop, MessageHandler, filters

    dictionaries = {field: getattr(ai_filter, name) for field, name in
                    [('fuel', 'FUEL'), ('gearbox', 'GEARBOX'), ('drive', 'DRIVE'), ('color', 'COLOR')]}
    pending = {}

    async def process(update, context, actor, picture, parsed, current_id):
        msg = update.effective_message
        start_card = context.user_data.get('car_last')
        card = None
        try:
            thinking = await msg.reply_text('Читаю данные автомобиля…')
            facts, rejected, _ = parsed
            if picture:
                if picture.file_size and picture.file_size > MAX_BYTES:
                    raise ValueError('PHOTO_SIZE')
                file = await asyncio.wait_for(context.bot.get_file(picture.file_id), timeout=10)
                payload = await asyncio.wait_for(file.download_as_bytearray(), timeout=15)
                text = await asyncio.to_thread(photo_text, bytes(payload), ocr)
                facts, rejected, _ = parse(text, ai_filter.ALLOWED, dictionaries)
                # Caption is explicit owner input, but never combines two VINs.
                caption, caption_bad, _ = parsed
                if caption.get('vin') and facts.get('vin') and caption['vin'] != facts['vin']:
                    raise ValueError('VIN_SOURCE_CONFLICT')
                facts.update(caption)
                rejected.difference_update(caption)
                rejected.update(caption_bad)
                for field in caption_bad:
                    facts.pop(field, None)
            if 'vin' in rejected:
                raise ValueError('VIN_UNCLEAR')
            if not facts:
                await thinking.edit_text('Поля не удалось прочитать однозначно. Пришлите чёткое фото или данные с названиями полей.')
                return
            if not facts.get('vin') and not current_id:
                await thinking.edit_text('Для новой карточки нужен VIN. Пришлите фото с полным VIN или данные вместе с VIN.')
                return
            if ai.is_stopped():
                await thinking.edit_text('Распознавание остановлено. Карточка не изменена.')
                return
            source = message_source(msg, picture)
            card, changes, created = await asyncio.to_thread(save, db, ai_filter.S, facts, actor, source, current_id)
            # A later navigation made while OCR ran keeps its chosen card.
            if context.user_data.get('car_last') == start_card:
                context.user_data[STATE] = card['id']
                context.user_data['car_last'] = card['id']
            number = html.escape(str(card.get('auto_number') or card['id']))
            title = ('Создана карточка ' if created else 'Открыта карточка ') + number
            lines = [title]
            for field in ai_filter.ORDER:
                if field in changes:
                    lines.append(html.escape(ai_filter.LABELS[field]) + ': ' + html.escape(str(changes[field])))
            if rejected:
                lines.append('Неоднозначные поля не перенесены: ' + ', '.join(html.escape(ai_filter.LABELS[k]) for k in sorted(rejected)))
            if not created and not changes:
                lines.append('Повторная карточка не создана. Сохранённые данные остаются прежними.')
            await thinking.edit_text('\n'.join(lines), parse_mode='HTML', reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('Открыть анкету', callback_data='car_open:%d' % card['id'])],
                [InlineKeyboardButton('Дополнить', callback_data='car_edit:%d' % card['id'])]]))
            return card['id']
        except Exception as error:
            log.warning('Explicit photo intake failed: %s', type(error).__name__)
            await msg.reply_text('Не удалось завершить заполнение. Повторите отправку: VIN проверяется перед созданием карточки.')
            return card['id'] if card else None

    async def drain(actor):
        try:
            previous = None
            while pending[actor]:
                update, context, picture, parsed, current_id, continuation = pending[actor].popleft()
                if continuation and not picture and not parsed[0].get('vin'):
                    current_id = previous
                previous = await process(update, context, actor, picture, parsed, current_id)
        finally:
            pending.pop(actor, None)

    async def handle(update, context):
        msg = update.effective_message
        if not msg or not update.effective_user:
            return
        # Explicit media/field/client dialogs retain their established routing.
        if any(context.user_data.get(key) for key in ('car_media_wait', 'car_wait', 'card', 'ai_draft')):
            return
        picture = msg.photo[-1] if msg.photo else None
        if not picture and msg.document and (msg.document.mime_type or '').startswith('image/'):
            picture = msg.document
        active = context.user_data.get(STATE)
        current_id = active if active == context.user_data.get('car_last') else None
        parsed = parse(msg.text or msg.caption or '', ai_filter.ALLOWED, dictionaries)
        if not picture and not (msg.text and (parsed[2] or current_id)):
            return
        staff = await asyncio.to_thread(db.get_staff, update.effective_user.id)
        if not staff or not staff.get('active') or staff.get('role') != db.ROLE_OWNER:
            return
        if ai.is_stopped():
            await msg.reply_text('Распознавание остановлено. Включите его в меню CRM.')
            raise ApplicationHandlerStop
        actor = staff['user_id']
        if len(pending.get(actor, ())) >= 8:
            await msg.reply_text('Обрабатываю ранее отправленные данные. Это сообщение пока не принято; повторите его после появления анкеты.')
            raise ApplicationHandlerStop
        try:
            await asyncio.to_thread(record_source, db, actor, message_source(msg, picture))
        except Exception:
            await msg.reply_text('Не удалось сохранить входящее сообщение. Повторите отправку.')
            raise ApplicationHandlerStop
        running = actor in pending
        pending.setdefault(actor, deque()).append((update, context, picture, parsed,
                                                  None if picture else current_id, running))
        # Finish dispatch immediately so unrelated buttons stay responsive.
        if not running:
            app.create_task(drain(actor), update=update)
        else:
            await msg.reply_text('Данные приняты. Заполню их после обработки предыдущего сообщения.')
        raise ApplicationHandlerStop

    app.add_handler(MessageHandler((filters.PHOTO | filters.Document.IMAGE | filters.TEXT) & ~filters.COMMAND,
                                  handle), group=-3)

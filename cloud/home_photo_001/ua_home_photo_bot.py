"""CRM button «Фото главной страницы» (HOME-PHOTO-001).

One job: the Telegram dialogue. The owner taps the button, sends a photo (as a
photo or as a file), sees how it will look on the home page and confirms; only
then the page changes. Framing is ua_home_photo_crop, the page write is
ua_home_photo_site. Other photos the owner sends keep going to the CRM as before.
"""
import asyncio
import logging
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationHandlerStop, CallbackQueryHandler, ContextTypes, MessageHandler, filters

import db
import ua_home_photo_site as site

log = logging.getLogger(__name__)

BUTTON = '🖼 Фото главной страницы'
OWNER_MENU_MARK = 'staff_list'   # team_bot.main_menu adds «Сотрудники» only for the owner
WAIT, READY, ALBUM = 'home_photo_wait', 'home_photo_ready', 'home_photo_album'
WAIT_SECONDS = 15 * 60
GROUP = -1000                    # before the CRM intake, so this photo does not become a new car
MAX_BYTES = 20 * 1024 * 1024     # Bot API download limit

ASK = ('Отправьте фото автомобиля для главной страницы.\n'
       'Лучше файлом (📎 → Файл) — так фото придёт без сжатия.\n'
       'Я найду машину, поставлю её по центру и уберу лишнее по краям.')
ERRORS = {
    'NOT_A_PHOTO': 'Не получилось открыть фото. Пришлите JPG или PNG.',
    'NO_CAR': 'Не нашёл автомобиль на фото. Пришлите другое фото, где машина видна целиком.',
    'TOO_SMALL': 'Машина на фото слишком маленькая — на сайте будет нечётко. Пришлите фото ближе или файлом.',
}


def with_button(original, menu):
    """Main menu with the photo button for the owner (original: the menu before the CRM filter)."""
    try:
        rows = list(menu.inline_keyboard)
        if any(getattr(b, 'callback_data', None) == OWNER_MENU_MARK for row in original.inline_keyboard for b in row):
            return InlineKeyboardMarkup(rows + [[InlineKeyboardButton(BUTTON, callback_data='home_photo')]])
    except Exception:
        log.exception('home photo: menu button skipped')
    return menu


def _is_owner(user):
    staff = db.get_staff(user.id)
    return bool(staff) and staff['active'] and staff['role'] == db.ROLE_OWNER


def _keyboard(*buttons):
    return InlineKeyboardMarkup([[InlineKeyboardButton(text, callback_data=data)] for text, data in buttons])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_owner(query.from_user):
        await query.message.reply_text('Фото главной страницы меняет только владелец.')
        raise ApplicationHandlerStop
    context.user_data.pop(READY, None)
    context.user_data[WAIT] = time.monotonic()
    await query.message.reply_text(ASK, reply_markup=_keyboard(('Отмена', 'home_photo_cancel')))
    raise ApplicationHandlerStop


def _image(message):
    if message.photo:
        return message.photo[-1]
    document = message.document
    if document and (document.mime_type or '').startswith('image/'):
        return document
    return None


async def receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Takes the next photo after the button; any other message ends the wait and goes on as usual."""
    message = update.effective_message
    if message.media_group_id and message.media_group_id == context.user_data.get(ALBUM):
        raise ApplicationHandlerStop  # the rest of an album sent for the home page is not a new car
    started = context.user_data.pop(WAIT, None)
    if started is None or time.monotonic() - started > WAIT_SECONDS or not _is_owner(update.effective_user):
        return
    image = _image(message)
    if image is None:
        await message.reply_text('Загрузка фото главной страницы отменена.')
        return
    if (image.file_size or 0) > MAX_BYTES:
        context.user_data[WAIT] = time.monotonic()
        await message.reply_text('Файл больше 20 МБ — Telegram не даёт боту его скачать. Пришлите фото поменьше.')
        raise ApplicationHandlerStop
    context.user_data[ALBUM] = message.media_group_id
    await message.reply_text('Обрабатываю фото…')
    import ua_home_photo_crop as crop  # OpenCV is loaded only when a photo is actually framed
    try:
        data = bytes(await (await image.get_file()).download_as_bytearray())
        jpeg = await asyncio.to_thread(crop.make_home_photo, data)
    except crop.PhotoError as exc:
        context.user_data[WAIT] = time.monotonic()
        await message.reply_text(ERRORS[str(exc)], reply_markup=_keyboard(('Отмена', 'home_photo_cancel')))
        raise ApplicationHandlerStop
    except Exception:
        log.exception('home photo: processing failed')
        await message.reply_text('Не получилось обработать фото. Сайт не изменён.')
        raise ApplicationHandlerStop
    context.user_data[READY] = jpeg
    await message.reply_photo(jpeg, caption='Так фото будет на главной странице.', reply_markup=_keyboard(
        ('✅ Поставить на главную', 'home_photo_ok'), ('🔄 Другое фото', 'home_photo'), ('Отмена', 'home_photo_cancel')))
    raise ApplicationHandlerStop


async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    jpeg = context.user_data.pop(READY, None)
    if not _is_owner(query.from_user):
        raise ApplicationHandlerStop
    if jpeg is None:
        await query.message.reply_text('Фото уже не в памяти бота. Нажмите «%s» и пришлите его ещё раз.' % BUTTON)
        raise ApplicationHandlerStop
    try:
        address = await asyncio.to_thread(site.publish, jpeg)
    except Exception:
        log.exception('home photo: publish failed')
        await query.message.reply_text('Не получилось поставить фото. Главная страница не изменена.')
        raise ApplicationHandlerStop
    log.info('home photo: published %d bytes', len(jpeg))
    await query.message.reply_text('Готово: фото на главной странице.\n%s' % address)
    raise ApplicationHandlerStop


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.pop(WAIT, None)
    context.user_data.pop(READY, None)
    await query.message.reply_text('Отменено. Главная страница не изменена.')
    raise ApplicationHandlerStop


def register(app):
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, receive), group=GROUP)
    app.add_handler(CallbackQueryHandler(start, pattern='^home_photo$'), group=GROUP)
    app.add_handler(CallbackQueryHandler(confirm, pattern='^home_photo_ok$'), group=GROUP)
    app.add_handler(CallbackQueryHandler(cancel, pattern='^home_photo_cancel$'), group=GROUP)

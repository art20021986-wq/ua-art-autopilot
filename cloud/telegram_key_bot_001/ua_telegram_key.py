"""The owner sends the Telegram API key to the CRM bot in one message (TELEGRAM-KEY-BOT, owner 2026-11-19).

Message: api_id digits, a space or a line break, then the 32 hex characters of api_hash. Only an owner of the CRM, only a
private chat. The handler runs before every other handler (group KEY_GROUP) and stops further processing, so the
message never reaches the inbox, the CRM database, the AI parsing or any log; the bot deletes the message at once.
The key is written to KEY_PATH (two lines, mode 600). The values are never logged or echoed.
"""
import logging
import os
from pathlib import Path
import re
import tempfile

log = logging.getLogger(__name__)

KEY_PATH = Path('/home/Carix/telegram_api.txt')
KEY_GROUP = -10000
KEY = re.compile(r'\s*(\d{5,12})\s+([0-9a-fA-F]{32})\s*')
# A message that looks like a key attempt (digits, then a long token): it is handled here even if malformed, so a
# mistyped key does not reach the other handlers either.
ATTEMPT = re.compile(r'\s*\d{5,12}\s+[0-9A-Za-z]{16,64}\s*')
SAVED = 'Ключ сохранён ✅'
WRONG = 'Формат не тот: цифры, пробел, 32 знака'
FAILED = 'Ключ не сохранён: ошибка записи на сервере.'


def is_owner(user_id):
    import db
    staff = db.get_staff(user_id)
    return bool(staff) and staff.get('role') == db.ROLE_OWNER


def write_key(api_id, api_hash, path=None):
    """Atomic write, mode 600 from the first byte."""
    path = Path(path or KEY_PATH)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix='.telegram-api-')
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
            handle.write('%s\n%s\n' % (api_id, api_hash.lower()))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


async def on_message(update, context):
    from telegram.ext import ApplicationHandlerStop
    message = update.effective_message
    text = getattr(message, 'text', None)
    if not text or not ATTEMPT.fullmatch(text):
        return
    if getattr(update.effective_chat, 'type', '') != 'private' or not is_owner(update.effective_user.id):
        return
    match = KEY.fullmatch(text)
    try:
        await message.delete()
    except Exception as error:
        log.warning('Сообщение с ключом не удалено: %s', type(error).__name__)
    if not match:
        reply = WRONG
    else:
        try:
            write_key(match.group(1), match.group(2))
            reply = SAVED
        except Exception as error:
            log.warning('Ключ не записан: %s', type(error).__name__)
            reply = FAILED
    await context.bot.send_message(chat_id=update.effective_chat.id, text=reply)
    raise ApplicationHandlerStop


def register(app):
    from telegram.ext import MessageHandler, filters
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, on_message),
                    group=KEY_GROUP)

"""The owner sends the Google Ads API keys to the CRM bot in one message (ADS-KEYS-001, owner «Да» 2026-11-25).

Message: the developer token, the OAuth client id («…apps.googleusercontent.com») and the client secret («GOCSPX-…»),
in any order, separated by spaces or line breaks. Only the full-rights staff (ua_full_access), only a private chat.
The handler runs before every other handler (group KEY_GROUP, before the Telegram key group −10000) and stops further
processing, so the message never reaches the inbox, the CRM database, the AI parsing or any log; the bot deletes the
message at once, keeps the keys (ua_google_ads_auth) and answers with the one-time «Разрешить» link.
"""
import logging
import re

log = logging.getLogger(__name__)

KEY_GROUP = -10001
CLIENT = re.compile(r'\b\d{6,20}-[0-9a-z]{20,40}\.apps\.googleusercontent\.com\b')
SECRET = re.compile(r'(?<![A-Za-z0-9_-])GOCSPX-[A-Za-z0-9_-]{20,40}(?![A-Za-z0-9_-])')
TOKEN = re.compile(r'[A-Za-z0-9_-]{18,40}')
SAVED = ('Ключи Google Ads сохранены ✅\n\nОстался один шаг: откройте ссылку, войдите своей почтой и нажмите '
         '«Разрешить» (ссылка действует 30 минут):\n%s')
WRONG = 'Формат не тот: нужны токен разработчика, идентификатор клиента и секрет клиента — каждый с новой строки.'
FAILED = 'Ключи не сохранены: ошибка на сервере.'


def is_attempt(text):
    """A message that carries Google OAuth client values; handled here even if malformed."""
    return 'googleusercontent.com' in text or 'GOCSPX-' in text


def parse(text):
    """(developer_token, client_id, client_secret) or None."""
    clients, secrets = CLIENT.findall(text), SECRET.findall(text)
    if len(clients) != 1 or len(secrets) != 1:
        return None
    rest = text.replace(clients[0], ' ').replace(secrets[0], ' ').split()
    if len(rest) != 1 or not TOKEN.fullmatch(rest[0]):
        return None
    return rest[0], clients[0], secrets[0]


def is_full_rights(user_id):
    import db
    import ua_full_access
    staff = db.get_staff(user_id)
    return bool(staff) and staff.get('role') in ua_full_access.roles()


async def on_message(update, context):
    from telegram.ext import ApplicationHandlerStop
    message = update.effective_message
    text = getattr(message, 'text', None)
    if not text or not is_attempt(text):
        return
    if getattr(update.effective_chat, 'type', '') != 'private' or not is_full_rights(update.effective_user.id):
        return
    try:
        await message.delete()
    except Exception as error:
        log.warning('Сообщение с ключами Google Ads не удалено: %s', type(error).__name__)
    values = parse(text)
    if values is None:
        reply = WRONG
    else:
        try:
            import ua_google_ads_auth as auth
            auth.save_client(*values)
            reply = SAVED % auth.auth_url()
        except Exception as error:
            log.warning('Ключи Google Ads не записаны: %s', type(error).__name__)
            reply = FAILED
    await context.bot.send_message(chat_id=update.effective_chat.id, text=reply, disable_web_page_preview=True)
    raise ApplicationHandlerStop


def register(app):
    from telegram.ext import MessageHandler, filters
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, on_message),
                    group=KEY_GROUP)

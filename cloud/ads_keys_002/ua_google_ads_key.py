"""The owner sends the Google Ads API keys to the CRM bot (ADS-KEYS-001, owner «Да» 2026-11-25; step by step:
ADS-KEYS-002, owner 2026-11-25 «чтобы я вставлял по очереди»).

Three values: the OAuth client id («…apps.googleusercontent.com»), the client secret («GOCSPX-…») and the developer
token. They may come in one message or one by one (client id and secret in any order, then the token); each answer says
which value was taken and which is still missing, or exactly which value has the wrong shape. A lone token is taken
only while the same person's chat is collecting (15 minutes after the client id or secret), so ordinary messages are
never touched. Only the full-rights staff (ua_full_access), only a private chat. The handler runs before every other
handler (group KEY_GROUP, before the Telegram key group −10000) and stops further processing; every key message is
deleted at once. The values wait in this process's memory only (never in chat_data, never on disk) until all three
are there, then go to ua_google_ads_auth and the bot answers with the one-time «Разрешить» link.
"""
import logging
import re
import time

log = logging.getLogger(__name__)

KEY_GROUP = -10001
CLIENT = re.compile(r'\b\d{6,20}-[0-9a-z]{20,40}\.apps\.googleusercontent\.com\b')
SECRET = re.compile(r'(?<![A-Za-z0-9_-])GOCSPX-[A-Za-z0-9_-]{20,40}(?![A-Za-z0-9_-])')
TOKEN = re.compile(r'[A-Za-z0-9_-]{18,40}')
WAIT_SECONDS = 900
NAMES = {'client_id': 'идентификатор клиента', 'client_secret': 'секрет клиента (GOCSPX-…)',
         'developer_token': 'токен разработчика'}
ORDER = ('client_id', 'client_secret', 'developer_token')
SAVED = ('Ключи Google Ads сохранены ✅\n\nОстался один шаг: откройте ссылку, войдите своей почтой и нажмите '
         '«Разрешить» (ссылка действует 30 минут):\n%s')
TAKEN = '%s принят ✅\nТеперь пришлите: %s.'
BAD = {'client_id': 'Идентификатор клиента не подошёл: он должен быть целиком, цифры-буквы и в конце '
                    '«.apps.googleusercontent.com». Скопируйте его кнопкой копирования в Google Cloud.',
       'client_secret': 'Секрет клиента не подошёл: он начинается с «GOCSPX-» и идёт без пробелов. Скопируйте его целиком.',
       'developer_token': 'Токен разработчика не подошёл: нужен один набор латинских букв и цифр (можно «-» и «_»), '
                          'без пробелов и подписей.'}
FAILED = 'Ключи не сохранены: ошибка на сервере.'

# chat id -> {'expires': time, value name: value}; memory only.
PENDING = {}


def is_attempt(text):
    """A message that carries a Google OAuth client value; handled here even if malformed."""
    return 'googleusercontent.com' in text or 'GOCSPX-' in text


def pieces(text):
    """{value name: value} found in the text, and the names that look present but have the wrong shape."""
    found, bad, rest = {}, [], text
    clients, secrets = CLIENT.findall(text), SECRET.findall(text)
    if 'googleusercontent.com' in text:
        if len(clients) == 1:
            found['client_id'] = clients[0]
            rest = rest.replace(clients[0], ' ')
        else:
            bad.append('client_id')
    if 'GOCSPX-' in text:
        if len(secrets) == 1:
            found['client_secret'] = secrets[0]
            rest = rest.replace(secrets[0], ' ')
        else:
            bad.append('client_secret')
    words = rest.split()
    if words and not bad:
        if len(words) == 1 and TOKEN.fullmatch(words[0]):
            found['developer_token'] = words[0]
        else:
            bad.append('developer_token')
    return found, bad


def parse(text):
    """(developer_token, client_id, client_secret) when one message carries all three, else None."""
    found, bad = pieces(text)
    if bad or len(found) != 3:
        return None
    return found['developer_token'], found['client_id'], found['client_secret']


def is_full_rights(user_id):
    import db
    import ua_full_access
    staff = db.get_staff(user_id)
    return bool(staff) and staff.get('role') in ua_full_access.roles()


def collect(chat_id, text, now):
    """The reply for one key message of this chat; keeps the partial values in PENDING."""
    pending = PENDING.get(chat_id)
    if pending and pending['expires'] < now:
        PENDING.pop(chat_id, None)
        pending = None
    found, bad = pieces(text)
    if not ({'client_id', 'client_secret'} & set(found)) and 'client_id' not in bad and 'client_secret' not in bad \
            and not pending:
        return None  # a lone word outside a collecting chat is an ordinary message
    if bad:
        return BAD[bad[0]]
    pending = pending or {}
    pending.update(found)
    pending['expires'] = now + WAIT_SECONDS
    missing = [name for name in ORDER if name not in pending]
    if missing:
        PENDING[chat_id] = pending
        taken = ', '.join(NAMES[name] for name in ORDER if name in found)
        return TAKEN % (taken[:1].upper() + taken[1:], NAMES[missing[0]])
    PENDING.pop(chat_id, None)
    try:
        import ua_google_ads_auth as auth
        auth.save_client(pending['developer_token'], pending['client_id'], pending['client_secret'])
        return SAVED % auth.auth_url()
    except Exception as error:
        log.warning('Ключи Google Ads не записаны: %s', type(error).__name__)
        return FAILED


async def on_message(update, context):
    from telegram.ext import ApplicationHandlerStop
    message = update.effective_message
    text = getattr(message, 'text', None)
    chat = update.effective_chat
    if not text or getattr(chat, 'type', '') != 'private':
        return
    collecting = chat.id in PENDING
    # While collecting, any one-word message is taken as the token (a wrong one gets the exact reason).
    if not is_attempt(text) and not (collecting and len(text.split()) == 1):
        return
    if not is_full_rights(update.effective_user.id):
        return
    reply = collect(chat.id, text, time.time())
    if reply is None:
        return
    try:
        await message.delete()
    except Exception as error:
        log.warning('Сообщение с ключами Google Ads не удалено: %s', type(error).__name__)
    await context.bot.send_message(chat_id=chat.id, text=reply, disable_web_page_preview=True)
    raise ApplicationHandlerStop


def register(app):
    from telegram.ext import MessageHandler, filters
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, on_message),
                    group=KEY_GROUP)

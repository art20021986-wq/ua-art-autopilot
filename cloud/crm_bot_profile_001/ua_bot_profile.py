"""Оформление обоих ботов в Telegram (CRM-BOT-PROFILE-001, владелец 15.11: «оформить Telegram красиво…
ты больше меня знаешь», «у нас же два бота», «всё на русском»).

Одна ответственность: после запуска CRM-бота один раз сверить с Telegram и, если отличается, поставить тексты ниже.
CRM-бот: описание до «Старт», строка профиля, подписи «Меню». Клиентский бот: описание и строка профиля (его меню
команд задаёт сам lead_bot — не трогаем). Обработчики ботов не меняет. Сбой только пишется в журнал.
"""
import logging
import os

from telegram import Bot, BotCommand

log = logging.getLogger(__name__)
CRM = {
    'description': ('Внутренняя CRM UA ART: автомобили, клиенты, заказы.\n\n'
                    'Вход — по коду приглашения от руководителя.'),
    'short_description': 'Внутренняя CRM UA ART для сотрудников.',
    'commands': (('start', '🏠 Главная'), ('cancel', '✖️ Отменить действие')),
}
CLIENT = {
    'description': ('UA ART — авто из Кореи и Японии под заказ в Украину. Авто в наличии, условия оплаты '
                    'и доставки, связь с менеджером. Нажмите «Старт».'),
    'short_description': 'Авто из Кореи и Японии под заказ в Украину.',
}
CLIENT_TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bot_token.txt')
DELAY = 10  # секунд после запуска: команды при старте ставит team_bot.post_init, эти идут после него
JOB = 'ua-bot-profile-001'


async def apply(bot, texts):
    """Поставить тексты, которые отличаются; вернуть список изменённого."""
    changed = []
    if (await bot.get_my_description()).description != texts['description']:
        await bot.set_my_description(texts['description'])
        changed.append('description')
    if (await bot.get_my_short_description()).short_description != texts['short_description']:
        await bot.set_my_short_description(texts['short_description'])
        changed.append('short_description')
    if 'commands' in texts and \
            [(c.command, c.description) for c in await bot.get_my_commands()] != list(texts['commands']):
        await bot.set_my_commands([BotCommand(c, d) for c, d in texts['commands']])
        changed.append('commands')
    return changed


def client_token():
    with open(CLIENT_TOKEN_FILE, encoding='utf-8') as handle:
        return handle.read().strip()


async def _job(context):
    try:
        log.info('оформление CRM-бота: %s', ', '.join(await apply(context.bot, CRM)) or 'без изменений')
    except Exception as e:
        log.warning('оформление CRM-бота не поставлено: %s', e)
    try:
        async with Bot(client_token()) as client:
            log.info('оформление клиентского бота: %s', ', '.join(await apply(client, CLIENT)) or 'без изменений')
    except Exception as e:
        log.warning('оформление клиентского бота не поставлено: %s', e)


def register(app):
    if app.job_queue is None:
        log.warning('оформление ботов: нет job_queue')
        return
    if not app.job_queue.get_jobs_by_name(JOB):
        app.job_queue.run_once(_job, when=DELAY, name=JOB)

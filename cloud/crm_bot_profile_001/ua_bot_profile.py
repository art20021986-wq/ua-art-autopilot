"""Оформление CRM-бота в Telegram: описание до «Старт», строка профиля и подписи в «Меню» (CRM-BOT-PROFILE-001,
владелец 15.11: «оформить Telegram красиво… ты больше меня знаешь»).

Одна ответственность: после запуска бота один раз сверить с Telegram и, если отличается, поставить тексты ниже.
Обработчики и меню бота не меняет. Сбой только пишется в журнал.
"""
import logging

from telegram import BotCommand

log = logging.getLogger(__name__)
DESCRIPTION = ('Внутренняя CRM UA ART: автомобили, клиенты, заказы.\n\n'
               'Вход — по коду приглашения от руководителя.')
SHORT_DESCRIPTION = 'Внутренняя CRM UA ART для сотрудников.'
COMMANDS = (('start', '🏠 Главная'), ('cancel', '✖️ Отменить действие'))
DELAY = 10  # секунд после запуска: команды при старте ставит team_bot.post_init, эти идут после него
JOB = 'ua-bot-profile-001'


async def apply(bot):
    """Поставить тексты, которые отличаются; вернуть список изменённого."""
    changed = []
    if (await bot.get_my_description()).description != DESCRIPTION:
        await bot.set_my_description(DESCRIPTION)
        changed.append('description')
    if (await bot.get_my_short_description()).short_description != SHORT_DESCRIPTION:
        await bot.set_my_short_description(SHORT_DESCRIPTION)
        changed.append('short_description')
    wanted = [BotCommand(c, d) for c, d in COMMANDS]
    if [(c.command, c.description) for c in await bot.get_my_commands()] != list(COMMANDS):
        await bot.set_my_commands(wanted)
        changed.append('commands')
    return changed


async def _job(context):
    try:
        changed = await apply(context.bot)
        log.info('оформление бота: %s', ', '.join(changed) or 'без изменений')
    except Exception as e:
        log.warning('оформление бота не поставлено: %s', e)


def register(app):
    if app.job_queue is None:
        log.warning('оформление бота: нет job_queue')
        return
    if not app.job_queue.get_jobs_by_name(JOB):
        app.job_queue.run_once(_job, when=DELAY, name=JOB)

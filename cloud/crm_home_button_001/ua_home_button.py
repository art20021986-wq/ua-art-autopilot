"""Постоянная кнопка «🏠 Главная» внизу чата CRM-бота (CRM-HOME-BUTTON-001, владелец 15.11, вариант Б).

Одна ответственность: нажатие кнопки работает ровно как команда /start (тот же обработчик, те же сбросы
начатого ввода), а сама кнопка (постоянная нижняя клавиатура Telegram) приходит один раз на чат после /start.
Ничего другого не меняет.
"""
import logging

from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import ApplicationHandlerStop, CommandHandler, MessageHandler, filters

log = logging.getLogger(__name__)
HOME_TEXT = '🏠 Главная'
NOTE = '🏠 Кнопка «Главная» внизу — одно нажатие возвращает в главное меню.'
GROUP = -100  # раньше всех обработчиков бота (перехват сообщений CRM — группа -1)
_SHOWN = '_ua_home_button_shown'


def keyboard():
    return ReplyKeyboardMarkup([[HOME_TEXT]], resize_keyboard=True, is_persistent=True)


def as_start(update, bot):
    """То же сообщение, но с текстом /start: дальше бот обрабатывает его как обычную команду."""
    data = update.to_dict()
    data['message']['text'] = '/start'
    data['message']['entities'] = [{'type': 'bot_command', 'offset': 0, 'length': 6}]
    return Update.de_json(data, bot)


async def on_home(update, context):
    await context.application.process_update(as_start(update, context.bot))
    raise ApplicationHandlerStop


async def on_start(update, context):
    """Перед обычным /start: один раз на чат (до перезапуска бота) прислать кнопку. /start идёт дальше."""
    if context.chat_data.get(_SHOWN):
        return
    try:
        await update.effective_message.reply_text(NOTE, reply_markup=keyboard())
        context.chat_data[_SHOWN] = True
    except Exception as e:
        log.warning('кнопка «Главная» не отправлена: %s', e)


def register(app):
    private = filters.ChatType.PRIVATE
    app.add_handler(MessageHandler(private & filters.UpdateType.MESSAGE & filters.Text([HOME_TEXT]), on_home),
                    group=GROUP)
    app.add_handler(CommandHandler('start', on_start, filters=private), group=GROUP)

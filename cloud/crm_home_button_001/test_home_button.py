"""ua_home_button with the real python-telegram-bot (22.x, as on the server); skipped when it is not installed.

Run: python3 cloud/crm_home_button_001/test_home_button.py
"""
import asyncio
import datetime
import importlib.util
from pathlib import Path
import unittest

try:
    import telegram
    from telegram.ext import (ApplicationBuilder, CallbackQueryHandler, CommandHandler, ConversationHandler,
                              MessageHandler, filters)
except ImportError:  # the CI runner has no python-telegram-bot
    telegram = None

HERE = Path(__file__).resolve().parent


def module():
    spec = importlib.util.spec_from_file_location('ua_home_button', HERE / 'ua_home_button.py')
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


@unittest.skipIf(telegram is None, 'python-telegram-bot is not installed')
class HomeButtonTests(unittest.TestCase):
    def setUp(self):
        self.hb = module()
        self.events, self.sent = [], []
        app = ApplicationBuilder().token('123:abc').updater(None).build()
        sent = self.sent

        async def fake_reply(message, text, *args, **kwargs):
            sent.append((text, kwargs.get('reply_markup')))
        self._orig = telegram.Message.reply_text
        telegram.Message.reply_text = fake_reply
        ev = self.events

        async def start(u, c):
            ev.append('start')
        async def catch(u, c):
            ev.append('catch:' + u.message.text)
        async def ask(u, c):
            ev.append('ask')
            return 1
        async def step(u, c):
            ev.append('step:' + u.message.text)
            return ConversationHandler.END
        async def cancel(u, c):
            ev.append('conv_cancelled')
            return ConversationHandler.END
        conv = ConversationHandler(entry_points=[CommandHandler('ask', ask)],
                                   states={1: [MessageHandler(filters.TEXT & ~filters.COMMAND, step)]},
                                   fallbacks=[CommandHandler('start', cancel)], allow_reentry=True)
        self.hb.register(app)
        app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, catch), group=-1)
        app.add_handler(conv)
        app.add_handler(CommandHandler('start', start), group=1)
        # initialize() would ask Telegram who the bot is (network); give the answer directly
        app.bot._bot_user = telegram.User(1, 'CRM', True, username='crm_test_bot')
        app._initialized = True
        self.app = app
        self.n = 0

    def tearDown(self):
        telegram.Message.reply_text = self._orig

    def send(self, text, chat_type='private'):
        self.n += 1
        entities = [{'type': 'bot_command', 'offset': 0, 'length': len(text)}] if text.startswith('/') else []
        data = {'update_id': self.n, 'message': {
            'message_id': self.n, 'date': int(datetime.datetime.now().timestamp()), 'text': text, 'entities': entities,
            'chat': {'id': 7, 'type': chat_type}, 'from': {'id': 7, 'is_bot': False, 'first_name': 'A'}}}
        asyncio.run(self.app.process_update(telegram.Update.de_json(data, self.app.bot)))

    def test_start_sends_the_button_once_and_goes_on(self):
        self.send('/start')
        self.send('/start')
        self.assertEqual(self.events, ['start', 'start'])
        self.assertEqual(len(self.sent), 1)
        text, markup = self.sent[0]
        self.assertEqual(text, self.hb.NOTE)
        self.assertEqual(markup.keyboard[0][0].text, '🏠 Главная')
        self.assertTrue(markup.is_persistent and markup.resize_keyboard)

    def test_button_works_as_start_and_ends_started_input(self):
        self.send('/ask')
        self.send('🏠 Главная')
        self.send('hello')
        # The button is not taken as the answer and not caught as text; the dialog is ended like by /start.
        self.assertEqual(self.events, ['ask', 'conv_cancelled', 'start', 'catch:hello'])

    def test_other_text_and_groups_untouched(self):
        self.send('Главная')
        self.send('🏠 Главная', chat_type='group')
        self.assertEqual(self.events, ['catch:Главная', 'catch:🏠 Главная'])
        self.assertEqual(self.sent, [])


if __name__ == '__main__':
    unittest.main()

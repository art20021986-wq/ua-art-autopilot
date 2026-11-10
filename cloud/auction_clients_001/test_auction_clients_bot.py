"""The bot dialogue: create a client, change password, block, deposit — with stand-ins for Telegram and the bot."""
import asyncio
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


class Stop(Exception):
    pass


class BadRequest(Exception):
    pass


telegram = types.ModuleType('telegram')
telegram.ext = types.ModuleType('telegram.ext')
telegram.ext.ApplicationHandlerStop = Stop
telegram.error = types.ModuleType('telegram.error')
telegram.error.BadRequest = BadRequest
orders = types.ModuleType('ua_crm_orders')
orders.allowed = lambda update: update.staff
orders.markup = lambda buttons: buttons
sys.modules.update({'telegram': telegram, 'telegram.ext': telegram.ext, 'telegram.error': telegram.error,
                    'ua_crm_orders': orders})
import ua_auction_clients as store  # noqa: E402
import ua_auction_clients_bot as bot  # noqa: E402


class Message:
    def __init__(self, log):
        self.log, self.text = log, ''

    async def reply_text(self, text, **kw):
        self.log.append((text, kw.get('reply_markup')))

    async def edit_message_text(self, text, **kw):
        self.log.append((text, kw.get('reply_markup')))


class Query(Message):
    def __init__(self, log, data):
        super().__init__(log)
        self.data, self.message = data, Message(log)

    async def answer(self, *a, **kw):
        pass


class BotTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patcher = patch.object(store, 'DB', Path(tmp.name) / 'clients.db')
        patcher.start()
        self.addCleanup(patcher.stop)
        self.log, self.context = [], types.SimpleNamespace(user_data={})

    def press(self, data, staff=True):
        query = Query(self.log, data)
        update = types.SimpleNamespace(callback_query=query, effective_message=query.message, staff=staff,
                                       effective_user=types.SimpleNamespace(id=397376186))
        with self.assertRaises(Stop):
            asyncio.run(bot.callback(update, self.context))

    def say(self, text):
        message = Message(self.log)
        message.text = text
        update = types.SimpleNamespace(effective_message=message, staff=True,
                                       effective_user=types.SimpleNamespace(id=397376186))
        with self.assertRaises(Stop):
            asyncio.run(bot.text(update, self.context))

    def create(self):
        self.press('ac:new')
        for answer in ('+380991112233', 'Шевченко', 'Тарас', 't@example.com'):
            self.say(answer)
        self.press('ac:city:Киев')
        self.say('4000')
        self.assertIn('лимит ставок 30 000 $', self.log[-1][0])
        self.press('ac:ok')

    def test_create_shows_card_and_message_to_forward(self):
        self.create()
        card, forward = self.log[-2][0], self.log[-1][0]
        self.assertIn('✅ Клиент создан', card)
        self.assertIn('Логін: +380991112233', forward)
        password = forward.split('Пароль: ')[1].split('\n')[0]
        self.assertIsNotNone(store.verify('+380991112233', password))
        self.assertEqual(self.context.user_data, {})

    def test_password_block_deposit(self):
        self.create()
        self.press('ac:pw:+380991112233')
        self.assertIn('Пароль изменён', self.log[-2][0])
        self.press('ac:block:+380991112233')
        self.assertIn('Доступ закрыт', self.log[-1][0])
        self.assertTrue(store.get('+380991112233')['blocked'])
        self.press('ac:dep:+380991112233')
        self.say('6000')
        self.assertIn('лимит ставок: 45 000 $', self.log[-1][0])

    def test_wrong_phone_ends_the_dialogue_with_a_hint(self):
        self.press('ac:new')
        for answer in ('12', 'Ш', 'Т', 't@e.com', 'Київ', '4000'):
            self.say(answer)
        self.assertIn('Телефон не похож на номер', self.log[-1][0])
        self.assertEqual(self.context.user_data, {})

    def test_strangers_are_refused(self):
        self.press('ac:new', staff=False)
        self.assertEqual(self.context.user_data, {})

    def test_folder_rows(self):
        self.create()
        self.assertEqual(bot.folder_rows(), [[('➕ Создать клиента', 'ac:new')], [('👥 Клиенты с доступом · 1', 'ac:list')]])


if __name__ == '__main__':
    unittest.main()

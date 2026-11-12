#!/usr/bin/env python3
"""NEW-CAR-VIN-001: the cars_ui.py edit, VIN input and the card through the installed photo_card.

cars_ui.py is the installed snapshot kept in cloud/lead_folders_001/fixtures; photo_card, ai_filter and
ai_fast_schema are the exact installed modules (loaded by the CRM-PHOTO-AUTOFILL-001 test helper); telegram and db
are stubs.
"""
import asyncio
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import candidate_builder  # noqa: E402
import edit_cars_ui  # noqa: E402

CARS_UI = ROOT / 'cloud/lead_folders_001/fixtures/cars_ui.txt'
VIN = 'WDD2452322J660244'


def photo_helper():
    """The CRM-PHOTO-AUTOFILL-001 test module (exact installed CRM modules), imported under its own name."""
    own = {name: sys.modules.pop(name) for name in ('candidate_builder', 'release_constants') if name in sys.modules}
    sys.path.insert(0, str(ROOT / 'cloud/crm_photo_card_001'))
    try:
        import test_photo_card  # binds the photo package's candidate_builder inside that module
    finally:
        sys.path.pop(0)
        sys.modules.update(own)
    return test_photo_card


class EditTests(unittest.TestCase):
    def setUp(self):
        self.source = CARS_UI.read_bytes()

    def test_button_line_above_the_folders_and_block_at_the_end(self):
        built = edit_cars_ui.build(self.source).decode('utf-8')
        # the snapshot has [REDACTED] lines: the whole file is compiled on the server by the preview
        compile(edit_cars_ui.BLOCK, 'block', 'exec')
        lines = built.splitlines()
        at = lines.index(edit_cars_ui.LINE.rstrip('\n'))
        self.assertEqual(lines[at - 4].strip(), "if data in ('cards_cars', 'cars_cards'):")
        self.assertIn("'← Назад', callback_data='menu'", lines[at + 1])
        self.assertTrue(built.endswith("log.warning('ua_new_car_bot не подключён: %s', e)\n"))
        original = self.source.decode('utf-8')
        self.assertEqual(built.replace(edit_cars_ui.LINE, '', 1)[:len(original.rstrip('\n'))], original.rstrip('\n'))
        self.assertEqual(len(built) - len(original.rstrip('\n')) - 1, len(edit_cars_ui.LINE) + len(edit_cars_ui.BLOCK))

    def test_refusals(self):
        built = edit_cars_ui.build(self.source)
        with self.assertRaisesRegex(ValueError, 'ALREADY_INSTALLED'):
            edit_cars_ui.build(built)
        anchor = edit_cars_ui.ANCHOR.encode('utf-8')
        with self.assertRaisesRegex(ValueError, 'ANCHOR'):
            edit_cars_ui.build(self.source.replace(anchor, b''))
        with self.assertRaisesRegex(ValueError, 'ANCHOR'):
            edit_cars_ui.build(self.source + b'\n' + anchor)

    def test_builder_refuses_unknown_dependencies(self):
        with self.assertRaisesRegex(ValueError, 'INPUT_HASH'):
            candidate_builder.build({'cars_ui.py': self.source}, {'db.py': b'x', 'photo_card.py': b'y'})

    def test_photo_card_pin_is_the_installed_module(self):
        import hashlib
        data = (ROOT / 'cloud/crm_photo_card_001/photo_card.py').read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), candidate_builder.DEPENDENCY_SHA256['photo_card.py'])


class Message:
    def __init__(self, text=''):
        self.text, self.replies = text, []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


class Query:
    def __init__(self, data):
        self.data, self.message, self.answers = data, Message(), []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


class BotTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        patcher, self.photo_card = photo_helper().crm_modules(Path(temp.name))
        self.addCleanup(patcher.stop)
        self.ai_filter = sys.modules['ai_filter']
        self.stop = sys.modules['telegram.ext'].ApplicationHandlerStop
        self.staff = {7: {'user_id': 70, 'active': 1}, 8: {'user_id': 80, 'active': 0}}
        sys.modules['db'].get_staff = self.staff.get
        sys.modules.pop('ua_new_car_bot', None)
        import ua_new_car_bot
        self.bot = ua_new_car_bot
        self.context = types.SimpleNamespace(user_data={})

    def run_handler(self, handler, update):
        try:
            return asyncio.run(handler(update, self.context))
        except self.stop:
            return 'STOP'

    def update(self, user=7, text=None, data=None):
        query = Query(data) if data else None
        message = Message(text) if text is not None else None
        return types.SimpleNamespace(effective_user=types.SimpleNamespace(id=user), callback_query=query,
                                     effective_message=message)

    def test_button_row(self):
        row = self.bot.rows()
        self.assertEqual([(b.text, b.callback_data) for b in row[0]], [('Создать новое объявление', 'ncv:start')])

    def test_vin_format(self):
        self.assertEqual(self.bot.vin_of(' wdd 2452322-j660244 '), VIN)
        for bad in ('', None, 'WDD2452322J66024', 'WDD2452322J6602444', 'WDD2452322J66024O', 'Привет'):
            self.assertIsNone(self.bot.vin_of(bad), bad)

    def test_button_asks_for_the_vin(self):
        update = self.update(data='ncv:start')
        self.assertEqual(self.run_handler(self.bot.start, update), 'STOP')
        self.assertEqual(update.callback_query.message.replies[0][0], 'Введите VIN-код для создания нового автомобиля')
        self.assertTrue(self.context.user_data[self.bot.WAIT])

    def test_only_active_staff(self):
        update = self.update(user=8, data='ncv:start')
        self.assertEqual(self.run_handler(self.bot.start, update), 'STOP')
        self.assertEqual(update.callback_query.message.replies, [])
        self.assertNotIn(self.bot.WAIT, self.context.user_data)

    def test_new_vin_creates_an_unpublished_card_through_photo_card(self):
        self.context.user_data[self.bot.WAIT] = True
        update = self.update(text=VIN.lower())
        with patch.object(self.ai_filter, 'find_by_vin', return_value=None), \
                patch.object(self.ai_filter, 'store', return_value=(42, 'UA-0042', True)) as store:
            self.assertEqual(self.run_handler(self.bot.text, update), 'STOP')
        store.assert_called_once_with({'brand': 'Mercedes-Benz', 'vin': VIN}, 70, None)
        text, kwargs = update.effective_message.replies[0]
        self.assertIn('UA-0042', text)
        self.assertIn('на сайте не опубликована', text)
        self.assertEqual([b.callback_data for r in kwargs['reply_markup'].rows for b in r], ['car_open:42', 'car_edit:42'])
        self.assertEqual(self.context.user_data, {'car_last': 42})

    def test_existing_vin_creates_nothing(self):
        self.context.user_data[self.bot.WAIT] = True
        update = self.update(text=VIN)
        with patch.object(self.ai_filter, 'find_by_vin', return_value={'id': 5, 'auto_number': 'UA-0005'}), \
                patch.object(self.ai_filter, 'store') as store:
            self.run_handler(self.bot.text, update)
        store.assert_not_called()
        self.assertIn('Карточка с таким VIN-кодом уже существует', update.effective_message.replies[0][0])
        self.assertEqual(self.context.user_data, {})

    def test_wrong_vin_asks_again(self):
        self.context.user_data[self.bot.WAIT] = True
        update = self.update(text='WDD2452322')
        with patch.object(self.ai_filter, 'store') as store:
            self.assertEqual(self.run_handler(self.bot.text, update), 'STOP')
        store.assert_not_called()
        self.assertEqual(update.effective_message.replies[0][0], self.bot.RETRY)
        self.assertTrue(self.context.user_data[self.bot.WAIT])

    def test_other_messages_go_on_to_the_bot(self):
        update = self.update(text=VIN)
        self.assertIsNone(self.run_handler(self.bot.text, update))
        self.context.user_data[self.bot.WAIT] = True
        self.assertIsNone(self.run_handler(self.bot.text, self.update(user=8, text=VIN)))
        self.assertEqual(update.effective_message.replies, [])

    def test_failure_answers_and_keeps_the_bot(self):
        self.context.user_data[self.bot.WAIT] = True
        update = self.update(text=VIN)
        with patch.object(self.ai_filter, 'find_by_vin', side_effect=RuntimeError('db')), \
                self.assertLogs('ua_new_car_bot', 'ERROR'):
            self.assertEqual(self.run_handler(self.bot.text, update), 'STOP')
        self.assertEqual(update.effective_message.replies[0][0], 'Не удалось создать карточку, попробуйте позже.')

    def test_other_button_ends_the_input(self):
        self.context.user_data[self.bot.WAIT] = True
        asyncio.run(self.bot.cancel(self.update(data='menu'), self.context))
        self.assertEqual(self.context.user_data, {})


if __name__ == '__main__':
    unittest.main()

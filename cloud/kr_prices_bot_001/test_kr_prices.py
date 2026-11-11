"""«💲 Цены Корея»: prices file, owner-only menu button, screens, cars_ui block."""
import asyncio
import datetime
import json
from pathlib import Path
import stat
import sys
import tempfile
import types
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


class Button:
    def __init__(self, text, callback_data=None):
        self.text, self.callback_data = text, callback_data


class Markup:
    def __init__(self, rows):
        self.inline_keyboard = tuple(tuple(row) for row in rows)


class Stop(Exception):
    pass


sys.modules.setdefault('telegram', types.SimpleNamespace(InlineKeyboardButton=Button, InlineKeyboardMarkup=Markup))
sys.modules.setdefault('telegram.ext', types.SimpleNamespace(ApplicationHandlerStop=Stop))

import candidate_builder  # noqa: E402
import edit_cars_ui  # noqa: E402
import ua_kr_prices_bot as bot  # noqa: E402
import ua_kr_prices_store as store  # noqa: E402

NOV = datetime.date(2026, 11, 11)
CARS_UI = (b'import logging\nlog = logging.getLogger(__name__)\n\n\ndef with_stats_button(markup):\n    return markup\n\n\n'
           b'def register(app):\n    app.append("base")\n')


def callbacks(markup):
    return [b.callback_data for row in markup.inline_keyboard for b in row]


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / 'video' / 'korea' / 'logistics.json'

    def tearDown(self):
        self.folder.cleanup()

    def test_defaults_add_up_as_on_the_page(self):
        self.assertEqual(store.per_car(store.DEFAULTS), 1200)
        self.assertEqual(store.total(store.DEFAULTS), 3450)

    def test_parse_six_numbers(self):
        self.assertEqual(store.parse('600 4800 250 1100 150 150'), store.DEFAULTS)
        self.assertEqual(store.parse('600,4800\n250; 1100 150 150'), store.DEFAULTS)
        for bad in ('600 4800 250 1100 150', '600 4 800 250 1100 150 150', '600 4800 250 1100 150 x', '-1 1 1 1 1 1',
                    '1.5 1 1 1 1 1', ''):
            with self.assertRaises(store.PriceError):
                store.parse(bad)
        with self.assertRaises(store.PriceError):
            store.parse('600 4800 250 1100 150 1000001')

    def test_months(self):
        self.assertEqual(store.months_ahead(datetime.date(2026, 11, 30)), ['2026-11', '2026-12', '2027-01'])
        months = {'2026-10': {}, '2026-12': {}}
        self.assertEqual(store.live_month(months, NOV), '2026-10')
        self.assertIsNone(store.live_month({'2026-12': {}}, NOV))

    def test_save_is_public_and_keeps_other_months(self):
        self.assertEqual(store.load(self.path), {})
        store.save_month('2026-11', store.DEFAULTS, self.path)
        months = store.save_month('2026-12', dict(store.DEFAULTS, fob=700), self.path)
        self.assertEqual(sorted(months), ['2026-11', '2026-12'])
        data = json.loads(self.path.read_text())
        self.assertEqual(data['version'], 1)
        self.assertEqual(data['months']['2026-12']['fob'], 700)
        self.assertEqual(store.load(self.path), months)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o644)
        self.assertEqual([p.name for p in self.path.parent.iterdir()], ['logistics.json'])
        with self.assertRaises(store.PriceError):
            store.save_month('2026-13', store.DEFAULTS, self.path)

    def test_path_is_the_site_file(self):
        self.assertEqual(store.PATH.relative_to(HERE), Path('video/korea/logistics.json'))


class BotTests(unittest.TestCase):
    owner = Markup([[Button('a', 'cards_cars')], [Button('s', 'staff_list')]])
    manager = Markup([[Button('a', 'cards_cars')]])

    def test_button_for_the_owner_only_and_once(self):
        shown = Markup([[Button('a', 'cards_cars')]])
        once = bot.with_button(self.owner, shown)
        self.assertEqual(callbacks(once), ['cards_cars', bot.HOME])
        self.assertEqual(callbacks(bot.with_button(self.owner, once)), ['cards_cars', bot.HOME])
        self.assertIs(bot.with_button(self.manager, shown), shown)
        self.assertEqual(once.inline_keyboard[-1][0].text, '💲 Цены Корея')

    def test_home_screen(self):
        screen = bot.home_screen({}, NOV)
        self.assertIn('цены страницы', screen['text'])
        self.assertIn('Итого за авто: 3450 $', screen['text'])
        self.assertEqual([row[0][1] for row in screen['buttons']],
                         ['krp:edit:2026-11', 'krp:edit:2026-12', 'krp:edit:2027-01', 'menu'])
        months = {'2026-11': store.DEFAULTS, '2026-12': dict(store.DEFAULTS, fob=700)}
        screen = bot.home_screen(months, NOV)
        self.assertIn('Сейчас на сайте (11.2026)', screen['text'])
        self.assertIn('12.2026', screen['text'])
        self.assertIn('Итого за авто: 3550 $', screen['text'])

    def test_ask_screen_shows_the_order_and_an_example(self):
        screen = bot.ask_screen('2026-12', {'2026-11': store.DEFAULTS}, NOV)
        self.assertIn('Цены на 12.2026', screen['text'])
        self.assertIn('<code>600 4800 250 1100 150 150</code>', screen['text'])
        self.assertEqual(screen['buttons'], [[('Отмена', bot.HOME)]])

    def test_callbacks_fit_telegram(self):
        for data in [bot.HOME, 'krp:edit:2026-11']:
            self.assertLessEqual(len(data.encode()), 64)


class Message:
    def __init__(self, text=''):
        self.text, self.replies = text, []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)


class DialogueTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / 'logistics.json'
        self.saved = (store.PATH, store.today_kyiv, bot._is_owner)
        store.PATH = self.path
        store.today_kyiv = lambda: NOV
        self.owner = True
        bot._is_owner = lambda update: self.owner
        original = store.save_month
        store.save_month = lambda month, prices, path=None: original(month, prices, self.path)
        self.original_save = original

    def tearDown(self):
        store.PATH, store.today_kyiv, bot._is_owner = self.saved
        store.save_month = self.original_save
        self.folder.cleanup()

    def send(self, text, waiting='2026-12'):
        context = types.SimpleNamespace(user_data={bot.WAIT: waiting} if waiting else {})
        message = Message(text)
        update = types.SimpleNamespace(effective_message=message)
        try:
            asyncio.run(bot.text(update, context))
            stopped = False
        except Stop:
            stopped = True
        return context, message, stopped

    def test_owner_saves_a_month(self):
        context, message, stopped = self.send('700 5200 260 1150 160 155')
        self.assertTrue(stopped)
        self.assertNotIn(bot.WAIT, context.user_data)
        self.assertEqual(store.load(self.path)['2026-12']['container'], 5200)
        self.assertIn('Цены на 12.2026 сохранены', message.replies[0])
        self.assertIn('Итого за авто: 3725 $', message.replies[0])

    def test_wrong_numbers_keep_waiting(self):
        context, message, stopped = self.send('700 5200')
        self.assertTrue(stopped)
        self.assertEqual(context.user_data[bot.WAIT], '2026-12')
        self.assertFalse(self.path.exists())
        self.assertIn('ровно 6', message.replies[0])

    def test_other_messages_go_on(self):
        for waiting, owner in ((None, True), ('2026-12', False)):
            self.owner = owner
            context, message, stopped = self.send('600 4800 250 1100 150 150', waiting)
            self.assertFalse(stopped)
            self.assertEqual(message.replies, [])
        self.assertFalse(self.path.exists())


class CarsUiTests(unittest.TestCase):
    def test_block_appended_once_and_keeps_previous_hooks(self):
        result = edit_cars_ui.build(CARS_UI)
        self.assertTrue(result.startswith(CARS_UI.rstrip(b'\n')))
        self.assertEqual(result.decode().count(edit_cars_ui.MARK), 1)
        with self.assertRaises(ValueError):
            edit_cars_ui.build(result)
        with self.assertRaises(ValueError):
            edit_cars_ui.build(b'def register(app):\n    pass\n')
        scope = {}
        sys.modules['ua_kr_prices_bot'] = bot
        exec(compile(result, 'cars_ui.py', 'exec'), scope)
        owner = Markup([[Button('s', 'staff_list')]])
        self.assertEqual(callbacks(scope['with_stats_button'](owner)), ['staff_list', bot.HOME])

    def test_candidate_needs_the_known_db(self):
        with self.assertRaises(ValueError):
            candidate_builder.build({'cars_ui.py': CARS_UI}, {'db.py': b'other'})


if __name__ == '__main__':
    unittest.main()

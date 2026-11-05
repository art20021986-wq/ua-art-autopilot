"""Enquiry desk: store, texts, and the bot flow with stand-ins for Telegram, the CRM db and the order package."""
import asyncio
import contextlib
import datetime
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ua_lead_calendar as cal
from ua_lead_desk_store import CLIENT, IN_WORK, NEW, STOPPED, Store


def ts(y, m, d, h=12):
    return datetime.datetime(y, m, d, h, tzinfo=cal.KYIV).timestamp()


class Stop(Exception):
    pass


class BadRequest(Exception):
    pass


def _stub_modules():
    """Minimal telegram, db and ua_order stand-ins (only what the desk touches)."""
    tg = types.ModuleType('telegram')
    tg.InlineKeyboardButton = lambda label, **kw: (label, kw)
    tg.InlineKeyboardMarkup = lambda rows: rows
    err = types.ModuleType('telegram.error')
    err.BadRequest = BadRequest
    ext = types.ModuleType('telegram.ext')
    ext.ApplicationHandlerStop = Stop
    order = types.ModuleType('ua_order')
    crm = types.ModuleType('ua_order.crm')
    crm.detail_view = lambda row, catalog: {'text': '<b>Заявка:</b> %s' % row['number']}
    storage = types.ModuleType('ua_order.storage')

    class NotFound(LookupError):
        pass
    storage.NotFound = NotFound
    db = types.ModuleType('db')
    db.cards = []
    db.create_card = lambda table, data, actor: db.cards.append((table, data, actor)) or len(db.cards)
    sys.modules.update({'telegram': tg, 'telegram.error': err, 'telegram.ext': ext, 'ua_order': order,
                        'ua_order.crm': crm, 'ua_order.storage': storage, 'db': db})
    return db, NotFound


DB, NOT_FOUND = _stub_modules()
import ua_lead_desk  # noqa: E402
import ua_lead_desk_view as view  # noqa: E402


def memory_store(clock):
    path = tempfile.NamedTemporaryFile(suffix='.db', delete=False).name  # a file, like crm.db; any thread

    @contextlib.contextmanager
    def connect():
        connection = sqlite3.connect(path)
        try:
            with connection:
                yield connection
        finally:
            connection.close()
    store = Store(connect, clock=clock)
    store.initialize()
    return store


class Repository:
    def __init__(self, rows):
        self.rows = {r['id']: r for r in rows}

    def list_requests(self, before=None, limit=2):
        rows = sorted((r for r in self.rows.values() if before is None or r['id'] < before), key=lambda r: -r['id'])
        return rows[:limit], rows[limit - 1]['id'] if len(rows) > limit else None

    def detail(self, order_id):
        if order_id not in self.rows:
            raise NOT_FOUND()
        return self.rows[order_id]


def row(order_id, created_at, name='Иван', **data):
    return {'id': order_id, 'number': 'OR-%06d' % order_id, 'created_at': created_at,
            'data': dict(customer_name=name, contact={'phone': '+380991112233'}, **data)}


class StoreTests(unittest.TestCase):
    def test_default_new_then_actions(self):
        store = memory_store(lambda: 100)
        self.assertEqual(store.get(5), {'status': NEW, 'note': '', 'client_id': None})
        store.set_note(5, '  перезвонить вечером ', 1)
        store.set_status(5, IN_WORK, 1)
        self.assertEqual(store.get(5), {'status': IN_WORK, 'note': 'перезвонить вечером', 'client_id': None})
        store.set_client(5, 9, 1)
        self.assertEqual(store.get(5)['status'], CLIENT)
        with self.assertRaises(ValueError):
            store.set_status(5, 'deleted', 1)

    def test_track_from_fixed_at_first_start(self):
        store = memory_store(lambda: 100)
        store.clock = lambda: 999
        store.initialize()
        self.assertEqual(store.track_from(), 100)

    def test_reminder_once(self):
        store = memory_store(lambda: 1)
        self.assertTrue(store.claim_reminder(3, 'last_day'))
        self.assertFalse(store.claim_reminder(3, 'last_day'))
        self.assertTrue(store.claim_reminder(3, 'overdue'))


class ViewTests(unittest.TestCase):
    NEW_STATE = {'status': NEW, 'note': '', 'client_id': None}

    def test_badges(self):
        r = row(1, ts(2026, 11, 5))  # Thursday; deadline end of Monday 09.11
        self.assertEqual(view.badge(r, self.NEW_STATE, ts(2026, 11, 5, 15), 0), '🟢 Осталось 3 раб. дн.')
        self.assertEqual(view.badge(r, self.NEW_STATE, ts(2026, 11, 9), 0), '🟡 Последний день')
        self.assertEqual(view.badge(r, self.NEW_STATE, ts(2026, 11, 10), 0), '🔴 Просрочена')
        self.assertEqual(view.badge(r, dict(self.NEW_STATE, status=IN_WORK), ts(2026, 11, 10), 0), '🔵 В работе')
        self.assertEqual(view.badge(r, self.NEW_STATE, ts(2026, 11, 10), ts(2026, 11, 6)), '🟢 Новая')

    def test_detail_shows_received_deadline_note(self):
        r = row(7, ts(2026, 11, 5, 10))
        screen = view.detail_view('BODY', r, dict(self.NEW_STATE, note='<b>VIP</b>'), ts(2026, 11, 5, 11), 0)
        self.assertIn('Поступила:</b> чт 05.11 10:00', screen['text'])
        self.assertIn('Ответить до:</b> конца дня пн 09.11', screen['text'])
        self.assertIn('&lt;b&gt;VIP', screen['text'])
        flat = [b[1] for line in screen['buttons'] for b in line]
        self.assertEqual(flat, ['leads:st:7:in_work', 'leads:st:7:stopped', 'leads:note:7', 'leads:client:7',
                                'leads:list'])

    def test_list_has_new_lead_form_link(self):
        screen = view.list_view([row(1, ts(2026, 11, 5))], {1: self.NEW_STATE}, ts(2026, 11, 5), 0, None, 'back')
        self.assertIn(('➕ Новая заявка', None, view.NEW_LEAD_URL), [b for line in screen['buttons'] for b in line])

    def test_client_card(self):
        card = view.client_card(row(4, 0, other_model='Kia K5'), 'звонить после 18', 'Kia K5')
        self.assertEqual(card, {'name': 'Иван', 'phone': '+380991112233', 'car_interest': 'Kia K5',
                                'wishes': 'звонить после 18', 'source': 'Заявка с сайта OR-000004'})


class FakeMessage:
    def __init__(self, text=''):
        self.text, self.replies = text, []

    async def reply_text(self, text, **kw):
        self.replies.append(text)


class FakeQuery:
    def __init__(self, data):
        self.data, self.message, self.shown, self.answers = data, FakeMessage(), [], []

    async def answer(self, *a, **kw):
        self.answers.append(a)

    async def edit_message_text(self, text, **kw):
        self.shown.append((text, kw['reply_markup']))


def update(data=None, text=None):
    u = types.SimpleNamespace(effective_user=types.SimpleNamespace(id=42))
    u.callback_query = FakeQuery(data) if data else None
    u.effective_message = FakeMessage(text) if text is not None else None
    return u


class DeskTests(unittest.TestCase):
    def setUp(self):
        DB.cards.clear()
        self.now = [ts(2026, 11, 5, 9)]
        self.store = memory_store(lambda: self.now[0])
        # Ids grow with time, as in the order database; enquiry 1 predates the desk (no deadline).
        self.repo = Repository([row(1, ts(2026, 11, 4)), row(2, ts(2026, 11, 5, 9), model='k5', purchase_country_code='kr'),
                                row(3, ts(2026, 11, 5, 9), name='Олег')])
        catalog = types.SimpleNamespace(model=lambda c, m: {'labels': {'ru': 'Kia K5'}})
        self.allowed = True
        self.desk = ua_lead_desk.Desk(self.repo, catalog, self.store, authorize=lambda u: self.allowed,
                                      staff_ids=lambda: [10, 11], menu_callback='cards_clients',
                                      clock=lambda: self.now[0])
        self.context = types.SimpleNamespace(user_data={})

    def press(self, data):
        u = update(data)
        with self.assertRaises(Stop):
            asyncio.run(self.desk.callback(u, self.context))
        return u.callback_query

    def test_denied_without_role(self):
        self.allowed = False
        query = self.press('leads:list')
        self.assertEqual(query.shown, [])

    def test_list_pages_and_status_flow(self):
        query = self.press('leads:list')
        text, rows = query.shown[0]
        labels = [b[0] for line in rows for b in line]
        self.assertTrue(labels[0].startswith('🟢 Осталось 3 раб. дн. · Олег'))
        self.assertIn('Далее →', labels)
        self.press('leads:st:3:in_work')
        self.assertEqual(self.store.get(3)['status'], IN_WORK)
        self.press('leads:st:3:stopped')
        self.assertEqual(self.store.get(3)['status'], STOPPED)
        self.press('leads:st:3:deleted')  # unknown action → «Заявка не найдена», nothing changed
        self.assertEqual(self.store.get(3)['status'], STOPPED)

    def test_note_then_client_card(self):
        self.press('leads:note:2')
        self.assertEqual(self.context.user_data[ua_lead_desk.NOTE_WAIT], 2)
        u = update(text='бюджет до 18 000 $')
        with self.assertRaises(Stop):
            asyncio.run(self.desk.note(u, self.context))
        self.assertEqual(self.store.get(2)['note'], 'бюджет до 18 000 $')
        self.press('leads:client:2')
        self.press('leads:client:2')  # second press opens, never duplicates
        self.assertEqual(len(DB.cards), 1)
        table, card, actor = DB.cards[0]
        self.assertEqual((table, card['car_interest'], card['wishes'], actor), ('clients', 'Kia K5', 'бюджет до 18 000 $', 42))
        self.assertEqual(self.store.get(2), {'status': CLIENT, 'note': 'бюджет до 18 000 $', 'client_id': 1})

    def test_other_text_passes_through(self):
        self.assertIsNone(asyncio.run(self.desk.note(update(text='обычное сообщение'), self.context)))

    def test_missing_enquiry(self):
        query = self.press('leads:open:99')
        self.assertIn('Заявка не найдена', query.shown[0][0])

    def test_reminders_last_day_then_overdue_once(self):
        sent = []
        bot = types.SimpleNamespace()

        async def send_message(chat, text, **kw):
            sent.append((chat, text))
        bot.send_message = send_message
        context = types.SimpleNamespace(bot=bot)
        self.store.set_status(3, IN_WORK, 1)  # answered: no reminders; enquiry 1 is untracked
        self.now[0] = ts(2026, 11, 9, 10)  # Monday, last day for enquiries 2 and 3
        asyncio.run(self.desk.remind(context))
        asyncio.run(self.desk.remind(context))
        self.assertEqual([(c, t.split('\n')[1]) for c, t in sent],
                         [(10, 'Заявка OR-000002 · Иван'), (11, 'Заявка OR-000002 · Иван')])
        sent.clear()
        self.now[0] = ts(2026, 11, 10, 3)  # night: silent
        asyncio.run(self.desk.remind(context))
        self.assertEqual(sent, [])
        self.now[0] = ts(2026, 11, 10, 9)
        asyncio.run(self.desk.remind(context))
        self.assertTrue(all(t.startswith('🔴 Срок ответа прошёл\nЗаявка OR-000002') for c, t in sent))
        self.assertEqual(len(sent), 2)


if __name__ == '__main__':
    unittest.main()

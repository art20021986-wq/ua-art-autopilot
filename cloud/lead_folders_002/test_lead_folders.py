#!/usr/bin/env python3
"""Lead desk and orders (LEAD-FOLDERS-001, fix 002) on a temporary database: folders, states, contract, stages."""
from contextlib import closing, contextmanager
import datetime
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(HERE.parent / 'lead_folders_001'))  # the other modules, installed by LEAD-FOLDERS-INSTALL
sys.path.insert(2, str(HERE.parent / 'lead_desk_001'))  # ua_lead_calendar, installed by ORDER-PROCESS-001
import ua_contract_files as files  # noqa: E402
import ua_crm_orders_view as orders_view  # noqa: E402
import ua_lead_desk  # noqa: E402
import ua_lead_desk_view as view  # noqa: E402
import ua_lead_folders as folders  # noqa: E402
import ua_lead_sources as sources  # noqa: E402
from ua_lead_desk_store import CONTRACT, IN_WORK, NEW, Store  # noqa: E402
from ua_order_book import OrderBook  # noqa: E402

NOW = int(datetime.datetime(2026, 11, 6, 12, 0, tzinfo=datetime.timezone.utc).timestamp())


def database():
    path = Path(tempfile.mkdtemp()) / 'crm.db'

    @contextmanager
    def connect():
        with closing(sqlite3.connect(path)) as connection:
            with connection:
                yield connection
    return connect


class Catalog:
    def model(self, country, key):
        return {'labels': {'ru': 'Kia K5'}} if key == 'kia-k5' else None


def detail_view(row, catalog):
    return {'text': '<b>Заявка:</b> %s' % row['number']}


def enquiry(row_id, data, created=NOW - 3600, channel='site'):
    return {'id': row_id, 'number': 'OR-%06d' % row_id, 'created_at': created, 'channel': channel, 'data': data,
            'telegram_user_id': None}


ROWS = [
    enquiry(3, {'schema_version': 'ua_order_request.card.v1', 'car_code': 'UA-0018', 'customer_name': 'Иван',
                'contact': {'phone': '+380992222002'}}),
    enquiry(2, {'schema_version': 'ua_order_request.quick.v1', 'purchase_country_code': 'korea', 'model': 'kia-k5',
                'customer_name': 'Олена', 'contact': {'phone': '+380501112233'}}),
    enquiry(1, {'schema_version': 'ua_order_request.v2', 'purchase_country_code': 'help', 'customer_name': 'Петро',
                'contact': {'method': 'telegram', 'value': 'petro_ua'}}, channel='telegram_bot'),
]
BOT = [{'uid': '42', 'name': 'Анна', 'username': 'anna', 'date': '2026-11-06', 'time': '10:15',
        'kind': 'бронь · Kia K5 2023', 'note': 'Бронь автомобиля'},
       {'uid': '43', 'name': 'Гість', 'username': None, 'date': '2026-11-06', 'time': '10:20',
        'kind': 'просмотр · Kia K5 2023', 'note': 'UA-0018'}]


class Repository:
    def list_requests(self, before=None):
        return ROWS, None

    def detail(self, row_id):
        return next(row for row in ROWS if row['id'] == row_id)


class Folders(unittest.TestCase):
    def test_where_each_lead_goes(self):
        leads = {lead.key: lead for lead in self.sources().all()}
        self.assertEqual(leads['or:3'].folder, folders.STOCK)
        self.assertEqual((leads['or:2'].folder, leads['or:2'].subject), ('korea', 'Kia K5'))
        self.assertEqual((leads['or:1'].folder, leads['or:1'].telegram, leads['or:1'].source),
                         (folders.GENERAL, 'petro_ua', 'Заявка из бота OR-000001'))
        bot = [lead for lead in leads.values() if lead.key.startswith('bot:')]
        self.assertEqual([(b.folder, b.subject, b.telegram) for b in bot], [(folders.STOCK, 'Kia K5 2023', '@anna')])
        self.assertEqual(len(leads), 4)  # a car view is not a lead
        self.assertEqual(self.sources().get(bot[0].key), bot[0])

    def test_every_country_has_a_folder(self):
        for country in ('korea', 'japan', 'usa', 'europe', 'china', 'canada', 'uae', 'georgia'):
            self.assertEqual(folders.of_enquiry({'purchase_country_code': country}), country)
        self.assertEqual(folders.of_enquiry({'purchase_country_code': 'other'}), folders.GENERAL)

    def sources(self):
        return sources.Sources(Repository(), Catalog(), detail_view, lambda: BOT, datetime.timezone.utc)


class DeskFlow(unittest.TestCase):
    def setUp(self):
        connect = database()
        self.store, self.book = Store(connect, clock=lambda: NOW - 86400), OrderBook(connect, clock=lambda: NOW)
        self.store.initialize()
        self.book.initialize()
        self.folder_root = tempfile.mkdtemp()
        self.desk = ua_lead_desk.Desk(Folders.sources(None), self.store, self.book, authorize=lambda u: True,
                                      recipients=lambda: [1], clock=lambda: NOW, files_root=self.folder_root)

    def test_home_and_folders(self):
        screen = self.desk.screen('home', '')
        self.assertIn('новых 4', screen['text'])
        self.assertEqual(len(screen['buttons']), len(folders.FOLDERS) + 1)
        self.assertEqual(screen['buttons'][0][0], ('🚗 Авто в наличии · 2', 'ld:f:stock'))
        stock = self.desk.screen('f', 'stock')
        self.assertTrue(stock['buttons'][0][0][0].endswith('06.11 14:00') or 'UA-0018' in stock['buttons'][0][0][0])

    def test_contract_makes_an_order_in_the_same_folder(self):
        name = files.save('or:3', b'%PDF-1', 'pdf', root=self.folder_root, clock=lambda: NOW)
        done = self.desk.make_order('or:3', ' 15/11 ', name, actor=7)
        self.assertIn('договор № 15/11', done['text'])
        self.assertEqual(self.store.get('or:3')['status'], CONTRACT)
        order = self.book.all()[0]
        self.assertEqual((order['folder'], order['contract_no'], order['name'], order['phone'], order['subject'], order['stage']),
                         ('stock', '15/11', 'Иван', '+380992222002', 'UA-0018', 'contract'))
        # The lead leaves the desk; a repeated confirm makes no second order.
        self.assertNotIn('or:3', [l.key for l in view.active(self.desk.sources.all(), self.store.all())])
        self.desk.make_order('or:3', '15/11', name, actor=7)
        self.assertEqual(len(self.book.all()), 1)
        self.assertIn('Договоров за месяц:</b> 1', self.desk.screen('home', '')['text'])
        self.assertEqual(files.path(name, root=self.folder_root).read_bytes(), b'%PDF-1')

    def test_status_and_note(self):
        self.store.set_status('or:2', IN_WORK, 7)
        self.store.set_note('or:2', '  позвонить завтра ', 7)
        screen = self.desk.detail('or:2')
        self.assertIn('🔵 В работе', screen['text'])
        self.assertIn('позвонить завтра', screen['text'])
        self.assertEqual(screen['buttons'][0], [('⚪ Остановить', 'ld:st:stopped:or:2')])
        self.assertEqual(self.store.get('or:1')['status'], NEW)

    def test_reminder_once(self):
        old = NOW - 10 * 86400
        self.store = Store(database(), clock=lambda: old - 1)
        self.store.initialize()
        ROWS.append(enquiry(9, {'schema_version': 'ua_order_request.quick.v1', 'purchase_country_code': 'japan',
                                'model': 'x', 'customer_name': 'Old', 'contact': {'phone': '+380'}}, created=old))
        try:
            self.desk.store = self.store
            due = self.desk._due()
            self.assertIn(('or:9', 'overdue'), [(lead.key, kind) for lead, kind in due])
            self.assertEqual(self.desk._due(), [])
        finally:
            ROWS.pop()


class Orders(unittest.TestCase):
    def setUp(self):
        self.book = OrderBook(database(), clock=lambda: NOW)
        self.book.initialize()
        values = {'lead_key': 'or:2', 'folder': 'korea', 'contract_no': '7', 'contract_file': 'or-2-1793872225.pdf',
                  'name': 'Олена', 'phone': '+380501112233', 'telegram': '', 'subject': 'Kia K5', 'source': 'Заявка с сайта'}
        self.order_id = self.book.create(values, 7)

    def test_stages_to_delivery(self):
        seen = 'contract'
        for _ in range(5):
            seen = self.book.advance(self.order_id, seen, 7)['stage']
        self.assertEqual(seen, 'delivered')
        order = self.book.get(self.order_id)
        self.assertEqual(len(order['stages']), 6)
        screen = orders_view.detail_view(order, datetime.timezone.utc)
        self.assertNotIn('➡️', str(screen['buttons']))

    def test_double_tap_marks_once(self):
        self.book.advance(self.order_id, 'contract', 7)
        self.assertEqual(self.book.advance(self.order_id, 'contract', 7)['stage'], 'bought')

    def test_home_counts_by_folder(self):
        screen = orders_view.home(self.book.all(), NOW, datetime.timezone.utc, [[('← Назад', 'menu')]])
        self.assertIn('Всего: 1 · в работе: 1 · выдано: 0 · за месяц: 1', screen['text'])
        self.assertIn([('🇰🇷 Корея · 1', 'co:f:korea')], screen['buttons'])
        self.assertEqual(screen['buttons'][-1], [('← Назад', 'menu')])
        detail = orders_view.detail_view(self.book.get(self.order_id), datetime.timezone.utc)
        self.assertEqual(detail['buttons'][0], [('➡️ Авто выкуплено', 'co:next:%d:contract' % self.order_id)])


class ContractFiles(unittest.TestCase):
    def test_kinds_and_paths(self):
        self.assertEqual(files.extension('Договор.PDF'), 'pdf')
        self.assertEqual(files.extension('scan', 'image/jpeg'), 'jpg')
        self.assertIsNone(files.extension('virus.exe', 'application/x-msdownload'))
        for bad in ('../crm.db', 'or-1-1.pdf', 'or-1-1793872225.exe'):
            with self.assertRaises(ValueError):
                files.path(bad)
        with self.assertRaises(ValueError):
            files.save('or:1', b'', 'pdf', root=tempfile.mkdtemp())


if __name__ == '__main__':
    unittest.main()

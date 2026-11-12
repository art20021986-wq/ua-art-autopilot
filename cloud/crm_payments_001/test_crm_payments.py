"""Tests of CRM-PAYMENTS-001: contract rules, the store and the cabinet read, texts, lot parsing, bot helpers."""
import contextlib
import datetime
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'lead_desk_001')]  # ua_lead_calendar is installed on the server

import edit_cars_ui  # noqa: E402
import ua_pay_lot as lot  # noqa: E402
import ua_pay_rules as rules  # noqa: E402
import ua_pay_store as payst  # noqa: E402
import ua_pay_view as view  # noqa: E402

D = datetime.date


class Rules(unittest.TestCase):
    def test_working_days_skip_sunday_and_holidays(self):
        self.assertEqual(rules.add_working_days(D(2026, 11, 14), 1), D(2026, 11, 16))  # Sat -> Mon (Sun skipped)
        self.assertEqual(rules.add_working_days(D(2026, 12, 24), 1), D(2026, 12, 26))  # 25.12 is a holiday

    def test_due_dates_of_the_contract(self):
        start = D(2026, 11, 12)  # Thursday
        self.assertIsNone(rules.due_date(1, start))
        self.assertEqual(rules.due_date(2, start), D(2026, 11, 20))  # 7 working days
        self.assertEqual(rules.due_date(3, start), D(2026, 11, 24))  # 10 working days
        self.assertEqual(rules.due_date(3, start, ferry=D(2026, 11, 20)), D(2026, 11, 19))  # before the ferry
        self.assertEqual(rules.due_date(4, start), D(2026, 11, 18))  # 5 working days

    def test_sanctions(self):
        due = D(2026, 12, 1)
        self.assertEqual(rules.sanctions(3450, due, due, 0.155)['total'], 0)
        s = rules.sanctions(3450, due, D(2026, 12, 3), 0.155)
        self.assertEqual((s['days'], s['work_days'], s['fine']), (2, 2, 0.0))
        self.assertAlmostEqual(s['penalty'], round(3450 * 0.31 / 365 * 2, 2))
        self.assertAlmostEqual(s["annual"], 6.81)
        late = rules.sanctions(3450, due, D(2026, 12, 9), 0.155)  # 7 working days late
        self.assertEqual(late['fine'], 172.5)

    def test_state(self):
        p = {'amount': 100, 'paid': 0, 'due': D(2026, 12, 1)}
        self.assertEqual(rules.state(p, D(2026, 12, 1)), 'open')
        self.assertEqual(rules.state(p, D(2026, 12, 2)), 'late')
        self.assertEqual(rules.state(p, rules.extra_deadline(D(2026, 12, 1)) + datetime.timedelta(days=1)), 'final')
        self.assertEqual(rules.state(dict(p, paid=100), D(2027, 1, 1)), 'paid')
        self.assertEqual(rules.state(None, D(2027, 1, 1)), 'none')


class Store(unittest.TestCase):
    def setUp(self):
        handle, self.path = tempfile.mkstemp(suffix='.db')
        os.close(handle)
        with sqlite3.connect(self.path) as c:
            c.execute('CREATE TABLE crm_orders (id INTEGER PRIMARY KEY, contract_no TEXT, name TEXT, phone TEXT, '
                      'stage TEXT, subject TEXT, created_by INTEGER)')
            c.execute("INSERT INTO crm_orders VALUES (1, 'A-1', 'Иван', '+38 (067) 123-45-67', 'bought', 'Kia', 7)")
        self.store = payst.PayStore(lambda: contextlib.closing(_Commit(self.path)), clock=lambda: 1_763_000_000)
        self.store.initialize()

    def tearDown(self):
        os.unlink(self.path)

    def test_payments_flow_and_cabinet(self):
        self.assertEqual(self.store.payments(1)[1]['amount'], 1600)
        self.store.pay(1, 1, 1600, 7)
        self.store.set_car(1, {'lot_id': '20261106043479', 'title': 'Kia Sorento', 'year': '2021', 'vin': 'KNA1',
                               'photos': ['https://x/1.jpg'], 'price_usd': 14200}, 7)
        due = self.store.confirm_price(1, 14200, D(2026, 11, 12), 7)
        self.assertEqual(due, D(2026, 11, 20))
        self.assertEqual(self.store.payments(1)[2]['amount'], 13200)
        self.store.issue(1, 3, 3450, D(2026, 11, 12), 7, ferry=D(2026, 12, 1))
        self.assertEqual([o['id'] for o in self.store.orders()], [1])
        self.assertTrue(self.store.claim_reminder('k'))
        self.assertFalse(self.store.claim_reminder('k'))
        cars = payst.purchased_cars('0671234567', self.path, today=D(2026, 11, 23))
        self.assertEqual(len(cars), 1)
        kinds = {p['kind']: p for p in cars[0]['payments']}
        self.assertEqual((kinds['services']['paid_usd'], kinds['deposit']['paid_usd']), (600, 1000))
        self.assertLess(kinds['car']['days_left'], 0)  # 20.11 passed
        self.assertGreater(kinds['car']['penalty_usd'], 0)
        self.assertEqual(kinds['logistics']['days_left'], 1)  # due 24.11
        self.assertEqual(cars[0]['penalty']['annual_percent'], 36.0)
        self.assertEqual([x['state'] for x in cars[0]['stages']], ['done', 'current'] + ['todo'] * 6)
        self.assertEqual(cars[0]['stages'][1]['label'], 'Авто викуплено на аукціоні')
        self.assertEqual(payst.purchased_cars('+380509999999', self.path), [])

    def test_screen_texts(self):
        order = {'id': 1, 'contract_no': 'A-1', 'name': 'Иван', 'stage': 'bought', 'subject': 'Kia'}
        payments = self.store.payments(1)
        screen = view.screen(order, None, payments, D(2026, 11, 12), 0.155)
        self.assertIn('Услуга 600 $ + передоплата 1 000 $', screen['text'])
        labels = [b[0] for row in screen['buttons'] for b in row]
        self.assertIn(view.LOT_BUTTON, labels)
        self.assertEqual(view.order_buttons(order, None)[0][0][0], view.BUTTON)
        self.assertEqual(len(view.order_buttons(dict(order, stage='contract'), None)), 1)
        self.assertIn('ты должен обязательно внести данные автомобиля', view.remind_car(order)['text'])


class _Commit(sqlite3.Connection):
    """sqlite connection that commits on close, like db.connect."""

    def __init__(self, path):
        super().__init__(path)

    def close(self):
        self.commit()
        super().close()


class Lot(unittest.TestCase):
    def test_lot_id(self):
        self.assertEqual(lot.lot_id('https://jpauto.auction/vehicle-detail/kr/20261106043479'), '20261106043479')
        self.assertEqual(lot.lot_id(' 20261106043479 '), '20261106043479')
        with self.assertRaises(ValueError):
            lot.lot_id('hello')

    def test_car_from_page(self):
        detail = {'specs': {'Manufacturer': 'KIA', 'Model': 'Sorento', 'Trim Level': '2.2 4WD',
                            'Model Year (Registration Date)': '2021 (2021-03)', 'Mileage': '45,000 km',
                            'Color': 'White'}, 'vin': 'KNAPU81BDM1234567', 'fuel': 'Diesel', 'photos': ['a', 'b']}
        car = lot.car_from_page('20261106043479', detail, 'Final Price 18,500,000 KRW', {'KRW': 0.03, 'USD': 41.5})
        self.assertEqual(car['title'], 'KIA Sorento 2.2 4WD')
        self.assertEqual((car['year'], car['price_krw'], car['price_usd']), ('2021', 18500000, 13373))
        self.assertIsNone(lot.car_from_page('1' * 14, detail, 'Final Price -', None)['price_usd'])


class Photos(unittest.TestCase):
    def test_save_photos(self):
        written = {}

        def fetch(url):
            if 'bad' in url:
                raise ValueError('NOT_AN_IMAGE')
            return b'jpg'

        urls = lot.save_photos(5, ['https://a/1.jpg', 'https://a/bad.jpg', 'https://a/3.jpg'], fetch,
                               lambda path, data: written.__setitem__(str(path), data), root=Path('/r'),
                               base='https://s/', token='abc')
        self.assertEqual(urls, ['https://s/5-abc/1.jpg', 'https://s/5-abc/3.jpg'])
        self.assertEqual(sorted(written), ['/r/5-abc/1.jpg', '/r/5-abc/3.jpg'])


class OrderStages(unittest.TestCase):
    def test_eight_stages_keep_old_keys(self):
        import edit_order_book
        source = (HERE.parent / 'lead_folders_001' / 'ua_order_book.py').read_bytes()
        ns = {}
        exec(compile(edit_order_book.build(source), 'ua_order_book.py', 'exec'), ns)
        keys = [k for k, _ in ns['STAGES']]
        self.assertEqual(keys, [k for k, _ in payst.STAGES])
        self.assertTrue({'contract', 'bought', 'transit', 'georgia', 'ukraine', 'delivered'} <= set(keys))
        self.assertEqual(ns['next_stage']('bought'), 'korea_port')
        with self.assertRaises(ValueError):
            edit_order_book.build(source + b'#')


class Edit(unittest.TestCase):
    def test_block_appended_once(self):
        source = b"import x\nlog = 1\n\ndef register(app):\n    pass\n"
        built = edit_cars_ui.build(source)
        self.assertIn(b'# CRM-PAYMENTS-001', built)
        with self.assertRaises(ValueError):
            edit_cars_ui.build(built)


class BotHelpers(unittest.TestCase):
    def test_helpers(self):
        sys.modules.setdefault('db', type(sys)('db'))
        import ua_pay_bot as bot
        self.assertEqual(bot.parse_nbu_rate([{'value': 15.5, 'dt': '20260101'}, {'value': 14, 'dt': '20251201'}]),
                         0.155)
        with self.assertRaises(ValueError):
            bot.parse_nbu_rate([])
        self.assertEqual(bot.number('1 500,50 $'), 1500.5)
        with self.assertRaises(ValueError):
            bot.number('нет')


if __name__ == '__main__':
    unittest.main()

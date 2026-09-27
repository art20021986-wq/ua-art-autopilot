"""Explicit integration checks. Only Carix$orders_test; synthetic data, no bots.

Run on PythonAnywhere with Python 3.10 and this package on PYTHONPATH.
The dedicated test database must exist and be empty on the first run.
"""
from concurrent.futures import ThreadPoolExecutor
import copy
from pathlib import Path
import unittest
from uuid import uuid4

from ua_order.catalog import Catalog
from ua_order.contract import Conflict
from ua_order.mysql_repository import MySQLRepository
from ua_order.service import OrderService, Principal
from ua_order.storage import NotFound, StorageUnavailable

OPTIONS = dict(host='Carix.mysql.pythonanywhere-services.com', user='Carix',
               database='Carix$orders_test', defaults_file='/home/Carix/.my.cnf')
CONFIG = Path(__file__).resolve().parents[2] / 'ua_order_ge_8country_guard_016/country_models.json'


class MySQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog(CONFIG)
        cls.repo = MySQLRepository(**OPTIONS)
        cls.repo.initialize()

    def setUp(self):
        self.now = 10000
        self.repo = MySQLRepository(**OPTIONS, clock=lambda: self.now)
        # All destructive fixture setup is pinned to the dedicated test DB.
        def clean(cursor):
            cursor.execute('SELECT DATABASE() AS name')
            if cursor.fetchone()['name'] != 'Carix$orders_test':
                raise RuntimeError('Refusing non-test database')
            cursor.execute("SELECT COUNT(*) AS count FROM information_schema.TABLE_CONSTRAINTS WHERE CONSTRAINT_SCHEMA=DATABASE() AND TABLE_NAME='order_outbox' AND CONSTRAINT_NAME='order_test_reject'")
            if cursor.fetchone()['count']:
                cursor.execute('ALTER TABLE order_outbox DROP CHECK order_test_reject')
            for table in ('order_notification_receipts', 'order_outbox', 'order_events', 'order_drafts', 'order_requests'):
                cursor.execute('DELETE FROM ' + table)
        self.repo._run(clean, write=True)
        self.service = OrderService(self.catalog, self.repo, 'test-consent-v1')
        self.user = Principal('web:test-session', 'site')
        self.data = dict(schema_version='ua_order_request.v1', request_id=str(uuid4()),
                         config_version=self.catalog.version, purchase_country_code='korea',
                         model='kia-k5', other_model='', budget={'code': 'b2', 'currency': 'USD'},
                         vehicle_type='k1', delivery_country='Україна', delivery_city='Київ',
                         customer_name='Тест 🧪', contact={'phone': '+380990000000'},
                         comment='Synthetic integration check', lang='uk', source_path='/video/podbor.html',
                         consent={'accepted': True, 'version': 'test-consent-v1'})

    def count(self, table):
        def count(cursor):
            cursor.execute('SELECT COUNT(*) AS count FROM ' + table)
            return cursor.fetchone()['count']
        return self.repo._run(count)

    def test_concurrent_submit_and_restart(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            receipts = list(pool.map(lambda _: self.service.submit(copy.deepcopy(self.data), self.user), range(16)))
        self.assertEqual(len({r['number'] for r in receipts}), 1)
        self.assertEqual(self.count('order_requests'), 1)
        self.assertEqual(self.count('order_outbox'), 1)
        restarted = OrderService(self.catalog, MySQLRepository(**OPTIONS), 'test-consent-v1')
        self.assertEqual(restarted.submit(self.data, self.user), receipts[0])
        self.assertEqual(self.repo.notification_data(self.data['request_id'])['data']['customer_name'], 'Тест 🧪')

    def test_payload_owner_and_event_conflicts(self):
        actor = Principal('telegram:123', 'telegram_bot', 'testbot:887')
        self.service.submit(self.data, actor)
        with self.assertRaises(Conflict):
            self.service.submit(dict(self.data, comment='changed'), actor)
        with self.assertRaises(Conflict):
            self.service.submit(self.data, self.user)
        with self.assertRaises(Conflict):
            self.service.submit(dict(self.data, request_id=str(uuid4())), actor)
        self.assertEqual(self.count('order_requests'), 1)
        self.assertEqual(self.count('order_outbox'), 1)
        self.assertEqual(self.count('order_events'), 1)

    def test_concurrent_event_replay_rolls_back_loser(self):
        actor = Principal('telegram:123', 'telegram_bot', 'testbot:900')
        def submit(_):
            try:
                return self.service.submit(dict(self.data, request_id=str(uuid4())), actor)
            except Conflict:
                return None
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(submit, range(8)))
        self.assertEqual(sum(r is not None for r in results), 1)
        self.assertEqual(self.count('order_requests'), 1)
        self.assertEqual(self.count('order_outbox'), 1)

    def test_failed_outbox_insert_rolls_back(self):
        self.repo._run(lambda c: c.execute('ALTER TABLE order_outbox ADD CONSTRAINT order_test_reject CHECK (available_at < 0)'), write=True)
        try:
            with self.assertRaises(StorageUnavailable):
                self.service.submit(self.data, self.user)
            self.assertEqual(self.count('order_requests'), 0)
        finally:
            self.repo._run(lambda c: c.execute('ALTER TABLE order_outbox DROP CHECK order_test_reject'), write=True)

    def test_concurrent_lease_expiry_and_retry(self):
        self.service.submit(self.data, self.user)
        with ThreadPoolExecutor(max_workers=8) as pool:
            claims = list(pool.map(lambda _: self.repo.claim_notification(), range(8)))
        first, = [c for c in claims if c]
        self.now += 61
        second = self.repo.claim_notification()
        self.assertNotEqual(first['lease'], second['lease'])
        self.repo.finish_notification(first, delivered=True)
        self.repo.finish_notification(second, delivered=False)
        self.assertIsNone(self.repo.claim_notification())
        self.now += 121
        third = self.repo.claim_notification()
        self.repo.finish_notification(third, delivered=True)
        self.assertIsNone(self.repo.claim_notification())
        self.service.submit(self.data, self.user)
        self.assertIsNone(self.repo.claim_notification())

    def test_lease_starts_after_lock_acquisition(self):
        self.service.submit(self.data, self.user)
        self.repo.clock = iter((10000, 10020)).__next__
        claim = self.repo.claim_notification()
        def lease(cursor):
            cursor.execute('SELECT lease_until FROM order_outbox WHERE id=%s', (claim['id'],))
            return cursor.fetchone()['lease_until']
        self.assertEqual(self.repo._run(lease), 10080)

    def test_handoff_first_user_binding_and_expiry(self):
        token = self.service.handoff(self.data, self.user)
        def redeem(index):
            try:
                self.repo.redeem_draft(token, 'telegram:' + str(index))
                return index
            except NotFound:
                return None
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(redeem, range(1, 9)))
        winner, = [r for r in results if r]
        self.assertEqual(self.repo.redeem_draft(token, 'telegram:' + str(winner))['model'], 'kia-k5')
        self.now += 1800
        with self.assertRaises(NotFound):
            self.repo.redeem_draft(token, 'telegram:' + str(winner))

    def test_recipient_receipts_owner_and_pagination(self):
        receipt = self.service.submit(self.data, self.user)
        self.assertEqual(self.repo.receipt_for_owner(self.data['request_id'], self.user.owner), receipt)
        with self.assertRaises(NotFound):
            self.repo.receipt_for_owner(self.data['request_id'], 'web:other')
        for _ in range(2):
            self.repo.notification_recipient_sent(self.data['request_id'], 123)
        self.assertEqual(self.repo.notification_recipients_sent(self.data['request_id']), {123})
        for _ in range(21):
            self.service.submit(dict(self.data, request_id=str(uuid4())), self.user)
        rows, before = self.repo.list_requests()
        self.assertEqual(len(rows), 20)
        rest, end = self.repo.list_requests(before=before)
        self.assertEqual(len(rest), 2)
        self.assertIsNone(end)
        self.assertEqual(self.repo.detail(rest[-1]['id'])['number'], receipt['number'])

    def test_refuse_unrelated_database(self):
        with self.assertRaises(ValueError):
            MySQLRepository(**dict(OPTIONS, database='Carix$default'))
        self.repo.check_ready()


if __name__ == '__main__':
    unittest.main(verbosity=2)

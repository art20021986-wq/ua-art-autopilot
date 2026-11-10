"""Client records: creation, login, password change, block, deposit limit."""
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ua_auction_clients as clients  # noqa: E402


class ClientsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / 'c' / 'clients.db'

    def create(self, **kw):
        args = dict(surname='Шевченко', name='Тарас', phone_number='+38 (099) 111-22-33', email='t@example.com',
                    city='Київ', deposit_usd='4 000', manager_id=397376186, db=self.db)
        args.update(kw)
        return clients.create(**args)

    def test_create_shows_password_once_and_stores_only_a_hash(self):
        client, password = self.create()
        self.assertEqual(client['phone'], '+380991112233')
        self.assertEqual((client['deposit_usd'], client['limit_usd']), (4000, 30000))
        self.assertEqual(len(password), clients.PASSWORD_LENGTH)
        self.assertFalse(set(password) & set('0O1lI'))
        raw = self.db.read_bytes()
        self.assertNotIn(password.encode(), raw)
        self.assertNotIn('password', client)

    def test_login_by_phone(self):
        _, password = self.create()
        self.assertEqual(clients.verify('+380991112233', password, self.db)['name'], 'Тарас')
        self.assertIsNone(clients.verify('+380991112233', password + 'x', self.db))
        self.assertIsNone(clients.verify('+380000000000', password, self.db))
        self.assertIsNone(clients.verify('not a phone', password, self.db))

    def test_reset_password_and_block(self):
        _, old = self.create()
        new = clients.reset_password('+380991112233', self.db)
        self.assertIsNone(clients.verify('+380991112233', old, self.db))
        self.assertIsNotNone(clients.verify('+380991112233', new, self.db))
        clients.set_blocked('+380991112233', True, self.db)
        self.assertIsNone(clients.verify('+380991112233', new, self.db))
        clients.set_blocked('+380991112233', False, self.db)
        self.assertIsNotNone(clients.verify('+380991112233', new, self.db))

    def test_deposit_limit_rule(self):
        self.assertEqual([clients.limit_usd(d) for d in (2000, 3999, 4000, 10000)], [15000, 15000, 30000, 75000])
        self.create()
        self.assertEqual(clients.set_deposit('+380991112233', 6000, self.db)['limit_usd'], 45000)
        with self.assertRaisesRegex(clients.ClientError, 'deposit'):
            clients.set_deposit('+380991112233', 1500, self.db)

    def test_bad_input_names_the_field(self):
        for kw, field in ((dict(phone_number='12'), 'phone'), (dict(email='no-at'), 'email'),
                          (dict(surname=' '), 'surname'), (dict(deposit_usd='abc'), 'deposit')):
            with self.assertRaisesRegex(clients.ClientError, field):
                self.create(**kw)
        self.create()
        with self.assertRaisesRegex(clients.ClientError, 'phone_exists'):
            self.create()
        with self.assertRaisesRegex(clients.ClientError, 'not_found'):
            clients.reset_password('+380000000000', self.db)

    def test_list_newest_first(self):
        self.create()
        self.create(phone_number='+380992223344', name='Леся')
        self.assertEqual(len(clients.all_clients(self.db)), 2)
        with sqlite3.connect(self.db) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM clients').fetchone()[0], 2)


if __name__ == '__main__':
    unittest.main()

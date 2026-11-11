"""The bids ledger keeps the lot's VIN (owner 2026-11-11); an older ledger gets the column, the staff message shows it."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import importlib.machinery
import importlib.util
from pathlib import Path
import sqlite3
import sys
import tempfile
import types
import unittest

HERE = Path(__file__).resolve().parent


def load(name, file):
    loader = importlib.machinery.SourceFileLoader(name, str(HERE / file))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader))
    loader.exec_module(module)
    return module


bids = load('vin_test_bids', 'ua_auction_bids.py')
OLD_SCHEMA = '''CREATE TABLE bids (id INTEGER PRIMARY KEY, phone TEXT NOT NULL, lot_id TEXT NOT NULL, title TEXT NOT NULL,
    krw INTEGER NOT NULL, usd INTEGER NOT NULL, status TEXT NOT NULL, message TEXT NOT NULL, created_at TEXT NOT NULL,
    notified INTEGER NOT NULL DEFAULT 0)'''
CLIENT = {'phone': '+380991112233', 'surname': 'Иванов', 'name': 'Иван', 'limit_usd': 30000}
LOT = {'id': '20261112000123', 'title': 'Kia K5', 'year': 2021, 'vin': 'KNAG541BBNA169806'}
NOW = datetime(2026, 11, 11, 10, 5, tzinfo=timezone(timedelta(hours=9)))


class LedgerTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.db = Path(folder.name) / 'bids.db'

    def test_new_bid_keeps_the_vin(self):
        bids.record(CLIENT, {'lot': LOT, 'krw': 20000000, 'usd': 15000}, 'placed', '', self.db, NOW)
        row = bids.unnotified(self.db)[0]
        self.assertEqual((row['vin'], row['title'], row['lot_id']), ('KNAG541BBNA169806', 'Kia K5 2021', LOT['id']))

    def test_older_ledger_gets_the_column(self):
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute(OLD_SCHEMA)
            connection.execute("INSERT INTO bids (phone, lot_id, title, krw, usd, status, message, created_at) "
                               "VALUES ('+380991112233', '1', 'Kia K5 2019', 1, 1, 'placed', '', '2026-11-10T10:00:00+09:00')")
        bids.record(CLIENT, {'lot': dict(LOT, vin=None), 'krw': 1, 'usd': 1}, 'failed', 'too_low', self.db, NOW)
        rows = bids.unnotified(self.db)
        self.assertEqual([r['vin'] for r in rows], ['', ''])  # the old bid and a lot without VIN: empty

    def test_staff_message_shows_the_vin(self):
        sys.modules['ua_auction_bids'] = bids
        sys.modules.setdefault('ua_auction_clients', types.ModuleType('ua_auction_clients'))
        try:
            bot = load('vin_test_bot', 'ua_auction_bids_bot.py')
        finally:
            del sys.modules['ua_auction_bids']
        row = {'status': 'placed', 'message': '', 'phone': CLIENT['phone'], 'title': 'Kia K5 2021', 'lot_id': '1',
               'vin': 'KNAG541BBNA169806', 'krw': 20000000, 'usd': 15000, 'created_at': '2026-11-11T10:05:00+09:00'}
        self.assertIn('VIN: KNAG541BBNA169806', bot.text(row, CLIENT))
        self.assertIn('VIN: —', bot.text(dict(row, vin=''), CLIENT))


if __name__ == '__main__':
    unittest.main()

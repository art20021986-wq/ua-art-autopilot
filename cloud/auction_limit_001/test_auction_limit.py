"""AUCTION-LIMIT-001: deposit from 1 000 $, no bid limit in the store, the bids, the CRM bot, the login and the page."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_builder  # noqa: E402
import ua_auction_bids as bids  # noqa: E402
import ua_auction_clients as store  # noqa: E402
import ua_auction_clients_view as view  # noqa: E402
import ua_auction_stats as stats  # noqa: E402
import ua_auction_web as web  # noqa: E402

KST = timezone(timedelta(hours=9))


class StoreTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.db = Path(folder.name) / 'clients.db'

    def test_deposit_from_1000(self):
        self.assertEqual(store.deposit('1 000 $'), 1000)
        for value in ('999', '0', 'abc'):
            with self.assertRaises(store.ClientError):
                store.deposit(value)

    def test_client_has_no_limit(self):
        store.create('Иванов', 'Иван', '+380991112233', 'i@x.ua', 'Киев', 1000, 1, self.db)
        client = store.get('+380991112233', self.db)
        self.assertEqual(client['deposit_usd'], 1000)
        self.assertNotIn('limit_usd', client)
        self.assertTrue(all('limit_usd' not in c for c in store.all_clients(self.db)))
        self.assertFalse(hasattr(store, 'limit_usd'))


class BidsTest(unittest.TestCase):
    def test_big_bid_is_not_refused_by_a_limit(self):
        with tempfile.TemporaryDirectory() as folder:
            lots = Path(folder) / 'lots.json'
            lot = {'id': '20261112000123', 'title': 'Kia K5', 'year': 2021, 'start_krw': 10000000}
            lots.write_text(json.dumps({'nbu': {'usd_uah': 41.0, 'krw_uah': 0.03}, 'lots': [lot]}))
            bid = bids.check({'phone': '+380991112233', 'deposit_usd': 1000}, lot['id'], 1000000000, lots,
                             Path(folder) / 'bids.db', datetime(2026, 11, 12, 10, 0, tzinfo=KST))
        self.assertGreater(bid['usd'], 15000)


CLIENT = {'phone': '+380991112233', 'surname': 'Иванов', 'name': 'Иван', 'email': 'i@x.ua', 'city': 'Киев',
          'deposit_usd': 1000, 'blocked': 0, 'created_at': '2026-11-12T10:00:00+00:00'}


class ViewTest(unittest.TestCase):
    def test_deposit_question(self):
        self.assertIn('Передоплата в $ (от 1 000 $, засчитывается в стоимость авто):', view.ask(len(view.STEPS) - 1)['text'])
        self.assertEqual(view.FIELD_ERRORS['deposit'], 'Передоплата — число от 1000, например 1000.')
        self.assertNotIn('епозит', view.ask(len(view.STEPS) - 1)['text'])

    def test_no_limit_anywhere(self):
        numbers = stats.summary(now=datetime(2026, 11, 12, 10, 0, tzinfo=KST), db=Path('/nonexistent/bids.db'),
                                people=[CLIENT])
        self.assertNotIn('limit_usd', numbers)
        texts = [view.confirm(CLIENT)['text'], view.access_text(CLIENT, 'pass1234'), view.card(CLIENT)['text'],
                 view.home(numbers)['text'], view.deposit_prompt(CLIENT)['text']]
        for text in texts:
            self.assertNotRegex(text.lower(), 'лимит|ліміт|15 000')
        self.assertIn('Депозит: 1 000 $', view.card(CLIENT)['text'])

    def test_login_answer_has_no_limit(self):
        self.assertEqual(web._public(CLIENT), {'name': 'Иван', 'surname': 'Иванов', 'phone': '+380991112233'})


class PageTest(unittest.TestCase):
    def setUp(self):
        self.page = (HERE / 'fixtures' / 'korea_live.html').read_text(encoding='utf-8')

    def test_cabinet_without_limit(self):
        new = candidate_builder.apply(self.page)
        self.assertNotIn('kc-limit', new)
        self.assertNotIn('limit_usd', new)
        self.assertNotIn('ліміт', new)
        self.assertNotIn('лимит', new)
        self.assertNotIn('limit_over', new)
        self.assertIn('day_limit:"day_limit"', new)
        self.assertIn('id="kc-who"', new)
        self.assertIn('id="kc-out"', new)
        self.assertIn('.kb-hint").textContent=t("min")+" ₩"+n(min);btn.textContent', new)
        removed = sum(len(old) - len(repl) for old, repl in candidate_builder.PAGE_EDITS)
        self.assertEqual(len(self.page) - len(new), removed)

    def test_unexpected_page_stops(self):
        with self.assertRaisesRegex(ValueError, 'AUCTION_LIMIT_PAGE_UNEXPECTED'):
            candidate_builder.apply(candidate_builder.apply(self.page))

    def test_other_installed_version_stops(self):
        source = {name: b'other' for name in candidate_builder.MODULES}
        source[candidate_builder.PAGE] = self.page.encode('utf-8')
        with self.assertRaisesRegex(ValueError, 'INPUT_HASH'):
            candidate_builder.build(source, {})


if __name__ == '__main__':
    unittest.main()

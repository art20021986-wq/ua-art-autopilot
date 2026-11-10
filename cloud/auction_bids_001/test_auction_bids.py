"""Bid checks, the lot page form, the ledger; the auction site is a stand-in (nothing is sent anywhere)."""
from datetime import datetime
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ua_auction_bids as bids  # noqa: E402

LOT = {'id': '20261112000123', 'title': 'Kia K5', 'year': 2021, 'start_krw': 10000000}
CLIENT = {'phone': '+380991112233', 'limit_usd': 15000}
FORM = ('<form action="/bids/bid/20261112000123/" method="post" class="bid-form" id="bidding">'
        '<input type="hidden" name="usd-rate" value="1390.5"><input type="hidden" name="korea_auction_flg" value="1">'
        '<input type="text" name="bid_price" id="bid-amount"></form>')


class Browser:
    def __init__(self, orders):
        self.sent, self.orders = [], orders

    def login(self, email, password):
        self.sent.append(('login', email))

    def fetch(self, path, data=None):
        self.sent.append((path, data))
        return path, {'/bids/kr/': self.orders}.get(path, FORM)


class BidsTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.lots = self.dir / 'lots.json'
        self.lots.write_text(json.dumps({'nbu': {'usd_uah': 41.0, 'krw_uah': 0.03}, 'lots': [LOT]}))
        self.db = self.dir / 'bids.db'

    def check(self, krw, **kw):
        return bids.check(kw.get('client', CLIENT), kw.get('lot', LOT['id']), krw, self.lots, self.db,
                          datetime(2026, 11, 11, 20, 0, tzinfo=bids.KST))

    def test_rules(self):
        self.assertEqual(self.check(10050000)['usd'], round(10050000 * 0.03 / 41))
        for krw, code in ((10040000, 'too_low'), (10055000, 'step'), ('x', 'amount')):
            with self.assertRaisesRegex(bids.BidError, code):
                self.check(krw)
        with self.assertRaisesRegex(bids.BidError, 'limit'):
            self.check(30000000)                     # ≈ 21 951 $ > 15 000 $
        with self.assertRaisesRegex(bids.BidError, 'lot'):
            self.check(10050000, lot='20261112999999')
        self.lots.write_text(json.dumps({'nbu': {'usd_uah': 41.0, 'krw_uah': 0.03}, 'lots': [dict(LOT, start_krw=0)]}))
        with self.assertRaisesRegex(bids.BidError, 'no_start_price'):
            self.check(10050000)

    def test_day_limit(self):
        bid = self.check(10050000)
        for _ in range(bids.DAY_LIMIT):
            bids.record(CLIENT, bid, 'placed', '', self.db, datetime(2026, 11, 11, 9, 0, tzinfo=bids.KST))
        with self.assertRaisesRegex(bids.BidError, 'day_limit'):
            self.check(10050000)

    def test_place_sends_the_lot_form_in_10000_won_units_and_confirms(self):
        bid = self.check(10050000)
        browser = Browser('<tr><td>20261112000123</td><td>10,050,000</td></tr>')
        self.assertEqual(bids.place(CLIENT, bid, browser, ('e', 'p'), self.db), ('placed', ''))
        sent = dict(browser.sent[2][1])
        self.assertEqual(browser.sent[2][0], '/bids/bid/20261112000123/')
        self.assertEqual((sent['bid_price'], sent['korea_auction_flg']), ('1005', '1'))
        row = bids.unnotified(self.db)[0]
        self.assertEqual((row['status'], row['krw'], row['title']), ('placed', 10050000, 'Kia K5 2021'))
        bids.mark_notified(row['id'], self.db)
        self.assertEqual(bids.unnotified(self.db), [])

    def test_unconfirmed_bid_is_reported_failed(self):
        bid = self.check(10050000)
        self.assertEqual(bids.place(CLIENT, bid, Browser('<p>no orders</p>'), ('e', 'p'), self.db),
                         ('failed', 'not_confirmed'))


if __name__ == '__main__':
    unittest.main()

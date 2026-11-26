"""Tests for SEARCH-HOME-001 USA modules (standard library unittest)."""
import json
import pathlib
import tempfile
import unittest

import usa_costs
import usa_tariffs_sync as sync
import ua_usa_page as page

SHELL = ('<html><head><title data-uk="K">K</title><meta name="description" content="k">'
         '<meta property="og:title" content="k"><meta property="og:description" content="k">'
         '<meta property="og:url" content="https://x/korea.html"><link rel="canonical" href="https://x/korea.html">'
         '<link rel="alternate" hreflang="ru" href="https://x/ru/korea.html"></head><body><header>H</header>'
         '<main id="main-content">KOREA LOTS</main><footer>F</footer></body></html>')


class Costs(unittest.TestCase):
    def test_buy_fee_steps(self):
        self.assertEqual([usa_costs.buy_fee(n) for n in (1, 4, 5, 9, 10, 30)], [200, 200, 100, 100, 0, 0])

    def test_public(self):
        self.assertEqual(usa_costs.public(), {'buy': 200, 'port': 400, 'truck': 1100, 'service': 600,
                                              'expensive_from': 15000})


class Sync(unittest.TestCase):
    def test_price(self):
        self.assertEqual(sync.price('<div>PORT CA : 2.160</div>'), 2160)
        self.assertEqual(sync.price('PORT NJ : 980'), 980)
        self.assertIsNone(sync.price('No Record!'))
        self.assertIsNone(sync.price('PORT CA : 99.999'))

    def test_yard(self):
        self.assertEqual(sync.yard('Martinez / MARTINEZ / 94553', 'CA'), ('Martinez', 'martinez 94553 ca'))
        self.assertIsNone(sync.yard('1107 Broadway Pasadena, Tx, 77506 / X / 1', 'TX'))

    def test_collect_merges_auctions_by_max(self):
        def ask(name, data):
            if name == 'getState.php':
                return '<option value="">Choose</option><option value="4">CA</option>'
            if name == 'city.php':
                return '<option value="33">Martinez / MARTINEZ / 94553</option>'
            base = 2100 if data['auc_id_2'] == 1 else 2200
            return 'PORT CA : %d' % (base + (100 if data['type_id_2'] == 2 else 0))
        yards = sync.collect(ask)
        self.assertEqual(yards, [['Martinez', 'CA', 2200, 2300, 'martinez 94553 ca']])

    def test_write_keeps_old_file_when_too_few(self):
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d) / 'tariffs.json'
            path.write_text('OLD')
            with self.assertRaises(sync.SyncError):
                sync.write([['A', 'CA', 1, 2, 'a']], path=path)
            self.assertEqual(path.read_text(), 'OLD')

    def test_write(self):
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d) / 'usa' / 'tariffs.json'
            yards = [['Y%d' % i, 'CA', 1000, 1100, 'y'] for i in range(sync.MIN_YARDS)]
            sync.write(yards, path=path)
            data = json.loads(path.read_text())
            self.assertEqual(data['costs']['port'], 400)
            self.assertEqual(len(data['yards']), sync.MIN_YARDS)


class Page(unittest.TestCase):
    def test_build(self):
        out = page.build(SHELL)
        self.assertNotIn('KOREA LOTS', out)
        self.assertIn('<header>H</header>', out)
        self.assertIn('<footer>F</footer>', out)
        self.assertIn('href="https://www.uaart.com.ua/video/usa.html"', out)
        self.assertNotIn('hreflang', out)
        self.assertIn('id="usa-calc" hidden', out)
        self.assertIn('/video/usa/usa-calc.js', out)
        self.assertIn('600 $', out)
        for word in ('2mcars', '2M Cars', 'VS Brothers', 'vsbrothers'):
            self.assertNotIn(word, out)

    def test_layout_guard(self):
        with self.assertRaises(ValueError):
            page.build('<html>no main</html>')


if __name__ == '__main__':
    unittest.main()

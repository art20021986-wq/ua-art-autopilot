"""The KOREA-CARD candidate from the Korea page as KOREA-LOTS-FULL-INSTALL-20261112 left it."""
import importlib.machinery
import importlib.util
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_builder  # noqa: E402
import ua_korea_bid  # noqa: E402
import ua_korea_login  # noqa: E402
import ua_korea_lots  # noqa: E402


def installed_page():
    """korea.html with the installed lot list (KOREA-LOTS-FULL module, kept as a fixture)."""
    path = str(HERE / 'fixtures' / 'ua_korea_lots_installed.txt')
    loader = importlib.machinery.SourceFileLoader('installed_lots', path)
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader('installed_lots', loader))
    loader.exec_module(module)
    return module.apply((HERE / 'fixtures' / 'korea_live.html').read_text())


class CandidateTests(unittest.TestCase):
    def test_only_the_block_changes(self):
        page = installed_page()
        new = candidate_builder.build({'video/korea.html': page.encode()}, {})['video/korea.html'].decode()
        self.assertEqual(new.count(ua_korea_lots.MARK), 1)
        for part in ('"Усі дні"', 'id="kl-days"', 'value="date"', 'row("vin",l.vin)', 'kl-tbd',
                     '.kl-dialog{position:fixed;', '$("kl-card").scrollTop=0;',
                     'history.replaceState(null,"","#lot-"+id)', '"პარ"', '"пʼятниця"'):
            self.assertIn(part, new)
        for gone in ('row("lot",', 'Лот №', 'toLocaleDateString'):
            self.assertNotIn(gone, new)
        cut = lambda h: h[:h.index(ua_korea_lots.MARK)] + h[h.index(ua_korea_lots.END):]
        self.assertEqual(cut(new), cut(page))
        self.assertEqual(ua_korea_lots.apply(new), new)
        with self.assertRaises(ValueError):
            candidate_builder.build({'video/korea.html': new.encode()}, {})

    def test_login_and_bid_put_back_and_kept(self):
        before = (HERE / 'fixtures' / 'korea_before_lots_full.html').read_text()  # login and bid inside the list
        stripped = installed_page()                                              # as KOREA-LOTS-FULL left it
        self.assertNotIn(ua_korea_login.MARK, stripped)
        new = candidate_builder.build({'video/korea.html': stripped.encode()}, {})['video/korea.html'].decode()
        segment = lambda h, m: h[h.index(m.MARK):h.index(m.END) + len(m.END)]
        for module in (ua_korea_login, ua_korea_bid):
            self.assertEqual(segment(new, module), segment(before, module))      # exactly as before
        again = ua_korea_lots.apply(new)                                          # a later list release keeps them
        self.assertEqual(again, new)
        self.assertEqual(ua_korea_lots.apply(before).count(ua_korea_bid.MARK), 1)

    def test_copies_match_their_packages(self):
        for name, package in (('ua_korea_login.py', 'auction_clients_001'), ('ua_korea_bid.py', 'auction_bids_001')):
            self.assertEqual((HERE / name).read_bytes(), (HERE.parent / package / name).read_bytes())

    def test_labels_have_three_languages(self):
        self.assertTrue(all(len(v) == 3 for v in ua_korea_lots.LABELS.values()))
        self.assertEqual([len(d) for d in ua_korea_lots.WEEKDAYS + ua_korea_lots.WEEKDAYS_LONG], [7] * 6)


if __name__ == '__main__':
    unittest.main()

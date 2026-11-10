"""The AUCTION-BIDS candidate from the sources as AUCTION-CLIENTS-INSTALL-20261110 installed them."""
import importlib.machinery
import importlib.util
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_builder  # noqa: E402
import ua_korea_bid  # noqa: E402

CLIENTS = HERE.parent / 'auction_clients_001'


def _module(path, name):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader))
    loader.exec_module(module)
    return module


def installed_page():
    lots = _module(HERE.parent / 'korea_lots_page_002' / 'ua_korea_lots.py', 'installed_lots')
    login = _module(CLIENTS / 'ua_korea_login.py', 'installed_login')
    return login.apply(lots.apply((CLIENTS / 'fixtures' / 'korea_live.html').read_text()))


def source():
    return {'ua_auction_web.py': (CLIENTS / 'ua_auction_web.py').read_bytes(),
            'ua_auction_clients_bot.py': (CLIENTS / 'ua_auction_clients_bot.py').read_bytes(),
            'video/korea.html': installed_page().encode()}


class CandidateTests(unittest.TestCase):
    def test_candidate(self):
        result = candidate_builder.build(source(), {})
        for name in ('ua_auction_bids.py', 'ua_auction_bids_bot.py', 'ua_auction_web.py', 'ua_auction_clients_bot.py'):
            compile(result[name], name, 'exec')
        self.assertIn(b'def bid(self, environ, key):', result['ua_auction_web.py'])
        self.assertIn(b'ua_auction_bids_bot.register(app)', result['ua_auction_clients_bot.py'])
        page = result['video/korea.html'].decode()
        self.assertEqual(ua_korea_bid.remove(page), installed_page())
        self.assertLess(page.index('<!--/UA-KOREA-LOGIN-V1-->'), page.index(ua_korea_bid.MARK))

    def test_other_installed_versions_are_refused(self):
        changed = dict(source(), **{'ua_auction_web.py': b'# other'})
        with self.assertRaises(ValueError):
            candidate_builder.build(changed, {})


if __name__ == '__main__':
    unittest.main()

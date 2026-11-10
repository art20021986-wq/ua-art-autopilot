"""The AUCTION-CLIENTS candidate from the installed sources (bot module, order host, Korea page with the lot list)."""
import importlib.machinery
import importlib.util
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_builder  # noqa: E402
import ua_korea_login  # noqa: E402

FIX = HERE / 'fixtures'


def _module(path, name):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader))
    loader.exec_module(module)
    return module


def installed_page():
    """korea.html as KOREA-LOTS-PAGE2-INSTALL-20261110-R2 left it."""
    lots = _module(HERE.parent / 'korea_lots_page_002' / 'ua_korea_lots.py', 'installed_lots')
    return lots.apply((FIX / 'korea_live.html').read_text())


def source():
    return {'ua_crm_orders.py': (FIX / 'ua_crm_orders_installed.txt').read_bytes(),
            'ua_order/host.py': (FIX / 'order_host_probe.txt').read_bytes(),
            'video/korea.html': installed_page().encode()}


class CandidateTests(unittest.TestCase):
    def test_new_files_hooks_and_login_line(self):
        result = candidate_builder.build(source(), {})
        self.assertEqual(set(result), set(candidate_builder.NEW_FILES) | set(candidate_builder.SOURCE_FILES))
        for name in candidate_builder.NEW_FILES + ('ua_crm_orders.py',):
            compile(result[name], name, 'exec')
        self.assertIn(b'ua_auction_clients_bot.register(app)', result['ua_crm_orders.py'])
        self.assertIn(b'ua_auction_web.mount(application)', result['ua_order/host.py'])
        page = result['video/korea.html'].decode()
        self.assertEqual(page.count(ua_korea_login.MARK), 1)
        self.assertEqual(ua_korea_login.remove(page), installed_page())
        self.assertLess(page.index('id="lots"'), page.index(ua_korea_login.MARK))

    def test_second_build_refused(self):
        result = candidate_builder.build(source(), {})
        with self.assertRaises(ValueError):
            candidate_builder.build({k: result[k] for k in candidate_builder.SOURCE_FILES}, {})


if __name__ == '__main__':
    unittest.main()

"""The KOREA-LOTS-PAGE2 candidate from the Korea page as KOREA-LOTS-PAGE-INSTALL-20261110 left it."""
import importlib.machinery
import importlib.util
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_builder  # noqa: E402
import ua_korea_lots  # noqa: E402


def installed_page():
    """korea.html after KOREA-LOTS-PAGE-INSTALL-20261110: the live fixture with that release's module applied."""
    path = str(HERE.parent / 'korea_lots_page_001' / 'ua_korea_lots.py')
    loader = importlib.machinery.SourceFileLoader('installed_lots', path)
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader('installed_lots', loader))
    loader.exec_module(module)
    return module.apply((HERE / 'fixtures' / 'korea_live.html').read_text())


class CandidateTests(unittest.TestCase):
    def test_only_the_block_changes(self):
        page = installed_page()
        new = candidate_builder.build({'video/korea.html': page.encode()}, {})['video/korea.html'].decode()
        self.assertEqual(new.count(ua_korea_lots.MARK), 1)
        self.assertIn('kl-tbd', new)
        self.assertIn('Ціна — на торгах', new)
        cut = lambda h: h[:h.index(ua_korea_lots.MARK)] + h[h.index(ua_korea_lots.END):]
        self.assertEqual(cut(new), cut(page))
        self.assertEqual(ua_korea_lots.apply(new), new)
        with self.assertRaises(ValueError):
            candidate_builder.build({'video/korea.html': new.encode()}, {})


if __name__ == '__main__':
    unittest.main()

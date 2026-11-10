"""The HOME-TELEGRAM candidate from the home page and module as installed by HOME-ORDER-INSTALL-20261110."""
import importlib.machinery
import importlib.util
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_builder  # noqa: E402
import ua_korea_home as home  # noqa: E402

LIVE = (HERE / 'fixtures' / 'index_live.html').read_text()
INSTALLED_MODULE = (HERE / 'fixtures' / 'ua_korea_home_installed.txt').read_bytes()


def installed_module():
    """The HOME-ORDER release's module, loaded from its fixture as a regular source file."""
    path = str(HERE / 'fixtures' / 'ua_korea_home_installed.txt')
    loader = importlib.machinery.SourceFileLoader('installed_home', path)
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader('installed_home', loader))
    loader.exec_module(module)
    return module


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.home = installed_module().apply(LIVE)  # the home page after the HOME-ORDER release
        self.source = {'ua_korea_home.py': INSTALLED_MODULE, 'video/index.html': self.home.encode()}

    def test_only_the_telegram_button_goes(self):
        self.assertIn(home.PICK_TO + home.TELEGRAM, self.home)
        new = candidate_builder.build(self.source, {})['video/index.html'].decode()
        self.assertNotIn(home.TELEGRAM, new)
        self.assertNotIn('Написати в Telegram', new)
        self.assertEqual(new, home.apply(LIVE))
        back = home._photo_back(new).replace(home.PICK_TO, home.PICK_TO + home.TELEGRAM, 1)
        self.assertEqual(back.replace(home.GO_TO, home.GO_FROM), self.home)
        self.assertLess(new.index(home.PHOTO), new.index(home.STAGES))
        self.assertNotIn('<section class="hero ua-order-first"><picture>', new)
        self.assertEqual((new.count('>Дивитися аукціони<'), new.count('Дивитися онлайн')), (1, 0))
        self.assertEqual(home.apply(new), new)
        self.assertIn('header-telegram', new)  # the header contact line stays

    def test_remove_brings_the_page_back(self):
        flagged = LIVE.replace(home.FLAG_FROM, home.FLAG_TO)
        self.assertEqual(home._unordered(home.apply(LIVE)), flagged)
        self.assertEqual(home.remove(home.apply(LIVE)), installed_module().remove(self.home))

    def test_second_build_refused(self):
        result = candidate_builder.build(self.source, {})
        with self.assertRaises(ValueError):
            candidate_builder.build(result, {})


if __name__ == '__main__':
    unittest.main()

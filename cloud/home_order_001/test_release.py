"""The HOME-ORDER candidate from the home page and module as installed by KOREA-FLAG-INSTALL-20261110."""
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
    spec = importlib.util.spec_from_loader('installed_home', loader=None)
    module = importlib.util.module_from_spec(spec)
    exec(INSTALLED_MODULE, module.__dict__)
    return module


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.home = installed_module().apply(LIVE)  # the home page after the flag release
        self.source = {'ua_korea_home.py': INSTALLED_MODULE, 'video/index.html': self.home.encode()}

    def test_order_and_exact_reverse(self):
        new = candidate_builder.build(self.source, {})['video/index.html'].decode()
        order = [new.index(x) for x in (home.LAYOUT, home.MARK, home.HERO, home.STAGES,
                                        '<section class="confidence-strip', '<section class="ua-how',
                                        '<section class="ua-reviews')]
        self.assertEqual(order, sorted(order))
        self.assertIn(home.PICK_TO, new)
        self.assertNotIn(home.PICK_FROM, new)
        self.assertIn('href="korea.html"', new[new.index(home.LAYOUT):new.index(home.MARK)])
        self.assertEqual(home._unordered(new), self.home)
        self.assertEqual(home.remove(new), home.remove(self.home))
        self.assertEqual(home.apply(new), new)

    def test_three_languages_in_the_auctions_block(self):
        for word in ('Аукціони онлайн', 'Аукционы онлайн', 'აუქციონები ონლაინ', 'Смотреть онлайн'):
            self.assertIn(word, home.AUCTIONS)

    def test_unknown_structure_keeps_its_order(self):
        moved = self.home.replace('<section id="stages"', '<section id="stages-x"')
        self.assertNotIn(home.LAYOUT, home.apply(moved))
        with self.assertRaises(ValueError):
            candidate_builder.build({'ua_korea_home.py': INSTALLED_MODULE, 'video/index.html': moved.encode()}, {})

    def test_order_is_one_line_to_change(self):
        from unittest.mock import patch
        other = ('ticker', 'auctions', 'stages', 'hero', 'reviews', 'steps', 'advantages')
        with patch.object(home, 'ORDER', other):
            new = home.apply(self.home)
            found = home._blocks(new)[2]
            self.assertEqual(tuple(found), other)
            self.assertEqual(home._unordered(new), self.home)

    def test_second_build_refused(self):
        result = candidate_builder.build(self.source, {})
        with self.assertRaises(ValueError):
            candidate_builder.build(result, {})


if __name__ == '__main__':
    unittest.main()

"""The advantages block goes whole; every other byte stays; the home order module still leaves the page alone."""
import importlib.machinery
import importlib.util
from pathlib import Path
import unittest

import candidate_builder
import edit_home

FIXTURES = Path(__file__).resolve().parent/'fixtures'
HOME = (FIXTURES/'index_live.html').read_bytes()


def order_module():
    loader = importlib.machinery.SourceFileLoader('ua_korea_home', str(FIXTURES/'ua_korea_home.txt'))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader('ua_korea_home', loader))
    loader.exec_module(module)
    return module


class StripTests(unittest.TestCase):
    def setUp(self):
        self.before = HOME.decode('utf-8')
        self.after = edit_home.build(HOME).decode('utf-8')

    def test_block_gone(self):
        for words in edit_home.GONE + ('Діагностика</b>', 'Маршрут онлайн', 'Працюємо в Києві', 'Контейнер і дата'):
            self.assertNotIn(words, self.after)
        self.assertIn(edit_home.CHECK, self.after)

    def test_every_other_byte_stays(self):
        start, end = edit_home.block(self.before)
        self.assertEqual(self.before[:start] + self.before[end:], self.after)
        self.assertEqual(len(self.before) - len(self.after), end - start)

    def test_only_home_changes(self):
        self.assertEqual(candidate_builder.build({'video/index.html': HOME}, {}), {'video/index.html': edit_home.build(HOME)})

    def test_already_removed_or_doubled_changes_nothing(self):
        with self.assertRaisesRegex(ValueError, 'HOME_STRIP_ANCHOR'):
            edit_home.build(self.after.encode('utf-8'))
        start, end = edit_home.block(self.before)
        with self.assertRaisesRegex(ValueError, 'HOME_STRIP_ANCHOR'):
            edit_home.build(HOME + self.before[start:end].encode('utf-8'))

    def test_home_order_module_keeps_page(self):
        module = order_module()
        self.assertEqual(module.apply(self.after), self.after)


if __name__ == '__main__':
    unittest.main()

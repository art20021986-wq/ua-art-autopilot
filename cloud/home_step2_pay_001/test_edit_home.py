"""Step 2 payment line: «покупка» → «услуга» in ru/uk/ka; every other byte stays."""
from pathlib import Path
import unittest

import edit_home

HOME = (Path(__file__).resolve().parent/'fixtures'/'index_live.html').read_bytes()


class PayLineTests(unittest.TestCase):
    def test_only_the_word_changes(self):
        before = HOME.decode('utf-8')
        after = edit_home.build(HOME).decode('utf-8')
        self.assertEqual(after.replace(edit_home.NEW, edit_home.OLD, 1), before)
        for words in ('покупка — 600', 'купівля — 600', 'ყიდვა — 600'):
            self.assertNotIn(words, after)
        for words in ('услуга — 600 $, депозит — 1 000 $', edit_home.CHECK, 'მომსახურება — 600 $, დეპოზიტი'):
            self.assertIn(words, after)

    def test_already_live_or_missing_changes_nothing(self):
        with self.assertRaisesRegex(ValueError, 'HOME_STEP2_PAY_ANCHOR'):
            edit_home.build(edit_home.build(HOME))
        with self.assertRaisesRegex(ValueError, 'HOME_STEP2_PAY_ANCHOR'):
            edit_home.build(HOME + edit_home.OLD.encode())


if __name__ == '__main__':
    unittest.main()

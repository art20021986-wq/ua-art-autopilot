"""Step 2: only the old line goes, on the home page and (if present) the korea.html copy; every other byte stays."""
from pathlib import Path
import unittest

import candidate_builder
import edit_home

FIXTURES = Path(__file__).resolve().parent/'fixtures'
HOME = (FIXTURES/'index_live.html').read_bytes()
KOREA = (FIXTURES/'korea_live.html').read_bytes()


class Step2FixTests(unittest.TestCase):
    def test_only_the_old_line_goes(self):
        before = HOME.decode('utf-8')
        after = edit_home.build(HOME).decode('utf-8')
        self.assertEqual(before.count(edit_home.OLD), 1)
        self.assertNotIn(edit_home.GONE, after)
        self.assertNotIn('корейских аукционах', after)
        self.assertEqual(after.count(edit_home.STEP2), 1)
        self.assertEqual(before.replace(edit_home.OLD, '', 1), after)

    def test_rest_of_step2_stays(self):
        after = edit_home.build(HOME).decode('utf-8')
        for words in ('Вартість послуги — 600 $', 'Після оплати менеджер створює', 'депозит — 1 000 $'):
            self.assertIn(words, after)

    def test_korea_changes_only_if_it_holds_the_line(self):
        self.assertNotIn(edit_home.OLD.encode(), KOREA)
        self.assertEqual(candidate_builder.build({'video/index.html': HOME, 'video/korea.html': KOREA}, {}),
                         {'video/index.html': edit_home.build(HOME)})
        korea = KOREA.replace(b'</body>', edit_home.OLD.encode() + b'</body>', 1)
        result = candidate_builder.build({'video/index.html': HOME, 'video/korea.html': korea}, {})
        self.assertEqual(result['video/korea.html'], KOREA)

    def test_already_fixed_or_doubled_changes_nothing(self):
        after = edit_home.build(HOME)
        with self.assertRaisesRegex(ValueError, 'HOME_STEP2_ANCHOR'):
            edit_home.build(after)
        with self.assertRaisesRegex(ValueError, 'HOME_STEP2_ANCHOR'):
            edit_home.build(HOME + edit_home.OLD.encode())
        with self.assertRaisesRegex(ValueError, 'HOME_STEP2_ANCHOR'):
            edit_home.build(KOREA + (edit_home.OLD * 2).encode(), required=False)


if __name__ == '__main__':
    unittest.main()

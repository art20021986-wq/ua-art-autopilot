"""Step 2: the approved service text replaces the old line; other countries' title changes; every other byte stays."""
from pathlib import Path
import unittest

import candidate_builder
import edit_home
import service_text as T

FIXTURES = Path(__file__).resolve().parent/'fixtures'
HOME = (FIXTURES/'index_live.html').read_bytes()
KOREA = (FIXTURES/'korea_live.html').read_bytes()


class Step2Tests(unittest.TestCase):
    def setUp(self):
        self.before = HOME.decode('utf-8')
        self.after = edit_home.build(HOME).decode('utf-8')

    def test_old_words_gone(self):
        for words in edit_home.GONE + ('корейских аукционах', 'Подбор и проверка', 'შერჩევა და შემოწმება'):
            self.assertNotIn(words, self.after)

    def test_approved_text_in_order(self):
        order = [T.FIRST[1], T.INCLUDES[1]] + [i[1] for i in T.ITEMS] + ['Вартість послуги — 600 $', T.SEPARATE[1]]
        places = [self.after.index('>%s<' % w) for w in order]
        self.assertEqual(places, sorted(places))
        for words in (T.FIRST, T.SEPARATE, T.OTHER_TITLE) + T.ITEMS:
            self.assertIn('data-ru="%s" data-uk="%s" data-ka="%s">%s<' % (words + (words[1],)), self.after)

    def test_every_other_byte_stays(self):
        restored = (self.after.replace(edit_home.SERVICE, edit_home.OLD, 1).replace(edit_home.SEPARATE, '', 1)
                    .replace(edit_home.NEW_TITLE, edit_home.OLD_TITLE, 1))
        self.assertEqual(restored, self.before)

    def test_korea_copy_follows_where_present(self):
        result = candidate_builder.build({'video/index.html': HOME, 'video/korea.html': KOREA}, {})
        self.assertEqual(result['video/index.html'], edit_home.build(HOME))
        if edit_home.OLD_TITLE.encode() in KOREA or edit_home.OLD.encode() in KOREA:
            self.assertNotIn(edit_home.OLD_TITLE, result['video/korea.html'].decode())
        else:
            self.assertNotIn('video/korea.html', result)

    def test_already_live_or_doubled_changes_nothing(self):
        with self.assertRaisesRegex(ValueError, 'HOME_STEP2_ANCHOR'):
            edit_home.build(self.after.encode('utf-8'))
        with self.assertRaisesRegex(ValueError, 'HOME_STEP2_ANCHOR'):
            edit_home.build(HOME + edit_home.OLD.encode())
        with self.assertRaisesRegex(ValueError, 'HOME_STEP2_ANCHOR'):
            edit_home.build(HOME.replace(edit_home.OLD_TITLE.encode(), b'<b>x</b>'))

    def test_unsafe_text_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'HOME_STEP2_TEXT'):
            edit_home.text('p', ('a', '<b>', 'c'))


if __name__ == '__main__':
    unittest.main()

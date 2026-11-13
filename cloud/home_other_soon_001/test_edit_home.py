"""Other 7 countries: steps 2–5 removed, «coming soon» note; Korea, step 1 and every other byte stay."""
from pathlib import Path
import unittest

import edit_home

HOME = (Path(__file__).resolve().parent/'fixtures'/'index_live.html').read_bytes()


class OtherSoonTests(unittest.TestCase):
    def test_only_other_steps_and_note_change(self):
        before = HOME.decode('utf-8')
        after = edit_home.build(HOME).decode('utf-8')
        restored = after.replace(edit_home.CSS, '', 1).replace(edit_home.NEW, edit_home.OLD, 1)
        anchor = '</ol><div class="ua-cc-other"'
        restored = restored.replace(anchor, ''.join(edit_home.OLD_STEPS) + anchor, 1)
        self.assertEqual(restored, before)
        for words in edit_home.GONE + ('уточняйте у менеджера', 'დააზუსტეთ მენეჯერთან'):
            self.assertNotIn(words, after)
        for words in (edit_home.CHECK, 'Скоро здесь появится подробная информация', 'მალე აქ',
                      'Заповнити заявку', '<li class="ua-step-free"><i>1</i>', 'data-ua-for="korea"'):
            self.assertIn(words, after)
        self.assertEqual(after.count('data-ua-for="other"'), 1)

    def test_already_live_or_missing_changes_nothing(self):
        with self.assertRaisesRegex(ValueError, 'HOME_OTHER_SOON_ANCHOR'):
            edit_home.build(edit_home.build(HOME))
        with self.assertRaisesRegex(ValueError, 'HOME_OTHER_SOON_ANCHOR'):
            edit_home.build(HOME.replace(edit_home.OLD_STEPS[1].encode(), b'', 1))


if __name__ == '__main__':
    unittest.main()

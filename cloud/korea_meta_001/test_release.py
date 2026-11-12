"""The KOREA-META candidate from the live Korea page."""
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_builder as cb  # noqa: E402


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.page = (HERE / 'fixtures' / 'korea_live.html').read_text()

    def test_only_the_deposit_sentence_leaves_the_description(self):
        new = cb.build({cb.PAGE: self.page.encode()}, {})[cb.PAGE].decode()
        old_tag, new_tag = cb.META.findall(self.page)[0], cb.META.findall(new)[0]
        self.assertTrue(all(s not in new_tag for s in cb.SENTENCES))
        self.assertIn('пробіг і стартова ціна."', new_tag)
        self.assertIn('пробег и стартовая цена."', new_tag)
        self.assertIn('ყოველკვირა."', new_tag)
        self.assertEqual(new, self.page.replace(old_tag, new_tag, 1))
        self.assertEqual(len(new), len(self.page) - len(old_tag) + len(new_tag))

    def test_installed_page_is_refused(self):
        with self.assertRaises(ValueError):
            cb.apply(cb.apply(self.page))

    def test_page_without_the_description_is_refused(self):
        with self.assertRaises(ValueError):
            cb.apply(self.page.replace('<meta name="description"', '<meta name="x"'))


if __name__ == '__main__':
    unittest.main()

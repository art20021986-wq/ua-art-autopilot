import pathlib
import unittest

import model_groups

LIVE = (pathlib.Path(__file__).with_name('fixtures') / 'korea_live.html').read_bytes()


class ModelGroupsTest(unittest.TestCase):
    def test_only_the_model_list_changes(self):
        out = model_groups.build(LIVE).decode('utf-8')
        self.assertIn(model_groups.CHECK, out)
        self.assertEqual(out.replace(model_groups.NEW, model_groups.OLD).encode('utf-8'), LIVE)

    def test_applied_once_and_unknown_page_refused(self):
        with self.assertRaises(ValueError):
            model_groups.build(model_groups.build(LIVE))
        with self.assertRaises(ValueError):
            model_groups.build(LIVE.replace(model_groups.OLD.encode('utf-8'), b''))


if __name__ == '__main__':
    unittest.main()

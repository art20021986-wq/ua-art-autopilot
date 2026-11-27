"""KOREA-PLAN-DAYS-001: the four Korea page edits, on the live page, and how the day buttons read `planned`."""
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import plan_page  # noqa: E402

LIVE = (HERE / 'fixtures' / 'korea_live.html').read_bytes()


class PlanPageTests(unittest.TestCase):
    def test_only_the_edits_change(self):
        page = plan_page.build(LIVE).decode('utf-8')
        back = page
        for old, new in plan_page.edits():
            self.assertEqual(page.count(new), 1)
            back = back.replace(new, old)
        self.assertEqual(back.encode('utf-8'), LIVE)  # every other byte stays
        self.assertIn('PLAN=d.planned||null', page)
        self.assertIn('t("soon"):t("none")', page)  # without planned: as before

    def test_refuses_a_changed_or_edited_page(self):
        with self.assertRaises(ValueError):
            plan_page.build(plan_page.build(LIVE))
        with self.assertRaises(ValueError):
            plan_page.build(LIVE.replace(plan_page.DECL.encode(), b''))


if __name__ == '__main__':
    unittest.main()

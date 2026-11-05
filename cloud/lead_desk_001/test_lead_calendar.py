import datetime
import unittest

import ua_lead_calendar as cal

D = datetime.date


def ts(y, m, d, h=12):
    return datetime.datetime(y, m, d, h, tzinfo=cal.KYIV).timestamp()


class CalendarTests(unittest.TestCase):
    def test_orthodox_easter(self):
        # Known dates: 2024-05-05, 2025-04-20, 2026-04-12, 2027-05-02.
        self.assertEqual([cal.orthodox_easter(y) for y in (2024, 2025, 2026, 2027)],
                         [D(2024, 5, 5), D(2025, 4, 20), D(2026, 4, 12), D(2027, 5, 2)])

    def test_holidays_any_year(self):
        h = cal.holidays(2027)
        self.assertIn(D(2027, 1, 1), h)
        self.assertIn(D(2027, 8, 24), h)
        self.assertIn(D(2027, 6, 20), h)  # Trinity = Easter + 49
        self.assertNotIn(D(2027, 1, 7), h)  # Removed in 2023.

    def test_sunday_and_holiday_off_saturday_works(self):
        self.assertFalse(cal.is_working_day(D(2026, 11, 8)))   # Sunday
        self.assertTrue(cal.is_working_day(D(2026, 11, 7)))    # Saturday
        self.assertFalse(cal.is_working_day(D(2026, 12, 25)))  # Christmas

    def test_deadline_counts_full_working_days(self):
        # Thursday 2026-11-05 → Fri, Sat, (Sun off) Mon → end of Monday 09.11 (= 10.11 00:00).
        self.assertEqual(cal.deadline(ts(2026, 11, 5)), datetime.datetime(2026, 11, 10, tzinfo=cal.KYIV))

    def test_deadline_skips_holiday(self):
        # Tuesday 2026-12-22 → Wed 23, Thu 24, (Fri 25 off) Sat 26 → end of 26.12.
        self.assertEqual(cal.deadline(ts(2026, 12, 22, 23)), datetime.datetime(2026, 12, 27, tzinfo=cal.KYIV))

    def test_days_left(self):
        created = ts(2026, 11, 5)
        self.assertEqual(cal.working_days_left(created, ts(2026, 11, 5)), 3)  # arrival day not counted
        self.assertEqual(cal.working_days_left(created, ts(2026, 11, 6)), 3)  # Fri, Sat, Mon
        self.assertEqual(cal.working_days_left(created, ts(2026, 11, 8)), 1)  # Sunday: only Monday left
        self.assertEqual(cal.working_days_left(created, ts(2026, 11, 9)), 1)  # last day
        self.assertEqual(cal.working_days_left(created, ts(2026, 11, 10)), 0)


if __name__ == '__main__':
    unittest.main()

"""KOREA-WEEK-DAYS: one exact edit of the live korea.html; week() gives 7 days from today in Korea (run in node)."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

import candidate_builder
import week_days

LIVE = (Path(__file__).resolve().parent/'fixtures'/'korea_live.html').read_text(encoding='utf-8')


def week(now_utc, counts):
    """Run the page's week() at a fixed moment (ISO, UTC) in node."""
    script = ('Date.now=function(){return Date.parse(%s);};%s;console.log(JSON.stringify(week(%s)));'
              % (json.dumps(now_utc), week_days.WEEK, json.dumps(counts)))
    out = subprocess.run(['node', '-e', script], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


class EditTests(unittest.TestCase):
    def setUp(self):
        self.after = week_days.build(LIVE)

    def test_one_edit_every_other_byte_stays(self):
        self.assertNotIn(week_days.OLD, self.after)
        self.assertEqual(self.after.count(week_days.CHECK), 1)
        self.assertEqual(self.after.replace(week_days.WEEK, '', 1).replace(week_days.NEW, week_days.OLD, 1), LIVE)

    def test_candidate_is_the_page_only(self):
        result = candidate_builder.build({'video/korea.html': LIVE.encode('utf-8')}, {})
        self.assertEqual(result, {'video/korea.html': self.after.encode('utf-8')})

    def test_already_applied_or_other_page_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'ALREADY_APPLIED'):
            week_days.build(self.after)
        with self.assertRaisesRegex(ValueError, 'FRAGMENT_NOT_UNIQUE'):
            week_days.build(LIVE.replace(week_days.OLD, ''))
        with self.assertRaisesRegex(ValueError, 'FRAGMENT_NOT_UNIQUE'):
            week_days.build(LIVE + week_days.OLD)


@unittest.skipUnless(shutil.which('node'), 'node')
class WeekTests(unittest.TestCase):
    def test_wednesday_to_tuesday(self):
        # Wed 18.11 10:00 in Korea; lots listed for two days only
        days = week('2026-11-18T01:00:00Z', {'2026/11/18': 378, '2026/11/20': 56})
        self.assertEqual(days, ['2026/11/18', '2026/11/19', '2026/11/20', '2026/11/21', '2026/11/22',
                                '2026/11/23', '2026/11/24'])

    def test_day_starts_at_korea_midnight(self):
        self.assertEqual(week('2026-11-12T14:59:00Z', {})[0], '2026/11/12')
        self.assertEqual(week('2026-11-12T15:00:00Z', {})[0], '2026/11/13')

    def test_month_end_and_later_listed_day(self):
        days = week('2026-12-28T03:00:00Z', {'2027/01/02': 5, '2027/01/09': 7, '2026/12/27': 1})
        self.assertEqual(days, ['2026/12/28', '2026/12/29', '2026/12/30', '2026/12/31', '2027/01/01',
                                '2027/01/02', '2027/01/03', '2027/01/09'])


if __name__ == '__main__':
    unittest.main()

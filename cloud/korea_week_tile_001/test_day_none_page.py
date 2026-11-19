"""KOREA-WEEKTILE-001: the Korea page day buttons say «Аукціонів немає» when there is no auction that day."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import day_none_page  # noqa: E402

LIVE = (HERE / 'fixtures' / 'korea_live.html').read_bytes()  # the live Korea page, 18.11


class DayNonePageTest(unittest.TestCase):
    def test_edits_apply_once_and_keep_the_rest(self):
        page = day_none_page.build(LIVE).decode('utf-8')
        self.assertIn('"none": ["Аукціонів немає", "Аукционов нет", "აუქციონები არ არის"]', page)
        self.assertIn('SCH=d.schedule||null;days();', page)
        self.assertEqual(page.count('function reason(d,c){'), 1)
        with self.assertRaises(ValueError):
            day_none_page.build(page.encode('utf-8'))  # applied once only
        rest = LIVE.decode('utf-8')
        for old, new in day_none_page.edits():
            rest = rest.replace(old, new, 1)
        self.assertEqual(rest, page)

    @unittest.skipUnless(shutil.which('node'), 'node')
    def test_reason_in_the_page_script(self):
        page = day_none_page.build(LIVE).decode('utf-8')
        script = page[page.index('var SCH=null;'):page.index('function days(){')]
        cases = [  # (schedule, cars per day, day) on Thursday 19.11 (Korea)
            (None, {'2026/11/23': 5}, '2026/11/20'), (None, {}, '2026/11/20'),
            ([['AutoPlus'], [], ['Auto Hub'], [], ['AutoPlus'], [], []], {}, '2026/11/24'),
            ([['AutoPlus'], [], ['Auto Hub'], [], ['AutoPlus'], [], []], {}, '2026/11/20'),
            ([['AutoPlus'], [], [], [], [], [], []], {'2026/11/23': 5}, '2026/11/20'),
            (None, {'2026/11/23': 5}, '2026/11/23'), (None, {}, '2026/11/21'), (None, {}, '2026/11/19')]
        js = ('Date.now=function(){return Date.parse("2026-11-19T02:00:00Z");};'
              'function t(k){return k;}function n(x){return String(x);}function tri(f){return f(0);}'
              + script + 'var out=[];' + ''.join('SCH=%s;out.push(reason(%s,%s));' % (json.dumps(s), json.dumps(d),
                                                                                       json.dumps(c))
                                                 for s, c, d in cases) + 'console.log(JSON.stringify(out));')
        result = subprocess.run(['node', '-e', js], capture_output=True, text=True, timeout=30, check=True)
        self.assertEqual(json.loads(result.stdout), ['none', 'soon', 'none', 'soon', 'none', '5 cars', 'dayoff',
                                                     '0 cars'])


if __name__ == '__main__':
    unittest.main()

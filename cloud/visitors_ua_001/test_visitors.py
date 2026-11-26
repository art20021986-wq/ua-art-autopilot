#!/usr/bin/env python3
"""«Посетители из Украины»: edits on the live sources, the counter script, the report, the screens."""
import asyncio
import datetime
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_builder as cb  # noqa: E402
import ua_visitors_bot as bot  # noqa: E402
import ua_visitors_ua as report  # noqa: E402

FIX = HERE / 'fixtures'


def edited(name):
    return cb.edit(name, (FIX / (name[:-3] + '.txt')).read_text())


class EditTests(unittest.TestCase):
    def test_counter_script(self):
        text = edited('analitika_yadro.py')
        script = re.search(r'SKRIPT = r"""(.*?)"""', text, re.S).group(1)
        for part in ("'ua_staff'", 'timeZone', "'Реклама Google'", 'tz:TZ,lg:LG,dv:DV', "par.get('gclid')"):
            self.assertIn(part, script)
        if shutil.which('node'):
            with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False) as handle:
                handle.write(script)
            result = subprocess.run(['node', '--check', handle.name], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('ALTER TABLE sessions ADD COLUMN', text)
        self.assertIn('put,tz,lg,dv) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)', text)
        with self.assertRaisesRegex(ValueError, 'ALREADY_APPLIED'):
            cb.edit('analitika_yadro.py', text)

    def test_counter_stores_time_zone(self):
        text = edited('analitika_yadro.py')
        with tempfile.TemporaryDirectory() as temp:
            module = types.ModuleType('yadro_preview')
            path = Path(temp) / 'yadro_preview.py'
            path.write_text(text.replace('DOM   = "/home/Carix"', 'DOM   = %r' % temp))
            import importlib.util
            spec = importlib.util.spec_from_file_location('yadro_preview', path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            old = sqlite3.connect(Path(temp) / 'analytics.db')  # the live table, before the release
            old.execute('CREATE TABLE sessions(sid TEXT PRIMARY KEY, vid TEXT, nachalo INTEGER, konec INTEGER, istochnik TEXT, '
                        'utm_source TEXT, utm_medium TEXT, utm_campaign TEXT, utm_content TEXT, put TEXT)')
            old.commit()
            old.close()
            self.assertEqual(module.zapisat({'t': 'page', 'v': 'v1', 's': 's1', 'e': 'e1', 'p': '/video/index.html',
                                             'tz': 'Europe/Kyiv', 'lg': 'uk-UA', 'dv': 'm'}), 'ok')
            row = sqlite3.connect(Path(temp) / 'analytics.db').execute('SELECT tz, lg, dv FROM sessions').fetchone()
        self.assertEqual(row, ('Europe/Kyiv', 'uk-UA', 'm'))

    def test_button_and_routing(self):
        text = edited('analitika_knopka.py')
        self.assertIn('("🇺🇦 Посетители из Украины", "v_an_ua")', text)
        self.assertLess(text.index('if not vladelec_li(kto)'), text.index('deystvie.startswith("v_an_ua")'))
        self.assertIn('ua_visitors_bot.register(app)', edited('analitika_bot.py'))

    def test_build_pins_live_files(self):
        with self.assertRaisesRegex(ValueError, 'INPUT_HASH'):
            cb.build({n: b'x' for n in cb.SOURCE_SHA256}, {n: b'x' for n in cb.DEPENDENCY_SHA256})


def database(path, now):
    con = sqlite3.connect(path)
    con.execute('CREATE TABLE sessions(sid TEXT, vid TEXT, nachalo INTEGER, konec INTEGER, istochnik TEXT, utm_source TEXT, '
                'utm_medium TEXT, utm_campaign TEXT, utm_content TEXT, put TEXT, tz TEXT, lg TEXT, dv TEXT)')
    con.execute('CREATE TABLE events(id INTEGER PRIMARY KEY, eid TEXT, sid TEXT, vid TEXT, ts INTEGER, tip TEXT, '
                'stranica TEXT, avto TEXT, znachenie TEXT)')
    rows = [('s1', 'v1', now - 600, 'Реклама Google', 'Europe/Kyiv', 'm',
             [(0, 'page', '/video/index.html', ''), (90, 'page', '/video/korea.html', ''), (200, 'telegram', '/video/korea.html', 'Telegram')]),
            ('s2', 'v2', now - 500, 'Google', 'Europe/Kyiv', 'd', [(0, 'page', '/video/katalog.html', '')]),
            ('s3', 'v3', now - 400, 'Прямой / неизвестный', 'America/Chicago', 'd', [(0, 'page', '/', '')]),
            ('s4', 'v4', now - 300, 'Прямой / неизвестный', 'Europe/Kiev', 'm',
             [(0, 'page', '/video/seo/ua/avto-z-korei-do-kyieva-pid-kluch.html', ''),
              (30, 'knopka', '/video/seo/ua/avto-z-korei-do-kyieva-pid-kluch.html', 'Отримати пропозицію в месенджері')])]
    n = 0
    for sid, vid, began, source, tz, dv, events in rows:
        con.execute('INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)', (sid, vid, began, began, source, '', '', '', '', '',
                                                                               tz, 'uk', dv))
        for offset, tip, page, value in events:
            n += 1
            con.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?)', (n, 'e%d' % n, sid, vid, began + offset, tip, page, '', value))
    con.commit()
    con.close()


class ReportTests(unittest.TestCase):
    def test_ukraine_only_with_outcomes(self):
        now = 1795700000
        with tempfile.TemporaryDirectory() as temp:
            db = str(Path(temp) / 'analytics.db')
            database(db, now)
            text, pages = report.build(now - 3600, now + 60, 'Сегодня', db=db)
        self.assertEqual(pages, 1)
        self.assertIn('Людей: <b>3</b>', text)  # Chicago is not counted
        self.assertIn('🔥 Заинтересовались: 2 · 👋 Зашли и вышли: 1', text)
        self.assertIn('📞 Нажали «связаться»: 1 · 📝 Заявки: 1', text)
        self.assertIn('Реклама Google', text)
        self.assertIn('index.html (1 мин) → korea.html', text)
        self.assertNotIn('Chicago', text)

    def test_before_the_release_no_time_zone(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / 'analytics.db'
            sqlite3.connect(db).execute('CREATE TABLE sessions(sid TEXT, vid TEXT, nachalo INTEGER)').connection.close()
            text, pages = report.build(0, 10, 'Вчера', db=str(db))
        self.assertIn('нет', text)

    def test_periods(self):
        now = datetime.datetime(2026, 11, 26, 12, tzinfo=report.kyiv()).timestamp()
        start, end, title = report.bounds('yesterday', now)
        self.assertEqual(end - start, 86400)
        start, end, title = report.bounds('30d', now)
        self.assertEqual(round((end - start) / 86400), 30)


class BotTests(unittest.TestCase):
    def test_callbacks_fit_telegram(self):
        datas = [d for row in bot.menu() for _, d in row] + ['v_an_ua_r:20261101:20261125:12']
        self.assertTrue(all(len(d.encode()) <= 64 for d in datas))
        self.assertTrue(all(d.startswith('v_an_') or d == 'v_analytics' for d in datas))

    def test_range_parsing(self):
        today = datetime.date(2026, 11, 26)
        self.assertEqual(bot.parse_range('01.11–25.11', today), (datetime.date(2026, 11, 1), datetime.date(2026, 11, 25)))
        self.assertEqual(bot.parse_range('1.11.2026 - 3.11.2026', today)[1], datetime.date(2026, 11, 3))
        self.assertIsNone(bot.parse_range('25.11–01.11', today))
        self.assertIsNone(bot.parse_range('привет', today))

    def test_pager(self):
        buttons = bot.pager('v_an_ua_p:7d', 1, 3)
        self.assertEqual([d for _, d in buttons[0]], ['v_an_ua_p:7d:0', 'v_an_ua_p:7d:2'])

    def test_register_adds_handler_and_daily_job(self):
        jobs = []
        app = types.SimpleNamespace(handlers=[], add_handler=lambda h, group=0: app.handlers.append((h, group)),
                                    job_queue=types.SimpleNamespace(run_daily=lambda cb_, time, name: jobs.append((time, name))))
        fake = types.ModuleType('telegram.ext')
        fake.MessageHandler = lambda f, cb_: ('handler', cb_)
        fake.filters = types.SimpleNamespace(TEXT=_F(), ChatType=types.SimpleNamespace(PRIVATE=_F()), Regex=lambda r: _F())
        with patch.dict(sys.modules, {'telegram': types.ModuleType('telegram'), 'telegram.ext': fake}):
            self.assertTrue(bot.register(app))
        self.assertEqual(app.handlers[0][1], -1)
        self.assertEqual((jobs[0][0].hour, jobs[0][0].minute, jobs[0][1]), (9, 0, 'ua_visitors_daily'))


class _F:
    def __and__(self, other):
        return self


if __name__ == '__main__':
    unittest.main()

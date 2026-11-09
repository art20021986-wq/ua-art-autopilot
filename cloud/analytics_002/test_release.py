#!/usr/bin/env python3
"""Release-specific checks: exact installed input, the report patch on the real source, pages and the log count."""
import datetime
import gzip
import hashlib
import importlib.util
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

import candidate_builder
import ua_google_tag
import ua_server_visits as visits

HERE = Path(__file__).resolve().parent
OTCHET = (HERE/'fixtures/analitika_otchet.txt').read_bytes()
PHONE = 'Mozilla/5.0 (iPhone) Mobile Safari'


def line(ip, stamp, path, agent=PHONE, method='GET', status='200'):
    return '%s - - [%s +0000] "%s %s HTTP/1.1" %s 5 "-" "%s"' % (ip, stamp, method, path, status, agent)


LOG = '\n'.join([
    line('1.1.1.1', '07/Nov/2026:21:30:00', '/video/UA-0013.html'),     # 23:30 Kyiv, 7 Nov
    line('1.1.1.1', '07/Nov/2026:22:30:00', '/video/katalog.html'),     # 00:30 Kyiv, 8 Nov
    line('1.1.1.1', '07/Nov/2026:22:31:00', '/video/UA-0014.html'),
    line('2.2.2.2', '08/Nov/2026:10:00:00', '/'),
    line('2.2.2.2', '08/Nov/2026:10:00:01', '/ua/a/e', method='POST', status='204'),
    line('2.2.2.2', '08/Nov/2026:10:00:02', '/video/img/x.jpg'),
    line('3.3.3.3', '08/Nov/2026:10:00:00', '/video/UA-0013.html', agent='Googlebot/2.1'),
    line('4.4.4.4', '08/Nov/2026:10:00:00', '/video/nope.html', status='404'),
])


def build(source, pages):
    pins = {name: hashlib.sha256(value).hexdigest() for name, value in source.items()}
    original = candidate_builder.SOURCE_SHA256
    candidate_builder.SOURCE_SHA256 = pins
    try:
        return candidate_builder.build(source, pages)
    finally:
        candidate_builder.SOURCE_SHA256 = original


def module(source, name):
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp)/(name + '.py')
        path.write_bytes(source)
        spec = importlib.util.spec_from_file_location(name, path)
        value = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(value)
        return value


class ReleaseTests(unittest.TestCase):
    def test_fixture_is_the_installed_report(self):
        self.assertEqual(hashlib.sha256(OTCHET).hexdigest(), candidate_builder.SOURCE_SHA256['analitika_otchet.py'])
        self.assertEqual(hashlib.sha256((HERE/'ua_google_tag.py').read_bytes()).hexdigest(),
                         'f5f0a30489d20d7f7d973c27bd31e583e9827fb5a6d1e24a97fb35d1e6a3b6d4')

    def test_builder_refuses_unexpected_input_and_double_patch(self):
        with self.assertRaisesRegex(ValueError, 'INPUT_HASH'):
            candidate_builder.build({'analitika_otchet.py': b'other'}, {})
        patched = build({'analitika_otchet.py': OTCHET}, {})['analitika_otchet.py']
        with self.assertRaisesRegex(ValueError, 'ALREADY_PATCHED'):
            build({'analitika_otchet.py': patched}, {})

    def test_planned_files_and_pages(self):
        tagged = ua_google_tag.apply('<html><head></head><body></body></html>').encode()
        pages = {'video/UA-0018-diag.html': b'<html><head><title>d</title></head><body>x</body></html>',
                 'site/UA-0018-diag.html': tagged}
        result = build({'analitika_otchet.py': OTCHET}, pages)
        self.assertEqual(sorted(result), ['analitika_otchet.py', 'ua_server_visits.py', 'video/UA-0018-diag.html'])
        self.assertEqual(result['video/UA-0018-diag.html'].count(b'G-6SRBQK6GY4'), 2)
        compile(result['analitika_otchet.py'], 'otchet', 'exec')

    def test_report_shows_the_server_line_under_views(self):
        report = module(build({'analitika_otchet.py': OTCHET}, {})['analitika_otchet.py'], 'otchet_under_test')
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp)/'analytics.db'
            con = sqlite3.connect(db)
            con.execute('CREATE TABLE events(ts INTEGER, vid TEXT, sid TEXT, tip TEXT, stranica TEXT, avto TEXT, '
                        'znachenie TEXT, eid TEXT)')
            con.execute('CREATE TABLE sessions(sid TEXT, vid TEXT, nachalo INTEGER, istochnik TEXT, utm_source TEXT, '
                        'utm_campaign TEXT, utm_medium TEXT, put TEXT)')
            con.execute("INSERT INTO events VALUES(?, 'v', 's', 'page', '/video/index.html', '', '', 'e')",
                        (int(datetime.datetime.now().timestamp()),))
            con.commit()
            con.close()
            report.BAZA = str(db)
            fake = type(sys)('ua_server_visits')
            fake.stroki = lambda ot, do: ['🖥 Все посетители по журналу сервера: 7']
            sys.modules['ua_server_visits'] = fake
            try:
                text = report.otchet('today')
            finally:
                del sys.modules['ua_server_visits']
        lines = text.splitlines()
        self.assertEqual(lines[lines.index([x for x in lines if x.startswith('👁 Просмотров')][0]) + 1],
                         '🖥 Все посетители по журналу сервера: 7')

    def test_report_survives_a_broken_server_module(self):
        source = build({'analitika_otchet.py': OTCHET}, {})['analitika_otchet.py'].decode()
        self.assertIn('    try:  # UA-SERVER-VISITS-001', source)
        self.assertIn('    except Exception:\n        pass\n', source)

    def test_log_counts_people_by_kyiv_day(self):
        found = visits.from_logs([LOG])
        self.assertEqual(found, {'2026-11-07': (1, 1), '2026-11-08': (2, 3)})

    def test_totals_read_rotated_logs_and_keep_daily_totals(self):
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp)/'access.log'
            log.write_text(LOG.splitlines()[0] + '\n')
            Path(str(log) + '.1').write_text('\n'.join(LOG.splitlines()[1:4]) + '\n')
            Path(str(log) + '.2.gz').write_bytes(gzip.compress(('\n'.join(LOG.splitlines()[4:]) + '\n').encode()))
            baza = Path(temp)/'server_visits.db'
            kiev = visits._kiev()
            start = datetime.datetime(2026, 11, 8, tzinfo=kiev).timestamp()
            self.assertEqual(visits.totals(start, start + 86400, log, baza), (2, 3, 1))
            stored = dict((d, p) for d, p in sqlite3.connect(baza).execute('SELECT den, lyudi FROM days'))
            self.assertEqual(stored, {'2026-11-08': 2})  # the oldest log day may be cut by rotation
            log.write_text('')
            Path(str(log) + '.1').write_text('')
            Path(str(log) + '.2.gz').unlink()
            # after rotation removed that day from the log, the saved total answers
            self.assertEqual(visits.totals(start, start + 86400, log, baza), (2, 3, 1))

    def test_line_text_and_silence_without_data(self):
        original = visits.totals
        try:
            visits.totals = lambda ot, do: (12, 40, 1)
            self.assertEqual(visits.stroki(0, 1), ['🖥 Все посетители по журналу сервера: 12'])
            visits.totals = lambda ot, do: (80, 300, 7)
            self.assertEqual(visits.stroki(0, 1), ['🖥 Все посетители по журналу сервера: 80 (сумма по дням)'])
            visits.totals = lambda ot, do: (0, 0, 0)
            self.assertEqual(visits.stroki(0, 1), [])
            visits.totals = lambda ot, do: 1 / 0
            self.assertEqual(visits.stroki(0, 1), [])
        finally:
            visits.totals = original

    def test_no_ip_is_stored(self):
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp)/'access.log'
            log.write_text(LOG + '\n')
            baza = Path(temp)/'server_visits.db'
            visits.totals(0, 1, log, baza)
            self.assertNotIn(b'1.1.1.1', baza.read_bytes())

    def test_page_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for relative in ('video/UA-0018-diag.html', 'site/UA-0001-diag.html', 'video/UA-0018.html',
                             'video/privacy.html', 'video/proba-index.html', 'video/preview/UA-0001-diag.html'):
                (root/relative).parent.mkdir(parents=True, exist_ok=True)
                (root/relative).write_text('x')
            self.assertEqual(sorted(candidate_builder.page_paths(root)),
                             ['site/UA-0001-diag.html', 'video/UA-0018-diag.html', 'video/privacy.html'])


if __name__ == '__main__':
    unittest.main()

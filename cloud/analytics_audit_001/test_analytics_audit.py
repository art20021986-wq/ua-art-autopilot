#!/usr/bin/env python3
import json
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import controller as c  # noqa: E402
import source_remote as remote  # noqa: E402
import transport  # noqa: E402

PHONE = 'Mozilla/5.0 (iPhone) Mobile Safari'
LOG = '\n'.join([
    '1.1.1.1 - - [06/Nov/2026:10:00:00 +0000] "GET /video/UA-0013.html HTTP/1.1" 200 5 "https://www.google.com/" "%s"' % PHONE,
    '1.1.1.1 - - [06/Nov/2026:10:01:00 +0000] "GET /video/katalog.html HTTP/1.1" 200 5 "-" "%s"' % PHONE,
    '1.1.1.1 - - [06/Nov/2026:10:01:01 +0000] "POST /ua/a/e HTTP/1.1" 204 0 "-" "%s"' % PHONE,
    '2.2.2.2 - - [06/Nov/2026:11:00:00 +0000] "GET /video/UA-0014.html HTTP/1.1" 200 5 "-" "%s"' % PHONE,
    '3.3.3.3 - - [06/Nov/2026:11:00:00 +0000] "GET /video/UA-0014.html HTTP/1.1" 200 5 "-" "Googlebot/2.1"',
])


class FakeAPI:
    def __init__(self, report):
        self.report = report

    def run(self, mode, run_id, bundle):
        return self.report


class ControllerTests(unittest.TestCase):
    TASK = 'ANALYTICS-AUDIT-PROBE-20261107'

    def env(self, root):
        request = root / 'tasks/requests' / (self.TASK + '.json')
        request.parent.mkdir(parents=True)
        request.write_text(json.dumps({'production_required': False}))
        return {'UAART_TASK_ID': self.TASK, 'UAART_RECEIPT_PATH': 'state/receipts/%s.json' % self.TASK,
                'UAART_REQUEST_PATH': 'tasks/requests/%s.json' % self.TASK,
                'UAART_REQUEST_SHA256': c.sha(request.read_bytes()), 'UAART_RUN_ID': '7'}

    def test_report_saved(self):
        with tempfile.TemporaryDirectory() as temp:
            receipt = c.execute(self.env(Path(temp)), root=temp, api=FakeAPI({'status': 'PASS'}), upload=lambda a: 'b' * 64)
        self.assertEqual((receipt['probe_status'], receipt['evidence_path']),
                         ('PASS', 'cloud/analytics_audit_001/20261107.json'))

    def test_production_request_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            env = self.env(Path(temp))
            request = Path(temp) / env['UAART_REQUEST_PATH']
            request.write_text(json.dumps({'production_required': True}))
            env['UAART_REQUEST_SHA256'] = c.sha(request.read_bytes())
            with self.assertRaisesRegex(c.ProbeError, 'SCOPE'):
                c.execute(env, root=temp, api=FakeAPI({}), upload=lambda a: 'b' * 64)


class TransportTests(unittest.TestCase):
    def test_never_the_bot(self):
        api = transport.API('test-token')
        with patch.object(api, 'file', return_value=None), patch.object(api, 'json', return_value={'id': transport.BOT_ID}):
            with self.assertRaisesRegex(transport.TransportError, 'TRIGGER_IDENTITY'):
                api.run('probe', '1', 'a' * 64)

    def test_bundle_names_pass_bootstrap_filter(self):
        for path in Path(__file__).resolve().parent.glob('*.py'):
            self.assertRegex(path.name, re.compile(r'[a-z_]+\.py'))


class RemoteTests(unittest.TestCase):
    FILES = {'/video/UA-0013.html': ('card', False, True), '/video/UA-0014.html': ('card', False, True),
             '/video/katalog.html': ('core', True, True), '/video/preview/UA-0001.html': ('preview', False, False)}

    def test_kinds(self):
        self.assertEqual([remote.kind(p) for p in ('video/UA-0013.html', 'video/UA-0013-diag.html', 'video/podbor.html',
                                                   'video/katalog.html', 'video/preview/UA-0001.html', 'video/ua/kredyt.html')],
                         ['card', 'diag', 'order', 'core', 'preview', 'landing'])

    def test_coverage_ignores_preview_in_lists(self):
        value = remote.coverage(self.FILES)
        self.assertEqual(value['by_kind']['card'], {'html': 2, 'own': 0, 'google': 2, 'both': 0, 'none': 0})
        self.assertNotIn('/video/preview/UA-0001.html', value['without_own_counter'])

    def test_access_counts_people_not_robots_and_keeps_no_ip(self):
        value = remote.access([LOG], self.FILES)
        day = value['daily_utc']['2026-11-06']
        self.assertEqual((day['human_visitors'], day['reached_own_counter'], day['saw_page_with_own_counter'],
                          day['landed_without_own_counter'], day['robot_requests']), (2, 1, 1, 2, 1))
        self.assertEqual(day['sources'], {'google': 1, 'direct': 1})
        self.assertNotIn('1.1.1.1', json.dumps(value))

    def test_own_db_read_only_totals(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'analytics.db'
            db = sqlite3.connect(path)
            db.execute('CREATE TABLE events(ts INTEGER, vid TEXT, sid TEXT, tip TEXT)')
            db.execute('CREATE TABLE sessions(nachalo INTEGER, istochnik TEXT)')
            now = int(remote.time.time())
            db.executemany('INSERT INTO events VALUES(?,?,?,?)', [(now, 'v1', 's1', 'page'), (now, 'v1', 's1', 'phone')])
            db.execute('INSERT INTO sessions VALUES(?,?)', (now, 'Google'))
            db.commit()
            db.close()
            with patch.object(remote, 'DB', path):
                value = remote.own_db()
            with self.assertRaises(sqlite3.OperationalError):
                sqlite3.connect('file:%s?mode=ro' % path, uri=True).execute('DELETE FROM events')
        self.assertEqual(list(value['daily_utc'].values()), [{'visitors': 1, 'sessions': 1, 'page_views': 1}])
        self.assertEqual(value['sources'], {'Google': 1})

    def test_sources_redact_secrets(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            (home / 'ua_google_tag.py').write_text("TOKEN = 'abc'\nx = 1  # /ua/a.js\n")
            with patch.object(remote, 'HOME', home), patch.object(remote, 'WSGI', home / 'none.py'):
                value = remote.sources()
        self.assertEqual(value['full']['ua_google_tag.py'], '[REDACTED]\nx = 1  # /ua/a.js')
        self.assertEqual(value['hits']['ua_google_tag.py'], [{'line': 2, 'text': 'x = 1  # /ua/a.js'}])
        self.assertFalse(value['analitika_stop']['exists'])

    def test_live_only_public_get(self):
        seen = []

        class Response:
            status = 200

            def __init__(self, body):
                self.body = body

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self, n):
                return self.body

        def opener(request, timeout):
            seen.append((request.get_method(), request.full_url))
            if request.full_url.endswith('sitemap.xml'):
                return Response(b'<loc>https://www.uaart.com.ua/video/UA-0013.html</loc>')
            return Response(b"<script src='/ua/a.js?v=1'></script> G-6SRBQK6GY4")
        with patch.object(remote.urllib.request, 'urlopen', side_effect=opener):
            value = remote.live()
        self.assertTrue(all(m == 'GET' and u.startswith('https://www.uaart.com.ua/') for m, u in seen))
        self.assertEqual(value['summary'], {'pages': 5, 'own': 5, 'google': 5})


if __name__ == '__main__':
    unittest.main()

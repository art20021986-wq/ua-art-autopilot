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
import render  # noqa: E402
import source_remote as remote  # noqa: E402
import transport  # noqa: E402

PHONE = 'Mozilla/5.0 (iPhone) Mobile Safari'
LOG = '\n'.join([
    '1.1.1.1 - - [06/Nov/2026:10:00:00 +0000] "GET /video/UA-0013.html HTTP/1.1" 200 5 "https://www.google.com/" "%s"' % PHONE,
    '1.1.1.1 - - [06/Nov/2026:10:01:01 +0000] "POST /ua/a/e HTTP/1.1" 204 0 "-" "%s"' % PHONE,
    '2.2.2.2 - - [06/Nov/2026:11:00:00 +0000] "POST /api/orders/submit HTTP/1.1" 200 5 "-" "%s"' % PHONE,
    '2.2.2.2 - - [06/Nov/2026:11:00:01 +0000] "POST /api/orders/submit HTTP/1.1" 429 5 "-" "%s"' % PHONE,
    '3.3.3.3 - - [06/Nov/2026:11:00:00 +0000] "GET /video/UA-0014.html HTTP/1.1" 200 5 "-" "Googlebot/2.1"',
    '4.4.4.4 - - [07/Nov/2026:11:00:00 +0000] "GET /x HTTP/1.1" 502 5 "-" "%s"' % PHONE,
])


def day(requests=100, heavy=0, errors=0, orders=0, beacons=0, recorded=0):
    return {'requests': requests, 'robot_requests': 10, 'errors_5xx': errors, 'limited_429': 0, 'beacons': beacons,
            'order_submits': orders, 'addresses': 20, 'heavy_addresses': heavy, 'recorded': recorded,
            'busiest': {'network': '5.6.7.0/24', 'requests': 2000 if heavy else 30}}


class FakeAPI:
    def __init__(self, report):
        self.report = report

    def run(self, mode, run_id, bundle):
        return self.report


class ControllerTests(unittest.TestCase):
    TASK = 'BOT-WATCH-20261127'

    def env(self, root):
        request = root / 'tasks/requests' / (self.TASK + '.json')
        request.parent.mkdir(parents=True)
        request.write_text(json.dumps({'production_required': False}))
        return {'UAART_TASK_ID': self.TASK, 'UAART_RECEIPT_PATH': 'state/receipts/%s.json' % self.TASK,
                'UAART_REQUEST_PATH': 'tasks/requests/%s.json' % self.TASK,
                'UAART_REQUEST_SHA256': c.sha(request.read_bytes()), 'UAART_RUN_ID': '7'}

    def test_report_and_markdown_saved(self):
        days = {'2026-11-2%d' % n: day() for n in range(1, 7)}
        with tempfile.TemporaryDirectory() as temp:
            receipt = c.execute(self.env(Path(temp)), root=temp, api=FakeAPI({'status': 'PASS', 'days': days}),
                                upload=lambda a: 'b' * 64)
            text = (Path(temp) / 'cloud/bot_watch_001/reports/20261127.md').read_text()
        self.assertEqual((receipt['probe_status'], receipt['attack_signs']), ('PASS', 0))
        self.assertIn('признаков атаки нет', text)

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
    def test_access_counts_and_keeps_no_full_address(self):
        days = remote.access([LOG])
        first = days['2026-11-06']
        self.assertEqual((first['requests'], first['robot_requests'], first['beacons'], first['order_submits'],
                          first['limited_429'], first['addresses']), (5, 1, 1, 2, 1, 3))
        self.assertEqual(days['2026-11-07']['errors_5xx'], 1)
        self.assertEqual(first['busiest'], {'network': '1.1.1.0/24', 'requests': 2})
        self.assertNotIn('1.1.1.1', json.dumps(days))

    def test_recorded_read_only(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / 'analytics.db'
            with sqlite3.connect(db) as con:
                con.execute('CREATE TABLE events(id INTEGER PRIMARY KEY, ts INTEGER)')
                con.executemany('INSERT INTO events(ts) VALUES(?)', [(1794312000,), (1794312001,)])
            with patch.object(remote, 'DB', db):
                self.assertEqual(remote.recorded({'2026-11-06': {}}), {'2026-11-10': 2})


class SignTests(unittest.TestCase):
    def test_quiet_days_have_no_signs(self):
        self.assertEqual(render.signs({'2026-11-2%d' % n: day() for n in range(1, 8)}), [])

    def test_each_sign(self):
        base = {'2026-11-2%d' % n: day() for n in range(1, 6)}
        cases = {'spike': day(requests=5000), 'heavy': day(heavy=1), 'errors': day(errors=60),
                 'orders': day(orders=25), 'left': day(beacons=900, recorded=100)}
        for name, value in cases.items():
            found = render.signs({**base, '2026-11-26': value})
            self.assertEqual([d for d, _ in found], ['2026-11-26'], name)

    def test_markdown_shows_last_three_days_and_signs(self):
        days = {'2026-11-2%d' % n: day() for n in range(1, 6)}
        days['2026-11-25'] = day(heavy=1)
        text, recent = render.markdown(days, 'Отчёт', '9')
        self.assertIn('есть признаки атаки', text)
        self.assertEqual(len(recent), 1)
        self.assertNotIn('2026-11-22 |', text)


if __name__ == '__main__':
    unittest.main()

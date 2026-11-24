import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import controller as c  # noqa: E402

TRACE = '''Nov 14 07:10:01 Traceback (most recent call last):
Nov 14 07:10:01   File "/home/Carix/ua_order/mysql_repository.py", line 190, in claim_notification
Nov 14 07:10:01     return self._run(claim, write=True)
Nov 14 07:10:01   File "/home/Carix/ua_order/mysql_repository.py", line 54, in _run
Nov 14 07:10:01 ua_order.storage.StorageUnavailable: Order storage unavailable
'''
LOG = ('Nov 13 10:00:00 start\n' + TRACE + TRACE.replace('07:10:01', '07:11:30')
       + TRACE.replace('07:10:01', '09:00:00') + 'Nov 14 09:00:01 _mysql_exceptions.OperationalError: (2013, lost) password=abc\n'
       + 'Nov 14 09:05:00 done chat 380671234567\n').encode()
SOURCE = b'def job():\n    token = "x"\n    pass\n'
HOST = 'async def error_handler(u, c):\n    text = "Ошибка в боте"\n'.encode()


class FakeApi:
    def __init__(self, files):
        self.files, self.calls = files, []

    def get(self, endpoint):
        self.calls.append(endpoint)
        if endpoint == 'cpu/':
            return 200, b'{"daily_cpu_limit_seconds": 10000}'
        path = endpoint[len('files/path'):]
        return (200, self.files[path]) if path in self.files else (404, b'')


class Tests(unittest.TestCase):
    def test_incidents_operations_and_redaction(self):
        log = c.analyse_log(LOG, 2026)
        self.assertEqual(log['failures'], 3)
        self.assertEqual(log['failures_by_operation'], {'claim_notification': 3})
        self.assertEqual(log['incident_count'], 2)
        self.assertEqual(log['incidents'][0]['count'], 2)
        self.assertEqual(log['incidents'][0]['seconds'], 89)
        self.assertEqual(log['longest_incident_seconds'], 89)
        self.assertEqual(log['mysql_line_count'], 1)
        self.assertIn('REDACTED', log['mysql_lines'][0])
        self.assertNotIn('380671234567', json.dumps(log))
        self.assertEqual(log['last_at'], 'Nov 14 09:05:00')
        self.assertEqual(len(log['last_tracebacks']), 3)
        self.assertIn('Traceback', log['last_tracebacks'][0][0])

    def test_collect_reads_only_allowed_files(self):
        files = {c.LOG: LOG, c.SOURCES[0]: SOURCE, c.HOSTS[0]: HOST}
        api = FakeApi(files)
        value = c.collect(api, 2026)
        self.assertEqual(set(api.calls), {'cpu/'} | {'files/path' + p for p in c.ALLOWED})
        self.assertIn('REDACTED', value['sources'][c.SOURCES[0]]['text'])
        self.assertTrue(any('Ошибка в боте' in l for l in value['handlers'][c.HOSTS[0]]['lines']))
        self.assertEqual(value['status'][c.HOSTS[1]], 404)

    def test_missing_log_stops(self):
        with self.assertRaisesRegex(c.ProbeError, 'LOG_UNAVAILABLE'):
            c.collect(FakeApi({}), 2026)

    def test_api_scope(self):
        api = c.Api('token')
        for endpoint in ('files/path/home/Carix/crm.db', 'always_on/', 'files/path/home/Carix/ua_order/other.py'):
            with self.assertRaisesRegex(c.ProbeError, 'API_PATH_OUTSIDE_SCOPE'):
                api.get(endpoint)

    def test_execute_writes_evidence_and_receipt(self):
        root = Path(tempfile.mkdtemp())
        task = c.TASKS[0]
        request = root/('tasks/requests/%s.json' % task)
        request.parent.mkdir(parents=True)
        request.write_text(json.dumps({'production_required': False}))
        env = {'UAART_TASK_ID': task, 'UAART_RUN_ID': '1',
               'UAART_RECEIPT_PATH': 'state/receipts/%s.json' % task,
               'UAART_REQUEST_PATH': 'tasks/requests/%s.json' % task,
               'UAART_REQUEST_SHA256': c.sha(request.read_bytes())}
        receipt = c.execute(env, root=root, api=FakeApi({c.LOG: LOG}), year=2026)
        self.assertEqual(receipt['status'], 'FINISHED')
        evidence = json.loads((root/c.PACKAGE/'evidence.json').read_text())
        self.assertEqual(evidence['log']['failures'], 3)

    def test_wrong_identity_refused(self):
        with self.assertRaisesRegex(c.ProbeError, 'IDENTITY'):
            c.validate_identity({'UAART_TASK_ID': 'OTHER'}, Path('/'))


if __name__ == '__main__':
    unittest.main()

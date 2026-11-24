import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import controller as c  # noqa: E402

A = 'a' * 64
B = 'b' * 64
OLD = 'c' * 64


class FakeApi:
    def __init__(self):
        self.calls = []

    def get(self, endpoint):
        self.calls.append(endpoint)
        if endpoint == 'files/path' + c.INBOX + '/':
            return 200, {'newcarvin2-' + A: {}, 'newcarvin2-' + B: {}, 'newcarvin-' + OLD: {}, 'opod-x': {},
                         'newcarvin2_bootstrap.py': {}}
        if endpoint.startswith('files/tree/'):
            folder = endpoint.split('newcarvin2-')[1][:64]
            base = c.INBOX + '/newcarvin2-' + folder + '/'
            return 200, [base + 'deployment_remote.py', base + 'backups/', base + 'backups/ad08/manifest.json',
                         base + 'runs/1/receipt-backup.json', '/elsewhere/x']
        return 200, [{'id': 266084, 'enabled': True, 'state': 'running', 'command': 'python3.10 start_safe.py'},
                     {'id': 7, 'enabled': True, 'state': 'running',
                      'command': 'python3.10 ' + c.INBOX + '/newcarvin2_bootstrap.py --bundle x'}]


class Tests(unittest.TestCase):
    def test_lists_only_newcarvin_folders_and_reads_only(self):
        api = FakeApi()
        value = c.collect(api)
        self.assertEqual(value['inbox_newcarvin_folders'],
                         ['newcarvin-' + OLD, 'newcarvin2-' + A, 'newcarvin2-' + B])
        self.assertEqual(sorted(value['newcarvin2_trees']), ['newcarvin2-' + A, 'newcarvin2-' + B])
        self.assertEqual(value['newcarvin2_trees']['newcarvin2-' + A]['paths'],
                         ['backups/', 'backups/ad08/manifest.json', 'runs/1/receipt-backup.json'])
        self.assertEqual([t['newcarvin_bootstrap'] for t in value['always_on']['tasks']], [False, True])
        self.assertNotIn('command', json.dumps(value))

    def test_api_scope_is_get_on_three_shapes_only(self):
        api = c.Api('token')
        for endpoint in ('always_on/266084/', 'files/path/home/Carix/crm.db', 'files/tree/?path=/home/Carix/',
                         'files/tree/?path=' + c.INBOX + '/opod-' + A + '/', 'cpu/'):
            with self.assertRaisesRegex(c.ProbeError, 'API_PATH_OUTSIDE_SCOPE'):
                api.get(endpoint)
        self.assertFalse(hasattr(api, 'call'))

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
        receipt = c.execute(env, root=root, api=FakeApi())
        self.assertEqual(receipt['status'], 'FINISHED')
        self.assertTrue((root/c.PACKAGE/'evidence.json').exists())

    def test_wrong_identity_refused(self):
        with self.assertRaisesRegex(c.ProbeError, 'IDENTITY'):
            c.validate_identity({'UAART_TASK_ID': 'OTHER'}, Path('/'))


if __name__ == '__main__':
    unittest.main()

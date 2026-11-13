import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import controller as c  # noqa: E402

BOT = {'id': 266084, 'description': 'CRM bot', 'enabled': True, 'state': 'running',
       'command': 'python3.10 /home/Carix/start_safe.py'}
LEFT = {'id': 900, 'description': 'quick lead backup 43372167569', 'enabled': True, 'state': 'running',
        'command': 'python3.10 /home/Carix/autopilot_inbox/cloud/task_068_ferry_vin/opod_bootstrap.py --mode backup'}
OTHER = {'id': 901, 'description': 'other', 'enabled': True, 'state': 'running',
         'command': 'python3.10 /home/Carix/autopilot_inbox/x/chat_bootstrap.py'}


class FakeApi:
    def __init__(self, tasks):
        self.tasks = list(tasks)
        self.calls = []

    def call(self, method, endpoint):
        self.calls.append((method, endpoint))
        if endpoint == 'cpu/':
            return 200, {'daily_cpu_limit_seconds': 4000, 'daily_cpu_total_usage_seconds': 1000}
        if method == 'DELETE':
            ident = int(endpoint.split('/')[1])
            self.tasks = [t for t in self.tasks if t['id'] != ident]
            return 204, None
        return 200, list(self.tasks)


class Tests(unittest.TestCase):
    def test_removes_only_own_leftover_never_the_bot(self):
        api = FakeApi([BOT, LEFT, OTHER])
        value = c.collect(api)
        self.assertEqual([m for m, _ in api.calls].count('DELETE'), 1)
        self.assertIn(('DELETE', 'always_on/900/'), api.calls)
        self.assertEqual(value['bot']['state'], 'running')
        self.assertEqual(value['leftovers_after'], [])
        self.assertEqual([t['id'] for t in value['always_on_after']], [266084, 901])
        self.assertNotIn('command', json.dumps(value['always_on_after']))

    def test_bot_with_matching_command_is_never_removed(self):
        bot = dict(BOT, command='python3.10 opod_bootstrap.py')
        api = FakeApi([bot])
        c.collect(api)
        self.assertFalse(any(m == 'DELETE' for m, _ in api.calls))

    def test_nothing_left_means_no_delete(self):
        api = FakeApi([BOT])
        value = c.collect(api)
        self.assertEqual(value['leftovers_found'], [])
        self.assertFalse(any(m == 'DELETE' for m, _ in api.calls))

    def test_api_scope(self):
        api = c.Api('token')
        for endpoint in ('webapps/x/', 'files/path/home/Carix/crm.db', 'always_on/266084/x'):
            with self.assertRaisesRegex(c.ProbeError, 'API_PATH_OUTSIDE_SCOPE'):
                api.call('GET', endpoint)

    def test_execute_writes_evidence_and_receipt(self):
        root = Path(tempfile.mkdtemp())
        request = root/'tasks/requests/SERVER-CHECK-20261113.json'
        request.parent.mkdir(parents=True)
        request.write_text(json.dumps({'production_required': False}))
        env = {'UAART_TASK_ID': 'SERVER-CHECK-20261113', 'UAART_RUN_ID': '1',
               'UAART_RECEIPT_PATH': 'state/receipts/SERVER-CHECK-20261113.json',
               'UAART_REQUEST_PATH': 'tasks/requests/SERVER-CHECK-20261113.json',
               'UAART_REQUEST_SHA256': c.sha(request.read_bytes())}
        receipt = c.execute(env, root=root, api=FakeApi([BOT, LEFT]))
        self.assertEqual(receipt['status'], 'FINISHED')
        evidence = json.loads((root/c.PACKAGE/'evidence.json').read_text())
        self.assertEqual([t['id'] for t in evidence['leftovers_found']], [900])

    def test_wrong_identity_refused(self):
        with self.assertRaisesRegex(c.ProbeError, 'IDENTITY'):
            c.validate_identity({'UAART_TASK_ID': 'OTHER'}, Path('/'))


if __name__ == '__main__':
    unittest.main()

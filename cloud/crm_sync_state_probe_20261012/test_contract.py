#!/usr/bin/env python3
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import controller as c  # noqa: E402

STATE = {'version': 1, 'baseline_at': 1, 'last_success': {'code': 'UA-0021', 'at': 2},
         'revisions': {'14': {'code': 'UA-0012', 'sha256': 'a' * 64, 'delivery_status': 'georgia'}},
         'retry': {'26': {'sha256': 'b' * 64, 'count': 7, 'after': 3,
                          'error': 'RuntimeError: CATALOG_ROW_SET_MISMATCH token=secret'}},
         'catalog_retry': {'source_revision': 'c' * 64, 'after': 4, 'code': 'CATALOG_ROW_SET_MISMATCH'}}


class ContractTests(unittest.TestCase):
    def test_fixed_get_scope(self):
        self.assertEqual(len(c.ENDPOINTS), 3)
        self.assertIn('files/path/home/Carix/.crm_public_sync_state.json', c.ENDPOINTS)
        api = c.ReadOnlyAPI('test-value', opener=object())
        for bad in ('files/path/home/Carix/crm.db', 'always_on/', '../x'):
            with self.assertRaises(c.ProbeError):
                api.read(bad)

    def test_state_summary_drops_hashes_and_secrets(self):
        facts = c.inspect_state(json.dumps(STATE).encode())
        self.assertEqual(facts['revisions']['14'], {'code': 'UA-0012', 'delivery_status': 'georgia'})
        self.assertEqual(facts['retry']['26']['count'], 7)
        self.assertNotIn('secret', json.dumps(facts))
        self.assertNotIn('a' * 64, json.dumps(facts))

    def test_log_keeps_sync_lines_and_dates(self):
        raw = ('noise\n' * 40 + '2026-10-11 13:17:37,831 WARNING CRM sync failed; retry pending: UA-0012\n'
               'phone +380 67 123 45 67\n').encode()
        text = '\n'.join(c.inspect_log(raw)['lines'])
        self.assertIn('2026-10-11 13:17:37', text)
        self.assertIn('UA-0012', text)
        self.assertNotIn('123 45 67', text)

    def test_execute_writes_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            request = root / c.REQUEST
            request.parent.mkdir(parents=True)
            request.write_text(json.dumps({'task_id': c.TASK_ID, 'production_required': False, 'read_only': True}))
            env = {'UAART_TASK_ID': c.TASK_ID, 'UAART_TASK_CLASS': 'STANDARD', 'UAART_REQUEST_PATH': c.REQUEST,
                   'UAART_REQUEST_SHA256': c.sha(request.read_bytes()), 'UAART_RUN_ID': '1',
                   'UAART_RECEIPT_PATH': c.RECEIPT}

            class Fake:
                def read(self, endpoint):
                    if endpoint.endswith('.json'):
                        return json.dumps(STATE).encode()
                    if endpoint.endswith('.py'):
                        return b'def rebuild_catalog():\n    return True, "ok"\n'
                    return b'CRM sync PASS: UA-0021\n'
            receipt = c.execute(env, root=root, api=Fake())
            evidence = json.loads((root / c.EVIDENCE).read_text())
        self.assertEqual(receipt['status'], 'FINISHED')
        self.assertEqual(evidence['sync_state']['retry']['26']['count'], 7)
        self.assertEqual(evidence['remote_write_count'], 0)


if __name__ == '__main__':
    unittest.main()

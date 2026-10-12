#!/usr/bin/env python3
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import controller as c  # noqa: E402

MODULE = ("def media_spool_worker_job(ctx):\n    token = 'abc'\n    return 'ждёт скачивания'\n"
          "def other():\n    return 1\n")
LOG = ('Oct 12 03:59:00 old media line\n'
       'Oct 12 04:24:08 INFO ua_crm_public_sync: CRM sync PASS: UA-0020\n'
       'Oct 12 04:25:00 INFO unrelated heartbeat\n'
       'Oct 12 04:26:00 WARNING media download http://x/y?id=SECRETX chat 380501234567\n')


class Fake:
    def server(self, path):
        return {c.HOME: json.dumps({'cars_ui.py': {'type': 'file'}, 'crm.db': {'type': 'file'}}).encode(),
                c.HOME + 'cars_ui.py': MODULE.encode(), c.LOG: LOG.encode()}.get(path)


class ProbeTests(unittest.TestCase):
    def test_scope(self):
        reader = c.Reader('test-value', opener=object())
        for bad in ('/home/Carix/crm.db', '/home/Carix/video/', '/var/log/other.log', '../x'):
            with self.assertRaises(c.ProbeError):
                reader.server(bad)

    def test_execute(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / c.REQUEST).parent.mkdir(parents=True)
            (root / c.REQUEST).write_text(json.dumps({'read_only': True, 'production_required': False}))
            env = {'UAART_TASK_ID': c.TASK_ID, 'UAART_RECEIPT_PATH': c.RECEIPT, 'UAART_REQUEST_PATH': c.REQUEST,
                   'UAART_REQUEST_SHA256': c.sha((root / c.REQUEST).read_bytes()), 'UAART_RUN_ID': '1'}
            c.execute(env, root=root, reader=Fake())
            raw = (root / c.EVIDENCE).read_text()
            excerpt = (root / c.EXCERPTS).read_text()
        evidence = json.loads(raw)
        self.assertIn('def media_spool_worker_job', excerpt)
        self.assertNotIn('def other', excerpt)
        self.assertNotIn("'abc'", excerpt)
        self.assertEqual(evidence['log']['matched'], 2)
        for secret in ('SECRETX', '380501234567'):
            self.assertNotIn(secret, raw)


if __name__ == '__main__':
    unittest.main()

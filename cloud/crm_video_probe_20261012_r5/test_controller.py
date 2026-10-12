#!/usr/bin/env python3
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import controller as c  # noqa: E402

MODULE = "def shag():\n    token = 'abc'\n    url = 'https://api.telegram.org/bot1/x'\n    return 1\n"


class Fake:
    def server(self, path):
        return {c.HOME + 'kadry_diagnostiki.py': MODULE.encode(),
                c.HOME + 'kadry_diagnostiki.log': b'UA-0020: downloaded 1 chat 380501234567\n'}.get(path)


class ProbeTests(unittest.TestCase):
    def test_scope(self):
        reader = c.Reader('test-value', opener=object())
        for bad in ('/home/Carix/crm.db', '/home/Carix/', '/home/Carix/cars_ui.py', '/var/log/x.log'):
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
        self.assertIn('def shag', excerpt)
        self.assertIn('return 1', excerpt)
        for secret in ("'abc'", 'api.telegram.org', '380501234567'):
            self.assertNotIn(secret, excerpt + raw)
        self.assertIsNone(evidence['module_sha256']['run_all.py'])
        self.assertEqual(list(evidence['downloader_logs']), ['kadry_diagnostiki.log'])


if __name__ == '__main__':
    unittest.main()

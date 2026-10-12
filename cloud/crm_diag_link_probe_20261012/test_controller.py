#!/usr/bin/env python3
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import controller as c  # noqa: E402

MODULE = ("def edit_ask(cid):\n    return 'Сейчас: —'\n"
          "def other():\n    return 1\n"
          "class Ui:\n    def route(self):\n        return 'car_wait'\n"
          "def main():\n    token = 'abc'\n    app.add_handler(MessageHandler(f, run_ai_draft))\n")


class Fake:
    def server(self, path):
        return {'': json.dumps({'cars_ui.py': {'type': 'file'}, 'crm.db': {'type': 'file'},
                                'video': {'type': 'directory'}}).encode(),
                'cars_ui.py': MODULE.encode()}.get(path)


class ProbeTests(unittest.TestCase):
    def test_scope(self):
        reader = c.Reader('test-value', opener=object())
        for bad in ('../x', 'crm.db', 'video/', '.env', 'Cars.py'):
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
            evidence = json.loads((root / c.EVIDENCE).read_text())
            excerpt = (root / c.EXCERPTS).read_text()
        self.assertIn('def edit_ask', excerpt)
        self.assertIn('def route', excerpt)
        self.assertIn('def main', excerpt)
        self.assertIn('MessageHandler', excerpt)
        self.assertNotIn('def other', excerpt)
        self.assertNotIn('token', excerpt)
        self.assertTrue(evidence['modules_scanned']['cars_ui.py']['match'])
        self.assertEqual(evidence['remote_write_count'], 0)


if __name__ == '__main__':
    unittest.main()

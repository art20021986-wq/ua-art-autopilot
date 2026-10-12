#!/usr/bin/env python3
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import controller as c  # noqa: E402


class SnapshotTests(unittest.TestCase):
    def test_saves_only_fixed_public_pages(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / c.REQUEST).parent.mkdir(parents=True)
            (root / c.REQUEST).write_text('{}')
            env = {'UAART_TASK_ID': c.TASK_ID, 'UAART_RECEIPT_PATH': c.RECEIPT, 'UAART_RUN_ID': '1',
                   'UAART_REQUEST_SHA256': c.sha(b'{}')}
            seen = []
            c.execute(env, root, lambda path: seen.append(path) or b'<html></html>')
            self.assertEqual(seen, list(c.PAGES))
            self.assertTrue((root / c.PACKAGE / 'UA-0017.html').exists())
            self.assertEqual(json.loads((root / c.RECEIPT).read_text())['status'], 'FINISHED')


if __name__ == '__main__':
    unittest.main()

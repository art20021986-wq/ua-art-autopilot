#!/usr/bin/env python3
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import controller as c  # noqa: E402


class ReloadTests(unittest.TestCase):
    TASK = 'WEBAPP-RELOAD-20261108'

    def env(self, root, production=False):
        request = root / 'tasks/requests' / (self.TASK + '.json')
        request.parent.mkdir(parents=True, exist_ok=True)
        request.write_text(json.dumps({'production_required': production}))
        return {'UAART_TASK_ID': self.TASK, 'UAART_RECEIPT_PATH': 'state/receipts/%s.json' % self.TASK,
                'UAART_REQUEST_PATH': 'tasks/requests/%s.json' % self.TASK,
                'UAART_REQUEST_SHA256': c.sha(request.read_bytes()), 'UAART_RUN_ID': '7'}

    def test_reload_then_live_script(self):
        calls = []
        states = iter([False, True])
        with tempfile.TemporaryDirectory() as temp:
            receipt = c.execute(self.env(Path(temp)), root=temp, do_reload=lambda t: calls.append(t) or 'HTTP_200',
                                wait=lambda *a: next(states))
        self.assertEqual((receipt['reload'], len(calls)), ('HTTP_200', 1))

    def test_already_live_skips_reload(self):
        with tempfile.TemporaryDirectory() as temp:
            receipt = c.execute(self.env(Path(temp)), root=temp, do_reload=lambda t: self.fail('reloaded'),
                                wait=lambda *a: True)
        self.assertEqual(receipt['reload'], 'SKIPPED_ALREADY_LIVE')

    def test_old_script_is_not_success(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(c.ReloadError, 'SCRIPT_NOT_LIVE'):
                c.execute(self.env(Path(temp)), root=temp, do_reload=lambda t: 'HTTP_200', wait=lambda *a: False)
            self.assertFalse((Path(temp) / 'state/receipts').exists())

    def test_production_request_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(c.ReloadError, 'SCOPE'):
                c.execute(self.env(Path(temp), True), root=temp, do_reload=lambda t: 'x', wait=lambda *a: True)

    def test_reload_posts_only_to_the_site_webapp(self):
        seen = []

        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def opener(request, timeout):
            seen.append((request.get_method(), request.full_url))
            return Response()
        with patch.object(c.urllib.request, 'urlopen', side_effect=opener):
            self.assertEqual(c.reload('token'), 'HTTP_200')
        self.assertEqual(seen, [('POST', c.RELOAD)])


if __name__ == '__main__':
    unittest.main()

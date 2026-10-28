#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('home_photo_probe', HERE / 'controller.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


class Response:
    status = 200

    def __init__(self, url, payload=b'x'):
        self.url, self.payload = url, payload

    def geturl(self):
        return self.url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size):
        value, self.payload = self.payload[:size], self.payload[size:]
        return value


class Opener:
    def __init__(self):
        self.calls = []

    def open(self, request, timeout):
        self.calls.append((request.get_method(), request.full_url, request.data))
        return Response(request.full_url)


def listing(**entries):
    return json.dumps({k: {'type': v, 'url': 'u'} for k, v in entries.items()}).encode()


class FakeServer:
    files = {
        'files/path/home/Carix/team_bot.py': b'import cars_ui\nTOKEN = "1"\ndef main():\n    cars_ui.register(app)\n',
        'files/path/home/Carix/cars_ui.py': (b'HIDE = {"a"}\nX = 1\ndef with_stats_button(m):\n    return m\n'
                                             b'def other():\n    return "private"\n'),
        'files/path/home/Carix/video/index.html': (b'<head><style id="ua-home-audi-001">x</style></head>'
                                                   b'<section class="hero ua-order-first"><picture>'
                                                   b'<img src="/video/order/audi_owner.jpg"></picture></section>'),
        'files/path/home/Carix/video/order/': listing(**{'audi_owner.jpg': 'file'}),
        'always_on/': json.dumps([{'id': 266084, 'enabled': True, 'state': 'running',
                                   'command': 'python3.10 /home/Carix/team_bot.py'}]).encode(),
        'files/path/usr/local/lib/': listing(**{'python3.10': 'directory', 'other': 'directory'}),
        'files/path/usr/local/lib/python3.10/': listing(**{'site-packages': 'directory', 'os.py': 'file'}),
        'files/path/usr/local/lib/python3.10/site-packages/': listing(
            PIL='directory', numpy='directory', requests='directory', **{'cv2': 'directory'}),
    }

    def __init__(self):
        self.calls = []

    def read(self, endpoint):
        self.calls.append(endpoint)
        if endpoint not in c.ENDPOINTS and not c.LISTING.match(endpoint):
            raise AssertionError('outside allowlist: ' + endpoint)
        if endpoint not in self.files:
            raise c.ProbeError('HTTP_404')
        return self.files[endpoint]


class ContractTests(unittest.TestCase):
    def test_get_only_allowlist(self):
        op = Opener()
        api = c.ReadOnlyAPI('test-value', opener=op)
        api.read('files/path/home/Carix/cars_ui.py')
        api.read('files/path/usr/local/lib/python3.10/site-packages/')
        self.assertEqual([m for m, _, _ in op.calls], ['GET', 'GET'])
        self.assertTrue(all(d is None for _, _, d in op.calls))
        for endpoint in ('files/path/home/Carix/.env', 'files/path/home/Carix/crm.db', '../x',
                         'files/path/usr/local/lib/python3.10/site-packages/PIL/', 'consoles/',
                         'files/path/home/Carix/.local/lib/../../crm.db', 'https://evil.invalid/'):
            with self.assertRaises(c.ProbeError):
                api.read(endpoint)
        self.assertEqual(len(op.calls), 2)

    def test_source_selection_and_secret_skip(self):
        raw = (b'HIDE = {"x"}\nY = 2\ndef other():\n    return "private"\n'
               b'def with_stats_button(m):\n    return m\ndef leak():\n    token = "abc"\n    return with_stats_button(1)\n')
        facts, excerpt = c.inspect_source(raw, '/home/Carix/cars_ui.py')
        self.assertIn('def with_stats_button', excerpt)
        self.assertIn('HIDE', excerpt)
        self.assertNotIn('private', excerpt)
        self.assertNotIn('Y = 2', excerpt)
        self.assertNotIn('abc', excerpt)
        self.assertEqual([d['excerpt'] for d in facts['definitions']], ['EXPORTED', 'EXPORTED', 'OMITTED_SENSITIVE'])
        facts, excerpt = c.inspect_source(b'import x\nTOKEN = "12345:abc"\napp.add_handler(h)\n', c.TEAM_BOT)
        self.assertIn('import x', excerpt)
        self.assertIn('app.add_handler(h)', excerpt)
        self.assertNotIn('12345', excerpt)

    def test_execute_collects_facts_without_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            request = root / c.REQUEST
            request.parent.mkdir(parents=True)
            request.write_text(json.dumps({'task_id': c.TASK_ID, 'production_required': False, 'read_only': True}))
            env = {'UAART_TASK_ID': c.TASK_ID, 'UAART_TASK_CLASS': 'STANDARD', 'UAART_REQUEST_PATH': c.REQUEST,
                   'UAART_REQUEST_SHA256': c.sha(request.read_bytes()), 'UAART_RUN_ID': '1',
                   'UAART_RECEIPT_PATH': c.RECEIPT}
            server = FakeServer()
            receipt = c.execute(env, root=root, api=server)
            evidence = json.loads((root / c.EVIDENCE).read_text())
            excerpt = (root / c.EXCERPTS).read_text()
            self.assertEqual(evidence['remote_write_count'], 0)
            self.assertEqual(evidence['packages'], {'/usr/local/lib/python3.10/site-packages/': ['PIL', 'cv2', 'numpy']})
            self.assertEqual(evidence['home']['hero_count'], 1)
            self.assertEqual(evidence['home']['style_ids'], ['ua-home-audi-001'])
            self.assertEqual(evidence['always_on'][0]['command'], 'python3.10 /home/Carix/team_bot.py')
            self.assertEqual(receipt['unavailable_endpoints'], ['files/path/home/Carix/crm_photo_intake.py'])
            self.assertNotIn('TOKEN', excerpt)
            self.assertNotIn('private', excerpt)
            self.assertNotIn('files/path/usr/local/lib/other/', server.calls)
            with self.assertRaises(c.ProbeError):
                c.execute(env, root=root, api=FakeServer())

    def test_identity_mismatch_refused(self):
        with self.assertRaises(c.ProbeError):
            c.execute({'UAART_TASK_ID': 'OTHER'}, root='/nonexistent', api=object())


if __name__ == '__main__':
    unittest.main()

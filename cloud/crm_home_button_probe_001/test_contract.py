#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('crm_home_button_probe', HERE / 'controller.py')
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


H = 'files/path/home/Carix/'


class FakeServer:
    files = {
        H: listing(**{'team_bot.py': 'file', 'cars_ui.py': 'file', 'ua_x.py': 'file', 'lead_bot.py': 'file',
                      'crm.db': 'file', 'video': 'directory'}),
        H + 'team_bot.py': (b'import cars_ui\nTOKEN = "1"\nasync def post_init(a):\n'
                            b'    await a.bot.set_my_commands([BotCommand("start", "Menu")])\n'
                            b'app.add_handler(CommandHandler("start", start))\n'),
        H + 'cars_ui.py': (b'import os\ndef register(app):\n    import ua_x\n    ua_x.register(app)\n'
                           b'def other():\n    return "private"\n'),
        H + 'ua_x.py': b'def kb():\n    return ReplyKeyboardRemove()\ndef hidden():\n    return "private2"\n',
        H + 'lead_bot.py': b'def kb():\n    return ReplyKeyboardMarkup([])\n',
    }

    def __init__(self):
        self.calls = []

    def read(self, endpoint):
        self.calls.append(endpoint)
        if not c.allowed(endpoint):
            raise AssertionError('outside allowlist: ' + endpoint)
        if endpoint not in self.files:
            raise c.ProbeError('HTTP_404')
        return self.files[endpoint]


class ContractTests(unittest.TestCase):
    def test_get_only_allowlist(self):
        op = Opener()
        api = c.ReadOnlyAPI('test-value', opener=op)
        api.read(H + 'cars_ui.py')
        self.assertEqual([m for m, _, _ in op.calls], ['GET'])
        self.assertTrue(all(d is None for _, _, d in op.calls))
        for endpoint in (H + '.env', H + 'crm.db', H + '../x.py', H + 'video/index.html', 'consoles/',
                         H + 'anthropic_key.txt', H + 'sub/x.py', 'always_on/', 'https://evil.invalid/'):
            with self.assertRaises(c.ProbeError):
                api.read(endpoint)
        self.assertEqual(len(op.calls), 1)

    def test_execute_follows_imports_and_exports_only_markers(self):
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
            self.assertEqual(receipt['modules_read'], 3)
            self.assertEqual(sorted(evidence['source_facts']), ['cars_ui.py', 'team_bot.py', 'ua_x.py'])
            self.assertNotIn(H + 'lead_bot.py', server.calls)
            self.assertEqual(evidence['totals']['reply_keyboard_remove'], 1)
            self.assertEqual(evidence['totals']['set_my_commands'], 1)
            self.assertEqual(evidence['totals']['start_command_handler'], 1)
            self.assertIn('set_my_commands', excerpt)
            self.assertIn('def register', excerpt)
            self.assertIn('ReplyKeyboardRemove', excerpt)
            self.assertNotIn('TOKEN', excerpt)
            self.assertNotIn('private', excerpt)
            with self.assertRaises(c.ProbeError):
                c.execute(env, root=root, api=FakeServer())

    def test_identity_mismatch_refused(self):
        with self.assertRaises(c.ProbeError):
            c.execute({'UAART_TASK_ID': 'OTHER'}, root='/nonexistent', api=object())


if __name__ == '__main__':
    unittest.main()

#!/usr/bin/env python3
import base64
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import probe as p  # noqa: E402

HOME = (b'<html><link rel="stylesheet" href="ua.css?v=1"><img src="/video/a.webp"><script src="m.js"></script>'
        b'<source srcset="/video/b.webp 1x, /video/c.webp 2x"><a href="https://evil.example/x.js">x</a>'
        b'<a href="katalog.html">k</a></html>')
FILES = {p.HOME: HOME, 'https://www.uaart.com.ua/video/ua.css?v=1': b'.a{background:url("img/d.png")}',
         'https://www.uaart.com.ua/video/a.webp': b'A', 'https://www.uaart.com.ua/video/b.webp': b'B',
         'https://www.uaart.com.ua/video/c.webp': b'C', 'https://www.uaart.com.ua/video/img/d.png': b'D',
         'https://www.uaart.com.ua/video/m.js': b'fetch("order/models.json");import {x} from "./p.js?v=1"',
         'https://www.uaart.com.ua/video/order/models.json': b'{}',
         'https://www.uaart.com.ua/video/p.js?v=1': b'export const x=1'}


def fake(url):
    if not url.startswith(p.ORIGIN + '/'):
        raise AssertionError('outside scope: ' + url)
    return (200, 'x', FILES[url]) if url in FILES else (404, None, b'')


class ProbeTests(unittest.TestCase):
    def test_scope(self):
        with self.assertRaises(p.ProbeError):
            p.get('https://evil.example/')

    def test_collect(self):
        files = p.collect(fake)['files']
        self.assertEqual(set(files), set(FILES))
        self.assertEqual(base64.b64decode(files['https://www.uaart.com.ua/video/img/d.png']['b64']), b'D')

    def test_execute(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            task = p.TASKS[0]
            request = root/'tasks/requests'/(task+'.json')
            request.parent.mkdir(parents=True)
            request.write_text(json.dumps({'read_only': True, 'production_required': False}))
            env = {'UAART_TASK_ID': task, 'UAART_RECEIPT_PATH': 'state/receipts/%s.json' % task,
                   'UAART_REQUEST_PATH': 'tasks/requests/%s.json' % task,
                   'UAART_REQUEST_SHA256': p.sha(request.read_bytes()), 'UAART_RUN_ID': '1'}
            receipt = p.execute(env, root=root, fetch=fake)
            evidence = json.loads((root/receipt['evidence_path']).read_text())
        self.assertEqual(evidence['remote_write_count'], 0)
        self.assertEqual(len(evidence['files']), len(FILES))


if __name__ == '__main__':
    unittest.main()

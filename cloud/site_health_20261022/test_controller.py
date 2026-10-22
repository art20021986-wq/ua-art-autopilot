#!/usr/bin/env python3
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import controller as c  # noqa: E402

ACCESS = '1.2.3.4 - - [22/Oct/2026:13:00:00 +0000] "GET /video/katalog.html HTTP/1.1" 502 10 "-" "x"\n'
ERROR = '2026-10-22 13:00:01,1 Error running WSGI application from 1.2.3.4\n'


class Fake:
    def api(self, endpoint):
        body = {c.LOGS['access']: ACCESS, c.LOGS['error']: ERROR, 'cpu/': '{"daily_cpu_total_usage_seconds": 5}',
                'always_on/': '[{"id": 266084, "enabled": true, "state": "running", "command": "python3.10 start_safe.py", "x": 1}]',
                c.ENDPOINTS[0]: '{"enabled": true, "expiry": null}',
                c.HISTORY['publication_log']: '2026-10-22 12:59:08  FAIL  x\n',
                c.WEBAPP_DIR: '{"flask_app.py": {}, "notes.txt": {}}',
                c.WEBAPP_DIR + 'flask_app.py': 'import stranica\nTOKEN = "x"  # stranica token\nstranica.main()\n'}.get(endpoint)
        return {'http': 200 if body else 404, 'body': (body or '').encode()}

    def public(self, url):
        if url.startswith('http://'):
            return {'http': 301, 'body': b'', 'location': 'https://www.uaart.com.ua/'}
        return {'http': 200, 'body': b'<title>UA ART</title>' + b'x' * 600, 'type': 'text/html'}


class ProbeTests(unittest.TestCase):
    def test_scope(self):
        reader = c.Reader('t', opener=object())
        for bad in ('files/path/home/Carix/crm.db', 'consoles/', 'always_on/266084/', c.WEBAPP_DIR + '../db.py',
                    c.WEBAPP_DIR + 'x.txt'):
            with self.assertRaises(c.ProbeError):
                reader.api(bad)
        with self.assertRaises(c.ProbeError):
            reader.public('https://evil.example/')

    def test_execute(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            task = c.TASKS[2]
            request = root/'tasks/requests'/(task+'.json')
            request.parent.mkdir(parents=True)
            request.write_text(json.dumps({'read_only': True, 'production_required': False}))
            env = {'UAART_TASK_ID': task, 'UAART_RECEIPT_PATH': 'state/receipts/%s.json' % task,
                   'UAART_REQUEST_PATH': 'tasks/requests/%s.json' % task,
                   'UAART_REQUEST_SHA256': c.sha(request.read_bytes()), 'UAART_RUN_ID': '1'}
            receipt = c.execute(env, root=root, reader=Fake())
            raw = (root/receipt['evidence_path']).read_text()
        evidence = json.loads(raw)
        self.assertNotIn('1.2.3.4', raw)
        self.assertEqual(evidence['access_log']['hours']['22/Oct/2026 13'], {'5xx': 1, '5xx /video/katalog.html': 1})
        self.assertEqual(evidence['error_log']['per_hour'], {'2026-10-22 13': 1})
        self.assertEqual(evidence['always_on'][0]['state'], 'running')
        self.assertNotIn('x', evidence['always_on'][0])
        self.assertEqual(evidence['public']['http://uaart.com.ua/']['location'], 'https://www.uaart.com.ua/')
        self.assertEqual(evidence['public']['https://www.uaart.com.ua/']['title'], 'UA ART')
        self.assertEqual(evidence['server_log']['http'], 404)
        calls = evidence['history']['webapp_sources']['calls']['flask_app.py']
        self.assertEqual(calls, ['1: import stranica', '3: stranica.main()'])
        self.assertEqual(evidence['history']['publication_log']['last'], ['2026-10-22 12:59:08  FAIL  x'])


if __name__ == '__main__':
    unittest.main()

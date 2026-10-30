#!/usr/bin/env python3
import gzip
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import controller as c  # noqa: E402

LOG = ('1.2.3.4 - - [28/Oct/2026:10:00:00 +0000] "GET /video/../crm.db HTTP/1.1" 404 12 "-" '
       '"meta-externalagent/1.1" "-" response-time=0.1\n'
       '1.2.3.5 - - [28/Oct/2026:10:00:01 +0000] "GET /video/index.html HTTP/1.1" 200 10 "-" "Mozilla" "-"\n'
       '1.2.3.6 - - [29/Oct/2026:10:00:02 +0000] "GET /crm.db HTTP/1.1" 200 4096 "-" "curl/8" "-"\n'
       'garbage\n')
OLD = '1.2.3.7 - - [20/Oct/2026:10:00:00 +0000] "GET /admin HTTP/1.1" 404 5 "-" "Mozilla" "-"\n'


class Fake:
    def __init__(self):
        self.calls = []

    def api(self, endpoint):
        self.calls.append(endpoint)
        files = {c.LOG: LOG.encode(), c.LOG + '.1': OLD.encode(), c.LOG + '.2.gz': gzip.compress(b'')}
        return (200, files[endpoint]) if endpoint in files else (404, None)

    def public(self, path):
        return {'http': 404, 'bytes': 9, 'content_type': 'text/html', 'sqlite_header': False}


class ProbeTests(unittest.TestCase):
    def test_scope(self):
        reader = c.Reader('test-value', opener=object(), public_opener=object())
        for bad in ('files/path/home/Carix/crm.db', 'webapps/', 'always_on/'):
            with self.assertRaises(c.ProbeError):
                reader.api(bad)
        with self.assertRaises(c.ProbeError):
            reader.public('/video/UA-0018.html')

    def test_body_is_never_kept(self):
        class Opener:
            def open(self, request, timeout):
                class Response:
                    status = 200
                    headers = {'Content-Type': 'application/octet-stream'}
                    def read(self, limit):
                        return b'SQLite format 3\x00secret rows'
                    def __enter__(self):
                        return self
                    def __exit__(self, *exc):
                        return False
                return Response()
        value = c.Reader('test-value', opener=object(), public_opener=Opener()).public('/crm.db')
        self.assertEqual(value, {'http': 200, 'bytes': 27, 'content_type': 'application/octet-stream', 'sqlite_header': True})

    def test_execute(self):
        fake = Fake()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            task = 'SECURITY-PATH-PROBE-20261031'
            request = root / 'tasks/requests' / (task + '.json')
            request.parent.mkdir(parents=True)
            request.write_text(json.dumps({'read_only': True, 'production_required': False}))
            env = {'UAART_TASK_ID': task, 'UAART_RECEIPT_PATH': 'state/receipts/%s.json' % task,
                   'UAART_REQUEST_PATH': 'tasks/requests/%s.json' % task,
                   'UAART_REQUEST_SHA256': c.sha(request.read_bytes()), 'UAART_RUN_ID': '1'}
            receipt = c.execute(env, root=root, reader=fake)
            raw = (root / receipt['evidence_path']).read_text()
        evidence = json.loads(raw)
        self.assertNotIn('1.2.3.', raw)
        self.assertEqual(evidence['suspect_count'], 3)
        self.assertEqual([h['client'] for h in evidence['suspect_requests']], ['meta-externalagent', 'curl', 'other'])
        self.assertEqual(evidence['database_served'][0]['path'], '/crm.db')
        self.assertEqual(sorted(evidence['public']), sorted(c.PUBLIC))


if __name__ == '__main__':
    unittest.main()

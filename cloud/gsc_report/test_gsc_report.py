#!/usr/bin/env python3
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import controller as c  # noqa: E402
import gsc_remote as remote  # noqa: E402
import transport  # noqa: E402


class FakeAPI:
    def __init__(self, report):
        self.report, self.calls = report, []

    def run(self, mode, run_id, bundle):
        self.calls.append((mode, run_id, bundle))
        return self.report


class ControllerTests(unittest.TestCase):
    TASK = 'GSC-REPORT-20261027'

    def env(self, root):
        request = root / 'tasks/requests' / (self.TASK + '.json')
        request.parent.mkdir(parents=True)
        request.write_text(json.dumps({'read_only': False, 'production_required': False}))
        return {'UAART_TASK_ID': self.TASK, 'UAART_RECEIPT_PATH': 'state/receipts/%s.json' % self.TASK,
                'UAART_REQUEST_PATH': 'tasks/requests/%s.json' % self.TASK,
                'UAART_REQUEST_SHA256': c.sha(request.read_bytes()), 'UAART_RUN_ID': '7'}

    def test_report_saved(self):
        api = FakeAPI({'status': 'PASS', 'permission': 'siteFullUser', 'run_id': '7'})
        with tempfile.TemporaryDirectory() as temp:
            receipt = c.execute(self.env(Path(temp)), root=temp, api=api, upload=lambda a: 'b' * 64)
            evidence = json.loads((Path(temp) / receipt['evidence_path']).read_text())
        self.assertEqual(api.calls, [('probe', '7', 'b' * 64)])
        self.assertEqual((receipt['gsc_status'], evidence['permission']), ('PASS', 'siteFullUser'))
        self.assertEqual(receipt['evidence_path'], 'cloud/gsc_report/20261027.json')

    def test_key_material_never_saved(self):
        api = FakeAPI({'status': 'PASS', 'leak': '"private_key": "-----BEGIN PRIVATE KEY-----"'})
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(c.ProbeError, 'KEY_MATERIAL'):
                c.execute(self.env(Path(temp)), root=temp, api=api, upload=lambda a: 'b' * 64)

    def test_wrong_task_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            env = dict(self.env(Path(temp)), UAART_TASK_ID='OTHER')
            with self.assertRaisesRegex(c.ProbeError, 'IDENTITY'):
                c.execute(env, root=temp, api=FakeAPI({}), upload=lambda a: 'b' * 64)


class TransportTests(unittest.TestCase):
    def test_only_probe_mode_and_never_the_bot(self):
        api = transport.API('test-token')
        for args in (('install', '1', 'a' * 64), ('probe', 'x', 'a' * 64), ('probe', '1', 'short')):
            with self.assertRaises(transport.TransportError):
                api.run(*args)
        with patch.object(api, 'file', return_value=None), \
             patch.object(api, 'json', return_value={'id': transport.BOT_ID}):
            with self.assertRaisesRegex(transport.TransportError, 'TRIGGER_IDENTITY'):
                api.run('probe', '1', 'a' * 64)


class RemoteTests(unittest.TestCase):
    def test_missing_key_lists_candidates_only(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            (home / 'uaart-autopilot-other').write_text('{"private_key": "x"}')
            with patch.object(remote, 'HOME', home), patch.object(remote, 'KEYS', (home / 'absent.json',)):
                value = remote.report()
        self.assertEqual(value, {'status': 'FAIL', 'error': 'KEY_MISSING', 'candidates': ['uaart-autopilot-other']})

    def test_report_shapes_api_answers(self):
        def call(bearer, url, body=None):
            if url.endswith('/sites'):
                return 200, {'siteEntry': [{'siteUrl': remote.SITE, 'permissionLevel': 'siteFullUser'}]}
            if url.endswith('/sitemaps'):
                return 200, {'sitemap': [{'path': remote.SITE + 'sitemap.xml', 'errors': '0', 'extra': 1}]}
            if url.endswith('/searchAnalytics/query'):
                return 200, {'rows': [{'keys': ['авто из кореи'], 'clicks': 1, 'impressions': 9, 'position': 8.44}]}
            return 200, {'inspectionResult': {'indexStatusResult': {'verdict': 'PASS', 'coverageState': 'Indexed'}}}
        with tempfile.TemporaryDirectory() as temp:
            key = Path(temp) / 'uaart-autopilot-110fb4d36d23'
            key.write_text('{}')
            sitemap = Path(temp) / 'sitemap.xml'
            sitemap.write_text(''.join('<url><loc>%svideo/UA-00%02d.html</loc></url>' % (remote.SITE, i) for i in range(1, 100)))
            with patch.object(remote, 'SITEMAP', sitemap), patch.object(remote, 'KEYS', (Path(temp) / 'absent.json', key)), patch.object(remote, 'token', return_value=('sa@x', 't')), \
                 patch.object(remote, 'call', side_effect=call):
                value = remote.report()
        self.assertEqual((value['status'], value['permission'], value['service_account']), ('PASS', 'siteFullUser', 'sa@x'))
        self.assertEqual(value['queries']['rows'][0], {'key': 'авто из кореи', 'clicks': 1, 'impressions': 9, 'position': 8.4})
        self.assertEqual(value['dates']['rows'][0]['impressions'], 9)
        self.assertNotIn('extra', value['sitemaps']['entries'][0])
        self.assertEqual(value['inspection']['video/UA-0018.html']['coverageState'], 'Indexed')
        self.assertEqual(len(value['inspection']), remote.MAX_PAGES)


if __name__ == '__main__':
    unittest.main()

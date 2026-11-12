#!/usr/bin/env python3
import json
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import controller as c  # noqa: E402
import source_remote as remote  # noqa: E402
import transport  # noqa: E402


class FakeAPI:
    def __init__(self, report):
        self.report = report

    def run(self, mode, run_id, bundle):
        return self.report

    def json(self, method, endpoint):
        return [{'id': 1576351, 'command': 'python3.10 /home/Carix/korea_ticker_job.py', 'enabled': False, 'secret': 'x'},
                {'id': 2, 'command': 'other.py'}]


class ControllerTests(unittest.TestCase):
    TASK = 'SOCIAL-PROBE-20261105'

    def env(self, root):
        request = root / 'tasks/requests' / (self.TASK + '.json')
        request.parent.mkdir(parents=True)
        request.write_text(json.dumps({'production_required': False}))
        return {'UAART_TASK_ID': self.TASK, 'UAART_RECEIPT_PATH': 'state/receipts/%s.json' % self.TASK,
                'UAART_REQUEST_PATH': 'tasks/requests/%s.json' % self.TASK,
                'UAART_REQUEST_SHA256': c.sha(request.read_bytes()), 'UAART_RUN_ID': '7'}

    def test_report_saved(self):
        with tempfile.TemporaryDirectory() as temp:
            receipt = c.execute(self.env(Path(temp)), root=temp, api=FakeAPI({'status': 'PASS'}), upload=lambda a: 'b' * 64)
        self.assertEqual((receipt['probe_status'], receipt['evidence_path']),
                         ('PASS', 'cloud/social_probe_001/20261105.json'))

    def test_key_material_never_saved(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(c.ProbeError, 'KEY_MATERIAL'):
                c.execute(ControllerTests.env(ControllerTests(), Path(temp)), root=temp, api=FakeAPI({'x': '-----BEGIN PRIVATE KEY'}),
                          upload=lambda a: 'b' * 64)


class TransportTests(unittest.TestCase):
    def test_never_the_bot(self):
        api = transport.API('test-token')
        with patch.object(api, 'file', return_value=None), \
             patch.object(api, 'json', return_value={'id': transport.BOT_ID}):
            with self.assertRaisesRegex(transport.TransportError, 'TRIGGER_IDENTITY'):
                api.run('probe', '1', 'a' * 64)

    def test_own_server_prefix(self):
        self.assertIn('diagprobe-', Path(transport.__file__).read_text())
        self.assertNotIn('crmprobe', Path(transport.__file__).read_text())

    def test_bundle_names_pass_bootstrap_filter(self):
        for path in Path(__file__).resolve().parent.glob('*.py'):
            self.assertRegex(path.name, re.compile(r'[a-z_]+\.py'))


class RemoteTests(unittest.TestCase):
    def test_sources_callers_footers(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            (home / 'video/ua').mkdir(parents=True)
            (home / 'site_ge_inject.py').write_text("TOKEN = 'abc'\ndef inject_html(s):\n    return s\n")
            (home / 'writer.py').write_text("from site_ge_inject import inject_html\nx = '</footer>'\n")
            (home / 'video/index.html').write_text('<body><main>x</main><footer class="site-footer">'
                                                   '<a href="https://evil.example/x">a</a> +380 99 222 20 02</footer></body>')
            (home / 'video/ua/UA-0001.html').write_text('<body>' + 'x' * 3000 + '<p>end</p></body>')
            value = remote.report(home)
        self.assertEqual(value['sources']['site_ge_inject.py']['source'].splitlines()[0], '[REDACTED]')
        self.assertIsNone(value['sources']['ua_seo_index.py'])
        self.assertEqual(sorted(value['callers']), ['site_ge_inject.py', 'writer.py'])
        end = value['footers']['video/index.html']['end']
        self.assertTrue(value['footers']['video/index.html']['has_footer'])
        self.assertIn('[URL]', end)
        self.assertIn('[N]', end)
        self.assertNotIn('evil', end)
        card = value['footers']['video/ua/UA-0001.html']
        self.assertFalse(card['has_footer'])
        self.assertTrue(card['end'].endswith('<p>end</p></body>'))
        self.assertIsNone(value['footers']['video/info.html'])
        self.assertEqual(value['counts']['video/ua'], 1)

    def test_r2_rows(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            (home / 'video/ua').mkdir(parents=True)
            (home / 'video/UA-0001.html').write_text('<body>x<!--UA-SOCIAL-V1--></body>')
            (home / 'video/UA-0002.html').write_text('<body>x</body>')
            (home / 'video/UA-0001-diag.html').write_text('<!--UA-SOCIAL-V1--><!--UA-SOCIAL-V1-->')
            (home / 'video/index.html').write_text('<!--UA-SOCIAL-V1-->')
            (home / 'video/ua/UA-0001.html').write_text('<!--UA-SOCIAL-V1-->')
            rows = remote.report_r2(home)['rows']
        self.assertEqual((rows['cards']['pages'], rows['cards']['with_row'], rows['cards']['missing']), (2, 1, ['UA-0002.html']))
        self.assertEqual(rows['diag']['double'], ['UA-0001-diag.html'])
        self.assertEqual((rows['top']['pages'], rows['top']['with_row']), (1, 1))
        self.assertEqual(rows['cards_ua']['with_row'], 1)
        self.assertEqual(rows['cards_ru']['pages'], 0)


    def test_r3_hosts_and_sync(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            (home / 'video').mkdir()
            (home / 'ua_additional_spec.py').write_text('_UA115_APPROVED_HOSTS = {"t.me", "schema.org"}\n')
            (home / '.crm_public_sync_state.json').write_text(json.dumps({'version': 1, 'last_success': {'code': 'UA-0001', 'at': 5},
                'retry': {'7': {'sha256': 'x', 'count': 3, 'error': 'UA115:www.tiktok.com +380 99 222 20 02'}}}))
            (home / 'video/UA-0001.html').write_text('<body></body>')
            value = remote.report_r3(home)
        self.assertEqual(value['approved_hosts'], ['schema.org', 't.me'])
        self.assertEqual(value['sync']['retry']['7']['count'], 3)
        self.assertNotIn('222 20 02', value['sync']['retry']['7']['error'])
        self.assertIn('UA-0001.html', value['times']['video'])


    def test_r4_versions(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            (home / 'video/ua').mkdir(parents=True)
            (home / 'video/ru').mkdir()
            (home / 'video/katalog.html').write_text('<a href="ua/UA-0001.html">a</a><a href="ua/UA-0022.html">b</a><a href="UA-0003.html">c</a>')
            (home / 'video/ua/UA-0022.html').write_text('x')
            (home / 'video/UA-0003.html').write_text('x')
            (home / 'video/sitemap.xml').write_text('<loc>https://www.uaart.com.ua/video/ua/UA-0022.html</loc><loc>https://www.uaart.com.ua/video/index.html</loc>')
            value = remote.report_r4(home)
        self.assertEqual(value['catalog_links']['ua/'], ['ua/UA-0001.html', 'ua/UA-0022.html'])
        self.assertEqual(value['catalog_links_broken'], ['ua/UA-0001.html'])
        self.assertEqual(value['versions'], {'ua': ['UA-0022.html'], 'ru': []})
        self.assertEqual(value['sitemap']['card_urls'], {'/video/ua/': 1})


    def test_r5_combines(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            (home / 'video/ua').mkdir(parents=True)
            (home / 'video/katalog.html').write_text('<a href="ua/UA-0001.html">a</a>')
            (home / 'video/ua/UA-0001.html').write_text('<!--UA-SOCIAL-V1-->')
            value = remote.report_r5(home)
        self.assertEqual(value['rows']['cards_ua']['with_row'], 1)
        self.assertEqual(value['catalog_links_broken'], [])
        self.assertEqual(value['versions']['ua'], ['UA-0001.html'])


    def test_r6_ticker(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            (home / 'video/korea').mkdir(parents=True)
            (home / 'korea_auction').mkdir()
            (home / 'korea_auction_data').mkdir()
            (home / 'video/korea/ticker.html').write_text('<div class="kt-x"></div>')
            (home / 'korea_auction/ticker.py').write_text("X = 'kt-legend'")
            (home / 'jpauto_login.txt').write_text('a@b.c\nsecret\n')
            (home / 'korea_ticker_job.py').write_text('password = "x"\nimport korea_auction.job\n')
            value = remote.report_r6(home)
        self.assertEqual(value['ticker_html']['kt_legend'], 0)
        self.assertEqual(value['package']['ticker.py']['kt_legend'], 1)
        self.assertEqual(value['login_lines'], 2)
        self.assertNotIn('secret', json.dumps(value))
        self.assertEqual(value['job_script'].splitlines()[0], '[REDACTED]')


    def test_schedule_kept_korea_only(self):
        with tempfile.TemporaryDirectory() as temp:
            c.execute(ControllerTests.env(ControllerTests(), Path(temp)), root=temp, api=FakeAPI({'status': 'PASS'}), upload=lambda a: 'b' * 64)
            saved = json.loads((Path(temp) / 'cloud/social_probe_001/20261105.json').read_text())
        self.assertEqual(saved['schedule'], [{'id': 1576351, 'command': 'python3.10 /home/Carix/korea_ticker_job.py',
                                              'enabled': False, 'interval': None, 'hour': None, 'minute': None,
                                              'expiry': None, 'can_enable': None, 'logfile': None, 'description': None}])


if __name__ == '__main__':
    unittest.main()

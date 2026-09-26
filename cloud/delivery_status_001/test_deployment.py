"""Recovery rehearsal against temporary files and a temporary CRM database."""
from contextlib import nullcontext
from io import BytesIO
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
import urllib.error
import urllib.parse
from unittest.mock import patch
from types import SimpleNamespace

import deployment_controller as controller
import deployment_remote as remote
from deployment_transport import canonical, sha
from deployment_transport import API, BOT_ID, BOT_COMMAND, TransportError


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.saved = self.root/'backup'
        self.saved.mkdir()
        self.root_patch = patch.object(remote, 'ROOT', self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        with sqlite3.connect(self.root/'crm.db') as connection:
            connection.execute('CREATE TABLE cars(id INTEGER PRIMARY KEY, status TEXT, vin TEXT, price INTEGER)')
            connection.execute("INSERT INTO cars VALUES(1,'archive','VIN-PRESERVED',12345)")
        (self.root/'protected.html').write_bytes(b'original photos and VIN')
        self.plan = {'files': {}, 'protected': {'protected.html': sha(b'original photos and VIN')},
                     'crm_sha256': remote.row_digest(remote.crm_rows()), 'counts': {'all': 0}}
        for name, before, after in [('ua_delivery_status.py', None, b'policy'),
                                    ('db.py', b'original', b'candidate')]:
            self.plan['files'][name] = {'before': sha(before) if before else None,
                                       'after': sha(after), 'mode': 0o644}
            if before:
                remote.atomic(self.root/name, before)
                remote.atomic(self.saved/'before'/name, before)
            remote.atomic(self.saved/'after'/name, after)
        self.plan_sha = sha(canonical(self.plan))
        self.manifest = {'plan': self.plan, 'plan_sha256': self.plan_sha}
        self.events = []
        outer = self
        class FakeAPI:
            enabled = True
            def __init__(self, token):
                pass
            def bot(self):
                return {'enabled': self.enabled, 'state': 'running' if self.enabled else 'stopped'}
            def set_bot(self, enabled):
                self.enabled = enabled
                outer.events.append(enabled)
                return self.bot()
        self.api = FakeAPI

    def lifecycle(self, mode):
        with patch.object(remote, 'API', self.api), \
             patch.object(remote, 'load_backup', return_value=(self.saved, self.manifest)), \
             patch.object(remote, 'writer_exclusion', side_effect=nullcontext), \
             patch.object(remote, 'no_bot_processes'):
            return remote.lifecycle(mode, '123', self.plan_sha, 'a'*64)

    def test_install_and_real_file_rollback(self):
        result = self.lifecycle('install')
        self.assertTrue(result['installed'])
        remote.verify_files(self.plan, True)
        result = self.lifecycle('rollback')
        self.assertTrue(result['restored'])
        self.assertTrue(result['crm_unchanged'])
        remote.verify_files(self.plan, False)
        self.assertEqual(self.events, [False, True, False, True])

    def test_interrupted_install_restores_and_resumes(self):
        remote.atomic(self.root/'ua_delivery_status.py', b'policy')
        remote.atomic(self.saved/'journal-install.json', canonical({
            'stage': 'APPLYING', 'mode': 'install', 'backup_sha256': 'a'*64}))
        result = self.lifecycle('install')
        self.assertEqual(result['status'], 'FAIL')
        self.assertTrue(result['restored'])
        self.assertTrue(result['crm_resume']['enabled'])
        remote.verify_files(self.plan, False)

    def test_finished_install_retry_only_resumes(self):
        self.lifecycle('install')
        self.events.clear()
        result = self.lifecycle('install')
        self.assertTrue(result['installed'])
        self.assertEqual(self.events, [True])
        remote.verify_files(self.plan, True)

    def test_drift_before_install_resumes_without_changes(self):
        (self.root/'db.py').write_bytes(b'other editor')
        result = self.lifecycle('install')
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual((self.root/'db.py').read_bytes(), b'other editor')
        self.assertFalse((self.root/'ua_delivery_status.py').exists())
        self.assertTrue(result['crm_resume']['enabled'])

    def test_rollback_refuses_concurrent_file_edit(self):
        self.lifecycle('install')
        (self.root/'db.py').write_bytes(b'other editor')
        with self.assertRaisesRegex(remote.DeploymentError, 'ROLLBACK_CONCURRENT_CHANGE'):
            remote.restore(self.saved, self.plan)
        self.assertEqual((self.root/'ua_delivery_status.py').read_bytes(), b'policy')

    def test_rollback_preserves_concurrent_crm_edit(self):
        self.lifecycle('install')
        with sqlite3.connect(self.root/'crm.db') as connection:
            connection.execute('UPDATE cars SET price=99999 WHERE id=1')
        with self.assertRaisesRegex(remote.DeploymentError, 'CRM_CHANGED'):
            remote.restore(self.saved, self.plan)
        self.assertEqual(remote.crm_rows()[0]['price'], 99999)
        self.assertEqual((self.root/'db.py').read_bytes(), b'candidate')

    def test_rollback_preserves_protected_files(self):
        self.lifecycle('install')
        (self.root/'protected.html').write_bytes(b'legitimate new photo')
        with self.assertRaisesRegex(remote.DeploymentError, 'PROTECTED_CHANGED'):
            remote.restore(self.saved, self.plan)
        self.assertEqual((self.root/'protected.html').read_bytes(), b'legitimate new photo')

    def test_atomic_write_rejects_symlink_on_read(self):
        (self.root/'alias.py').symlink_to(self.root/'db.py')
        with self.assertRaises(remote.DeploymentError):
            remote.read(self.root/'alias.py')


class TransportTests(unittest.TestCase):
    def test_resume_does_not_reset_an_already_starting_bot(self):
        api = API('test-token')
        with patch.object(api, 'bot', side_effect=[
            {'enabled': True, 'state': 'Starting'},
            {'enabled': True, 'state': 'Running'},
        ]), patch.object(api, 'json') as mutate:
            self.assertTrue(api.set_bot(True)['enabled'])
            mutate.assert_not_called()

    def test_wrong_bot_identity_is_rejected_before_pause(self):
        api = API('test-token')
        with patch.object(api, 'json', return_value={
            'id': BOT_ID, 'command': BOT_COMMAND+' --other', 'enabled': True,
        }) as call:
            with self.assertRaisesRegex(TransportError, 'BOT_IDENTITY'):
                api.set_bot(False)
            self.assertEqual(call.call_count, 1)
            self.assertEqual(call.call_args.args[0], 'GET')


class PublicVerificationTests(unittest.TestCase):
    def setUp(self):
        self.counter_source = b'def catalog_snapshot(page):\n import json\n value=json.loads(page)\n return value["records"], value["counts"]\n'
        self.api = SimpleNamespace(file=lambda _: self.counter_source)
        self.records = {'UA-0001': 'sea', 'UA-0002': 'kiev'}
        self.counts = {'all': 2, 'korea': 0, 'sea': 1, 'georgia': 0, 'kiev': 1}
        self.plan = {'protected': {'ua_site_counters.py': sha(self.counter_source)},
                     'catalog_records_sha256': sha(canonical(self.records)), 'counts': self.counts}
        self.sleep = patch.object(controller.time, 'sleep')
        self.sleep.start()
        self.addCleanup(self.sleep.stop)

    def response(self, request, timeout, *, final_url=None, records=None):
        response = BytesIO(json.dumps({'records': self.records if records is None else records,
                                      'counts': self.counts}).encode())
        response.url = final_url or request.full_url
        return response

    def verify(self):
        return controller.public_verify(self.api, 'a'*64, 'b'*64, self.plan)

    def test_public_catalog_is_checked_with_and_without_cache_buster(self):
        with patch.object(controller.urllib.request, 'urlopen', side_effect=self.response) as fetch:
            self.assertEqual(set(self.verify().values()), {'PASS'})
        urls = [call.args[0].full_url for call in fetch.call_args_list]
        self.assertEqual(len(urls), 2)
        self.assertEqual([urllib.parse.urlsplit(url).path for url in urls], ['/video/katalog.html']*2)
        self.assertEqual(urllib.parse.urlsplit(urls[0]).query, '')
        self.assertTrue(urllib.parse.urlsplit(urls[1]).query.startswith('delivery_verify='))

    def test_redirect_to_home_is_rejected_even_with_matching_content(self):
        with patch.object(controller.urllib.request, 'urlopen', side_effect=lambda *a, **kw:
                          self.response(*a, **kw, final_url='https://www.uaart.com.ua/video/index.html')):
            with self.assertRaisesRegex(RuntimeError, 'PUBLIC_CATALOG_REDIRECT'):
                self.verify()

    def test_matching_counts_cannot_hide_wrong_car_statuses(self):
        with patch.object(controller.urllib.request, 'urlopen', side_effect=lambda *a, **kw:
                          self.response(*a, **kw, records={'UA-0001': 'kiev', 'UA-0002': 'sea'})):
            with self.assertRaisesRegex(RuntimeError, 'CATALOG_MISMATCH'):
                self.verify()

    def test_network_failure_remains_visible_in_error(self):
        with patch.object(controller.urllib.request, 'urlopen', side_effect=urllib.error.URLError('offline')):
            with self.assertRaisesRegex(RuntimeError, 'URLError:.*offline'):
                self.verify()


if __name__ == '__main__':
    unittest.main()

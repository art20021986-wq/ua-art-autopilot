"""Recovery rehearsal against temporary files and a temporary CRM database."""
from contextlib import nullcontext
from io import BytesIO
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
        for name, before, after in [('new_module.py', None, b'policy'),
                                    ('db.py', b'original', b'candidate')]:
            self.plan['files'][name] = {'before': sha(before) if before else None,
                                       'after': sha(after), 'mode': 0o644}
            if before:
                remote.atomic(self.root/name, before)
                remote.atomic(self.saved/'before'/name, before)
            remote.atomic(self.saved/'after'/name, after)
        self.plan_sha = sha(canonical(self.plan))
        self.manifest = {'plan': self.plan, 'plan_sha256': self.plan_sha, 'run_id':'123'}
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
        self.assertEqual((self.root/'db.py').read_bytes(), b'original')
        self.assertFalse((self.root/'new_module.py').exists())

    def test_interrupted_install_restores_and_resumes(self):
        remote.atomic(self.root/'new_module.py', b'policy')
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
        self.assertFalse((self.root/'new_module.py').exists())
        self.assertTrue(result['crm_resume']['enabled'])

    def test_rollback_refuses_concurrent_file_edit(self):
        self.lifecycle('install')
        (self.root/'db.py').write_bytes(b'other editor')
        with self.assertRaisesRegex(remote.DeploymentError, 'ROLLBACK_CONCURRENT_CHANGE'):
            remote.restore(self.saved, self.plan)
        self.assertEqual((self.root/'new_module.py').read_bytes(), b'policy')

    def test_rollback_preserves_concurrent_crm_edit(self):
        self.lifecycle('install')
        with sqlite3.connect(self.root/'crm.db') as connection:
            connection.execute('UPDATE cars SET price=99999 WHERE id=1')
        result=self.lifecycle('rollback')
        self.assertTrue(result['restored'])
        self.assertTrue(result['crm_unchanged'])
        self.assertEqual(remote.crm_rows()[0]['price'], 99999)
        self.assertEqual((self.root/'db.py').read_bytes(), b'original')

    def test_rollback_preserves_protected_files(self):
        self.lifecycle('install')
        (self.root/'protected.html').write_bytes(b'legitimate new photo')
        with self.assertRaisesRegex(remote.DeploymentError, 'PROTECTED_CHANGED'):
            remote.restore(self.saved, self.plan)
        self.assertEqual((self.root/'protected.html').read_bytes(), b'legitimate new photo')

    def test_protected_data_change_during_install_restores_and_resumes(self):
        with patch.object(remote, 'protected_data', side_effect=[{'n': 1}, {'n': 2}]):
            result = self.lifecycle('install')
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn('PROTECTED_DATA_CHANGED', result['error'])
        self.assertTrue(result['crm_resume']['enabled'])
        remote.verify_files(self.plan, False)

    def test_planned_page_is_not_protected_data(self):
        (self.root/'video').mkdir()
        (self.root/'video/index.html').write_bytes(b'home')
        (self.root/'video/katalog.html').write_bytes(b'catalog')
        pages = remote.protected_data({'files': {'video/index.html': {}}})['pages_and_pending_ledger']
        self.assertEqual(list(pages), ['video/katalog.html'])

    def test_atomic_write_rejects_symlink_on_read(self):
        (self.root/'alias.py').symlink_to(self.root/'db.py')
        with self.assertRaises(remote.DeploymentError):
            remote.read(self.root/'alias.py')

    def test_mid_install_write_failure_restores_every_file_and_resumes(self):
        original=remote.atomic
        failed=[]
        def interrupted(path,value,mode=0o600):
            if path==self.root/'db.py' and value==b'candidate' and not failed:
                failed.append(True)
                raise OSError('injected disk error')
            return original(path,value,mode)
        with patch.object(remote,'atomic',side_effect=interrupted):
            result=self.lifecycle('install')
        self.assertEqual(result['status'],'FAIL')
        self.assertTrue(result['crm_resume']['enabled'])
        remote.verify_files(self.plan,False)
        self.assertEqual(remote.crm_rows()[0]['price'],12345)

    def test_pending_publication_requests_survive_install_and_rollback(self):
        ledger=self.root/'.crm_publish_requests/requests.sqlite3'
        ledger.parent.mkdir()
        ledger.write_bytes(b'pending publication must survive')
        self.lifecycle('install');self.lifecycle('rollback')
        self.assertEqual(ledger.read_bytes(),b'pending publication must survive')

    def test_wrong_backup_run_is_rejected_before_pause(self):
        self.manifest['run_id']='456'
        with self.assertRaisesRegex(remote.DeploymentError,'INSTALL_PLAN_IDENTITY'):
            self.lifecycle('install')
        self.assertEqual(self.events,[])

    def test_backup_integrity_catches_corruption(self):
        old_here=remote.HERE
        try:
            remote.HERE=self.root
            remote.atomic(self.saved/'crm.db',(self.root/'crm.db').read_bytes())
            self.manifest['database_backup_sha256']=sha((self.saved/'crm.db').read_bytes())
            digest=sha(canonical(self.manifest))
            remote.atomic(self.saved/'manifest.json',canonical(self.manifest))
            (self.root/'backups').mkdir()
            target=self.root/'backups'/digest
            self.saved.rename(target)
            remote.load_backup(digest)
            (target/'crm.db').write_bytes(b'corrupt')
            with self.assertRaisesRegex(remote.DeploymentError,'DATABASE_BACKUP_CHANGED'):
                remote.load_backup(digest)
        finally:
            remote.HERE=old_here


class StorageProbeTests(unittest.TestCase):
    def du(self, stdout, returncode=0):
        return SimpleNamespace(stdout=stdout, stderr='du: denied', returncode=returncode)

    def test_quota_measurement_keeps_shared_figure(self):
        shared = SimpleNamespace(total=6*10**12, used=5*10**12, free=10**12)
        with patch.object(remote.subprocess, 'run', return_value=self.du('8000000000\t/home/Carix\n200000000\t/tmp\n')), \
             patch.object(remote.shutil, 'disk_usage', return_value=shared):
            probe = remote.storage_probe()
        self.assertEqual((probe['total_bytes'], probe['used_bytes'], probe['free_bytes']),
                         (35*10**9, 8200000000, 26800000000))
        self.assertTrue(probe['account_quota_measured'])
        self.assertEqual(probe['shared_filesystem']['used_bytes'], 5*10**12)

    def test_incomplete_measurement_fails_closed(self):
        for result in (self.du('8000000000\t/home/Carix\n', 0), self.du('1\t/home/Carix\n2\t/tmp\n', 1)):
            with patch.object(remote.subprocess, 'run', return_value=result):
                with self.assertRaisesRegex(remote.DeploymentError, 'ACCOUNT_USAGE'):
                    remote.storage_probe()

    def test_over_quota_fails_closed(self):
        with patch.object(remote.subprocess, 'run', return_value=self.du('36000000000\t/home/Carix\n0\t/tmp\n')):
            with self.assertRaisesRegex(remote.DeploymentError, 'ACCOUNT_OVER_QUOTA'):
                remote.storage_probe()


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


def page(request, body):
    response = BytesIO(body.encode())
    response.url = request.full_url
    response.status = 200
    return response


NAV = '<!--UA-HEADER-NAV-V1--><div class="ua-hnav"></div><!--/UA-HEADER-NAV-V1-->'
SWITCH = '<div class="lang-toggle ua-site-lang"></div>'


class PublicVerificationTests(unittest.TestCase):
    def response(self, request, timeout):
        nav = '' if request.full_url.endswith('/index.html') else NAV
        return page(request, '<html><head></head><body>' + 'x'*300 + nav + SWITCH + '</body></html>')

    def test_buttons_on_home_are_not_success(self):
        def home_with_buttons(request, timeout):
            return page(request, '<html><head></head><body>' + 'x'*300 + NAV + '</body></html>')
        with patch.object(controller.urllib.request, 'urlopen', side_effect=home_with_buttons):
            with self.assertRaisesRegex(RuntimeError, 'PUBLIC_CHANGE_MISSING:/video/index.html'):
                controller.public_verify(None, 'a'*64, 'b'*64, {})

    def test_exact_canonical_pages(self):
        with patch.object(controller.urllib.request, 'urlopen', side_effect=self.response) as fetch:
            result = controller.public_verify(None, 'a'*64, 'b'*64, {})
        self.assertEqual(result, {'/video/index.html': 'PASS', '/video/katalog.html': 'PASS'})
        self.assertEqual(fetch.call_count, 2)

    def test_catalogue_without_buttons_is_not_success(self):
        def old(request, timeout):
            return page(request, '<html><head></head><body>' + 'x'*300 + SWITCH + '</body></html>')
        with patch.object(controller.urllib.request, 'urlopen', side_effect=old):
            with self.assertRaisesRegex(RuntimeError, 'PUBLIC_CHANGE_MISSING:/video/katalog.html'):
                controller.public_verify(None, 'a'*64, 'b'*64, {})

    def test_redirect_is_not_success(self):
        def wrong(*args, **kwargs):
            response = self.response(*args, **kwargs)
            response.url = 'https://www.uaart.com.ua/'
            return response
        with patch.object(controller.urllib.request, 'urlopen', side_effect=wrong):
            with self.assertRaisesRegex(RuntimeError, 'PUBLIC_CANONICAL_HEALTH'):
                controller.public_verify(None, 'a'*64, 'b'*64, {})

    def test_network_failure_propagates(self):
        with patch.object(controller.urllib.request, 'urlopen', side_effect=urllib.error.URLError('offline')):
            with self.assertRaises(urllib.error.URLError):
                controller.public_verify(None, 'a'*64, 'b'*64, {})


class CardObservationTests(unittest.TestCase):
    def watch(self, bodies):
        calls = iter(bodies)
        def fetch(request, timeout):
            self.assertTrue(request.full_url.endswith('/video/ua/UA-0001.html'))
            body = next(calls)
            if isinstance(body, Exception):
                raise body
            return page(request, body)
        with patch.object(controller.urllib.request, 'urlopen', side_effect=fetch), \
             patch.object(controller.time, 'sleep'):
            return controller.card_live(deadline_seconds=3600)

    def test_republished_card_passes(self):
        old = '<div class="shapka">' + SWITCH + "<div class='svyaz'>"
        new = '<div class="shapka">' + NAV + SWITCH + "<div class='svyaz'>"
        self.assertEqual(self.watch([old, urllib.error.URLError('x'), new]),
                         {'card': '/video/ua/UA-0001.html', 'buttons': 'PASS'})

    def test_buttons_not_before_the_switch_fail(self):
        with self.assertRaisesRegex(RuntimeError, 'PUBLIC_CARD_LAYOUT'):
            self.watch([SWITCH + NAV])
        with self.assertRaisesRegex(RuntimeError, 'PUBLIC_CARD_LAYOUT'):
            self.watch([NAV + NAV + SWITCH])

    def test_pending_republication_is_reported_not_failed(self):
        with patch.object(controller.urllib.request, 'urlopen', side_effect=lambda r, timeout: page(r, SWITCH)), \
             patch.object(controller.time, 'sleep'):
            result = controller.card_live(deadline_seconds=0)
        self.assertEqual(result['buttons'], 'PENDING_CRM_REPUBLISH')


class AccountUsageTests(unittest.TestCase):
    def run_du(self, code, out, err):
        with patch.object(remote.subprocess, 'run', return_value=SimpleNamespace(returncode=code, stdout=out, stderr=err)):
            return remote.account_used_bytes()

    def test_vanished_file_is_tolerated(self):
        err = "du: cannot access '/home/Carix/x.db-journal': No such file or directory\n"
        self.assertEqual(self.run_du(1, '100\t/home/Carix\n20\t/tmp\n', err), 120)

    def test_other_errors_refuse(self):
        with self.assertRaisesRegex(remote.DeploymentError, 'ACCOUNT_USAGE'):
            self.run_du(1, '100\t/home/Carix\n20\t/tmp\n', "du: cannot read directory '/x': Permission denied\n")
        with self.assertRaisesRegex(remote.DeploymentError, 'ACCOUNT_USAGE'):
            self.run_du(1, '100\t/home/Carix\n', "du: cannot access 'y': No such file or directory\n")


class SmokeTests(unittest.TestCase):
    """The preview on a copy of the server: the installed LOGO-001 writers (reference copies in the sibling packages,
    pinned by hash) and live pages."""

    def setUp(self):
        import test_release
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for name, path in test_release.INSTALLED.items():
            (self.root/name).write_bytes(test_release.installed(name))
        here = Path(__file__).resolve().parent
        for folder in ('video', 'video/ua', 'video/ru'):
            (self.root/folder).mkdir(parents=True, exist_ok=True)
        for name, target in (('index.html', 'video/index.html'), ('katalog.html', 'video/katalog.html'),
                             ('card.html', 'video/ua/UA-0023.html'), ('podbor.html', 'video/podbor.html')):
            (self.root/target).write_bytes((here.parent/'logo_site_001/fixtures'/name).read_bytes())
        self.after = self.root/'preview'
        (self.after/'after').mkdir(parents=True)
        (self.after/'after/ua_header_nav.py').write_bytes((here/'ua_header_nav.py').read_bytes())
        patcher = patch.object(remote, 'ROOT', self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_preview_smoke(self):
        value = remote.smoke(self.after)
        self.assertEqual((value['live_pages'], value['live_pages_as_before'], value['live_pages_buttons_added']),
                         (4, 4, []))
        self.assertTrue(value['fresh_card_buttons_before_switch'] and value['fresh_card_rest_exact']
                        and value['fresh_card_repeat_exact'])
        self.assertEqual(value['fresh_card_buttons_before'], 0)

    def test_old_module_is_refused_as_candidate(self):
        (self.after/'after/ua_header_nav.py').write_bytes((self.root/'ua_header_nav.py').read_bytes())
        with self.assertRaisesRegex(remote.DeploymentError, 'SMOKE_RESULT'):
            remote.smoke(self.after)


if __name__ == '__main__':
    unittest.main()

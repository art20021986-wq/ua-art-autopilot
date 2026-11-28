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
from candidate_builder import NEW, OLD
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
        old_page = ('<html><head>' + OLD.SNIPPET + '</head><body>card</body></html>').encode()
        self.old_page, self.new_page = old_page, old_page.replace(OLD.SNIPPET.encode(), NEW.SNIPPET.encode())
        for name, before, after in [('new_module.py', None, b'policy'),
                                    ('db.py', b'original', b'candidate'),
                                    ('video/UA-0001.html', self.old_page, self.new_page)]:
            self.plan['files'][name] = {'before': sha(before) if before else None,
                                       'after': sha(after), 'mode': 0o644, 'page': name.endswith('.html')}
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
        class FakeIndex:
            """The installed landing writer: rewrite(root) is what a refresh writes; returns the changed landings."""
            rewrite = None
            def refresh(self, video):
                outer.events.append('refresh')
                changed = self.rewrite(video.parent) if self.rewrite else []
                self.rewrite = None
                return {'status': 'PASS', 'landings_changed': changed, 'sitemap_changed': bool(changed)}
        self.index = FakeIndex()

    def lifecycle(self, mode):
        with patch.object(remote, 'API', self.api), \
             patch.object(remote, 'load_backup', return_value=(self.saved, self.manifest)), \
             patch.object(remote, 'writer_exclusion', side_effect=nullcontext), \
             patch.object(remote, 'jobs_stopped', side_effect=nullcontext), \
             patch.object(remote, 'no_bot_processes'), \
             patch.object(remote, 'installed_modules', return_value=self.index):
            return remote.lifecycle(mode, '123', self.plan_sha, 'a'*64)

    def test_install_and_real_file_rollback(self):
        result = self.lifecycle('install')
        self.assertTrue(result['installed'])
        remote.verify_files(self.plan, True)
        result = self.lifecycle('rollback')
        self.assertTrue(result['restored'])
        self.assertTrue(result['crm_unchanged'])
        remote.verify_files(self.plan, False)
        self.assertEqual(self.events, [False, 'refresh', 'refresh', True, False, True])
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
        (self.root/'video').mkdir(exist_ok=True)
        (self.root/'video/index.html').write_bytes(b'home')
        (self.root/'video/katalog.html').write_bytes(b'catalog')
        pages = remote.protected_data({'files': {'video/index.html': {}, 'video/UA-0001.html': {}}})['pages_and_pending_ledger']
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


    def test_page_rewritten_by_a_writer_after_install(self):
        self.lifecycle('install')
        rewritten = self.new_page.replace(b'card', b'card with a new price')
        (self.root/'video/UA-0001.html').write_bytes(rewritten)
        remote.verify_files(self.plan, True)
        result = self.lifecycle('rollback')
        self.assertTrue(result['restored'])
        self.assertEqual((self.root/'video/UA-0001.html').read_bytes(),
                         rewritten.replace(NEW.SNIPPET.encode(), OLD.SNIPPET.encode()))
        self.assertEqual((self.root/'db.py').read_bytes(), b'original')

    def test_page_rewritten_with_v1_after_install_is_not_installed(self):
        self.lifecycle('install')
        (self.root/'video/UA-0001.html').write_bytes(self.old_page.replace(b'card', b'other'))
        with self.assertRaisesRegex(remote.DeploymentError, 'FILE_CHANGED:video/UA-0001.html'):
            remote.verify_files(self.plan, True)
        result = self.lifecycle('rollback')
        self.assertTrue(result['restored'])
        self.assertEqual((self.root/'video/UA-0001.html').read_bytes(), self.old_page.replace(b'card', b'other'))

    def test_page_without_the_block_is_not_a_rewrite(self):
        self.lifecycle('install')
        (self.root/'video/UA-0001.html').write_bytes(b'<html><head></head><body>card</body></html>')
        with self.assertRaisesRegex(remote.DeploymentError, 'FILE_CHANGED'):
            remote.verify_files(self.plan, True)
        with self.assertRaisesRegex(remote.DeploymentError, 'ROLLBACK_CONCURRENT_CHANGE:video/UA-0001.html'):
            remote.restore(self.saved, self.plan)
        self.assertEqual((self.root/'db.py').read_bytes(), b'candidate')

    def test_install_rollback_is_byte_for_byte(self):
        self.lifecycle('install')
        self.assertEqual((self.root/'video/UA-0001.html').read_bytes(), self.new_page)
        self.lifecycle('rollback')
        self.assertEqual((self.root/'video/UA-0001.html').read_bytes(), self.old_page)

    def test_auction_jobs_are_held(self):
        import fcntl
        with remote.jobs_stopped():
            for name in remote.JOB_LOCKS:
                with open(self.root/name, 'a') as other:
                    with self.assertRaises(BlockingIOError):
                        fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with open(self.root/remote.JOB_LOCKS[1], 'a') as busy:
            fcntl.flock(busy, fcntl.LOCK_EX)
            with patch.object(remote.time, 'monotonic', side_effect=[0, 0, 0, 1000]), \
                 patch.object(remote.time, 'sleep'):
                with self.assertRaisesRegex(remote.DeploymentError, 'AUCTION_JOB_BUSY'):
                    with remote.jobs_stopped():
                        pass

    # R2: the landing writer during the install (ADS-AWTAG-SITE-INSTALL-20261128: a bot still «stopping» kept the
    # module it had imported and rewrote every landing after the locks were released).

    def add_landing(self, before):
        name = 'video/seo/ru/audi-a6-koreya-kiev.html'
        after = before.replace(OLD.SNIPPET.encode(), NEW.SNIPPET.encode())
        self.plan['files'][name] = {'before': sha(before), 'after': sha(after), 'mode': 0o644, 'page': True}
        for folder, value in ((self.root, before), (self.saved/'before', before), (self.saved/'after', after)):
            remote.atomic(folder/name, value)
        self.plan_sha = sha(canonical(self.plan))
        self.manifest.update(plan=self.plan, plan_sha256=self.plan_sha)
        return name

    def writer(self, name, value):
        def rewrite(root):
            remote.atomic(root/name, value)
            return [name[len('video/'):]]
        return rewrite

    def test_controlled_refresh_is_checked_byte_for_byte_under_the_locks(self):
        name = self.add_landing(self.old_page.replace(b'card', b'landing'))
        written = self.new_page.replace(b'card', b'landing with a new tile')
        self.index.rewrite = self.writer(name, written)
        result = self.lifecycle('install')
        self.assertTrue(result['installed'])
        self.assertEqual(result['refreshed'], {name: sha(written)})
        self.assertEqual(self.events, [False, 'refresh', 'refresh', True])  # the bot resumes after the refresh
        remote.verify_files(self.plan, True, result['refreshed'], strict=True)
        with self.assertRaisesRegex(remote.DeploymentError, 'FILE_CHANGED:'+name):
            remote.verify_files(self.plan, True, strict=True)

    def test_writer_with_the_old_module_fails_the_install_and_restores(self):
        name = self.add_landing(self.old_page.replace(b'card', b'landing'))
        self.index.rewrite = self.writer(name, self.old_page.replace(b'card', b'landing, old module'))
        result = self.lifecycle('install')
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn('SEO_REFRESH_TAG:'+name, result['error'])
        self.assertTrue(result['crm_resume']['enabled'])
        self.assertEqual((self.root/'db.py').read_bytes(), b'original')
        self.assertEqual((self.root/name).read_bytes(), self.old_page.replace(b'card', b'landing, old module'))

    def test_unstable_refresh_fails_the_install(self):
        name = self.add_landing(self.old_page.replace(b'card', b'landing'))
        calls = []
        def rewrite(root):
            calls.append(1)
            remote.atomic(root/name, self.new_page.replace(b'card', b'landing %d' % len(calls)))
            return [name[len('video/'):]]
        self.index.refresh = lambda video: {'status': 'PASS', 'landings_changed': rewrite(video.parent)}
        result = self.lifecycle('install')
        self.assertIn('SEO_REFRESH_NOT_STABLE', result['error'])
        self.assertTrue(result['crm_resume']['enabled'])
        self.assertEqual((self.root/'db.py').read_bytes(), b'original')
        self.assertTrue(remote.is_old((self.root/name).read_text()))

    def test_rewrite_after_resume_verify(self):
        """The verify after the resume: a page a V2 writer rewrote passes, a page written with V1 fails, and the
        pages are read under the page writers' locks."""
        name = self.add_landing(self.old_page.replace(b'card', b'landing'))
        result = self.lifecycle('install')
        remote.atomic(self.root/'backups'/('a'*64)/'journal-install.json',
                      canonical({'stage': 'FINISHED', 'result': result}))
        held = []
        @remote.contextmanager
        def locks():
            held.append('in'); yield; held.append('out')
        def verify():
            with patch.object(remote, 'HERE', self.root), \
                 patch.object(remote, 'load_backup', return_value=(self.saved, self.manifest)), \
                 patch.object(remote, 'page_writers_held', side_effect=locks):
                return remote.installed('123', self.plan_sha, 'a'*64)
        verify()
        self.assertEqual(held, ['in', 'out'])
        remote.atomic(self.root/name, self.new_page.replace(b'card', b'landing with a new tile'))
        verify()
        remote.atomic(self.root/name, self.old_page.replace(b'card', b'landing with a new tile'))
        with self.assertRaisesRegex(remote.DeploymentError, 'FILE_CHANGED:'+name):
            verify()

    def test_rollback_puts_modules_back_before_pages_and_every_page_gets_v1(self):
        already = self.new_page.replace(b'card', b'landing already V2')  # rewritten by the stale bot on 28.11
        name = 'video/seo/ua/landing.html'
        self.plan['files'][name] = {'before': sha(already), 'after': sha(already), 'mode': 0o644, 'page': True}
        for folder in (self.root, self.saved/'before', self.saved/'after'):
            remote.atomic(folder/name, already)
        self.plan_sha = sha(canonical(self.plan))
        self.manifest.update(plan=self.plan, plan_sha256=self.plan_sha)
        self.lifecycle('install')
        original = remote.atomic
        order = []
        def record(path, value, mode=0o600):
            if path.parent != self.saved and path.suffix in ('.py', '.html'):
                order.append(path.suffix)
            return original(path, value, mode)
        with patch.object(remote, 'atomic', side_effect=record):
            result = self.lifecycle('rollback')
        self.assertTrue(result['restored'])
        self.assertEqual(order, sorted(order, key=lambda suffix: suffix == '.html'))
        self.assertEqual((self.root/name).read_bytes(), already.replace(NEW.SNIPPET.encode(), OLD.SNIPPET.encode()))
        self.assertEqual((self.root/'video/UA-0001.html').read_bytes(), self.old_page)


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

    def test_pause_waits_for_the_explicit_stopped_state(self):
        api = API('test-token')
        states = [{'id': BOT_ID, 'command': BOT_COMMAND, 'enabled': True, 'state': 'Running'}] + [
            {'id': BOT_ID, 'command': BOT_COMMAND, 'enabled': False, 'state': state}
            for state in ('Running', 'Stopping', 'Stopping', 'Stopped')]
        with patch.object(api, 'bot', side_effect=states), patch.object(api, 'json') as mutate, \
             patch('deployment_transport.time.sleep'):
            self.assertEqual(api.set_bot(False)['state'], 'stopped')
        mutate.assert_called_once()

    def test_a_stopping_bot_is_not_paused(self):
        api = API('test-token')
        stopping = {'id': BOT_ID, 'command': BOT_COMMAND, 'enabled': False, 'state': 'Stopping'}
        with patch.object(api, 'bot', return_value=stopping), patch.object(api, 'json'), \
             patch('deployment_transport.time.sleep'), \
             patch('deployment_transport.time.monotonic', side_effect=[0, 0, 200]):
            with self.assertRaisesRegex(TransportError, 'BOT_STATE_TIMEOUT'):
                api.set_bot(False)

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


class PublicVerificationTests(unittest.TestCase):
    def response(self, request, timeout):
        return page(request, '<html><head>' + NEW.SNIPPET + '</head><body>' + 'x'*300 + '</body></html>')

    def test_exact_canonical_pages(self):
        with patch.object(controller.urllib.request, 'urlopen', side_effect=self.response) as fetch:
            result = controller.public_verify(None, 'a'*64, 'b'*64, {})
        self.assertEqual(result, {path: 'PASS' for path in controller.PAGES})
        self.assertEqual(fetch.call_count, len(controller.PAGES))

    def test_v1_block_is_not_success(self):
        def old(request, timeout):
            return page(request, '<html><head>' + OLD.SNIPPET + '</head><body>' + 'x'*300 + '</body></html>')
        with patch.object(controller.urllib.request, 'urlopen', side_effect=old):
            with self.assertRaisesRegex(RuntimeError, 'PUBLIC_CHANGE_MISSING:/video/index.html'):
                controller.public_verify(None, 'a'*64, 'b'*64, {})

    def test_two_blocks_are_not_success(self):
        def twice(request, timeout):
            return page(request, '<html><head>' + NEW.SNIPPET*2 + '</head><body>' + 'x'*300 + '</body></html>')
        with patch.object(controller.urllib.request, 'urlopen', side_effect=twice):
            with self.assertRaisesRegex(RuntimeError, 'PUBLIC_CHANGE_MISSING'):
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
    """The preview on a copy of the server: the installed V1 module, the catalogue design guard (JAPAN-SITE-001 copy)
    and copies of live pages in the public folders."""

    def setUp(self):
        import test_release
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        here = Path(__file__).resolve().parent
        (self.root/'ua_google_tag.py').write_bytes((here/'ua_google_tag_old.py').read_bytes())
        (self.root/'catalog_design_guard.py').write_bytes(test_release.GUARD.read_bytes())
        for name in ('start_safe.py', 'run_all.py', 'team_bot.py', 'lead_bot.py', 'db.py', 'publication_fence.py',
                     'ua_public_freshness.py', 'ua_site_counters.py', 'cars_schema.py', 'stranica.py', 'master_card.py',
                     'publish_transaction_guard.py', 'ua_spec_permanent.py', 'ua_crm_public_sync.py',
                     'ua_card_lang_job.py', 'ua_seo_metadata.py', 'ua_seo_index.py', 'site_ge_inject.py',
                     'ua_own_counter.py'):
            (self.root/name).write_text('# ' + name + '\n')
        for name, path in test_release.PAGES.items():
            (self.root/name).parent.mkdir(parents=True, exist_ok=True)
            (self.root/name).write_bytes(path.read_bytes())
        (self.root/'video/plain.html').write_text('<html><head></head><body>no tag</body></html>')
        self.pages = sorted(test_release.PAGES)
        patcher = patch.object(remote, 'ROOT', self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_preview_plan_and_smoke(self):
        plan = remote.prepare(self.root/'preview')
        self.assertEqual(sorted(plan['files']), sorted(['ua_google_tag.py'] + self.pages))
        self.assertEqual([n for n, item in plan['files'].items() if not item['page']], ['ua_google_tag.py'])
        self.assertNotIn('video/plain.html', plan['files'])
        self.assertIn('catalog_design_guard.py', plan['protected'])
        value = remote.smoke(self.root/'preview')
        self.assertEqual((value['pages'], value['pages_block_only'], value['pages_writer_same'],
                          value['fresh_pages_same']), (8, 8, 8, 8))
        self.assertEqual(value['catalog_shell_same'], [True])
        self.assertTrue(value['hosts_same'])

    def test_other_change_on_a_page_fails_the_smoke(self):
        remote.prepare(self.root/'preview')
        target = self.root/'preview/after/video/podbor.html'
        target.write_bytes(target.read_bytes().replace(b'</body>', b'<p>extra</p></body>', 1))
        with self.assertRaisesRegex(remote.DeploymentError, 'SMOKE_RESULT'):
            remote.smoke(self.root/'preview')

    def test_landing_already_v2_is_kept_as_it_is(self):
        name = 'video/seo/ua/landing.html'
        page = self.root/name
        page.write_bytes(page.read_bytes().replace(OLD.SNIPPET.encode(), NEW.SNIPPET.encode()))
        plan = remote.prepare(self.root/'preview')
        self.assertEqual(plan['files'][name]['before'], plan['files'][name]['after'])
        value = remote.smoke(self.root/'preview')
        self.assertEqual((value['pages'], value['pages_block_only'], value['pages_already_v2']), (8, 8, 1))

    def test_installed_v2_is_refused(self):
        (self.root/'ua_google_tag.py').write_bytes((Path(__file__).resolve().parent/'ua_google_tag.py').read_bytes())
        with self.assertRaisesRegex(ValueError, 'AWTAG_LIVE_MODULE_UNEXPECTED'):
            remote.prepare(self.root/'preview')


if __name__ == '__main__':
    unittest.main()

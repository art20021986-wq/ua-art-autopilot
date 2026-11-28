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

PACKAGE = Path(__file__).resolve().parent

import deployment_controller as controller
import deployment_remote as remote
from deployment_transport import canonical, sha
from deployment_transport import API, BOT_ID, BOT_COMMAND, USA_JOB_COMMAND, TransportError


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
        for name, before, after in [('usa_auction/pages.py', b'old reader', b'policy'),
                                    ('video/usa.html', b'<html>calculator</html>', b'<html>calculator lots</html>'),
                                    ('korea_auction/ticker.py', b'old ticker', b'new ticker'),
                                    ('db.py', b'original', b'candidate')]:
            self.plan['files'][name] = {'before': sha(before), 'after': sha(after), 'mode': 0o644}
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
            def usa_job(self):
                if not outer.usa_task:
                    raise TransportError('USA_JOB_STATE')
                return {'id': 1607343, 'interval': 'hourly', 'minute': 21, 'enabled': True}
            def run_soon(self, delay=2):
                outer.moved.append(delay)
                return {'id': 1607343, 'minute': 40, 'previous_minute': 21}
        self.usa_task, self.moved = True, []
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

    def test_install_moves_the_usa_task_and_rollback_keeps_it_and_the_outputs(self):
        result = self.lifecycle('install')
        self.assertEqual(result['job'], {'usa': {'id': 1607343, 'interval': 'hourly', 'minute': 21, 'enabled': True,
                                                 'run_soon': {'id': 1607343, 'minute': 40, 'previous_minute': 21}}})
        self.assertEqual(self.moved, [2])
        kept = ['video/usa/lots.json', 'video/usa/feed.json', 'video/usa/gallery/1.json', 'video/usa/lots/1-a.jpg',
                'usa_auction_data/state.json', 'video/usa/usa-calc.js', 'video/korea/lots.json']
        for name in kept:
            remote.atomic(self.root/name, b'{}')
        result = self.lifecycle('rollback')
        self.assertTrue(result['restored'])
        self.assertEqual((self.root/'usa_auction/pages.py').read_bytes(), b'old reader')
        self.assertEqual((self.root/'video/usa.html').read_bytes(), b'<html>calculator</html>')
        self.assertEqual((self.root/'korea_auction/ticker.py').read_bytes(), b'old ticker')
        for name in kept:
            self.assertEqual((self.root/name).read_bytes(), b'{}', name)
        self.assertEqual(self.moved, [2])

    def test_install_refuses_without_the_usa_task(self):
        self.usa_task = False
        result = self.lifecycle('install')
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn('USA_JOB_STATE', result['error'])
        remote.verify_files(self.plan, False)
        self.assertEqual(self.moved, [])
        self.assertTrue(result['crm_resume']['enabled'])

    def test_failed_run_soon_restores_the_previous_files(self):
        def refused(delay=2):
            raise TransportError('HTTP_500')
        self.api.run_soon = lambda self, delay=2: refused(delay)
        result = self.lifecycle('install')
        self.assertEqual(result['status'], 'FAIL')
        remote.verify_files(self.plan, False)
        self.assertTrue(result['crm_resume']['enabled'])

    def test_a_running_usa_job_is_waited_for_before_the_bot_pause(self):
        import fcntl
        with open(self.root/'.usa_auction_job.lock', 'a') as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            with patch.object(remote.time, 'monotonic', side_effect=[0, 0, 1000]), patch.object(remote.time, 'sleep'):
                result = self.lifecycle('install')
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn('USA_JOB_BUSY', result['error'])
        self.assertEqual(self.events, [True])  # never paused; resumed (it was running)
        remote.verify_files(self.plan, False)

    def test_rollback_waits_for_a_running_usa_job(self):
        import fcntl
        self.lifecycle('install')
        with open(self.root/'.usa_auction_job.lock', 'a') as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            with patch.object(remote.time, 'monotonic', side_effect=[0, 0, 1000]), patch.object(remote.time, 'sleep'):
                result = self.lifecycle('rollback')
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn('USA_JOB_BUSY', result['error'])
        remote.verify_files(self.plan, True)

    def test_interrupted_install_restores_and_resumes(self):
        remote.atomic(self.root/'usa_auction/pages.py', b'policy')
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
        self.assertEqual((self.root/'usa_auction/pages.py').read_bytes(), b'old reader')
        self.assertTrue(result['crm_resume']['enabled'])

    def test_rollback_refuses_concurrent_file_edit(self):
        self.lifecycle('install')
        (self.root/'db.py').write_bytes(b'other editor')
        with self.assertRaisesRegex(remote.DeploymentError, 'ROLLBACK_CONCURRENT_CHANGE'):
            remote.restore(self.saved, self.plan)
        self.assertEqual((self.root/'usa_auction/pages.py').read_bytes(), b'policy')

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

    def test_sync_state_counts_ua115_failures(self):
        (self.root/'.crm_public_sync_state.json').write_text(json.dumps({'last_success': {'code': 'UA-0012'}, 'retry': {
            '10': {'count': 3, 'error': 'BASE_PUBLISH_FAILED:UA-0004 (UA115_UNAPPROVED_EXTERNAL_HOST:UA-0004:www.googletagmanager.com)'},
            '11': {'count': 1, 'error': 'other'}}}))
        self.assertEqual(remote.sync_state(), {'retry_cards': 2, 'ua115_retries': 1, 'last_success': {'code': 'UA-0012'}})

    def test_planned_page_is_not_protected_data(self):
        (self.root/'video').mkdir(exist_ok=True)
        (self.root/'video/index.html').write_bytes(b'home')
        (self.root/'video/katalog.html').write_bytes(b'catalog')
        pages = remote.protected_data({'files': {'video/index.html': {}, 'video/usa.html': {}}})['pages_and_pending_ledger']
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

    def test_pause_waits_for_explicit_stopped(self):
        api = API('test-token')
        with patch.object(api, 'bot', side_effect=[
            {'enabled': False, 'state': 'Stopping'},
            {'enabled': False, 'state': 'Stopping'},
            {'enabled': False, 'state': 'Stopped'},
        ]), patch.object(api, 'json') as mutate, patch('time.sleep') as pause:
            self.assertEqual(api.set_bot(False)['state'], 'stopped')
            mutate.assert_not_called()
            self.assertEqual(pause.call_count, 1)

    def test_pause_waits_longer_than_two_minutes(self):
        """Run 46161221342: the bot took longer than 120 s to stop; the pause now waits up to 480 s."""
        api = API('test-token')
        clock = iter([0, 0, 200, 400])
        with patch.object(api, 'bot', side_effect=[
            {'enabled': False, 'state': 'Stopping'},
            {'enabled': False, 'state': 'Stopping'},
            {'enabled': False, 'state': 'Stopped'},
        ]), patch.object(api, 'json'), patch('time.sleep'), patch('time.monotonic', side_effect=lambda: next(clock)):
            self.assertEqual(api.set_bot(False)['state'], 'stopped')

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
    def response(self, request, timeout):
        markers = ' '.join(piece for pieces in controller.EXPECTED.values() for piece in pieces).encode()
        response = BytesIO(b'<html>' + b'x'*300 + markers + b'</html>')
        response.url = request.full_url; response.status = 200
        return response

    def test_exact_canonical_pages(self):
        with patch.object(controller.urllib.request, 'urlopen', side_effect=self.response):
            self.assertEqual(controller.public_verify(None, 'a'*64, 'b'*64, {}), {p: 'PASS' for p in controller.EXPECTED})

    def test_redirect_is_not_success(self):
        def wrong(*args, **kwargs):
            response = self.response(*args, **kwargs); response.url = 'https://www.uaart.com.ua/'
            return response
        with patch.object(controller.urllib.request, 'urlopen', side_effect=wrong):
            with self.assertRaisesRegex(RuntimeError, 'PUBLIC_CANONICAL_HEALTH'):
                controller.public_verify(None, 'a'*64, 'b'*64, {})

    def test_usa_page_without_the_lot_list_is_not_success(self):
        def old(request, timeout):
            response = self.response(request, timeout)
            if request.full_url.endswith('/video/usa.html'):
                response = BytesIO(response.read().replace(b'<!--UA-USA-LOTS-V1-->', b''))
                response.url = request.full_url; response.status = 200
            return response
        with patch.object(controller.urllib.request, 'urlopen', side_effect=old):
            with self.assertRaisesRegex(RuntimeError, 'PUBLIC_CHANGE_MISSING:/video/usa.html'):
                controller.public_verify(None, 'a'*64, 'b'*64, {})

    def test_page_without_the_ticker_slot_is_not_success(self):
        def old(request, timeout):
            response = BytesIO(b'<html>' + b'x'*300 + b'</html>')
            response.url = request.full_url; response.status = 200
            return response
        with patch.object(controller.urllib.request, 'urlopen', side_effect=old):
            with self.assertRaisesRegex(RuntimeError, 'PUBLIC_CHANGE_MISSING:/video/index.html'):
                controller.public_verify(None, 'a'*64, 'b'*64, {})


class SmokeTests(unittest.TestCase):
    """The server smoke on the repository's installed files and the live page fixtures (USA-PAGE-001)."""

    def setUp(self):
        import candidate_builder
        import test_release
        self.builder, self.release = candidate_builder, test_release
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        tmp = Path(temporary.name)
        self.root, self.work = tmp/'root', tmp/'work'
        here = tmp/'pkg'
        source = test_release.live()
        for name, value in source.items():
            remote.atomic(self.root/name, value)
        for name in candidate_builder.USA_MODULES:
            remote.atomic(here/('uauc_%s.py' % name), (PACKAGE/'usa_auction'/(name+'.py')).read_bytes())
        for name in candidate_builder.KOREA_MODULES:
            remote.atomic(here/('kauc_%s.py' % name), (PACKAGE/'korea_auction'/(name+'.py')).read_bytes())
        files = candidate_builder.build(source, {}, here=here, sha=sha)
        for name, value in files.items():
            remote.atomic(self.work/'after'/name, value)
            remote.atomic(self.work/'before'/name, source[name])
        remote.atomic(self.work/'plan.json', canonical({'files': {name: {} for name in files}}))
        patcher = patch.object(remote, 'ROOT', self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_page_and_code_checks_pass(self):
        self.assertEqual(remote.smoke(self.work), {
            'usa_page_built': True, 'usa_page_idempotent': True, 'usa_page_list': True, 'usa_page_rest_kept': True,
            'usa_once': True, 'usa_make_model': True, 'usa_old_page_once': True, 'usa_fixture_run': True,
            'ticker_usa_no_price_no_km': True, 'ticker_usa_priced': True, 'usa_paths': True})

    def test_each_installed_module_fails_the_smoke(self):
        """The installed pages.py (no once), views.py (capitals) or ticker.py («$0», «0 км») each fails the same smoke:
        the check sees every part of the fix."""
        installed = self.release.installed()
        for name in ('usa_auction/pages.py', 'usa_auction/views.py', 'korea_auction/ticker.py'):
            new = (self.work/'after'/name).read_bytes()
            remote.atomic(self.work/'after'/name, installed[name])
            with self.assertRaisesRegex(remote.DeploymentError, 'SMOKE_(RESULT|CODE)'):
                remote.smoke(self.work)
            remote.atomic(self.work/'after'/name, new)
        self.assertTrue(all(remote.smoke(self.work).values()))

    def test_changed_installed_module_is_refused(self):
        (self.root/'usa_auction'/'fetch.py').write_bytes(b'# edited')
        with self.assertRaisesRegex(remote.DeploymentError, 'SMOKE_SOURCE_CHANGED'):
            remote.smoke(self.work)
        remote.atomic(self.root/'usa_auction'/'fetch.py', (self.release.INSTALL/'usa_auction/fetch.py').read_bytes())
        (self.root/'korea_auction'/'fuel.py').write_bytes(b'# edited')
        with self.assertRaisesRegex(remote.DeploymentError, 'SMOKE_SOURCE_CHANGED'):
            remote.smoke(self.work)

    def test_a_page_not_built_from_the_live_bytes_fails(self):
        built = (self.work/'after'/'video/usa.html').read_bytes()
        remote.atomic(self.work/'after'/'video/usa.html', built.replace(b'id="usa-calc"', b'id="other"'))
        with self.assertRaisesRegex(remote.DeploymentError, 'SMOKE_RESULT'):
            remote.smoke(self.work)


class RunSoonTests(unittest.TestCase):
    def test_moves_the_usa_task_two_minutes_ahead(self):
        import datetime
        api = API.__new__(API)
        calls = []
        tasks = [{'id': 1607343, 'command': USA_JOB_COMMAND, 'interval': 'hourly', 'enabled': True, 'minute': 21},
                 {'id': 1576351, 'command': 'python3.10 /home/Carix/korea_ticker_job.py', 'interval': 'hourly',
                  'enabled': True, 'minute': 22}]
        def json_call(method, endpoint, fields=None, allowed=(200,)):
            calls.append((method, endpoint, fields))
            return tasks if method == 'GET' else {}
        api.json = json_call
        at = datetime.datetime(2026, 11, 27, 18, 59, tzinfo=datetime.timezone.utc)
        self.assertEqual(api.run_soon(at), {'id': 1607343, 'minute': 1, 'previous_minute': 21})
        self.assertEqual(calls, [('GET', 'schedule/', None), ('PATCH', 'schedule/1607343/', {'minute': 1})])

    def test_missing_or_doubled_usa_task_is_refused(self):
        api = API.__new__(API)
        task = {'id': 1, 'command': USA_JOB_COMMAND, 'interval': 'hourly', 'enabled': True, 'minute': 21}
        for tasks in ([], [task, dict(task, id=2)], [dict(task, enabled=False)], [dict(task, interval='daily')]):
            api.json = lambda method, endpoint, fields=None, allowed=(200,), tasks=tasks: tasks
            with self.assertRaisesRegex(TransportError, 'USA_JOB_STATE'):
                api.usa_job()


class StalePreviewTests(unittest.TestCase):
    def test_only_own_preview_tasks_are_removed(self):
        import deployment_transport as transport
        api = transport.API.__new__(transport.API)
        boot = transport.INBOX + '/uspage1_bootstrap.py'
        tasks = [{'id': transport.BOT_ID, 'command': 'python3.10 run_all.py', 'description': 'bot'},
                 {'id': 7, 'command': 'python3.10 %s --mode preview' % boot, 'description': 'usa page preview 1'},
                 {'id': 8, 'command': 'python3.10 %s --mode install' % boot, 'description': 'usa page install 1'},
                 {'id': 9, 'command': 'python3.10 other_bootstrap.py', 'description': 'usa page preview 2'},
                 {'id': 10, 'command': 'python3.10 %s --mode preview' % boot.replace('uspage1', 'ulfix4'),
                  'description': 'usa lots fix preview 3'}]
        deleted = []
        api.json = lambda method, endpoint, fields=None, allowed=(200,): tasks
        api.request = lambda method, endpoint, data=None, content_type=None, allowed=(200,): deleted.append(endpoint)
        api.drop_stale_previews()
        self.assertEqual(deleted, ['always_on/7/'])


if __name__ == '__main__':
    unittest.main()

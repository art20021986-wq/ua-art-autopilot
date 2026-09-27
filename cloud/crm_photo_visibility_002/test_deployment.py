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
from deployment_transport import API, BOT_ID, BOT_COMMAND, INBOX, TransportError


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
        for name, before, after in [('ua_publish_requests.py', None, b'policy'),
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

    def test_interrupted_install_restores_and_resumes(self):
        remote.atomic(self.root/'ua_publish_requests.py', b'policy')
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
        self.assertFalse((self.root/'ua_publish_requests.py').exists())
        self.assertTrue(result['crm_resume']['enabled'])

    def test_rollback_after_prewrite_drift_preserves_the_other_edit(self):
        (self.root/'db.py').write_bytes(b'other editor')
        self.assertEqual(self.lifecycle('install')['status'],'FAIL')
        result=self.lifecycle('rollback')
        self.assertTrue(result['restored'])
        self.assertEqual(result['rollback_scope'],'NO_FILE_WRITES_STARTED_JOURNAL_PROOF')
        self.assertEqual((self.root/'db.py').read_bytes(),b'other editor')
        self.assertFalse((self.root/'ua_publish_requests.py').exists())
        self.assertTrue(result['crm_resume']['enabled'])

    def test_rollback_refuses_concurrent_file_edit(self):
        self.lifecycle('install')
        (self.root/'db.py').write_bytes(b'other editor')
        with self.assertRaisesRegex(remote.DeploymentError, 'ROLLBACK_CONCURRENT_CHANGE'):
            remote.restore(self.saved, self.plan)
        self.assertEqual((self.root/'ua_publish_requests.py').read_bytes(), b'policy')

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

    def test_reviewed_page_content_preserves_its_existing_permissions(self):
        name='video/UA-0023.html'
        before=b'38 photos';after=b'37 photos'
        self.plan['files'][name]={'before':sha(before),'after':sha(after),'mode':'preserve'}
        for path,value in ((self.root/name,before),(self.saved/'before'/name,before),(self.saved/'after'/name,after)):
            remote.atomic(path,value,0o664)
        self.plan_sha=sha(canonical(self.plan));self.manifest['plan_sha256']=self.plan_sha
        self.assertTrue(self.lifecycle('install')['installed'])
        self.assertEqual((self.root/name).read_bytes(),after)
        self.assertEqual((self.root/name).stat().st_mode&0o777,0o664)
        self.assertTrue(self.lifecycle('rollback')['restored'])
        self.assertEqual((self.root/name).read_bytes(),before)
        self.assertEqual((self.root/name).stat().st_mode&0o777,0o664)

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


class TransportTests(unittest.TestCase):
    def test_pause_waits_for_stopped_and_rejects_stopping(self):
        api = API('test-token')
        with patch.object(api, 'bot', side_effect=[
            {'enabled': True, 'state': 'Running'},
            {'enabled': False, 'state': 'Stopping'},
            {'enabled': False, 'state': 'Stopped'},
        ]) as observe, patch.object(api, 'json') as mutate, \
             patch('deployment_transport.time.sleep') as wait:
            result = api.set_bot(False)
        self.assertEqual(result['state'], 'stopped')
        self.assertEqual(observe.call_count, 3)
        mutate.assert_called_once_with('PATCH', 'always_on/%d/' % BOT_ID, {'enabled': 'false'})
        self.assertEqual(wait.call_count, 2)

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


class TransientControlTests(unittest.TestCase):
    def test_pause_reads_back_a_lost_patch_acknowledgement(self):
        api = API('test-token')
        with patch.object(api, 'bot', side_effect=[
            {'enabled': True, 'state': 'Running'},
            {'enabled': False, 'state': 'Stopping'},
            {'enabled': False, 'state': 'Stopped'},
        ]), patch.object(api, 'json', side_effect=TransportError('HTTP_502')) as update, \
             patch('deployment_transport.time.sleep'):
            self.assertEqual(api.set_bot(False)['state'], 'stopped')
        self.assertEqual(update.call_count, 1)

    def test_resume_recovers_a_transient_status_read_without_restarting(self):
        api = API('test-token')
        with patch.object(api, 'bot', side_effect=[TransportError('HTTP_500'),
            {'enabled': True, 'state': 'Starting'}, {'enabled': True, 'state': 'Running'}]), \
             patch.object(api, 'json') as update, patch('deployment_transport.time.sleep'):
            self.assertEqual(api.set_bot(True)['state'], 'running')
        update.assert_not_called()

    def test_bot_authorization_error_fails_without_mutation(self):
        api = API('test-token')
        with patch.object(api, 'bot', side_effect=TransportError('HTTP_403')), \
             patch.object(api, 'json') as update:
            with self.assertRaisesRegex(TransportError, 'HTTP_403'):
                api.set_bot(False)
        update.assert_not_called()

    def test_status_outage_still_stops_at_the_bounded_pause_deadline(self):
        api = API('test-token')
        with patch.object(api, 'bot', side_effect=TransportError('HTTP_502')), \
             patch('deployment_transport.time.monotonic', side_effect=[0, 0, 481]), \
             patch('deployment_transport.time.sleep'):
            with self.assertRaisesRegex(TransportError, 'BOT_STATE_TIMEOUT'):
                api.set_bot(False)

    def test_receipt_outage_does_not_recreate_or_rollback_running_installer(self):
        api = API('test-token')
        receipt = canonical({'run_id': '123', 'mode': 'install', 'safe_to_stop': True, 'status': 'PASS'})
        with patch.object(api, 'file', side_effect=[None, TransportError('HTTP_500'), receipt]), \
             patch.object(api, 'json', return_value={'id': 999}) as create, \
             patch.object(api, 'request', return_value=(204, b'')) as cleanup, \
             patch('deployment_transport.time.sleep'):
            self.assertEqual(api.run('install', '123', 'a'*64)['status'], 'PASS')
        self.assertEqual(create.call_count, 1)
        cleanup.assert_called_once_with('DELETE', 'always_on/999/', allowed=(200, 202, 204, 404))

    def test_unsafe_receipt_never_stops_the_recovery_owner(self):
        api = API('test-token')
        receipt = canonical({'run_id': '123', 'mode': 'install', 'safe_to_stop': False})
        with patch.object(api, 'file', side_effect=[None, receipt]), \
             patch.object(api, 'json', return_value={'id': 999}), \
             patch.object(api, 'request') as cleanup:
            with self.assertRaisesRegex(TransportError, 'REMOTE_RECEIPT_BINDING'):
                api.run('install', '123', 'a'*64)
        cleanup.assert_not_called()


class UploadRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.api = API('test-token')
        self.path = INBOX+'/immutable-test.zip'
        self.payload = b'exact reviewed bundle'

    def test_existing_identical_upload_is_read_only(self):
        with patch.object(self.api, 'file', return_value=self.payload), \
             patch.object(self.api, 'request') as post:
            self.api.upload(self.path, self.payload)
        post.assert_not_called()

    def test_lost_upload_acknowledgement_accepts_exact_readback(self):
        with patch.object(self.api, 'file', side_effect=[None, self.payload]), \
             patch.object(self.api, 'request', side_effect=TransportError('HTTP_500')) as post:
            self.api.upload(self.path, self.payload)
        self.assertEqual(post.call_count, 1)

    def test_uncommitted_transient_upload_retries_same_bytes_and_path(self):
        with patch.object(self.api, 'file', side_effect=[None, None, self.payload]), \
             patch.object(self.api, 'request', side_effect=[TransportError('HTTP_500'), (201, b'')]) as post, \
             patch('deployment_transport.time.sleep') as wait:
            self.api.upload(self.path, self.payload)
        self.assertEqual(post.call_count, 2)
        self.assertEqual(post.call_args_list[0], post.call_args_list[1])
        wait.assert_called_once_with(1)

    def test_authorization_failure_is_not_retried(self):
        with patch.object(self.api, 'file', return_value=None) as readback, \
             patch.object(self.api, 'request', side_effect=TransportError('HTTP_403')) as post:
            with self.assertRaisesRegex(TransportError, 'HTTP_403'):
                self.api.upload(self.path, self.payload)
        self.assertEqual(post.call_count, 1)
        self.assertEqual(readback.call_count, 1)

    def test_repeated_transient_failure_remains_bounded_and_fails_closed(self):
        with patch.object(self.api, 'file', return_value=None), \
             patch.object(self.api, 'request', side_effect=TransportError('HTTP_500')) as post, \
             patch('deployment_transport.time.sleep') as wait:
            with self.assertRaisesRegex(TransportError, 'HTTP_500'):
                self.api.upload(self.path, self.payload)
        self.assertEqual(post.call_count, 3)
        self.assertEqual(wait.call_count, 2)

    def test_success_response_with_wrong_readback_is_rejected(self):
        with patch.object(self.api, 'file', side_effect=[None, b'wrong']), \
             patch.object(self.api, 'request', return_value=(201, b'')):
            with self.assertRaisesRegex(TransportError, 'UPLOAD_READBACK'):
                self.api.upload(self.path, self.payload)


class PublicVerificationTests(unittest.TestCase):
    def response(self,request,timeout):
        response=BytesIO(b'<html>'+b'x'*300+b'</html>')
        response.url=request.full_url;response.status=200
        return response

    def test_exact_canonical_pages(self):
        with patch.object(controller.urllib.request,'urlopen',side_effect=self.response) as fetch:
            result=controller.public_verify(None,'a'*64,'b'*64,{})
        self.assertEqual(result,{'/video/index.html':'PASS','/video/katalog.html':'PASS'})
        self.assertEqual(fetch.call_count,2)

    def test_redirect_is_not_success(self):
        def wrong(*args,**kwargs):
            response=self.response(*args,**kwargs);response.url='https://www.uaart.com.ua/'
            return response
        with patch.object(controller.urllib.request,'urlopen',side_effect=wrong):
            with self.assertRaisesRegex(RuntimeError,'PUBLIC_CANONICAL_HEALTH'):
                controller.public_verify(None,'a'*64,'b'*64,{})

    def test_network_failure_propagates(self):
        with patch.object(controller.urllib.request,'urlopen',side_effect=urllib.error.URLError('offline')):
            with self.assertRaises(urllib.error.URLError):
                controller.public_verify(None,'a'*64,'b'*64,{})

    def test_published_pages_must_match_reviewed_candidate_bytes(self):
        content=b'<html>'+b'x'*300+b'</html>'
        plan={'site_write':True,'files':{name:{'after':sha(content)} for name in
              ('video/UA-0023.html','video/katalog.html','video/index.html')}}
        with patch.object(controller.urllib.request,'urlopen',side_effect=self.response):
            self.assertEqual(controller.public_verify(None,'a'*64,'b'*64,plan)['/video/UA-0023.html'],
                             'EXACT_PUBLISHED_BYTES_PASS')
            plan['files']['video/UA-0023.html']['after']='c'*64
            with self.assertRaisesRegex(RuntimeError,'PUBLIC_TARGET_HASH'):
                controller.public_verify(None,'a'*64,'b'*64,plan)




if __name__ == '__main__':
    unittest.main()

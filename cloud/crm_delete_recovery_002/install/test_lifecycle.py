"""Offline failure tests: provider, authority and live-process reads are fakes."""
from datetime import datetime, timedelta, timezone
import copy
import fcntl
import os
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest import mock

from package_install import encoded, sha
from lifecycle_controller import (Lifecycle, RepositoryAdmission, ProviderAPI, provider_inventory, load_control_plane,
    installation_policy_sha256, verify_installation_policy, verify_open_transaction, verify_pinned_recovery_sources,
    TASK, PARENT_TASK, ACCEPTANCE_SCOPE)
from lifecycle_worker import InstallWorker
import test_package_install as install_fixture


class Interrupted(BaseException):
    pass


class Admission:
    def __init__(self):
        self.calls = 0
        self.reject = False

    def check(self):
        self.calls += 1
        if self.reject:
            raise RuntimeError('existing authority rejected installation')
        return {'status': 'EXISTING_AUTHORITY_PASS'}


class Provider:
    def __init__(self):
        self.enabled = True
        self.effects = []
        self.timeout_enable_once = False
        self.always = [dict(id=266084, command='python3.10 /home/Carix/start_safe.py', enabled=True),
                       dict(id=270984, command='python3.10 /home/Carix/uaart_connection_monitor.py', enabled=True)]
        self.scheduled = []

    def request(self, method, endpoint):
        return self.always if endpoint == 'always_on/' else self.scheduled

    def supervisor(self):
        return dict(self.always[0], enabled=self.enabled, state='running' if self.enabled else 'stopped')

    def set_enabled(self, value):
        self.enabled = value
        self.effects.append(('enabled', value))
        if value and self.timeout_enable_once:
            self.timeout_enable_once = False
            raise RuntimeError('timeout after successful enable')
        return self.supervisor()

    def reload(self):
        self.effects.append(('reload',))
        return {}


class Worker:
    def __init__(self):
        self.state, self.calls = 'BASELINE', []
        self.install_failure = False
        self.recovery_failure = False
        self.startup_candidate_failure = False

    def backup_and_apply(self):
        self.calls.append('install')
        self.state = 'PARTIAL' if self.install_failure else 'INSTALLED'
        if self.install_failure:
            raise RuntimeError('failed midway through file replacement')
        return {'backup_manifest_sha256': 'b' * 64}

    def recover(self):
        self.calls.append('recover')
        if self.recovery_failure:
            raise RuntimeError('newer source preserved')
        if self.state == 'INSTALLED':
            return 'INSTALLED'
        self.state = 'BASELINE'
        return 'ROLLED_BACK'

    def rollback(self):
        self.calls.append('rollback')
        if self.recovery_failure:
            raise RuntimeError('pending deletion requires forward recovery')
        self.state = 'BASELINE'
        return 'ROLLED_BACK'

    def startup(self, *, since_epoch, installed):
        self.calls.append('startup_candidate' if installed else 'startup_baseline')
        if installed and self.startup_candidate_failure:
            raise RuntimeError('runtime did not activate')
        return {'status': 'RUNNING', 'live_telegram_action_verified': False}


def plan_for(api):
    normalize = lambda row: {'id': row['id'], 'command_sha256': sha(row['command'].encode()), 'enabled': row['enabled']}
    return {'package_manifest_sha256': 'a' * 64, 'maximum_seconds': 600,
            'provider': {'always_on': [normalize(row) for row in api.always], 'scheduled': [],
                         'monitor_python_sha256': sha(encoded(['python3.10', '/home/Carix/uaart_connection_monitor.py']))}}


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.context = dict(owner_pid=100, start_ticks=200, pgid=100, result_path=str(self.root / 'result.json'))
        self.api, self.worker, self.admission = Provider(), Worker(), Admission()
        self.plan = plan_for(self.api)
        self.ready = True
        self.stage_interrupt = None
        self.lifecycle = Lifecycle(plan=self.plan, context=self.context, context_sha256='c' * 64,
            directory=self.root, admission=self.admission, api=self.api, worker=self.worker,
            probe=lambda plan, installed: [{'installed': installed}], watchdog_ready=lambda: self.ready,
            fault=self.fault)

    def tearDown(self):
        self.temp.cleanup()

    def fault(self, stage):
        if stage == self.stage_interrupt:
            self.stage_interrupt = None
            raise Interrupted(stage)

    def test_complete_lifecycle_has_one_pause_and_runtime_readback(self):
        result = self.lifecycle.run()
        self.assertEqual('COMPLETE', result['status'])
        self.assertEqual([('enabled', False), ('reload',), ('enabled', True)], self.api.effects)
        self.assertEqual(['install', 'startup_candidate'], self.worker.calls)
        self.assertFalse(result['live_telegram_action_verified'])

    def test_authority_rejection_or_missing_watchdog_never_pauses(self):
        self.admission.reject = True
        with self.assertRaises(RuntimeError):
            self.lifecycle.run()
        self.assertEqual([], self.api.effects)
        self.admission.reject = False
        self.ready = False
        with self.assertRaisesRegex(RuntimeError, 'WATCHDOG_NOT_READY'):
            self.lifecycle.run()
        self.assertEqual([], self.api.effects)
        self.assertFalse((self.root / 'lifecycle.json').exists())

    def test_current_provider_drift_refuses_before_pause(self):
        self.api.always.append(dict(id=999, command='python3.10 unknown.py', enabled=True))
        with self.assertRaisesRegex(RuntimeError, 'PROVIDER_INVENTORY_DRIFT'):
            self.lifecycle.run()
        self.assertEqual([], self.api.effects)

    def test_partial_failure_rolls_back_before_resuming(self):
        self.worker.install_failure = True
        result = self.lifecycle.run()
        self.assertEqual('ROLLED_BACK', result['status'])
        self.assertEqual('BASELINE', self.worker.state)
        self.assertTrue(self.api.enabled)
        self.assertEqual(['install', 'recover', 'startup_baseline'], self.worker.calls)

    def test_unconfirmed_recovery_leaves_crm_disabled_and_reports_blocked(self):
        self.worker.install_failure = self.worker.recovery_failure = True
        result = self.lifecycle.run()
        self.assertEqual('BLOCKED', result['status'])
        self.assertFalse(self.api.enabled)
        self.assertFalse(result['crm_resume_confirmed'])

    def test_pause_intent_interruption_is_owned_and_reconciled(self):
        self.stage_interrupt = 'PAUSE_INTENT'
        with self.assertRaises(Interrupted):
            self.lifecycle.run()
        self.assertEqual([], self.api.effects)
        result = self.lifecycle.run(recovery=True)
        self.assertEqual('ROLLED_BACK', result['status'])
        self.assertNotIn('install', self.worker.calls)
        self.assertTrue(self.api.enabled)

    def test_finished_install_interruption_never_replays_install(self):
        self.stage_interrupt = 'INSTALLED'
        with self.assertRaises(Interrupted):
            self.lifecycle.run()
        self.admission.reject = True  # Recovery grants no new installation.
        result = self.lifecycle.run(recovery=True)
        self.assertEqual('COMPLETE', result['status'])
        self.assertEqual(1, self.worker.calls.count('install'))

    def test_uncertain_resume_retries_only_resume_not_install_or_rollback(self):
        self.api.timeout_enable_once = True
        with self.assertRaisesRegex(RuntimeError, 'timeout'):
            self.lifecycle.run()
        result = self.lifecycle.run(recovery=True)
        self.assertEqual('COMPLETE', result['status'])
        self.assertEqual(['install', 'startup_candidate'], self.worker.calls)
        self.assertEqual(1, self.api.effects.count(('enabled', False)))

    def test_candidate_startup_failure_pauses_again_and_restores_baseline(self):
        self.worker.startup_candidate_failure = True
        result = self.lifecycle.run()
        self.assertEqual('ROLLED_BACK', result['status'])
        self.assertIn('rollback', self.worker.calls)
        self.assertEqual(2, self.api.effects.count(('enabled', False)))
        self.assertTrue(self.api.enabled)

    def test_terminal_journal_crash_recreates_result_without_provider_calls(self):
        self.stage_interrupt = 'TERMINAL'
        with self.assertRaises(Interrupted):
            self.lifecycle.run()
        self.assertFalse((self.root / 'result.json').exists())
        effects = list(self.api.effects)
        result = self.lifecycle.run(recovery=True)
        self.assertEqual('COMPLETE', result['status'])
        self.assertEqual(effects, self.api.effects)
        self.assertEqual(result, json.loads((self.root / 'result.json').read_bytes()))

    def test_context_without_journal_recovers_without_provider_mutation(self):
        result = self.lifecycle.run(recovery=True)
        self.assertEqual('RECOVERED', result['status'])
        self.assertTrue(result['no_pause_or_application_write'])
        self.assertEqual([], self.api.effects)

    def test_schedule_due_in_window_is_not_treated_as_quiescent(self):
        now = datetime.now(timezone.utc)
        due = now + timedelta(minutes=5)
        row = dict(id=1502215, command='python3.10 scheduled.py', enabled=True,
                   hour=due.hour, minute=due.minute, interval='daily')
        self.api.scheduled = [row]
        expected = dict(row)
        expected['command_sha256'] = sha(expected.pop('command').encode())
        self.plan['provider']['scheduled'] = [expected]
        with self.assertRaisesRegex(RuntimeError, 'SCHEDULE_DUE_DURING_INSTALL'):
            provider_inventory(self.api, self.plan)

    def test_existing_halt_precedes_git_or_control_plane_activity(self):
        (self.root / 'state').mkdir()
        (self.root / 'state/AUTOPILOT_HALT.json').write_text('{"status":"EMERGENCY_HALT"}')
        gate = RepositoryAdmission({'authority': {'repository_root': str(self.root)}})
        with mock.patch('lifecycle_controller.subprocess.check_output') as git:
            with self.assertRaisesRegex(RuntimeError, 'EXISTING_AUTOPILOT_HALT'):
                gate.check()
            git.assert_not_called()

    def test_actual_source_bound_control_plane_interface_rejects_halt(self):
        source = Path(__file__).resolve().parents[3] / 'automation/control_plane.py'
        cp = load_control_plane(source, sha(source.read_bytes()))
        (self.root / 'state').mkdir()
        (self.root / 'state/EXECUTION_MODE.json').write_text('{}')
        (self.root / 'state/AUTOPILOT_HALT.json').write_text('{"status":"EMERGENCY_HALT"}')
        with self.assertRaisesRegex(cp.ControlPlaneError, 'AUTOMATIC_MODE_HALTED'):
            cp.verify_execution_mode(root=self.root, required_mode='AUTOMATIC', allow_halt_for_recovery=False)
        self.assertTrue(callable(cp._production_transaction_context))
        with self.assertRaisesRegex(RuntimeError, 'HASH_MISMATCH'):
            load_control_plane(source, '0' * 64)

    def test_remote_provider_requests_are_paced_without_burst_or_redirects(self):
        now=[0.0]
        starts=[]
        def sleep(seconds):
            now[0]+=seconds
        response=mock.MagicMock()
        response.__enter__.return_value.read.return_value=b'{}'
        def opened(*args,**kwargs):
            starts.append(now[0])
            return response
        opener=mock.Mock(open=opened)
        with mock.patch('lifecycle_controller.urllib.request.build_opener',return_value=opener) as build:
            api=ProviderAPI('fixture-not-a-credential',clock=lambda:now[0],sleep=sleep)
            for unused in range(4):
                api.request('GET','always_on/')
            self.assertTrue(all(b-a>=3.2-1e-9 for a,b in zip(starts,starts[1:])))
            self.assertEqual('NoRedirect',type(build.call_args.args[0]).__name__)


class AdmissionBindingTests(unittest.TestCase):
    """Persisted authority fixtures never imply a real production approval."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        source = Path(__file__).resolve().parents[3] / 'automation/control_plane.py'
        self.cp = load_control_plane(source, sha(source.read_bytes()))
        self.authority = dict(repository_root=str(self.root), main_commit='f'*40,
            control_plane_sha256='a'*64, critical_workflow_sha256='b'*64,
            trusted_controller_sha256='5'*64,
            request_path='requests/fixture.json', request_sha256='c'*64, run_id='fixture-run',
            transaction_id='tx-fixture-123456789', installation_approval={'path':'approval.json', 'sha256':'d'*64})
        self.plan = dict(version=1, task_id=TASK, parent_task_id=PARENT_TASK, acceptance_scope=ACCEPTANCE_SCOPE,
            package_sources={'lifecycle_controller.py':'e'*64},
            package_manifest_path=str(self.root/'manifest.json'), package_manifest_sha256='1'*64,
            maximum_seconds=600, provider={'always_on':[], 'scheduled':[]},
            http_checks={'installed':[{'url':'https://www.uaart.com.ua/','status':200}], 'baseline':[]},
            authority=self.authority)
        self.plan['installation_policy_sha256'] = installation_policy_sha256(self.plan)
        self.request = dict(task_id=TASK, installation_policy_sha256=self.plan['installation_policy_sha256'],
            critical={'manifest_sha256':'2'*64, 'owner_approval_path':'approval.json', 'owner_approval_sha256':'d'*64})
        subject = copy.deepcopy(self.request)
        subject['critical']['owner_approval_sha256'] = '0'*64
        self.approved = {'request_subject_sha256':sha(self.cp.canonical_json(subject)), 'manifest_sha256':'2'*64}
        now = datetime.now(timezone.utc)
        iso = lambda value: value.isoformat().replace('+00:00','Z')
        self.claim = dict(mode_epoch=7, autostart_ledger_path='ledger.json',
            production_transaction_id=self.authority['transaction_id'],
            production_transaction_path='transaction.json', production_transaction_status='OPEN')
        receipt = dict(task_id=TASK, request_sha256=self.authority['request_sha256'], run_id='fixture-run',
            transaction_id=self.authority['transaction_id'], manifest_sha256='2'*64,
            backup_manifest_sha256='3'*64, schema_version='UA-ART-PRODUCTION-BACKUP-RECEIPT-1',
            operation='backup', status='PASS', backup='PASS', unexpected_changes=0)
        (self.root/'backup.json').write_bytes(encoded(receipt))
        self.transaction = dict(autostart_ledger_path='ledger.json', backup_manifest_sha256='3'*64,
            backup_receipt_path='backup.json', backup_receipt_sha256=sha(encoded(receipt)),
            expires_at=iso(now+timedelta(hours=1)), mode_epoch=7, opened_at=iso(now-timedelta(seconds=1)),
            prepared_at=iso(now-timedelta(seconds=2)), request_path='requests/fixture.json',
            request_sha256=self.authority['request_sha256'], run_id='fixture-run',
            schema_version=self.cp.PRODUCTION_TRANSACTION_SCHEMA, status='OPEN', task_id=TASK,
            transaction_id=self.authority['transaction_id'])
        (self.root/'ledger.json').write_bytes(encoded({'expires_at': self.transaction['expires_at']}))
        self.write_transaction()

    def tearDown(self):
        self.temp.cleanup()

    def write_transaction(self):
        (self.root/'transaction.json').write_bytes(encoded(self.transaction))

    def check_transaction(self, expected_state='OPEN'):
        return verify_open_transaction(root=self.root, authority=self.authority, cp=self.cp,
            claim=self.claim, request=self.request, request_sha=self.authority['request_sha256'],
            backup_rel='backup.json', backup_path=self.root/'backup.json', transaction_rel='transaction.json',
            expected_state=expected_state)

    def test_static_policy_binds_behavior_without_dynamic_hash_cycle(self):
        original = verify_installation_policy(self.plan, self.request, self.approved)
        dynamic = copy.deepcopy(self.plan)
        dynamic['authority'].update(main_commit='9'*40, request_sha256='8'*64, run_id='new-run', transaction_id='new-tx')
        self.assertEqual(original, installation_policy_sha256(dynamic))
        for key, value in [('provider', {'always_on':[{'id':1}], 'scheduled':[]}),
                           ('http_checks', {'installed':[], 'baseline':[]}), ('maximum_seconds',601),
                           ('package_sources', {'lifecycle_controller.py':'0'*64})]:
            with self.subTest(key=key):
                changed = copy.deepcopy(self.plan)
                changed[key] = value
                with self.assertRaisesRegex(RuntimeError, 'INSTALLATION_POLICY_CHANGED'):
                    verify_installation_policy(changed, self.request, self.approved)
                changed['installation_policy_sha256'] = installation_policy_sha256(changed)
                with self.assertRaisesRegex(RuntimeError, 'REQUEST_INSTALLATION_POLICY_BINDING'):
                    verify_installation_policy(changed, self.request, self.approved)

    def test_owner_command_document_and_policy_must_be_request_bound(self):
        with self.assertRaisesRegex(RuntimeError, 'APPROVAL_INSTALLATION_POLICY_BINDING'):
            verify_installation_policy(self.plan, self.request, {'request_subject_sha256':'0'*64})
        self.plan['authority']['installation_approval']['sha256'] = '0'*64
        with self.assertRaisesRegex(RuntimeError, 'REQUEST_INSTALLATION_APPROVAL_BINDING'):
            verify_installation_policy(self.plan, self.request, self.approved)

    def test_only_persisted_exact_open_accepts_and_preparing_never_does(self):
        self.assertEqual('OPEN', self.check_transaction()['transaction_status'])
        for state in ('PREPARING','ROLLING_BACK','CLOSED','BLOCKED'):
            with self.subTest(state=state):
                self.transaction['status'] = state
                self.write_transaction()
                with self.assertRaisesRegex(RuntimeError, 'NOT_EXACT_OPEN'):
                    self.check_transaction()
        self.transaction['status'] = 'OPEN'
        self.write_transaction()
        self.claim['production_transaction_status'] = 'PREPARING'
        with self.assertRaisesRegex(RuntimeError, 'NOT_EXACT_OPEN'):
            self.check_transaction()
        (self.root/'transaction.json').unlink()
        with self.assertRaisesRegex(RuntimeError, 'PERSISTED_OPEN_TRANSACTION_REQUIRED'):
            self.check_transaction()

    def test_open_identity_backup_and_expiry_are_verified(self):
        initial = dict(self.transaction)
        for key, value, expected in [('transaction_id','tx-other','NOT_EXACT_OPEN'),
                                     ('backup_receipt_sha256','0'*64,'HASH_MISMATCH'),
                                     ('expires_at','2020-01-01T00:00:00Z','TIME_BINDING')]:
            with self.subTest(key=key):
                self.transaction = dict(initial, **{key:value})
                self.write_transaction()
                with self.assertRaisesRegex(RuntimeError, expected):
                    self.check_transaction()

    def test_preparing_is_explicit_backup_only_and_has_no_prior_receipt(self):
        self.transaction.update(status='PREPARING', opened_at=None, backup_manifest_sha256=None,
                                backup_receipt_sha256=None)
        self.claim['production_transaction_status'] = 'PREPARING'
        self.write_transaction()
        with self.assertRaisesRegex(RuntimeError, 'PREPARING_BACKUP_STATE_REQUIRED'):
            self.check_transaction('PREPARING')
        (self.root/'backup.json').unlink()
        self.assertEqual('PREPARING', self.check_transaction('PREPARING')['transaction_status'])
        with self.assertRaisesRegex(RuntimeError, 'NOT_EXACT_OPEN'):
            self.check_transaction()

    def test_consumed_rollback_requires_exact_state_but_can_outlive_grant(self):
        self.transaction.update(status='ROLLING_BACK', prepared_at='2019-01-01T00:00:00Z',
                                opened_at='2019-01-01T00:00:01Z', expires_at='2020-01-01T00:00:00Z')
        self.claim['production_transaction_status'] = 'ROLLING_BACK'
        (self.root/'ledger.json').write_bytes(encoded({'expires_at': self.transaction['expires_at']}))
        self.write_transaction()
        self.assertEqual('ROLLING_BACK', self.check_transaction('ROLLING_BACK')['transaction_status'])
        with self.assertRaisesRegex(RuntimeError, 'NOT_EXACT_OPEN'):
            self.check_transaction()

    def test_actual_pinned_worktree_requires_exact_five_current_overlays(self):
        def git(*args):
            return subprocess.check_output(['git','-C',str(self.root),*args], stderr=subprocess.DEVNULL).decode().strip()
        git('init','-q')
        (self.root/'source.py').write_text('PINNED_SOURCE = True\n')
        git('add','source.py')
        git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','source')
        source_commit = git('rev-parse','HEAD')
        source_root = self.root/'pinned-worktree'
        git('worktree','add','--detach',str(source_root),source_commit)
        claim = dict(self.claim, autostart_source_commit=source_commit,
                     autostart_ledger_path='state/autostart_consumed/fixture.json')
        claim_rel = 'state/claims/%s.%s.%s.json' % (TASK,self.authority['request_sha256'],self.authority['run_id'])
        tx_rel, backup_rel = 'state/transactions/fixture.json', 'state/receipts/fixture.json'
        rows = {claim_rel:claim, tx_rel:self.transaction, backup_rel:{'fixture':'backup'},
                self.authority['request_path']:self.request, claim['autostart_ledger_path']:{'source_commit':source_commit}}
        for name, value in rows.items():
            path=self.root/name
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(encoded(value))
        git('add',*rows)
        git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','current durable authority')
        authority=dict(self.authority,main_commit=git('rev-parse','HEAD'),code_source_commit=source_commit)
        for name in rows:
            path=source_root/name
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes((self.root/name).read_bytes())
        def verify():
            return verify_pinned_recovery_sources(root=self.root,source_root=source_root,authority=authority,
                claim=claim,request_sha=self.authority['request_sha256'],backup_rel=backup_rel,transaction_rel=tx_rel)
        self.assertNotEqual(authority['main_commit'],source_commit)
        self.assertEqual(5,len(verify()['durable_overlay_sha256']))
        (source_root/tx_rel).write_bytes(b'{"changed":true}\n')
        with self.assertRaisesRegex(RuntimeError,'OVERLAY_MISMATCH'):
            verify()
        (source_root/tx_rel).write_bytes((self.root/tx_rel).read_bytes())
        claim['autostart_source_commit']='0'*40
        with self.assertRaisesRegex(RuntimeError,'CLAIM_SOURCE'):
            verify()


class WorkerTests(unittest.TestCase):
    """Reuse fixture setup without counting the inherited tests twice."""
    setUp = install_fixture.InstallTests.setUp
    tearDown = install_fixture.InstallTests.tearDown
    load_package = install_fixture.InstallTests.load_package
    def make_worker(self, payload=b'application = "after"\n'):
        self.wsgi_path = self.root / 'wsgi.py'
        self.wsgi_path.write_bytes(b'application = "before"\n')
        (self.stage / 'route.py').write_bytes(payload)
        self.manifest['route_patch'] = dict(destination='/var/www/www_uaart_com_ua_wsgi.py',
            before_sha256=sha(self.wsgi_path.read_bytes()), payload='route.py', payload_sha256=sha(payload), role='route')
        self.package = self.load_package()
        return InstallWorker(self.package, allowed_python_sha256=(), root=self.root,
                             wsgi_path=self.wsgi_path, inventory=lambda: [])

    def test_worker_installs_wsgi_before_entrypoint_and_recovers_receipt(self):
        worker = self.make_worker()
        worker.backup_and_apply()
        self.assertEqual(b'application = "after"\n', self.wsgi_path.read_bytes())
        self.assertEqual('INSTALLED', worker.recover())
        self.conn.execute('UPDATE cars SET price=16000 WHERE id=8')
        self.conn.commit()
        self.assertEqual('ROLLED_BACK', worker.rollback())
        self.assertEqual(16000, self.conn.execute('SELECT price FROM cars').fetchone()[0])
        self.assertEqual(b'application = "before"\n', self.wsgi_path.read_bytes())

    def test_interrupted_code_rollback_completes_wsgi_restore(self):
        worker = self.make_worker()
        worker.backup_and_apply()
        original = worker.wsgi.rollback
        worker.wsgi.rollback = mock.Mock(side_effect=Interrupted('before wsgi restore'))
        with self.assertRaises(Interrupted):
            worker.rollback()
        worker.wsgi.rollback = original
        self.assertEqual('ROLLED_BACK', worker.recover())
        self.assertEqual(b'application = "before"\n', self.wsgi_path.read_bytes())

    def test_wsgi_entrypoint_restored_before_helper_removal_and_crash_recovery(self):
        worker = self.make_worker(b'from ua_delete_runtime import INSTALLED\napplication = INSTALLED\n')
        worker.backup_and_apply()
        def check_fresh_wsgi():
            subprocess.run([sys.executable, '-I', '-B', '-c',
                'import runpy,sys;sys.path.insert(0,sys.argv[1]);runpy.run_path(sys.argv[2])',
                str(self.root), str(self.wsgi_path)], check=True, capture_output=True)
        check_fresh_wsgi()
        def interrupted(phase, name):
            if phase == 'file_restored' and name == 'ua_delete_runtime.py':
                self.assertFalse((self.root / name).exists())
                check_fresh_wsgi()
                raise Interrupted('helper removed after WSGI restoration')
        worker.transaction.fault = interrupted
        with self.assertRaises(Interrupted):
            worker.rollback()
        self.assertEqual('ROLLING_BACK', json.loads((worker.transaction.folder / 'journal.json').read_bytes())['stage'])
        worker.transaction.fault = lambda phase, name: None
        self.assertEqual('ROLLED_BACK', worker.recover())
        check_fresh_wsgi()

    def test_rollback_preflight_rejects_before_wsgi_change(self):
        worker = self.make_worker()
        worker.backup_and_apply()
        self.conn.execute('''INSERT INTO ua_delete_intents
            (operation_id,car_id,car_code,vin,actor_id,snapshot,snapshot_sha256,
             expected_snapshot,expected_snapshot_sha256,plan,plan_sha256,backup_sha256,state)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            ('operation', 8, 'UA-0002', 'VIN', 123, '{}', 'a'*64, '{}', 'a'*64,
             '{}', 'a'*64, 'b'*64, 'REQUESTED'))
        self.conn.commit()
        with self.assertRaisesRegex(RuntimeError, 'FORWARD_RECOVERY_REQUIRED'):
            worker.rollback()
        self.assertEqual(b'application = "after"\n', self.wsgi_path.read_bytes())
        self.conn.execute('DELETE FROM ua_delete_intents')
        self.conn.commit()
        (self.root / 'publikaciya.py').write_bytes(b'operator_change = True\n')
        with self.assertRaisesRegex(RuntimeError, 'NEWER_CODE_PRESERVED'):
            worker.rollback()
        self.assertEqual(b'application = "after"\n', self.wsgi_path.read_bytes())

    def test_separate_phases_apply_only_same_original_composite_backup(self):
        worker = self.make_worker()
        backup = worker.prepare_backup()
        digest = backup['backup_manifest_sha256']
        snapshot = (worker.transaction.folder/'crm.snapshot.db').read_bytes()
        self.assertEqual('BACKUP_VERIFIED', worker.verify_existing_backup(digest)['status'])
        result = worker.apply_existing(digest)
        self.assertEqual(digest, result['backup_manifest_sha256'])
        self.assertEqual(snapshot, (worker.transaction.folder/'crm.snapshot.db').read_bytes())
        self.assertEqual('ROLLED_BACK', worker.rollback_existing(digest))

    def test_phase_database_drift_refuses_without_resnapshot_or_code_effects(self):
        worker = self.make_worker()
        backup = worker.prepare_backup()
        digest = backup['backup_manifest_sha256']
        original = (worker.transaction.folder/'phase_backup_manifest.json').read_bytes()
        self.conn.execute('UPDATE cars SET price=17000 WHERE id=8')
        self.conn.commit()
        with self.assertRaisesRegex(RuntimeError, 'DATABASE_CHANGED_AFTER_BACKUP'):
            worker.apply_existing(digest)
        with self.assertRaisesRegex(RuntimeError, 'ORIGINAL_BACKUP_EXISTS'):
            worker.prepare_backup()
        self.assertEqual(original, (worker.transaction.folder/'phase_backup_manifest.json').read_bytes())
        self.assertEqual(17000, self.conn.execute('SELECT price FROM cars').fetchone()[0])
        self.assertEqual(self.originals['cars_ui.py'], (self.root/'cars_ui.py').read_bytes())
        self.assertEqual('UNCHANGED', worker.recover())

    def test_composite_backup_covers_wsgi_and_transaction_namespace(self):
        worker = self.make_worker()
        worker = InstallWorker(self.package, allowed_python_sha256=(), root=self.root,
            wsgi_path=self.wsgi_path, inventory=lambda: [], transaction_id='tx-fixture-123456789')
        backup = worker.prepare_backup()
        other = InstallWorker(self.package, allowed_python_sha256=(), root=self.root,
            wsgi_path=self.wsgi_path, inventory=lambda: [], transaction_id='tx-fixture-123456780')
        self.assertNotEqual(worker.transaction.folder, other.transaction.folder)
        with self.assertRaisesRegex(RuntimeError, 'ORIGINAL_PHASE_BACKUP_HASH_MISMATCH'):
            other.verify_existing_backup(backup['backup_manifest_sha256'])
        (worker.transaction.folder/'wsgi.before').write_bytes(b'changed\n')
        with self.assertRaisesRegex(RuntimeError, 'WSGI_BACKUP_BINDING'):
            worker.verify_existing_backup(backup['backup_manifest_sha256'])

    def test_phase_callbacks_share_real_lease_and_retained_config_requires_ownership(self):
        worker = self.make_worker()
        callbacks=[]
        def observe(operation, phase):
            fd=os.open(self.root/'.start_safe.singleton.lock',os.O_RDWR)
            try:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            finally:
                os.close(fd)
            callbacks.append(phase)
            return worker.verify_phase_before(operation) if phase=='before' else worker.verify_images(installed=operation=='execute')
        result=worker.perform_phase('backup',None,lambda:observe('backup','before'),lambda:observe('backup','after'))
        digest=result['mechanical']['backup_manifest_sha256']
        executed=worker.perform_phase('execute',digest,lambda:observe('execute','before'),lambda:observe('execute','after'))
        readiness=executed['after']['rollback_readiness']
        self.assertEqual('PASS',readiness['status'])
        self.assertEqual(digest,readiness['backup_manifest_sha256'])
        self.assertFalse(readiness['code_restore_performed'])
        self.assertEqual(0,readiness['deletion_state_counts']['ua_delete_intents'])
        worker.perform_phase('rollback',digest,lambda:observe('rollback','before'),lambda:observe('rollback','after'))
        self.assertEqual(['before','after']*3,callbacks)
        evidence=worker.verify_images(installed=False)
        self.assertEqual(self.package.runtime_config['payload_sha256'],evidence['runtime_config_sha256'])
        path=worker.transaction.folder/'journal.json'
        journal=json.loads(path.read_bytes())
        journal['stage']='BACKED_UP'
        path.write_bytes(encoded(journal))
        with self.assertRaisesRegex(RuntimeError,'RETAINED_CONFIG_OWNERSHIP_REQUIRED'):
            worker.verify_images(installed=False)

    def test_pre_pause_singleton_proof_uses_actual_kernel_owner(self):
        path=self.root/'.start_safe.singleton.lock'
        fd=os.open(path,os.O_RDWR)
        try:
            with self.assertRaisesRegex(RuntimeError,'OWNERSHIP_UNPROVEN'):
                InstallWorker.held_singleton_owner(path,os.getpid())
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.assertEqual(os.getpid(),InstallWorker.held_singleton_owner(path,os.getpid())['owner_pid'])
            with self.assertRaisesRegex(RuntimeError,'OWNERSHIP_UNPROVEN'):
                InstallWorker.held_singleton_owner(path,os.getpid()+1000000)
        finally:
            os.close(fd)

    def test_exact_additive_schema_projection_is_read_back_not_inferred(self):
        worker=self.make_worker()
        before=worker.verify_images(installed=False)
        self.assertEqual({name:None for name in self.package.schema},before['deletion_schema_projection'])
        worker.backup_and_apply()
        after=worker.verify_images(installed=True)
        self.assertEqual(self.package.schema,after['deletion_schema_projection'])
        raw=(json.dumps(self.package.schema,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
        self.assertEqual(sha(raw),after['deletion_schema_sha256'])
        self.conn.execute('ALTER TABLE ua_delete_jobs ADD COLUMN unexpected TEXT')
        self.conn.commit()
        with self.assertRaisesRegex(RuntimeError,'DELETION_SCHEMA_READBACK_CHANGED'):
            worker.verify_images(installed=True)


if __name__ == '__main__':
    unittest.main()

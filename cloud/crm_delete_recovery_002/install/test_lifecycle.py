"""Offline failure tests: provider, authority and live-process reads are fakes."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest import mock

from package_install import encoded, sha
from lifecycle_controller import Lifecycle, RepositoryAdmission, provider_inventory, load_control_plane
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


if __name__ == '__main__':
    unittest.main()

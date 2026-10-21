"""Offline dispatcher tests; synthetic receipts are never production evidence."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import controller
import contract

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + '\n')


class DispatcherFixture(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.package = self.root / contract.PACKAGE_REL
        shutil.copytree(HERE, self.package,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.pyo'))
        automation = self.root / 'automation'
        automation.mkdir()
        # These are the actual existing dispatcher sources, not task-provided
        # replacements. The temporary copy changes only their computed ROOT.
        for name in ('execution_contract.py', 'task_orchestrator.py'):
            shutil.copyfile(REPO / 'automation' / name, automation / name)
        spec = importlib.util.spec_from_file_location(
            '_crm_dispatcher_fixture_' + self.root.name, automation / 'execution_contract.py')
        self.ec = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = self.ec
        self.addCleanup(sys.modules.pop, spec.name, None)
        spec.loader.exec_module(self.ec)
        controllers = {'controller.py', 'backup_controller.py', 'rollback_controller.py'}
        paths = sorted(path.relative_to(self.root).as_posix()
                       for path in self.package.rglob('*.py'))
        tests = [name for name in paths if Path(name).name.startswith('test_')]
        dependencies = [name for name in paths
                        if name not in tests and Path(name).name not in controllers]
        execution = {'controller_path': contract.PACKAGE_REL + '/controller.py',
            'controller_sha256': _hash(self.package / 'controller.py'),
            'backup_controller_path': contract.PACKAGE_REL + '/backup_controller.py',
            'backup_controller_sha256': _hash(self.package / 'backup_controller.py'),
            'rollback_controller_path': contract.PACKAGE_REL + '/rollback_controller.py',
            'rollback_controller_sha256': _hash(self.package / 'rollback_controller.py'),
            'test_paths': tests, 'dependency_paths': dependencies,
            'file_sha256': {name: _hash(self.root / name) for name in tests + dependencies},
            'receipt_path': contract.RECEIPT_REL,
            'backup_receipt_path': contract.BACKUP_RECEIPT_REL,
            'rollback_receipt_path': contract.ROLLBACK_RECEIPT_REL,
            'evidence_paths': [contract.RECEIPT_REL, contract.BACKUP_RECEIPT_REL,
                               contract.ROLLBACK_RECEIPT_REL],
            'production_required': True, 'timeout_seconds': 20}
        self.request = {'task_id': contract.TASK_ID,
            'title': 'OFFLINE FIXTURE: child installation dispatcher validation',
            'description': 'Fixture only. No production authority is supplied.',
            'requested_min_class': 'CRITICAL', 'production_required': True,
            'changed_paths': ['production/operator-ui/cars_ui.py', 'production/crm.db'],
            'critical': {'manifest_sha256': 'a' * 64}, 'execution': execution}
        _json(self.root / contract.REQUEST_REL, self.request)

    def test_actual_execution_contract_accepts_complete_declared_python_closure(self):
        spec = self.ec.validate_execution(contract.REQUEST_REL, 'CRITICAL')
        inventory = {path.relative_to(self.root).as_posix()
                     for path in self.package.rglob('*.py')}
        self.assertEqual(inventory, set(spec.file_sha256))
        self.assertLessEqual(len(spec.dependency_paths), 50)
        self.assertEqual(contract.PACKAGE_REL + '/controller.py', spec.controller_path)
        self.ec.compile_spec(spec)

    def test_actual_dispatcher_rejects_unbound_module(self):
        (self.package / 'undeclared_dependency.py').write_text('VALUE = 1\n')
        with self.assertRaisesRegex(self.ec.ExecutionContractError, 'PACKAGE_PYTHON_CLOSURE'):
            self.ec.validate_execution(contract.REQUEST_REL, 'CRITICAL')

    def test_actual_isolated_backup_launcher_rejects_existing_halt_without_cli_plan(self):
        spec = self.ec.validate_execution(contract.REQUEST_REL, 'CRITICAL')
        _json(self.root / 'state/AUTOPILOT_HALT.json', {'fixture': True, 'status': 'EMERGENCY_HALT'})
        real_run = subprocess.run
        observed = []
        def capture(*args, **kwargs):
            value = real_run(*args, **dict(kwargs, capture_output=True, text=True))
            observed.append((args[0], value))
            return value
        environment = {'UAART_RUN_ID': 'offline-fixture',
                       'UAART_TRANSACTION_ID': 'tx-offline-fixture-123456',
                       'PYTHONANYWHERE_API_TOKEN': 'fixture-not-a-credential'}
        with mock.patch.dict(os.environ, environment), \
                mock.patch.object(self.ec.subprocess, 'run', side_effect=capture):
            with self.assertRaisesRegex(self.ec.ExecutionContractError, 'BACKUP_CONTROLLER_FAILED:1'):
                self.ec.run_backup(spec)
        self.assertEqual(1, len(observed))
        argv, result = observed[0]
        self.assertIn('-I', argv)
        self.assertNotIn('--plan', argv)
        self.assertEqual('ControllerError', json.loads(result.stdout)['error_type'])
        self.assertNotIn('fixture-not-a-credential', result.stdout + result.stderr)
        self.assertFalse((self.root / contract.BACKUP_RECEIPT_REL).exists())


class ControllerFlowTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.envelope = SimpleNamespace(root=self.root, operation='backup',
            receipt_path=self.root / contract.BACKUP_RECEIPT_REL)
        self.events = []
        events = self.events
        class FixtureTransport:
            def __init__(self, token):
                events.append('transport')
            def claim_transport(self, bundle):
                events.append('stage')
                return object()
            def run(self, stage, *, operation):
                events.append('remote-' + operation)
                return {'fixture': True}
            def release_transport(self, stage):
                events.append('terminal-cleanup')
        self.transport_class = FixtureTransport

    def test_order_requires_admission_before_staging_and_proof_before_receipt(self):
        import release_bundle
        import transport
        receipt = {'task_id': contract.TASK_ID, 'status': 'PASS', 'fixture_only': True}
        def proof(*args):
            self.events.append('proof')
            return receipt
        with mock.patch.object(controller, 'load_envelope', return_value=self.envelope), \
                mock.patch.object(controller, '_admit', side_effect=lambda *a: self.events.append('admit')), \
                mock.patch.object(controller, 'receipt_from_result', side_effect=proof), \
                mock.patch.object(release_bundle, 'prepare', side_effect=lambda *a: self.events.append('build')), \
                mock.patch.object(transport, 'PythonAnywhereTransport', self.transport_class):
            result = controller.run('backup', root=self.root,
                environment={'PYTHONANYWHERE_API_TOKEN': 'fixture'})
        self.assertEqual(receipt, result)
        self.assertEqual(['transport', 'build', 'admit', 'stage', 'remote-backup',
                          'terminal-cleanup', 'proof'], self.events)
        self.assertEqual(receipt, json.loads(self.envelope.receipt_path.read_text()))

    def test_uncertain_remote_outcome_does_not_force_stop_or_emit_receipt(self):
        import release_bundle
        import transport
        def uncertain(*args, **kwargs):
            self.events.append('uncertain')
            raise RuntimeError('offline uncertainty')
        with mock.patch.object(controller, 'load_envelope', return_value=self.envelope), \
                mock.patch.object(controller, '_admit'), \
                mock.patch.object(release_bundle, 'prepare'), \
                mock.patch.object(transport, 'PythonAnywhereTransport', self.transport_class), \
                mock.patch.object(self.transport_class, 'run', side_effect=uncertain):
            with self.assertRaises(RuntimeError):
                controller.run('backup', root=self.root,
                    environment={'PYTHONANYWHERE_API_TOKEN': 'fixture'})
        self.assertNotIn('terminal-cleanup', self.events)
        self.assertFalse(self.envelope.receipt_path.exists())

    def test_halt_is_checked_before_credential_or_imported_transport(self):
        _json(self.root / 'state/AUTOPILOT_HALT.json', {'fixture': True})
        with mock.patch.object(controller, 'load_envelope') as load:
            with self.assertRaisesRegex(controller.ControllerError, 'HALT'):
                controller.run('execute', root=self.root, environment={})
            load.assert_not_called()

    def test_receipt_publish_never_replaces_existing_evidence(self):
        path = self.root / 'receipts/result.json'
        controller._write_new_json(path, {'first': True})
        before = path.read_bytes()
        with self.assertRaises(FileExistsError):
            controller._write_new_json(path, {'second': True})
        self.assertEqual(before, path.read_bytes())
        self.assertEqual([path], list(path.parent.iterdir()))


class PinnedRollbackWorktreeTests(unittest.TestCase):
    def test_real_worktree_uses_fresh_authority_and_exact_five_overlays(self):
        import lifecycle_controller as lifecycle
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            current, pinned = folder / 'current', folder / 'pinned'
            current.mkdir()
            def git(*args):
                return subprocess.check_output(['git', '-C', str(current), *args],
                    stderr=subprocess.DEVNULL).decode().strip()
            git('init', '-q', '-b', 'main')
            (current / 'source.py').write_text('# pinned fixture code\n')
            git('add', '.')
            git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                'commit', '-qm', 'source')
            source_commit = git('rev-parse', 'HEAD')
            request_sha, run_id = 'a' * 64, '12345'
            claim_path = 'state/claims/%s.%s.%s.json' % (lifecycle.TASK, request_sha, run_id)
            paths = (claim_path, 'state/transactions/fixture.json', contract.REQUEST_REL,
                     'state/ledgers/fixture.json', contract.BACKUP_RECEIPT_REL)
            claim = {'autostart_source_commit': source_commit, 'autostart_ledger_path': paths[3]}
            for path in paths:
                _json(current / path, {'fixture': path})
            _json(current / claim_path, claim)
            _json(current / paths[3], {'source_commit': source_commit})
            git('add', '.')
            git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                'commit', '-qm', 'rolling-back durable fixture')
            main_commit = git('rev-parse', 'HEAD')
            git('-c', 'core.hooksPath=/dev/null', 'worktree', 'add', '--detach',
                str(pinned), source_commit)
            for name in paths:
                (pinned / name).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(current / name, pinned / name)
            authority = {'main_commit': main_commit, 'code_source_commit': source_commit,
                         'request_path': contract.REQUEST_REL, 'run_id': run_id}
            envelope = SimpleNamespace(root=pinned, operation='rollback')
            observed = controller._authority_roots(envelope, {'authority': authority})
            self.assertEqual((current, pinned), observed)
            evidence = lifecycle.verify_pinned_recovery_sources(root=current,
                source_root=pinned, authority=authority, claim=claim, request_sha=request_sha,
                backup_rel=contract.BACKUP_RECEIPT_REL, transaction_rel=paths[1])
            self.assertEqual(set(paths), set(evidence['durable_overlay_sha256']))
            (pinned / paths[1]).write_text('{"tampered": true}\n')
            with self.assertRaisesRegex(Exception, 'PINNED_DURABLE_OVERLAY_MISMATCH'):
                lifecycle.verify_pinned_recovery_sources(root=current, source_root=pinned,
                    authority=authority, claim=claim, request_sha=request_sha,
                    backup_rel=contract.BACKUP_RECEIPT_REL, transaction_rel=paths[1])


if __name__ == '__main__':
    unittest.main()

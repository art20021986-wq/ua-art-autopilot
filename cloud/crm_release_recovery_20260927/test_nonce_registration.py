"""Exercise actual mode/authority validation and preserve the consumed rollback."""
from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import nonce_registration as reg


ROOT = Path(__file__).resolve().parents[2]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NonceRegistrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)/'repo'
        shutil.copytree(ROOT, cls.root, ignore=shutil.ignore_patterns('.git', '__pycache__'))
        cls.cp = load(cls.root/'automation/control_plane.py', 'registered_control')
        cls.watchdog = load(cls.root/'automation/transaction_watchdog.py', 'registered_watchdog')
        cls.original = {p.relative_to(cls.root).as_posix():p.read_bytes()
                        for p in cls.root.rglob('*') if p.is_file()}

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def tearDown(self):
        for relative, payload in self.original.items():
            path = self.root/relative
            if path.is_symlink():
                path.unlink()
            if not path.exists() or path.read_bytes() != payload:
                path.write_bytes(payload)

    def read(self, relative):
        return json.loads((self.root/relative).read_bytes())

    def write(self, relative, value):
        (self.root/relative).write_bytes(reg.encode(value))

    def rebind(self):
        activation = self.read(reg.ACTIVATION)
        activation['runtime_manifest_sha256'] = reg.digest((self.root/reg.MANIFEST).read_bytes())
        self.write(reg.ACTIVATION, activation)
        mode = self.read(reg.MODE)
        mode['runtime_manifest_sha256'] = activation['runtime_manifest_sha256']
        mode['runtime_activation_sha256'] = reg.digest((self.root/reg.ACTIVATION).read_bytes())
        self.write(reg.MODE, mode)

    def verify(self):
        return self.cp.verify_execution_mode(root=self.root, required_mode='AUTOMATIC',
                                             allow_halt_for_recovery=True)

    def test_registered_chain_and_full_workflow_policy_pass(self):
        self.assertEqual(self.verify()['status'], 'PASS')
        self.assertEqual(self.cp.verify_production_credential_workflow_policy(root=self.root)
                         ['consumers'], sorted(self.cp.PRODUCTION_CREDENTIAL_WORKFLOW_ALLOWLIST))

    def test_normal_launch_remains_halted(self):
        with self.assertRaisesRegex(self.cp.ControlPlaneError, 'AUTOMATIC_MODE_HALTED'):
            self.cp.verify_execution_mode(root=self.root, required_mode='AUTOMATIC')

    def test_incident_still_pending_and_history_unchanged(self):
        before = {p:payload for p,payload in self.original.items() if p.startswith('state/')}
        result = self.watchdog.discover(root=self.root)
        self.assertEqual((result['pending_count'], result['transaction_status']), (1,'ROLLING_BACK'))
        self.assertEqual(result['transaction_id'], 'tx-36268504600-54c3be3cfc4dd0da')
        for relative, payload in before.items():
            self.assertEqual((self.root/relative).read_bytes(), payload)

    def test_consumed_rollback_cannot_be_restarted(self):
        result = self.watchdog.discover(root=self.root)
        with self.assertRaises(self.cp.ControlPlaneError):
            self.cp.start_production_rollback(result['request_path'], result['run_id'],
                                              result['transaction_id'], root=self.root)

    def test_failed_transaction_cannot_be_claimed_finished(self):
        result = self.watchdog.discover(root=self.root)
        with self.assertRaisesRegex(self.cp.ControlPlaneError, 'TRANSACTION_IDENTITY_MISMATCH'):
            self.cp.close_production_transaction(result['request_path'], result['run_id'],
                result['transaction_id'], 'FINISHED', root=self.root)

    def test_previous_mode_change_is_rejected(self):
        (self.root/reg.PREVIOUS_MODE).write_bytes(self.original[reg.PREVIOUS_MODE] + b' ')
        with self.assertRaisesRegex(self.cp.ControlPlaneError, 'NONCE_ACTIVATION_PREVIOUS_MODE'):
            self.verify()

    def test_previous_manifest_change_is_rejected(self):
        (self.root/reg.PREVIOUS_MANIFEST).write_bytes(self.original[reg.PREVIOUS_MANIFEST] + b' ')
        with self.assertRaisesRegex(self.cp.ControlPlaneError, 'NONCE_ACTIVATION_PREVIOUS_MANIFEST'):
            self.verify()

    def test_additional_runtime_change_is_rejected_even_with_new_hash(self):
        path = 'automation/execution_contract.py'
        (self.root/path).write_bytes(self.original[path] + b'\n')
        manifest = self.read(reg.MANIFEST)
        manifest['files'][path] = reg.digest((self.root/path).read_bytes())
        self.write(reg.MANIFEST, manifest)
        self.rebind()
        with self.assertRaisesRegex(self.cp.ControlPlaneError, 'NONCE_ACTIVATION_RUNTIME_SCOPE'):
            self.verify()

    def test_workflow_change_rejected_even_if_manifest_matches(self):
        path = '.github/workflows/uaart_critical.yml'
        (self.root/path).write_bytes(self.original[path] + b'\n')
        manifest = self.read(reg.MANIFEST)
        manifest['files'][path] = reg.digest((self.root/path).read_bytes())
        self.write(reg.MANIFEST, manifest)
        self.rebind()
        with self.assertRaisesRegex(self.cp.ControlPlaneError, 'WRITE_WORKFLOW_EXACT_SHA256_MISMATCH'):
            self.verify()

    def test_replay_grant_cannot_be_added(self):
        activation = self.read(reg.ACTIVATION)
        activation['rollback_replay_allowed'] = True
        self.write(reg.ACTIVATION, activation)
        self.rebind()
        with self.assertRaisesRegex(self.cp.ControlPlaneError, 'NONCE_ACTIVATION_SCOPE'):
            self.verify()

    def test_previous_mode_symlink_is_rejected(self):
        path = self.root/reg.PREVIOUS_MODE
        path.unlink()
        path.symlink_to(self.root/reg.MODE)
        with self.assertRaisesRegex(self.cp.ControlPlaneError, 'RUNTIME_ACTIVATION_SYMLINK'):
            self.verify()

    def test_original_task088_grants_remain_bound_to_same_requests(self):
        activation = self.read(self.cp.TASK088_ACTIVATION_PATH)
        for relative, binding in activation['allowed_requests'].items():
            raw = self.read(relative)
            result = self.cp._task088_owner_storage_override(relative, raw,
                binding['request_sha256'], root=self.root)
            self.assertIsNotNone(result)
        self.assertIsNone(self.cp._task088_owner_storage_override(
            'tasks/requests/DELIVERY-STATUS-INSTALL-20260927.json', {}, '0'*64, root=self.root))

    def test_builder_refuses_repeat_registration(self):
        with self.assertRaisesRegex(ValueError, 'BASELINE_DRIFT'):
            reg.build(self.root, '1'*40, '2026-09-27T07:00:00+00:00')


if __name__ == '__main__':
    unittest.main()

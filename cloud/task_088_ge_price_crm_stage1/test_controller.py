#!/usr/bin/env python3
"""No-network tests for protected credential and execution/receipt identity."""
from __future__ import annotations
import copy, json, pathlib, tempfile, unittest
from unittest import mock
import controller as C
import backup_controller as B
import rollback_controller as R

class ContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.patch = mock.patch.object(C, 'ROOT', self.root); self.patch.start()
        self.manifest = {'task_id': C.TASK_ID, 'backup_required': True, 'rollback_required': True,
            'operations': [{'path': path, 'action': 'replace'} for path in sorted(C.TARGET_PATHS)],
            'crm_price_plan': {'source_before_sha256': 'a'*64, 'source_after_sha256': 'b'*64,
                              'test_car_id': 19, 'protected_paths': ['/home/Carix/publikaciya.py']}}
        self.request = {'task_id': C.TASK_ID, 'production_required': True, 'read_only': False,
            'changed_paths': sorted(C.TARGET_PATHS),
            'critical': {'gate_b_authorized': True, 'allow_crm_vehicle_data': True, 'manifest_path': 'manifest.json'},
            'execution': {'production_required': True, 'receipt_path': C.RECEIPT_REL,
                'backup_receipt_path': C.BACKUP_RECEIPT_REL, 'rollback_receipt_path': C.ROLLBACK_RECEIPT_REL,
                'controller_path': 'cloud/task_088_ge_price_crm_stage1/controller.py'}}
        self.env = {'PYTHONANYWHERE_API_TOKEN': 'fake-test-token', 'UAART_REQUEST_PATH': 'request.json',
            'UAART_TASK_ID': C.TASK_ID, 'UAART_TASK_CLASS': 'CRITICAL', 'UAART_RUN_ID': '12345',
            'UAART_RECEIPT_PATH': C.RECEIPT_REL, 'UAART_TRANSACTION_ID': 'TX-test-12345',
            'UAART_OPERATION': 'execute', 'UAART_BACKUP_MANIFEST_SHA256': 'c'*64}
        self.sync()
    def tearDown(self): self.patch.stop(); self.temp.cleanup()
    def sync(self):
        self.env['UAART_MANIFEST_SHA256'] = C.sha(C.canonical(self.manifest))
        self.request['critical']['manifest_sha256'] = self.env['UAART_MANIFEST_SHA256']
        (self.root / 'manifest.json').write_bytes(C.canonical(self.manifest))
        raw = C.canonical(self.request); (self.root / 'request.json').write_bytes(raw)
        self.env['UAART_REQUEST_SHA256'] = C.sha(raw)
    def receipt(self, mode='verify'):
        return {**C.bindings(self.env), 'mode': mode, 'status': 'PASS', 'site_write': False,
            'publisher_write': False, 'unexpected_changes': 0, 'backup_manifest_sha256': 'c'*64,
            'db': {key: 'PASS' for key in C.DB_PROOFS}, 'ui_runtime': 'PASS',
            'restored_exact': True, 'protected_files_unchanged': True, 'crm_unchanged': True,
            'live_verify': 'PASS'}
    def test_nonproduction_rejected_before_any_network(self):
        self.request['production_required'] = False; self.sync()
        api = mock.Mock()
        with self.assertRaisesRegex(C.ControllerError, 'PROTECTED_CRM_ROUTE_REQUIRED'):
            C.execute(self.env, api_factory=api)
        api.assert_not_called()
    def test_missing_pinned_live_plan_rejected_before_network(self):
        del self.manifest['crm_price_plan']; self.sync()
        api = mock.Mock()
        with self.assertRaisesRegex(C.ControllerError, 'PINNED_CRM_PLAN_REQUIRED'):
            C.execute(self.env, api_factory=api)
        api.assert_not_called()
    def test_unrelated_site_write_scope_rejected_before_network(self):
        self.request['changed_paths'].append('production/site/index.html'); self.sync()
        with self.assertRaisesRegex(C.ControllerError, 'REQUEST_CRM_SCOPE'): C.required(self.env)
    def test_request_sha_and_manifest_sha_are_bound(self):
        for key in ('UAART_REQUEST_SHA256', 'UAART_MANIFEST_SHA256'):
            with self.subTest(key=key):
                values = dict(self.env); values[key] = 'd'*64
                with self.assertRaises(C.ControllerError): C.required(values)
    def test_remote_identity_all_fields_bound_and_status_scope_checked(self):
        for key in (*C.BINDINGS, 'backup_manifest_sha256', 'mode', 'status', 'site_write', 'publisher_write', 'unexpected_changes'):
            with self.subTest(key=key):
                value = self.receipt(); value[key] = 'wrong'
                with self.assertRaises(C.ControllerError): C.validate_remote(value, 'verify', self.env)
    def test_stale_cached_receipt_cannot_trigger_or_restart(self):
        api = C.API(C.required(self.env)); stale = self.receipt('install'); stale['run_id'] = '99999'
        with mock.patch.object(api, 'read', return_value=C.canonical(stale)), mock.patch.object(api, 'request') as request:
            with self.assertRaisesRegex(C.ControllerError, 'REMOTE_IDENTITY'): api.run('install')
            request.assert_not_called()
    def test_false_ui_pass_never_creates_finished_receipt(self):
        api = mock.Mock()
        installed, verified = self.receipt('install'), self.receipt('verify')
        verified['ui_runtime'] = 'NOT_VERIFIED'; api.run.side_effect = [installed, verified]
        api.restart.return_value = {'restart_requested': True, 'ui_runtime': 'NOT_VERIFIED'}
        result = C.execute(self.env, api_factory=lambda values: api)
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn('UI_RUNTIME_NOT_VERIFIED', result['error'])
        self.assertFalse((self.root / C.RECEIPT_REL).exists())
    def test_incomplete_database_proof_never_restarts_bot(self):
        api = mock.Mock(); value = self.receipt('install'); value['db']['db_commit'] = 'NOT_TESTED'
        api.run.return_value = value
        result = C.execute(self.env, api_factory=lambda values: api)
        self.assertEqual(result['status'], 'FAIL'); api.restart.assert_not_called()
        self.assertFalse((self.root / C.RECEIPT_REL).exists())
    def test_precise_backup_and_rollback_receipt_contract_keys(self):
        base = set(C.BINDINGS) | {'backup_manifest_sha256'}
        for operation, wrapper, path, keys in (
            ('backup', B, C.BACKUP_RECEIPT_REL, {'schema_version', 'operation', 'status', 'backup', 'unexpected_changes'}),
            ('rollback', R, C.ROLLBACK_RECEIPT_REL, {'schema_version', 'operation', 'status', 'rollback', 'restored', 'unexpected_changes', 'protected_files_unchanged', 'crm_unchanged', 'live_verify'})):
            with self.subTest(operation=operation):
                env = {**self.env, 'UAART_OPERATION': operation, 'UAART_RECEIPT_PATH': path,
                       'UAART_' + operation.upper() + '_RECEIPT_PATH': path}
                api = mock.Mock(); api.run.return_value = self.receipt(operation)
                receipt = wrapper.execute(env, api_factory=lambda values: api)
                self.assertEqual(set(receipt), base | keys)
    def test_only_exact_single_enabled_bot_command_may_restart(self):
        api = C.API(C.required(self.env))
        candidates = [{'id': 7, 'enabled': True, 'command': 'python3.10 /home/Carix/start_safe.py'}]
        with mock.patch.object(api, 'request', return_value=(200, C.canonical(candidates))):
            self.assertEqual(api.bot_task()['id'], 7)
        for bad in [candidates*2, [{'id': 7, 'enabled': True, 'command': 'python3.10 /home/Carix/site.py'}]]:
            with mock.patch.object(api, 'request', return_value=(200, C.canonical(bad))):
                with self.assertRaisesRegex(C.ControllerError, 'BOT_TASK_NOT_UNIQUE'): api.restart()
    def test_each_run_and_request_has_its_own_remote_directory(self):
        values = C.required(self.env); first = C.API(values)
        second = C.API({**values, 'UAART_RUN_ID': '54321'})
        third = C.API({**values, 'UAART_REQUEST_SHA256': 'e'*64})
        self.assertEqual(len({first.directory, second.directory, third.directory}), 3)
        with self.assertRaisesRegex(C.ControllerError, 'REMOTE_SCOPE'):
            first.file_url(second.directory + '/receipt-install.json')

if __name__ == '__main__': unittest.main()

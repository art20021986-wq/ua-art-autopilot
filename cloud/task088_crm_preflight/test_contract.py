import json
import pathlib
import tempfile
import unittest
from unittest import mock

import controller
import remote_probe
import owner_preflight


def values(operation='execute'):
    value = {'PYTHONANYWHERE_API_TOKEN': 'unit-test-only', 'UAART_TASK_ID': controller.TASK_ID, 'UAART_TASK_CLASS': 'CRITICAL', 'UAART_RUN_ID': '12345', 'UAART_REQUEST_SHA256': 'a' * 64, 'UAART_TRANSACTION_ID': 'transaction-test', 'UAART_MANIFEST_SHA256': 'b' * 64, 'UAART_BACKUP_MANIFEST_SHA256': 'c' * 64, 'UAART_OPERATION': operation, 'UAART_REQUEST_PATH': 'tasks/requests/test.json'}
    receipt = {'execute': controller.RECEIPT_REL, 'backup': controller.BACKUP_RECEIPT_REL, 'rollback': controller.ROLLBACK_RECEIPT_REL}[operation]
    value['UAART_RECEIPT_PATH'] = receipt
    if operation != 'execute':
        value['UAART_' + operation.upper() + '_RECEIPT_PATH'] = receipt
    return value


def result(v):
    return {**controller.bindings(v), 'backup_manifest_sha256': v['UAART_BACKUP_MANIFEST_SHA256'], 'collection_status': 'PASS', 'crm_prices_acceptance': 'NOT_PERFORMED', 'business_source_writes': 0, 'db_writes': 0, 'site_changes': 0, 'bot_restarts': 0, 'live_modules_imported': False, 'discovery': {'storage': {'status': 'NOT_VERIFIED'}}}


class Tests(unittest.TestCase):
    def test_business_paths_are_get_only_and_credentials_not_redirected(self):
        api = controller.API(values())
        for name in controller.BUSINESS_FILES:
            url = api.file_url('/home/Carix/' + name)
            with self.assertRaises(controller.ControllerError):
                api.file_url('/home/Carix/' + name, write=True)
            with self.assertRaises(controller.ControllerError):
                api.request('POST', url, b'forbidden')
        for method, endpoint in [('POST', 'webapps/site/reload/'), ('DELETE', 'files/path/home/Carix/crm.db'), ('POST', 'always_on/1/restart/')]:
            with self.assertRaises(controller.ControllerError):
                api.request(method, controller.BASE + endpoint)
        with self.assertRaises(controller.ControllerError):
            controller.NoRedirect().redirect_request(None, None, 302, None, None, 'https://elsewhere/')

    def test_scope_auth_and_noop_required_before_network(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(controller, 'ROOT', pathlib.Path(temp)):
            root = pathlib.Path(temp)
            manifest = {'task_id': controller.TASK_ID, 'operations': [{'path': path, 'action': 'noop'} for path in sorted(controller.TARGET_PATHS)], 'backup_required': True, 'rollback_required': True, 'live_verify_required': True, 'explicit_crm_vehicle_approval': True}
            (root / 'manifest.json').write_bytes(controller.canonical(manifest))
            v = values(); v['UAART_MANIFEST_SHA256'] = controller.sha(controller.canonical(manifest)); v['UAART_REQUEST_PATH'] = 'request.json'
            req = {'task_id': controller.TASK_ID, 'read_only': True, 'production_required': True, 'changed_paths': sorted(controller.TARGET_PATHS), 'critical': {'gate_b_authorized': True, 'allow_crm_vehicle_data': True, 'manifest_path': 'manifest.json', 'manifest_sha256': v['UAART_MANIFEST_SHA256']}, 'execution': {'production_required': True, 'controller_path': controller.PACKAGE + '/controller.py', 'receipt_path': controller.RECEIPT_REL, 'backup_receipt_path': controller.BACKUP_RECEIPT_REL, 'rollback_receipt_path': controller.ROLLBACK_RECEIPT_REL}}
            for field, bad in [('read_only', False), ('production_required', False)]:
                current = {**req, field: bad}; raw = controller.canonical(current); (root / 'request.json').write_bytes(raw); v['UAART_REQUEST_SHA256'] = controller.sha(raw)
                with self.assertRaises(controller.ControllerError):
                    controller.required(v, 'execute')
            raw = controller.canonical(req); (root / 'request.json').write_bytes(raw); v['UAART_REQUEST_SHA256'] = controller.sha(raw)
            self.assertEqual(controller.required(v, 'execute')['UAART_TASK_ID'], controller.TASK_ID)

    def test_backup_uses_only_source_reads_and_strict_receipt(self):
        v = values('backup'); api = controller.API(v); calls = []
        def read(path, missing=False):
            calls.append(path)
            return b'pass\n' if path.endswith('cars_ui.py') else None
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(controller, 'ROOT', pathlib.Path(temp)), mock.patch.object(controller, 'required', return_value=v), mock.patch.object(api, 'read', side_effect=read):
            receipt = controller.backup(v, lambda _: api)
        self.assertEqual(calls, ['/home/Carix/' + name for name in controller.BUSINESS_FILES])
        self.assertEqual(set(receipt), set(controller.BINDINGS) | {'schema_version', 'operation', 'status', 'backup', 'backup_manifest_sha256', 'unexpected_changes'})

    def test_immutable_upload_readback_rejects_preexisting_mismatch(self):
        api = controller.API(values())
        with mock.patch.object(api, 'read', return_value=b'old'), mock.patch.object(api, 'request') as request:
            with self.assertRaises(controller.ControllerError):
                api.upload('plan.json', b'new')
            request.assert_not_called()

    def test_remote_accepts_partial_readiness_but_rejects_wrong_identity_and_mutation(self):
        v = values(); good = result(v)
        controller.validate_remote(good, v)
        for field, bad in [('run_id', 'other'), ('backup_manifest_sha256', 'd' * 64), ('db_writes', 1), ('site_changes', False), ('crm_prices_acceptance', 'PASS'), ('live_modules_imported', True)]:
            with self.subTest(field=field), self.assertRaises(controller.ControllerError):
                controller.validate_remote({**good, field: bad}, v)

    def test_timeout_deletes_only_exact_created_trigger(self):
        v = values(); api = controller.API(v); items = [{'id': 9, 'command': 'python3.10 /home/Carix/start_safe.py', 'description': 'business bot'}]; deleted = []
        def request(method, url, *args, **kwargs):
            if method == 'POST':
                items.append({'id': 12, 'command': api.command(), 'description': api.description()}); return 201, b'{"id":12}'
            if method == 'DELETE':
                deleted.append(url); items[:] = [item for item in items if item['id'] != 12]; return 204, b''
            raise AssertionError('unexpected request')
        with mock.patch.object(api, 'read', return_value=None), mock.patch.object(api, 'upload'), mock.patch.object(api, 'tasks', side_effect=lambda: list(items)), mock.patch.object(api, 'request', side_effect=request):
            with self.assertRaisesRegex(controller.ControllerError, 'REMOTE_TIMEOUT'):
                api.collect({'sources': {}}, timeout=0)
        self.assertEqual(deleted, [controller.BASE + 'always_on/12/'])
        self.assertEqual(items[0]['id'], 9)

    def test_cleanup_refuses_mismatched_record_without_delete(self):
        api = controller.API(values())
        record = {**controller.bindings(api.values), 'id': 13}
        with mock.patch.object(api, 'read', return_value=controller.canonical(record)), mock.patch.object(api, 'tasks', return_value=[{'id': 12, 'command': api.command(), 'description': api.description()}]), mock.patch.object(api, 'request') as request:
            with self.assertRaises(controller.ControllerError):
                api.cleanup()
            request.assert_not_called()

    def test_remote_runner_once_only_preserves_partial_result(self):
        v = values(); plan = {**controller.bindings(v), 'backup_manifest_sha256': v['UAART_BACKUP_MANIFEST_SHA256']}
        discovery = {'read_only': True, 'crm_prices_acceptance': 'NOT_PERFORMED', 'db_writes': 0, 'site_changes': 0, 'bot_restarts': 0, 'live_modules_imported': False, 'storage': {'status': 'NOT_VERIFIED'}}
        collector = mock.Mock(return_value=discovery)
        with tempfile.TemporaryDirectory() as temp:
            here = pathlib.Path(temp)
            first = remote_probe.collect_once(plan, collector, here)
            original = (here / 'result.json').read_bytes()
            self.assertIsNone(remote_probe.collect_once(plan, collector, here))
            self.assertEqual((here / 'result.json').read_bytes(), original)
            self.assertEqual(first['collection_status'], 'PASS')
        collector.assert_called_once()

    def test_remote_plan_requires_exact_directory_and_all_file_hashes(self):
        v = values(); plan = {**controller.bindings(v), 'backup_manifest_sha256': v['UAART_BACKUP_MANIFEST_SHA256']}
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp); here = root / (v['UAART_RUN_ID'] + '-' + v['UAART_REQUEST_SHA256']); here.mkdir()
            plan['remote_source_sha256'] = {}
            for name in remote_probe.SOURCES:
                payload = b'# pinned\n'; (here / name).write_bytes(payload); plan['remote_source_sha256'][name] = controller.sha(payload)
            remote_probe.validate_plan(plan, here, root)
            (here / 'owner_preflight.py').write_bytes(b'# drift\n')
            with self.assertRaises(ValueError):
                remote_probe.validate_plan(plan, here, root)

    def test_execute_and_rollback_refuse_source_drift_without_business_write(self):
        v = values(); api = mock.Mock(); snapshot = {'sources': {'cars_ui.py': {'sha256': 'e' * 64}}}; v['UAART_BACKUP_MANIFEST_SHA256'] = controller.sha(controller.canonical(snapshot)); api.snapshot.side_effect = [snapshot, {'drift': True}]; api.collect.return_value = result(v)
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(controller, 'ROOT', pathlib.Path(temp)), mock.patch.object(controller, 'required', return_value=v):
            evidence = controller.execute(v, lambda _: api)
            self.assertEqual(evidence['status'], 'FAIL')
            self.assertFalse((pathlib.Path(temp) / controller.RECEIPT_REL).exists())
            api.snapshot.side_effect = None; api.snapshot.return_value = {'drift': True}
            with self.assertRaisesRegex(controller.ControllerError, 'SOURCE_DRIFT_REFUSE_OVERWRITE'):
                controller.rollback(v, lambda _: api)

    def test_failure_log_sanitizer_omits_source_and_secret_values(self):
        raw = b'File "/home/Carix/autopilot_inbox/task/remote_probe.py", line 88\n  token="never-export-this"\nValueError: arbitrary-sensitive-value\nTASK088_PREFLIGHT_DIAGNOSTIC {"phase":"startup_or_result_publication","error_type":"ValueError","error_code":"PACKAGE_SHA","token":"never-export-this"}\n'
        safe = controller.sanitize_task_log(raw)
        self.assertNotIn('never-export-this', json.dumps(safe))
        self.assertNotIn('arbitrary-sensitive-value', json.dumps(safe))
        self.assertEqual(safe['exception_types'], ['ValueError'])
        self.assertEqual(safe['package_frames'], [{'filename': 'remote_probe.py', 'line': 88}])
        self.assertEqual(safe['diagnostic_signals'][0]['error_code'], 'PACKAGE_SHA')

    def test_import_failure_is_durably_reported_after_once_only_claim(self):
        v = values(); plan = {**controller.bindings(v), 'backup_manifest_sha256': v['UAART_BACKUP_MANIFEST_SHA256']}
        def bad_import():
            raise ModuleNotFoundError('private-sensitive-text')
        with tempfile.TemporaryDirectory() as temp:
            here = pathlib.Path(temp)
            value = remote_probe.collect_once(plan, bad_import, here)
            self.assertEqual(value['collection_status'], 'FAIL')
            self.assertEqual(value['error_type'], 'ModuleNotFoundError')
            self.assertTrue((here / 'started.json').exists())
            payload = (here / 'result.json').read_text()
            self.assertNotIn('private-sensitive-text', payload)
        # Protected-tree enumeration must stop during traversal, before hashing.
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp); (root / 'site').mkdir()
            for index in range(5):
                (root / 'site' / str(index)).write_bytes(b'file')
            with mock.patch.object(owner_preflight.time, 'monotonic', side_effect=[0, 0, 0, 21] + [21] * 20), mock.patch.object(pathlib.Path, 'rglob', side_effect=AssertionError('unbounded traversal')):
                observed = owner_preflight.protected_probe(root)
            self.assertEqual(observed['site']['status'], 'NOT_VERIFIED')
            self.assertEqual(observed['site']['diagnostic_code'], 'PROTECTED_HASH_BUDGET')
            self.assertNotIn('tree_sha256', observed['site'])


if __name__ == '__main__':
    unittest.main()

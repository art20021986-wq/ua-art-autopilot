import json
import pathlib
import tempfile
import unittest
from unittest import mock
import controller
import read_existing


def values():
    return {'PYTHONANYWHERE_API_TOKEN': 'test-only', 'UAART_TASK_ID': controller.TASK_ID,
            'UAART_RUN_ID': '98765', 'UAART_REQUEST_SHA256': 'a' * 64,
            'UAART_TRANSACTION_ID': 'tx-98765-' + 'a' * 16, 'UAART_MANIFEST_SHA256': 'b' * 64,
            'UAART_BACKUP_MANIFEST_SHA256': 'c' * 64}


def payloads():
    return {'/home/Carix/' + name: b'raise RuntimeError("source-secret-never-export")\n' for name in controller.BUSINESS_FILES}


class Tests(unittest.TestCase):
    def test_remote_mutations_and_unrelated_reads_rejected_before_network(self):
        api = controller.API(values())
        with mock.patch.object(api.opener, 'open') as network:
            for method, endpoint in [('POST', 'always_on/'), ('DELETE', 'always_on/12/'), ('GET', 'files/path/home/Carix/.env'), ('GET', 'files/path/home/Carix/crm.db'), ('GET', 'files/path/var/log/alwayson-log-12.log')]:
                with self.subTest(method=method, endpoint=endpoint), self.assertRaises(controller.ControllerError):
                    api.request(method, controller.BASE + endpoint)
            network.assert_not_called()

    def test_redirect_refused(self):
        with self.assertRaises(controller.ControllerError):
            controller.NoRedirect().redirect_request(None, None, 302, None, None, 'https://example.invalid')

    def test_prior_log_requires_exact_original_task_identity(self):
        api = controller.API(values())
        with self.assertRaisesRegex(controller.ControllerError, 'PRIOR_TRIGGER_IDENTITY'):
            api.authorize_prior_log({**controller.PRIOR_IDENTITY, 'id': 12, 'run_id': 'wrong'})
        self.assertIsNone(api.prior_log_id)
        api.authorize_prior_log({**controller.PRIOR_IDENTITY, 'id': 12})
        self.assertEqual(api.prior_log_id, 12)

    def test_missing_evidence_is_reported_without_remote_execution_or_fake_price_pass(self):
        api = controller.API(values())
        files = payloads()
        with mock.patch.object(api, 'read', side_effect=lambda path, missing=False: files.get(path)):
            snapshot = api.snapshot()
            result = read_existing.collect(api, snapshot)
        self.assertEqual(result['collection_status'], 'PASS')
        self.assertEqual(result['crm_prices_acceptance'], 'NOT_PERFORMED')
        self.assertFalse(result['discovery']['prior_run']['result']['exists'])
        self.assertEqual(result['discovery']['remote_processes_created'], 0)
        self.assertEqual(result['discovery']['candidate']['status'], 'NOT_VERIFIED')
        self.assertNotIn('source-secret-never-export', json.dumps(result))

    def test_old_result_identity_mismatch_not_imported_as_current_discovery(self):
        api = controller.API(values())
        files = payloads()
        files[controller.PRIOR_DIRECTORY + '/result.json'] = json.dumps({'task_id': 'other', 'secret': 'private-value'}).encode()
        with mock.patch.object(api, 'read', side_effect=lambda path, missing=False: files.get(path)):
            result = read_existing.collect(api, api.snapshot())
        prior = result['discovery']['prior_run']['result']
        self.assertFalse(prior['identity_matches'])
        self.assertNotIn('private-value', json.dumps(result))

    def test_current_source_drift_stops_collection(self):
        api = controller.API(values())
        files = payloads()
        with mock.patch.object(api, 'read', side_effect=lambda path, missing=False: files.get(path)):
            snapshot = api.snapshot()
            files['/home/Carix/cars_ui.py'] = b'pass\n'
            with self.assertRaisesRegex(controller.ControllerError, 'SOURCE_DRIFT_DURING_READ'):
                read_existing.collect(api, snapshot)

    def test_log_redaction_keeps_only_error_types_and_known_package_frames(self):
        value = read_existing.safe_log(b'File "/home/Carix/remote_probe.py", line 42\nModuleNotFoundError: source-secret\nTOKEN=private-value\n')
        self.assertEqual(value['exception_types'], ['ModuleNotFoundError'])
        self.assertEqual(value['package_frames'], [{'file': 'remote_probe', 'line': 42}])
        self.assertNotIn('source-secret', json.dumps(value))
        self.assertNotIn('private-value', json.dumps(value))

    def test_failure_never_creates_finished_receipt(self):
        v = values()
        api = mock.Mock()
        api.snapshot.return_value = {'sources': {}}
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(controller, 'ROOT', pathlib.Path(temp)), mock.patch.object(controller, 'required', return_value=v):
            result = controller.execute(v, lambda _: api)
            self.assertEqual(result['status'], 'FAIL')
            self.assertIn('SOURCE_DRIFT_SINCE_BACKUP', result['error'])
            self.assertFalse((pathlib.Path(temp) / controller.RECEIPT_REL).exists())
            api.collect.assert_not_called()

    def test_success_receipt_is_get_only_not_crm_acceptance(self):
        v = values()
        snapshot = {'sources': {}}
        v['UAART_BACKUP_MANIFEST_SHA256'] = controller.sha(controller.canonical(snapshot))
        api = mock.Mock()
        api.snapshot.return_value = snapshot
        api.collect.return_value = {**controller.bindings(v), 'backup_manifest_sha256': v['UAART_BACKUP_MANIFEST_SHA256'], 'collection_status': 'PASS', 'crm_prices_acceptance': 'NOT_PERFORMED', 'business_source_writes': 0, 'db_writes': 0, 'site_changes': 0, 'bot_restarts': 0, 'live_modules_imported': False, 'discovery': {'mode': 'GET_ONLY_NO_REMOTE_PROCESS'}}
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(controller, 'ROOT', pathlib.Path(temp)), mock.patch.object(controller, 'required', return_value=v):
            self.assertEqual(controller.execute(v, lambda _: api)['status'], 'PASS')
            receipt = json.loads((pathlib.Path(temp) / controller.RECEIPT_REL).read_text())
            self.assertEqual(receipt['status'], 'FINISHED')
            self.assertEqual(receipt['crm_prices_acceptance'], 'NOT_PERFORMED')
            self.assertIn('GET_ONLY', receipt['verification_scope'])

    def test_rollback_uses_only_snapshot_without_remote_trigger_cleanup(self):
        v = values()
        api = mock.Mock()
        api.snapshot.return_value = {'sources': {}}
        v['UAART_BACKUP_MANIFEST_SHA256'] = controller.sha(controller.canonical(api.snapshot.return_value))
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(controller, 'ROOT', pathlib.Path(temp)), mock.patch.object(controller, 'required', return_value=v):
            self.assertEqual(controller.rollback(v, lambda _: api)['status'], 'ROLLED_BACK')
        api.cleanup.assert_not_called()


if __name__ == '__main__':
    unittest.main()

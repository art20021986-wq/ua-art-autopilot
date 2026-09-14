"""Actual adapter safety tests use public TEST fixtures and temporary roots only.

In the flat reviewed release package all dependencies live beside this file.
The source layout explicitly binds its reviewed sibling package; no environment
search path or current working directory participates in imports.
"""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
if HERE.name == "task088_v5_install":
    dependencies = HERE.parent / "task088_price_sync"
    if dependencies.is_symlink() or not all((dependencies / name).is_file() for name in
            ("install_package.py", "test_install_package.py", "outbox.py")):
        raise RuntimeError("EXACT_PUBLIC_INSTALLER_TEST_DEPENDENCIES_REQUIRED")
    sys.path.insert(1, str(dependencies))
elif HERE.name != "release" or not (HERE / "install_package.py").is_file():
    raise RuntimeError("EXACT_PUBLIC_INSTALLER_TEST_LAYOUT_REQUIRED")

import controller as C
import remote_adapter as R
import install_package as E
import test_install_package as fixtures


class RemoteSafetyTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.InstallTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root

    def backup(self):
        return R.backup(self.fixture.plan, self.fixture.files, self.fixture.evidence, self.root)

    def test_preparing_phase_backs_up_full_site_and_db_without_installing(self):
        before = E.system_inventory(self.root)
        result = self.backup()
        self.assertEqual(result["status"], "BACKUP_PASS")
        self.assertEqual(E.system_inventory(self.root), before)
        self.fixture.assert_original_database()
        self.assertEqual((Path(result["backup_directory"]) / "full/video/photo.jpg").read_bytes(), b"untouched photo bytes")

    def test_preparing_backup_refuses_source_drift(self):
        (self.root / "cars_ui.py").write_bytes(b"# another operator source")
        with self.assertRaisesRegex(E.InstallError, "CURRENT_SNAPSHOT_DRIFT"):
            self.backup()
        self.fixture.assert_original_database()

    def test_preparing_backup_never_replaces_historical_backup(self):
        first = self.backup()
        path = Path(first["backup_directory"]) / "manifest.json"
        previous = path.read_bytes()
        with self.assertRaises(FileExistsError):
            self.backup()
        self.assertEqual(path.read_bytes(), previous)

    def test_install_then_independent_verify_then_empty_schema_rollback(self):
        result = self.backup()
        self.fixture.call()
        checked = R.verify(self.fixture.plan, self.fixture.files, self.root)
        self.assertEqual(checked["status"], "INSTALLATION_VERIFIED")
        self.assertFalse(checked["stage3_complete"])
        restored = R.rollback(self.fixture.plan, self.fixture.files, self.root, result["backup_manifest_sha256"])
        self.assertEqual(restored["status"], "ROLLED_BACK")
        self.fixture.assert_no_candidate_files()
        self.fixture.assert_original_database()

    def test_rollback_never_overwrites_newer_operator_prices(self):
        result = self.backup()
        self.fixture.call()
        self.fixture.db.execute("UPDATE cars SET price_georgia=8500 WHERE id=7")
        self.fixture.db.commit()
        restored = R.rollback(self.fixture.plan, self.fixture.files, self.root, result["backup_manifest_sha256"])
        self.assertEqual(restored["status"], "ROLLED_BACK")
        self.assertEqual(self.fixture.db.execute("SELECT price_georgia FROM cars WHERE id=7").fetchone()[0], 8500)

    def test_rollback_preserves_later_unrelated_file_changes(self):
        result = self.backup()
        self.fixture.call()
        photo = self.root / "video/photo.jpg"
        photo.write_bytes(b"new legitimate photo bytes")
        restored = R.rollback(self.fixture.plan, self.fixture.files, self.root, result["backup_manifest_sha256"])
        self.assertEqual(restored["status"], "ROLLED_BACK")
        self.assertEqual(photo.read_bytes(), b"new legitimate photo bytes")

    def test_rollback_preserves_new_v5_audit_and_all_installed_files(self):
        result = self.backup()
        self.fixture.call()
        self.fixture.db.execute("INSERT INTO uaart_price_audit_v5(event_key,fact,payload_json,created_ms) VALUES('new','ACTUAL','{}',1)")
        self.fixture.db.commit()
        before = E.system_inventory(self.root)
        with self.assertRaisesRegex(E.InstallError, "ACTIVE_OPERATIONS_OR_AUDIT_PRESERVED"):
            R.rollback(self.fixture.plan, self.fixture.files, self.root, result["backup_manifest_sha256"])
        self.assertEqual(E.system_inventory(self.root), before)
        self.assertEqual(self.fixture.db.execute("SELECT count(*) FROM uaart_price_audit_v5").fetchone()[0], 1)

    def test_rollback_preserves_foreign_file_before_any_mutation(self):
        result = self.backup()
        self.fixture.call()
        (self.root / "cars_ui.py").write_bytes(b"# foreign new source")
        before = E.system_inventory(self.root)
        with self.assertRaisesRegex(E.InstallError, "FOREIGN_WRITE_CONFLICT"):
            R.rollback(self.fixture.plan, self.fixture.files, self.root, result["backup_manifest_sha256"])
        self.assertEqual(E.system_inventory(self.root), before)

    def test_rollback_refuses_backup_hash_substitution(self):
        self.backup()
        self.fixture.call()
        with self.assertRaisesRegex(E.InstallError, "BACKUP_HASH_MISMATCH"):
            R.rollback(self.fixture.plan, self.fixture.files, self.root, "a" * 64)

    def test_backup_schema_corruption_refuses_restore_before_any_mutation(self):
        result = self.backup()
        self.fixture.call()
        (Path(result["backup_directory"]) / "schema.json").write_bytes(b"[]")
        before = E.system_inventory(self.root)
        with self.assertRaisesRegex(E.InstallError, "BACKUP_SCHEMA_CORRUPTED"):
            R.rollback(self.fixture.plan, self.fixture.files, self.root, result["backup_manifest_sha256"])
        self.assertEqual(E.system_inventory(self.root), before)

    def test_backup_database_corruption_refuses_restore_before_any_mutation(self):
        result = self.backup()
        self.fixture.call()
        (Path(result["backup_directory"]) / "crm.sqlite").write_bytes(b"invalid backup")
        before = E.system_inventory(self.root)
        with self.assertRaisesRegex(E.InstallError, "BACKUP_DATABASE_CORRUPTED"):
            R.rollback(self.fixture.plan, self.fixture.files, self.root, result["backup_manifest_sha256"])
        self.assertEqual(E.system_inventory(self.root), before)

    def test_backup_untouched_media_corruption_refuses_restore_before_any_mutation(self):
        result = self.backup()
        self.fixture.call()
        (Path(result["backup_directory"]) / "full/video/photo.jpg").write_bytes(b"corrupted media")
        before = E.system_inventory(self.root)
        with self.assertRaisesRegex(E.InstallError, "BACKUP_FILE_CORRUPTED:video/photo.jpg"):
            R.rollback(self.fixture.plan, self.fixture.files, self.root, result["backup_manifest_sha256"])
        self.assertEqual(E.system_inventory(self.root), before)

    def test_exact_phase_validation_does_not_accept_preparing_for_install(self):
        f = self.fixture
        evidence = dict(f.evidence)
        for key in ("claim", "transaction"):
            value = json.loads(evidence[key])
            value["production_transaction_status" if key == "claim" else "status"] = "PREPARING"
            evidence[key] = E.encoded(value)
        plan = dict(f.plan, evidence_sha256={name: E.sha(raw) for name, raw in evidence.items()})
        E._validate(plan, f.files, evidence, f.now, f.root, testing=True, phase="PREPARING")
        with self.assertRaisesRegex(E.InstallError, "ACTIVE_CANONICAL_CLAIM_TRANSACTION_REQUIRED"):
            E._validate(plan, f.files, evidence, f.now, f.root, testing=True)


class ControllerBoundaryTests(unittest.TestCase):
    def test_supervisor_accepts_actual_provider_running_state(self):
        api = C.API({"UAART_RUN_ID": "123", "UAART_REQUEST_SHA256": "a" * 64, "PYTHONANYWHERE_API_TOKEN": "TEST-ONLY"})
        actual_shape = {"id": 266084, "command": "python3.10 /home/Carix/start_safe.py", "enabled": True, "state": "Running"}
        with patch.object(api, "request", return_value=(200, json.dumps(actual_shape).encode())) as network:
            result = api.supervisor()
        self.assertEqual(result["state"], "Running")
        self.assertFalse(result["restarted"])
        self.assertEqual(network.call_args.args[0], "GET")

    def test_missing_actual_execution_identity_is_rejected_before_network(self):
        with patch.object(C.API, "request") as network:
            with self.assertRaisesRegex(C.ControllerError, "COMPLETE_CANONICAL_ENVIRONMENT"):
                C.perform({}, "execute")
        network.assert_not_called()

    def test_api_refuses_arbitrary_file_name_or_origin(self):
        api = C.API({"UAART_RUN_ID": "123", "UAART_REQUEST_SHA256": "a" * 64, "PYTHONANYWHERE_API_TOKEN": "TEST-ONLY"})
        with self.assertRaisesRegex(C.ControllerError, "EXACT_RUN_FILE_SCOPE"):
            api.file_url("../../cars_ui.py")
        with self.assertRaisesRegex(C.ControllerError, "API_ORIGIN_SCOPE"):
            api.request("POST", "https://example.invalid/")

    def test_existing_run_payload_is_immutable(self):
        api = C.API({"UAART_RUN_ID": "123", "UAART_REQUEST_SHA256": "a" * 64, "PYTHONANYWHERE_API_TOKEN": "TEST-ONLY"})
        with patch.object(api, "read", return_value=b"old plan"), patch.object(api, "request") as network:
            with self.assertRaisesRegex(C.ControllerError, "EXISTING_REMOTE_RUN_FILE_DRIFT"):
                api.upload("execute-plan.json", b"different plan")
        network.assert_not_called()

    def test_remote_finished_boolean_is_not_an_installation_result(self):
        values = {"BINDINGS": {"task_id": "TASK088-TEST"}, "BACKUP_SHA": "a" * 64}
        with self.assertRaisesRegex(C.ControllerError, "REMOTE_RESULT_BINDING"):
            C.validate_remote({"status": "FINISHED", "stage3_complete": True}, values, "verify")

    def test_own_runner_cleanup_cannot_delete_another_supervisor(self):
        api = C.API({"UAART_RUN_ID": "123", "UAART_REQUEST_SHA256": "a" * 64, "PYTHONANYWHERE_API_TOKEN": "TEST-ONLY"})
        with patch.object(api, "request", return_value=(200, json.dumps({"id": 999, "command": "other", "enabled": True, "state": "running"}).encode())):
            with self.assertRaisesRegex(C.ControllerError, "EXACT_EXISTING_CRM_SUPERVISOR"):
                api.supervisor()

    def test_routing_accepts_observed_provider_path_shape_using_get_only(self):
        api = C.API({"UAART_RUN_ID": "123", "UAART_REQUEST_SHA256": "a" * 64, "PYTHONANYWHERE_API_TOKEN": "TEST-ONLY"})
        responses = [(200, json.dumps([{"domain_name": "www.uaart.com.ua", "enabled": True, "python_version": "3.10"}]).encode()),
                     (200, json.dumps([{"id": 2185199, "path": "/home/Carix/video/", "url": "/video/"}]).encode())]
        with patch.object(api, "request", side_effect=responses) as network:
            result = api.routing()
        self.assertFalse(result["provider_configuration_written"])
        self.assertEqual(len(network.call_args_list), 2)
        self.assertTrue(all(call.args[0] == "GET" for call in network.call_args_list))

    def test_changed_provider_mapping_is_rejected(self):
        api = C.API({"UAART_RUN_ID": "123", "UAART_REQUEST_SHA256": "a" * 64, "PYTHONANYWHERE_API_TOKEN": "TEST-ONLY"})
        responses = [(200, json.dumps([{"domain_name": "www.uaart.com.ua", "enabled": True, "python_version": "3.10"}]).encode()),
                     (200, json.dumps([{"path": "/home/Carix/site/", "url": "/video/"}]).encode())]
        with patch.object(api, "request", side_effect=responses):
            with self.assertRaisesRegex(C.ControllerError, "EXACT_EXISTING_STATIC_ROUTING_REQUIRED"):
                api.routing()


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Offline tests for the TASK120 CRITICAL workflow envelope."""
from __future__ import annotations

import inspect
import importlib.util
import json
import os
import pathlib
import sqlite3
import struct
import sys
import tempfile
import unittest

import controller


class EnvironmentContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temporary.name)
        self.old_root = controller.ROOT
        controller.ROOT = self.root
        manifest = {
            "contract_id": controller.CRITICAL_CONTRACT,
            "task_id": controller.TASK_ID,
            "task_class": "CRITICAL",
            "production_write": True,
            "explicit_crm_vehicle_approval": True,
        }
        manifest_sha = controller._sha(controller._canonical(manifest))
        manifest_path = self.root / controller.MANIFEST_REL
        manifest_path.parent.mkdir(parents=True)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        request = {
            "task_id": controller.TASK_ID,
            "production_required": True,
            "requested_min_class": "CRITICAL",
            "critical": {
                "manifest_path": controller.MANIFEST_REL,
                "manifest_sha256": manifest_sha,
            },
            "execution": {
                "controller_path": controller.CONTROLLER_REL,
                "backup_controller_path": controller.BACKUP_CONTROLLER_REL,
                "rollback_controller_path": controller.ROLLBACK_CONTROLLER_REL,
                "receipt_path": controller.RECEIPT_REL,
                "backup_receipt_path": controller.BACKUP_RECEIPT_REL,
                "rollback_receipt_path": controller.ROLLBACK_RECEIPT_REL,
            },
        }
        request_path = self.root / controller.REQUEST_REL
        request_path.parent.mkdir(parents=True)
        request_path.write_text(json.dumps(request), encoding="utf-8")
        self.environment = {
            "PYTHONANYWHERE_API_TOKEN": "secret",
            "UAART_OPERATION": "execute",
            "UAART_REQUEST_PATH": controller.REQUEST_REL,
            "UAART_REQUEST_SHA256": controller._sha(request_path.read_bytes()),
            "UAART_TASK_ID": controller.TASK_ID,
            "UAART_TASK_CLASS": "CRITICAL",
            "UAART_RUN_ID": "run-120",
            "UAART_TRANSACTION_ID": "transaction-120",
            "UAART_MANIFEST_SHA256": manifest_sha,
            "UAART_BACKUP_MANIFEST_SHA256": "b" * 64,
            "UAART_RECEIPT_PATH": controller.RECEIPT_REL,
        }

    def tearDown(self) -> None:
        controller.ROOT = self.old_root
        self.temporary.cleanup()

    def test_execute_envelope_and_exact_receipt(self) -> None:
        values, request = controller.required(self.environment, "execute")
        self.assertEqual(request["task_id"], controller.TASK_ID)
        self.assertEqual(
            controller.receipt_target(values), self.root / controller.RECEIPT_REL
        )

    def test_backup_and_rollback_aliases_are_exact(self) -> None:
        backup = dict(self.environment)
        backup.update({
            "UAART_OPERATION": "backup",
            "UAART_RECEIPT_PATH": controller.BACKUP_RECEIPT_REL,
            "UAART_BACKUP_RECEIPT_PATH": controller.BACKUP_RECEIPT_REL,
        })
        backup.pop("UAART_BACKUP_MANIFEST_SHA256")
        controller.required(backup, "backup")
        rollback = dict(self.environment)
        rollback.update({
            "UAART_OPERATION": "rollback",
            "UAART_RECEIPT_PATH": controller.ROLLBACK_RECEIPT_REL,
            "UAART_ROLLBACK_RECEIPT_PATH": controller.ROLLBACK_RECEIPT_REL,
        })
        controller.required(rollback, "rollback")
        rollback["UAART_ROLLBACK_RECEIPT_PATH"] = "state/receipts/wrong.json"
        with self.assertRaisesRegex(controller.ControllerError, "RECEIPT_ALIAS_IDENTITY"):
            controller.required(rollback, "rollback")

    def test_identity_mismatches_fail_before_network(self) -> None:
        for key, wrong in (
            ("UAART_TASK_ID", "TASK-WRONG"),
            ("UAART_TASK_CLASS", "STANDARD"),
            ("UAART_RUN_ID", "bad/run"),
            ("UAART_MANIFEST_SHA256", "0" * 64),
            ("UAART_BACKUP_MANIFEST_SHA256", "short"),
            ("UAART_RECEIPT_PATH", "state/receipts/wrong.json"),
        ):
            with self.subTest(key=key):
                changed = dict(self.environment)
                changed[key] = wrong
                with self.assertRaises(controller.ControllerError):
                    controller.required(changed, "execute")

    def test_primary_uses_backup_a_without_second_backup(self) -> None:
        source = inspect.getsource(controller.execute)
        self.assertIn('required(environment, "execute")', source)
        self.assertIn('"publish",', source)
        self.assertIn('backup_sha=values["UAART_BACKUP_MANIFEST_SHA256"]', source)
        self.assertNotIn('api.run("backup"', source)
        self.assertNotIn('api.run("probe"', source)
        main_source = inspect.getsource(controller.main)
        self.assertIn("execute(os.environ)", main_source)

    def test_api_run_passes_sha_without_manifest_path(self) -> None:
        api = controller.API("token")
        captured: dict[str, str] = {}
        active = False
        deleted: set[str] = set()

        def delete_file(path: str) -> None:
            deleted.add(path)

        api.delete_file = delete_file  # type: ignore[method-assign]

        def trigger(
            command: str, _description: str, *, allow_schedule: bool
        ) -> tuple[str, int]:
            nonlocal active
            self.assertFalse(allow_schedule)
            captured["command"] = command
            active = True
            return "always_on", 1

        api.trigger = trigger  # type: ignore[method-assign]
        api.delete_trigger = lambda _trigger: None  # type: ignore[method-assign]

        def read(path: str, missing: bool = False) -> bytes | None:
            del missing
            if path in deleted or not active:
                return None
            name = pathlib.PurePosixPath(path).stem
            run_id = name.removeprefix("task120-receipt-").removeprefix(
                "task120-completed-"
            )
            return json.dumps({"run_id": run_id}).encode()

        api.read = read  # type: ignore[method-assign]
        api.run(
            "publish", "a" * 64,
            workflow_run_id="run-120", transaction_id="transaction-120",
            backup_sha="b" * 64, timeout=1,
        )
        self.assertIn("--backup-manifest-sha256 " + "b" * 64, captured["command"])
        self.assertNotIn("--backup-manifest ", captured["command"])
        self.assertIn("python3.10 -B", captured["command"])

    def test_package_modules_compile_and_wrappers_are_env_only(self) -> None:
        package = pathlib.Path(__file__).resolve().parent
        for name in ("controller.py", "backup_controller.py", "rollback_controller.py"):
            source = (package / name).read_text(encoding="utf-8")
            compile(source, name, "exec")
            self.assertNotIn("argparse", source)
            self.assertIn("os.environ", source)


class RemoteSemanticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.old_test_root = os.environ.get("UAART_TASK120_TEST_ROOT")
        cls.old_allow = os.environ.get("UAART_TASK120_ALLOW_TEST_ROOT")
        os.environ["UAART_TASK120_TEST_ROOT"] = cls.temporary.name
        os.environ["UAART_TASK120_ALLOW_TEST_ROOT"] = "1"
        path = pathlib.Path(__file__).resolve().parent / "remote_installer.py"
        spec = importlib.util.spec_from_file_location("task120_remote_test", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        cls.remote = module

    @classmethod
    def tearDownClass(cls) -> None:
        sys.modules.pop("task120_remote_test", None)
        if cls.old_test_root is None:
            os.environ.pop("UAART_TASK120_TEST_ROOT", None)
        else:
            os.environ["UAART_TASK120_TEST_ROOT"] = cls.old_test_root
        if cls.old_allow is None:
            os.environ.pop("UAART_TASK120_ALLOW_TEST_ROOT", None)
        else:
            os.environ["UAART_TASK120_ALLOW_TEST_ROOT"] = cls.old_allow
        cls.temporary.cleanup()

    @staticmethod
    def _box(kind: bytes, payload: bytes) -> bytes:
        return struct.pack(">I4s", len(payload) + 8, kind) + payload

    @classmethod
    def _mp4(cls, matrix: tuple[int, ...]) -> bytes:
        ftyp = cls._box(b"ftyp", b"isom\0\0\0\0isom")
        mvhd = cls._box(
            b"mvhd", b"\0" * 12 + struct.pack(">II", 1000, 1000) + b"\0" * 8
        )
        tkhd_payload = (
            b"\0" * 40
            + b"".join(struct.pack(">i", value) for value in matrix)
            + struct.pack(">II", 320 << 16, 240 << 16)
        )
        tkhd = cls._box(b"tkhd", tkhd_payload)
        hdlr = cls._box(b"hdlr", b"\0" * 8 + b"vide" + b"\0" * 4)
        trak = cls._box(b"trak", tkhd + cls._box(b"mdia", hdlr))
        moov = cls._box(b"moov", mvhd + trak)
        return ftyp + moov + cls._box(b"mdat", b"0" * 10_000)

    def test_legacy_fact_and_runtime_contract(self) -> None:
        self.assertEqual({uid: len(rows) for uid, rows in self.remote.FACTS.items()}, {
            "UA-0017": 18, "UA-0018": 12,
        })
        self.assertEqual(
            self.remote.EXPECTED_RUNTIME_HASHES["catalog_design_golden.html"],
            "34fb82b9ec1bc66b76fccbbaad9b440d01ea4d60fe5c195954e88251442ecdd0",
        )
        source = (pathlib.Path(__file__).resolve().parent / "remote_installer.py").read_text()
        self.assertNotIn("ua116_spec_revision", source)
        self.assertNotIn("REVISION =", source)

    def test_rotated_horizontal_mp4_is_display_vertical(self) -> None:
        identity = (65536, 0, 0, 0, 65536, 0, 0, 0, 1073741824)
        quarter = (0, 65536, 0, -65536, 0, 0, 0, 0, 1073741824)
        with self.assertRaisesRegex(self.remote.Task120Error, "NOT_VERTICAL"):
            self.remote._mp4_video_metadata(self._mp4(identity))
        metadata = self.remote._mp4_video_metadata(self._mp4(quarter))
        self.assertEqual((metadata["width"], metadata["height"]), (240, 320))

    def test_video_boundary_and_web_scope(self) -> None:
        self.assertTrue(self.remote._is_target_video_name("UA-0018-extra.MP4", "UA-0018"))
        self.assertFalse(self.remote._is_target_video_name("UA-00180.mp4", "UA-0018"))
        self.assertTrue(self.remote._allowed_web_relative("video/UA-0018.html"))
        self.assertTrue(self.remote._allowed_web_relative("site/UA-0017-diag.html"))
        self.assertFalse(self.remote._allowed_web_relative("other/UA-0017.html"))

    def test_enriched_backup_html_entry_compares_as_live_state(self) -> None:
        live = {
            "exists": True,
            "sha256": "a" * 64,
            "size": 6000,
            "mode": 0o644,
        }
        enriched = {
            **live,
            "stored": "html/video/katalog.html.gz",
            "stored_sha256": "b" * 64,
        }
        self.assertEqual(self.remote._html_preimage_state(enriched), live)
        self.assertEqual(
            self.remote._html_preimage_state({"exists": False, "stored": "ignored"}),
            {"exists": False},
        )
        with self.assertRaisesRegex(self.remote.Task120Error, "BACKUP_HTML_STATE_INVALID"):
            self.remote._html_preimage_state({"exists": True, "sha256": "bad"})
        source = inspect.getsource(self.remote)
        self.assertGreaterEqual(source.count("_html_preimage_state("), 6)

    def test_wal_is_rejected_before_media_or_database_writes(self) -> None:
        main = pathlib.Path(self.temporary.name) / "journal-main.sqlite3"
        spec = pathlib.Path(self.temporary.name) / "journal-spec.sqlite3"
        for path in (main, spec):
            with sqlite3.connect(path) as connection:
                connection.execute("CREATE TABLE marker(value INTEGER)")
        with sqlite3.connect(main) as connection:
            connection.execute("ATTACH DATABASE ? AS ua120_spec", (str(spec),))
            self.assertEqual(
                self.remote._assert_atomic_journal_modes(connection),
                {"main": "delete", "ua120_spec": "delete"},
            )
        with sqlite3.connect(main) as connection:
            self.assertEqual(connection.execute("PRAGMA journal_mode=WAL").fetchone()[0], "wal")
        with sqlite3.connect(main) as connection:
            connection.execute("ATTACH DATABASE ? AS ua120_spec", (str(spec),))
            with self.assertRaisesRegex(
                self.remote.Task120Error, "MAIN_JOURNAL_NOT_ATOMIC:wal"
            ):
                self.remote._assert_atomic_journal_modes(connection)
        source = inspect.getsource(self.remote._publish)
        self.assertLess(source.index("_preflight()"), source.index("_stage_media("))

    def test_public_html_evidence_is_exact(self) -> None:
        metadata = {"sha256": "a" * 64, "size": 6000}
        verification = {
            "catalogs": {"video": dict(metadata)},
            "pages": {
                "video/UA-0017": {
                    "primary": dict(metadata), "diagnostic": dict(metadata),
                },
                "video/UA-0018": {
                    "primary": dict(metadata), "diagnostic": dict(metadata),
                },
            },
        }
        result = controller._expected_public_html(verification)
        self.assertEqual(
            set(result), {"catalog", "UA-0017", "UA-0017-diag", "UA-0018", "UA-0018-diag"}
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)

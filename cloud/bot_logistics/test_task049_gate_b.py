#!/usr/bin/env python3
"""Offline fail-closed tests for the approved TASK 049 installer."""
from __future__ import annotations

import contextlib
import hashlib
import os
import pathlib
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import task049_gate_b as G  # noqa: E402


ORIGINAL = b"value = 'original'\n"
CANDIDATE = """# 🚢 Этапы и доставка
# 🚢 Этапы и доставка
# callback_data="car_logistics:%d:card" % cid
# callback_data="car_logistics:%d:edit" % cid
# logistics_hub, pattern=r"^car_logistics:[0-9]+:(?:card|edit)$"
value = "candidate"
""".encode("utf-8")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class InstallerFixture:
    def __init__(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.source = self.root / "cars_ui.py"
        self.candidate = self.root / "candidate.py"
        self.approval = self.root / "approval.marker"
        self.backup = self.root / "backup.py"
        self.database = self.root / "crm.db"
        self.source.write_bytes(ORIGINAL)
        self.candidate.write_bytes(CANDIDATE)
        connection = sqlite3.connect(self.database)
        try:
            connection.execute(
                "CREATE TABLE cars (auto_number TEXT, sea_container TEXT, "
                "sea_date_out TEXT)"
            )
            connection.execute(
                "INSERT INTO cars VALUES (?, ?, ?)",
                ("UA-0006", G.EXPECTED_CONTAINER, G.EXPECTED_SEA_DATE_OUT),
            )
            connection.commit()
        finally:
            connection.close()
        self.required = {
            "TASK_ID": "task_049",
            "GATE": "B",
            "DECISION": "APPROVE",
            "USER_REPLY": "APPROVE",
            "SOURCE_SHA256": digest(ORIGINAL),
            "CANDIDATE_SHA256": digest(CANDIDATE),
            "UA_0006_CONTAINER": G.EXPECTED_CONTAINER,
            "UA_0006_SEA_DATE_OUT": G.EXPECTED_SEA_DATE_OUT,
        }
        self.write_approval(self.required)

    def write_approval(self, fields: dict[str, str]) -> None:
        self.approval.write_text(
            "".join(f"{key}: {value}\n" for key, value in fields.items()),
            encoding="utf-8",
        )

    @contextlib.contextmanager
    def patched(self):
        with mock.patch.multiple(
            G,
            SOURCE_PATH=self.source,
            CANDIDATE_PATH=self.candidate,
            APPROVAL_PATH=self.approval,
            BACKUP_PATH=self.backup,
            DB_PATH=self.database,
            EXPECTED_SOURCE_SHA=digest(ORIGINAL),
            EXPECTED_CANDIDATE_SHA=digest(CANDIDATE),
            REQUIRED_APPROVAL=dict(self.required),
        ):
            yield

    def close(self):
        self.temp.cleanup()


class GateBInstallerTests(unittest.TestCase):
    def setUp(self):
        self.fx = InstallerFixture()

    def tearDown(self):
        self.fx.close()

    def test_success_replaces_only_source_and_preserves_database_bytes(self):
        db_before = self.fx.database.read_bytes()
        with self.fx.patched():
            receipt = G.install()
        self.assertEqual(receipt["status"], "PASS")
        self.assertTrue(receipt["production_write"])
        self.assertFalse(receipt["db_write"])
        self.assertEqual(self.fx.source.read_bytes(), CANDIDATE)
        self.assertEqual(self.fx.backup.read_bytes(), ORIGINAL)
        self.assertEqual(self.fx.database.read_bytes(), db_before)
        self.assertEqual(receipt["db_sha256_before"], receipt["db_sha256_after"])
        self.assertTrue(receipt["ua0006_container_preserved"])
        self.assertTrue(receipt["ua0006_sea_date_preserved"])

    def test_post_replace_failure_automatically_restores_original(self):
        with self.fx.patched(), mock.patch.object(
            G,
            "verify_db_values",
            side_effect=[None, G.GateBBlocked("simulated_post_replace_failure")],
        ):
            receipt = G.install()
        self.assertEqual(receipt["status"], "ROLLED_BACK")
        self.assertTrue(receipt["rollback"])
        self.assertEqual(self.fx.source.read_bytes(), ORIGINAL)
        self.assertEqual(self.fx.backup.read_bytes(), ORIGINAL)

    def test_restart_failure_rollback_restores_source_and_preserves_db(self):
        db_before = self.fx.database.read_bytes()
        self.fx.source.write_bytes(CANDIDATE)
        self.fx.backup.write_bytes(ORIGINAL)
        with self.fx.patched():
            receipt = G.rollback_after_restart_failure()
        self.assertEqual(receipt["status"], "PASS")
        self.assertTrue(receipt["rollback"])
        self.assertTrue(receipt["production_write"])
        self.assertEqual(self.fx.source.read_bytes(), ORIGINAL)
        self.assertEqual(self.fx.database.read_bytes(), db_before)
        self.assertEqual(receipt["db_sha256_before"], receipt["db_sha256_after"])

    def test_bad_approval_blocks_before_source_write(self):
        fields = dict(self.fx.required)
        fields["DECISION"] = "WAIT"
        self.fx.write_approval(fields)
        with self.fx.patched():
            receipt = G.install()
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertFalse(receipt["production_write"])
        self.assertEqual(self.fx.source.read_bytes(), ORIGINAL)
        self.assertFalse(self.fx.backup.exists())

    def test_source_or_candidate_hash_mismatch_blocks_before_write(self):
        for path, changed in (
            (self.fx.source, b"changed source\n"),
            (self.fx.candidate, CANDIDATE + b"# changed\n"),
        ):
            with self.subTest(path=path.name):
                path.write_bytes(changed)
                with self.fx.patched():
                    receipt = G.install()
                self.assertEqual(receipt["status"], "BLOCKED")
                self.assertFalse(receipt["production_write"])
                self.assertFalse(self.fx.backup.exists())
                self.fx.source.write_bytes(ORIGINAL)
                self.fx.candidate.write_bytes(CANDIDATE)

    def test_wrong_container_or_date_blocks_before_write(self):
        for column, value in (
            ("sea_container", "WRONG"),
            ("sea_date_out", "2026-01-25"),
        ):
            with self.subTest(column=column):
                connection = sqlite3.connect(self.fx.database)
                try:
                    connection.execute(
                        f"UPDATE cars SET {column} = ? WHERE auto_number = ?",
                        (value, "UA-0006"),
                    )
                    connection.commit()
                finally:
                    connection.close()
                with self.fx.patched():
                    receipt = G.install()
                self.assertEqual(receipt["status"], "BLOCKED")
                self.assertFalse(receipt["production_write"])
                self.assertEqual(self.fx.source.read_bytes(), ORIGINAL)
                connection = sqlite3.connect(self.fx.database)
                try:
                    connection.execute(
                        "UPDATE cars SET sea_container = ?, sea_date_out = ? "
                        "WHERE auto_number = ?",
                        (
                            G.EXPECTED_CONTAINER,
                            G.EXPECTED_SEA_DATE_OUT,
                            "UA-0006",
                        ),
                    )
                    connection.commit()
                finally:
                    connection.close()

    def test_secure_digest_rejects_symlink(self):
        link = self.fx.root / "db-link"
        link.symlink_to(self.fx.database)
        with self.assertRaisesRegex(G.GateBBlocked, "not_single_regular_file"):
            G.secure_digest(link, G.MAX_DB_BYTES)


if __name__ == "__main__":
    unittest.main()

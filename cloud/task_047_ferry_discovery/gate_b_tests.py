#!/usr/bin/env python3
"""Offline destructive-path tests for the TASK 063 Gate B installer."""
from __future__ import annotations

import hashlib
import json
import pathlib
import tempfile
import unittest

import gate_b_controller
from gate_b_remote import ALLOWED_PATHS, OWNER_APPROVAL, PYTHON_PATHS, run_gate_b


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class GateBFixture:
    def __init__(self, root: pathlib.Path):
        self.root = root
        self.source = root / "source"
        self.candidates = root / "candidates"
        self.backups = root / "backups"
        self.source.mkdir()
        self.candidates.mkdir()
        self.backups.mkdir()
        self.crm = b"fixed read-only crm fixture\n"
        (self.source / "crm.db").write_bytes(self.crm)
        self.originals = {}
        self.replacements = {}
        self.files = []
        for index, rel_path in enumerate(ALLOWED_PATHS):
            source_data = ("source-%02d-%s\n" % (index, rel_path)).encode()
            if rel_path in PYTHON_PATHS:
                candidate_data = (
                    "# candidate %s\nVALUE = %r\n" % (rel_path, "На пароме")
                ).encode("utf-8")
                candidate_path = self.candidates / "python" / rel_path
                kind = "python"
            else:
                candidate_data = (
                    "<!doctype html><meta charset=utf-8><p>%s На пароме</p>\n" % rel_path
                ).encode("utf-8")
                candidate_path = self.candidates / rel_path
                kind = "html"
            source_path = self.source / rel_path
            source_path.parent.mkdir(parents=True, exist_ok=True)
            candidate_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.write_bytes(source_data)
            candidate_path.write_bytes(candidate_data)
            self.originals[rel_path] = source_data
            self.replacements[rel_path] = candidate_data
            self.files.append(
                {
                    "path": rel_path,
                    "kind": kind,
                    "source_sha256": digest(source_data),
                    "candidate_sha256": digest(candidate_data),
                    "candidate_size": len(candidate_data),
                }
            )

    def manifest(self, deployment="task063-offline-1"):
        return {
            "task": "task_063",
            "operation": "APPLY",
            "owner_approval": OWNER_APPROVAL,
            "deployment_id": deployment,
            "gate_a_generated_at_utc": "2026-08-28T07:42:13Z",
            "source_root": str(self.source),
            "candidate_root": str(self.candidates),
            "backup_root": str(self.backups / deployment),
            "crm": {
                "path": "crm.db",
                "sha256": digest(self.crm),
                "id_count": 10,
                "table": "cars",
                "id_column": "auto_number",
                "container_column": "sea_container",
            },
            "files": [dict(item) for item in self.files],
        }

    def write_manifest(self, manifest):
        data = (
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n"
        ).encode("utf-8")
        path = self.root / (manifest["deployment_id"] + ".json")
        path.write_bytes(data)
        return path, digest(data)


class GateBRemoteTests(unittest.TestCase):
    def run_fixture(self, fixture, manifest=None, **kwargs):
        manifest = manifest or fixture.manifest()
        path, manifest_hash = fixture.write_manifest(manifest)
        return run_gate_b(
            str(path), manifest_hash, enforce_fixed=False, **kwargs
        )

    def test_success_backs_up_and_installs_exact_allowlist(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = GateBFixture(pathlib.Path(directory))
            receipt = self.run_fixture(fixture)
            self.assertEqual(receipt["status"], "PASS")
            self.assertTrue(receipt["production_write"])
            self.assertEqual(receipt["production_files_changed"], len(ALLOWED_PATHS))
            self.assertFalse(receipt["crm_write"])
            self.assertFalse(receipt["db_write"])
            self.assertFalse(receipt["service_reload"])
            self.assertEqual(receipt["crm_sha256_before"], digest(fixture.crm))
            self.assertEqual(receipt["crm_sha256_after"], digest(fixture.crm))
            for rel_path in ALLOWED_PATHS:
                self.assertEqual((fixture.source / rel_path).read_bytes(), fixture.replacements[rel_path])
                self.assertEqual(
                    (fixture.backups / "task063-offline-1" / rel_path).read_bytes(),
                    fixture.originals[rel_path],
                )

    def test_stale_source_blocks_before_any_write(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = GateBFixture(pathlib.Path(directory))
            (fixture.source / ALLOWED_PATHS[3]).write_bytes(b"concurrent production edit\n")
            before = {
                path: (fixture.source / path).read_bytes() for path in ALLOWED_PATHS
            }
            receipt = self.run_fixture(fixture)
            self.assertEqual(receipt["status"], "BLOCKED")
            self.assertFalse(receipt["production_write"])
            self.assertIn("production_source_hash_mismatch", receipt["errors"][0])
            for rel_path in ALLOWED_PATHS:
                self.assertEqual((fixture.source / rel_path).read_bytes(), before[rel_path])

    def test_candidate_hash_mismatch_blocks_before_any_write(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = GateBFixture(pathlib.Path(directory))
            path = ALLOWED_PATHS[5]
            (fixture.candidates / path).write_bytes(b"unapproved candidate\n")
            receipt = self.run_fixture(fixture)
            self.assertEqual(receipt["status"], "BLOCKED")
            self.assertFalse(receipt["production_write"])
            self.assertIn("candidate_size_mismatch", receipt["errors"][0])
            for rel_path in ALLOWED_PATHS:
                self.assertEqual((fixture.source / rel_path).read_bytes(), fixture.originals[rel_path])

    def test_symlink_candidate_is_rejected_before_any_write(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = GateBFixture(pathlib.Path(directory))
            path = fixture.candidates / ALLOWED_PATHS[4]
            approved = path.read_bytes()
            alternate = fixture.root / "alternate-candidate.html"
            alternate.write_bytes(approved)
            path.unlink()
            path.symlink_to(alternate)
            receipt = self.run_fixture(fixture)
            self.assertEqual(receipt["status"], "BLOCKED")
            self.assertFalse(receipt["production_write"])
            self.assertTrue(
                "not_regular_file" in receipt["errors"][0]
                or "path_escape" in receipt["errors"][0]
            )
            for rel_path in ALLOWED_PATHS:
                self.assertEqual((fixture.source / rel_path).read_bytes(), fixture.originals[rel_path])

    def test_mid_install_failure_rolls_every_replacement_back(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = GateBFixture(pathlib.Path(directory))
            receipt = self.run_fixture(fixture, fail_after_replacements=3)
            self.assertEqual(receipt["status"], "ROLLED_BACK")
            self.assertTrue(receipt["production_write"])
            self.assertTrue(receipt["rollback_attempted"])
            self.assertTrue(receipt["rollback_completed"])
            for rel_path in ALLOWED_PATHS:
                self.assertEqual((fixture.source / rel_path).read_bytes(), fixture.originals[rel_path])

    def test_unsafe_or_extra_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = GateBFixture(pathlib.Path(directory))
            manifest = fixture.manifest()
            manifest["files"][0]["path"] = "../video/index.html"
            receipt = self.run_fixture(fixture, manifest)
            self.assertEqual(receipt["status"], "BLOCKED")
            self.assertFalse(receipt["production_write"])
            for rel_path in ALLOWED_PATHS:
                self.assertEqual((fixture.source / rel_path).read_bytes(), fixture.originals[rel_path])

    def test_second_run_is_hash_exact_and_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = GateBFixture(pathlib.Path(directory))
            first = self.run_fixture(fixture)
            self.assertEqual(first["status"], "PASS")
            second_manifest = fixture.manifest("task063-offline-2")
            second = self.run_fixture(fixture, second_manifest)
            self.assertEqual(second["status"], "PASS")
            self.assertFalse(second["production_write"])
            self.assertEqual(second["production_files_changed"], 0)
            self.assertTrue(all(item["action"] == "ALREADY_APPLIED" for item in second["files"]))

    def test_changed_crm_blocks_without_opening_it_for_write(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = GateBFixture(pathlib.Path(directory))
            (fixture.source / "crm.db").write_bytes(b"changed externally\n")
            receipt = self.run_fixture(fixture)
            self.assertEqual(receipt["status"], "BLOCKED")
            self.assertFalse(receipt["production_write"])
            self.assertEqual(receipt["errors"], ["crm_hash_changed_before_install"])

    def test_manifest_hash_is_required(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = GateBFixture(pathlib.Path(directory))
            manifest = fixture.manifest()
            path, _ = fixture.write_manifest(manifest)
            receipt = run_gate_b(str(path), "0" * 64, enforce_fixed=False)
            self.assertEqual(receipt["status"], "BLOCKED")
            self.assertEqual(receipt["errors"], ["manifest_hash_mismatch"])


class GateBControllerTests(unittest.TestCase):
    @unittest.skipUnless(
        gate_b_controller.GATE_A_EVIDENCE.exists(),
        "authoritative Gate A evidence is available in the GitHub checkout",
    )
    def test_controller_accepts_only_pinned_reviewed_gate_a(self):
        receipt = gate_b_controller.GateBController.load_approved_gate_a()
        self.assertEqual(receipt["generated_at_utc"], "2026-08-28T07:42:13Z")
        manifest, data = gate_b_controller.GateBController.build_manifest(receipt)
        self.assertEqual(set(item["path"] for item in manifest["files"]), set(ALLOWED_PATHS))
        self.assertEqual(manifest["owner_approval"], OWNER_APPROVAL)
        self.assertGreater(len(data), 1000)


if __name__ == "__main__":
    unittest.main(verbosity=2)

import hashlib
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
PKG_DIR = THIS_DIR.parent
sys.path.insert(0, str(PKG_DIR))

import gate_b_installer as gbi  # noqa: E402


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


class FixtureMixin:
    def make_fixture(self):
        tmp = tempfile.TemporaryDirectory()
        base = Path(tmp.name) / "base"
        candidates = Path(tmp.name) / "candidates"
        backups = Path(tmp.name) / "backups"
        (base / "video").mkdir(parents=True)
        (candidates / "video").mkdir(parents=True)
        backups.mkdir()

        source_a = b"<html>old wording B more</html>"
        candidate_a = b"<html>new wording ferry</html>"
        source_b = b"print('unchanged generator')"

        (base / "video" / "UA-0001.html").write_bytes(source_a)
        (candidates / "video" / "UA-0001.html").write_bytes(candidate_a)
        (base / "stranica.py").write_bytes(source_b)

        manifest = {
            "task_id": "task_057",
            "gate": "GATE_B",
            "status": "GENERATED",
            "allowlist": list(gbi.ALLOWLIST),
            "targets": [
                {
                    "path": "video/UA-0001.html",
                    "source_sha256": sha256_bytes(source_a),
                    "candidate_sha256": sha256_bytes(candidate_a),
                    "expected_size_bytes": len(candidate_a),
                    "approved_change_count": 1,
                    "action": "REPLACE",
                },
                {
                    "path": "stranica.py",
                    "source_sha256": sha256_bytes(source_b),
                    "candidate_sha256": sha256_bytes(source_b),
                    "expected_size_bytes": len(source_b),
                    "approved_change_count": 0,
                    "action": "VERIFY_UNCHANGED",
                },
            ],
            "manifest_sha256": None,
        }
        manifest["manifest_sha256"] = gbi.canonical_manifest_hash(manifest)
        manifest_path = Path(tmp.name) / "release_manifest.json"
        manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")

        approval_path = Path(tmp.name) / "approval.txt"
        approval_path.write_text(
            gbi.APPROVAL_PREFIX + manifest["manifest_sha256"], encoding="utf-8"
        )

        receipt_path = Path(tmp.name) / "receipt.json"

        self._tmp = tmp
        return {
            "tmp": tmp,
            "base": base,
            "candidates": candidates,
            "backups": backups,
            "manifest_path": manifest_path,
            "approval_path": approval_path,
            "receipt_path": receipt_path,
            "manifest": manifest,
            "source_a": source_a,
            "candidate_a": candidate_a,
        }


class TestCleanSuccess(FixtureMixin, unittest.TestCase):
    def test_clean_success_and_receipt_markers(self):
        fx = self.make_fixture()
        receipt = gbi.run_gate_b(
            fx["base"], fx["manifest_path"], fx["approval_path"],
            fx["candidates"], fx["receipt_path"], fx["backups"],
        )
        self.assertEqual(receipt["result"], "SUCCESS")
        self.assertTrue(receipt["production_touched"])
        self.assertFalse(receipt["crm_touched"])
        self.assertFalse(receipt["crm_db_written"])
        self.assertFalse(receipt["service_reloaded"])
        self.assertFalse(receipt["ua0009_published"])
        written = (fx["base"] / "video" / "UA-0001.html").read_bytes()
        self.assertEqual(written, fx["candidate_a"])
        unchanged = (fx["base"] / "stranica.py").read_bytes()
        self.assertEqual(unchanged, b"print('unchanged generator')")


class TestDriftAndTamper(FixtureMixin, unittest.TestCase):
    def test_source_drift_aborts(self):
        fx = self.make_fixture()
        (fx["base"] / "video" / "UA-0001.html").write_bytes(b"tampered live file")
        with self.assertRaises(gbi.GateBError) as ctx:
            gbi.run_gate_b(
                fx["base"], fx["manifest_path"], fx["approval_path"],
                fx["candidates"], fx["receipt_path"], fx["backups"],
            )
        self.assertIn("SOURCE_DRIFT_DETECTED", str(ctx.exception))

    def test_candidate_drift_aborts(self):
        fx = self.make_fixture()
        (fx["candidates"] / "video" / "UA-0001.html").write_bytes(b"unexpected candidate bytes")
        with self.assertRaises(gbi.GateBError) as ctx:
            gbi.run_gate_b(
                fx["base"], fx["manifest_path"], fx["approval_path"],
                fx["candidates"], fx["receipt_path"], fx["backups"],
            )
        self.assertIn("CANDIDATE_DRIFT_DETECTED", str(ctx.exception))

    def test_manifest_tamper_detected(self):
        fx = self.make_fixture()
        manifest = json.loads(fx["manifest_path"].read_text(encoding="utf-8"))
        manifest["targets"][0]["approved_change_count"] = 999
        fx["manifest_path"].write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
        with self.assertRaises(gbi.GateBError) as ctx:
            gbi.run_gate_b(
                fx["base"], fx["manifest_path"], fx["approval_path"],
                fx["candidates"], fx["receipt_path"], fx["backups"],
            )
        self.assertIn("MANIFEST_TAMPER_DETECTED", str(ctx.exception))


class TestApproval(FixtureMixin, unittest.TestCase):
    def test_invalid_approval_phrase(self):
        fx = self.make_fixture()
        fx["approval_path"].write_text("APPROVE_PRODUCTION WRONG PHRASE", encoding="utf-8")
        with self.assertRaises(gbi.GateBError) as ctx:
            gbi.run_gate_b(
                fx["base"], fx["manifest_path"], fx["approval_path"],
                fx["candidates"], fx["receipt_path"], fx["backups"],
            )
        self.assertIn("APPROVAL_PHRASE_MISMATCH", str(ctx.exception))

    def test_missing_approval_file(self):
        fx = self.make_fixture()
        missing_path = fx["approval_path"].parent / "does_not_exist.txt"
        with self.assertRaises(FileNotFoundError):
            gbi.run_gate_b(
                fx["base"], fx["manifest_path"], missing_path,
                fx["candidates"], fx["receipt_path"], fx["backups"],
            )


@unittest.skipUnless(hasattr(os, "symlink"), "symlink not supported")
class TestSymlinkHardlinkEscape(FixtureMixin, unittest.TestCase):
    def test_symlink_rejected(self):
        fx = self.make_fixture()
        real = fx["base"] / "video" / "UA-0001.html"
        real.unlink()
        target = fx["base"] / "video" / "UA-0001_real.html"
        target.write_bytes(fx["source_a"])
        os.symlink(target, real)
        with self.assertRaises(gbi.GateBError) as ctx:
            gbi.run_gate_b(
                fx["base"], fx["manifest_path"], fx["approval_path"],
                fx["candidates"], fx["receipt_path"], fx["backups"],
            )
        self.assertIn("REJECTED_SYMLINK", str(ctx.exception))

    def test_hardlink_rejected(self):
        fx = self.make_fixture()
        real = fx["base"] / "video" / "UA-0001.html"
        other = fx["base"] / "video" / "UA-0001_hardlink.html"
        try:
            os.link(real, other)
        except OSError:
            self.skipTest("hardlinks not supported on this filesystem")
        with self.assertRaises(gbi.GateBError) as ctx:
            gbi.run_gate_b(
                fx["base"], fx["manifest_path"], fx["approval_path"],
                fx["candidates"], fx["receipt_path"], fx["backups"],
            )
        self.assertIn("REJECTED_HARDLINK", str(ctx.exception))

    def test_path_escape_rejected(self):
        fx = self.make_fixture()
        manifest = json.loads(fx["manifest_path"].read_text(encoding="utf-8"))
        manifest["targets"][0]["path"] = "../escape.html"
        manifest["manifest_sha256"] = None
        manifest["manifest_sha256"] = gbi.canonical_manifest_hash(manifest)
        fx["manifest_path"].write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
        fx["approval_path"].write_text(
            gbi.APPROVAL_PREFIX + manifest["manifest_sha256"], encoding="utf-8"
        )
        with self.assertRaises(gbi.GateBError) as ctx:
            gbi.run_gate_b(
                fx["base"], fx["manifest_path"], fx["approval_path"],
                fx["candidates"], fx["receipt_path"], fx["backups"],
            )
        self.assertIn("REJECTED", str(ctx.exception))

    def test_allowlist_rejection(self):
        fx = self.make_fixture()
        manifest = json.loads(fx["manifest_path"].read_text(encoding="utf-8"))
        manifest["targets"][0]["path"] = "video/not_allowed.html"
        manifest["manifest_sha256"] = None
        manifest["manifest_sha256"] = gbi.canonical_manifest_hash(manifest)
        fx["manifest_path"].write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
        fx["approval_path"].write_text(
            gbi.APPROVAL_PREFIX + manifest["manifest_sha256"], encoding="utf-8"
        )
        with self.assertRaises(gbi.GateBError) as ctx:
            gbi.run_gate_b(
                fx["base"], fx["manifest_path"], fx["approval_path"],
                fx["candidates"], fx["receipt_path"], fx["backups"],
            )
        self.assertIn("REJECTED_NOT_IN_ALLOWLIST", str(ctx.exception))


class TestRollbackAndDeterminism(FixtureMixin, unittest.TestCase):
    def test_injected_mid_write_failure_full_rollback(self):
        fx = self.make_fixture()
        original = (fx["base"] / "video" / "UA-0001.html").read_bytes()
        with self.assertRaises(gbi.GateBError):
            gbi.run_gate_b(
                fx["base"], fx["manifest_path"], fx["approval_path"],
                fx["candidates"], fx["receipt_path"], fx["backups"],
                fail_after_n_writes=0,
            )
        restored = (fx["base"] / "video" / "UA-0001.html").read_bytes()
        self.assertEqual(restored, original)
        receipt = json.loads(fx["receipt_path"].read_text(encoding="utf-8"))
        self.assertFalse(receipt["production_touched"])
        self.assertIn(receipt["result"].startswith("FAILED"), [True])

    def test_receipt_determinism_of_structure(self):
        fx1 = self.make_fixture()
        r1 = gbi.run_gate_b(
            fx1["base"], fx1["manifest_path"], fx1["approval_path"],
            fx1["candidates"], fx1["receipt_path"], fx1["backups"],
        )
        fx2 = self.make_fixture()
        r2 = gbi.run_gate_b(
            fx2["base"], fx2["manifest_path"], fx2["approval_path"],
            fx2["candidates"], fx2["receipt_path"], fx2["backups"],
        )
        self.assertEqual(set(r1.keys()), set(r2.keys()))
        self.assertEqual(
            [f["path"] for f in r1["files"]], [f["path"] for f in r2["files"]]
        )
        self.assertEqual(
            [f["after_sha256"] for f in r1["files"]],
            [f["after_sha256"] for f in r2["files"]],
        )

    def test_no_crm_reload_ua0009_markers(self):
        fx = self.make_fixture()
        receipt = gbi.run_gate_b(
            fx["base"], fx["manifest_path"], fx["approval_path"],
            fx["candidates"], fx["receipt_path"], fx["backups"],
        )
        self.assertFalse(receipt["crm_touched"])
        self.assertFalse(receipt["crm_db_written"])
        self.assertFalse(receipt["service_reloaded"])
        self.assertFalse(receipt["ua0009_published"])

    def test_backup_mismatch_detected(self):
        fx = self.make_fixture()
        orig_copy2 = gbi.shutil.copy2

        def corrupting_copy2(src, dst, *a, **kw):
            orig_copy2(src, dst, *a, **kw)
            with open(dst, "ab") as fh:
                fh.write(b"CORRUPT")

        gbi.shutil.copy2 = corrupting_copy2
        try:
            with self.assertRaises(gbi.GateBError) as ctx:
                gbi.run_gate_b(
                    fx["base"], fx["manifest_path"], fx["approval_path"],
                    fx["candidates"], fx["receipt_path"], fx["backups"],
                )
            self.assertIn("BACKUP_HASH_MISMATCH", str(ctx.exception))
        finally:
            gbi.shutil.copy2 = orig_copy2


if __name__ == "__main__":
    unittest.main()

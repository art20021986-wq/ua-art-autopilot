import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import installer as inst


class TestInstaller(unittest.TestCase):
    def test_atomic_install_success(self):
        with tempfile.TemporaryDirectory() as work:
            target = os.path.join(work, "target.txt")
            with open(target, "w", encoding="utf-8") as handle:
                handle.write("old content")
            candidate = os.path.join(work, "candidate.txt")
            with open(candidate, "w", encoding="utf-8") as handle:
                handle.write("new content")
            backup_dir = os.path.join(work, "backup")
            preimage = inst.atomic_install({target: candidate}, {}, backup_dir)
            with open(target, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "new content")
            self.assertIn(target, preimage)

    def test_rollback_restores_preimage(self):
        with tempfile.TemporaryDirectory() as work:
            target = os.path.join(work, "target.txt")
            with open(target, "w", encoding="utf-8") as handle:
                handle.write("preimage content")
            preimage = inst.build_preimage_manifest([target])
            backup_path = os.path.join(work, "target.txt.bak")
            with open(backup_path, "w", encoding="utf-8") as handle:
                handle.write("preimage content")
            backups = {target: backup_path}
            with open(target, "w", encoding="utf-8") as handle:
                handle.write("corrupted content")
            inst.rollback(preimage, backups)
            with open(target, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "preimage content")

    def test_verify_preimage_restored_true(self):
        with tempfile.TemporaryDirectory() as work:
            target = os.path.join(work, "target.txt")
            with open(target, "w", encoding="utf-8") as handle:
                handle.write("stable content")
            preimage = inst.build_preimage_manifest([target])
            self.assertTrue(inst.verify_preimage_restored(preimage))

    def test_verify_preimage_restored_false_on_mismatch(self):
        with tempfile.TemporaryDirectory() as work:
            target = os.path.join(work, "target.txt")
            with open(target, "w", encoding="utf-8") as handle:
                handle.write("stable content")
            preimage = inst.build_preimage_manifest([target])
            with open(target, "w", encoding="utf-8") as handle:
                handle.write("mutated content")
            self.assertFalse(inst.verify_preimage_restored(preimage))

    def test_atomic_install_rolls_back_on_failure(self):
        with tempfile.TemporaryDirectory() as work:
            target = os.path.join(work, "target.txt")
            with open(target, "w", encoding="utf-8") as handle:
                handle.write("original content")
            missing_candidate = os.path.join(work, "does_not_exist.txt")
            backup_dir = os.path.join(work, "backup")
            with self.assertRaises(Exception):
                inst.atomic_install({target: missing_candidate}, {}, backup_dir)
            with open(target, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "original content")


if __name__ == "__main__":
    unittest.main()

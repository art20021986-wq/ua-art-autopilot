"""Offline unit tests for cloud/task_073/tools/gate_b_installer_v2.py."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import gate_b_installer_v2 as installer_mod  # noqa: E402


class TestAtomicInstaller(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="task073_test_")
        self.target_a = os.path.join(self.tmpdir, "a.txt")
        self.target_b = os.path.join(self.tmpdir, "b.txt")
        with open(self.target_a, "w", encoding="utf-8") as fh:
            fh.write("original-a")
        with open(self.target_b, "w", encoding="utf-8") as fh:
            fh.write("original-b")
        self.sha_a = installer_mod.sha256_file(self.target_a)
        self.sha_b = installer_mod.sha256_file(self.target_b)

    def _write_set(self, content_b=b"new-b"):
        return [
            installer_mod.WriteSetEntry(
                target_path=self.target_a,
                new_content=b"new-a",
                preimage_sha=self.sha_a,
            ),
            installer_mod.WriteSetEntry(
                target_path=self.target_b,
                new_content=content_b,
                preimage_sha=self.sha_b,
            ),
        ]

    def test_successful_install_and_readback(self):
        installer = installer_mod.AtomicInstaller(self._write_set())
        manifest = installer.install()
        self.assertTrue(manifest.committed)
        with open(self.target_a, "rb") as fh:
            self.assertEqual(fh.read(), b"new-a")
        with open(self.target_b, "rb") as fh:
            self.assertEqual(fh.read(), b"new-b")

    def test_preimage_drift_blocks_install(self):
        with open(self.target_a, "w", encoding="utf-8") as fh:
            fh.write("drifted")
        installer = installer_mod.AtomicInstaller(self._write_set())
        with self.assertRaises(installer_mod.InstallError):
            installer.install()
        with open(self.target_a, "r", encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "drifted")

    def test_full_rollback_on_readback_mismatch(self):
        write_set = self._write_set()

        class FlakyInstaller(installer_mod.AtomicInstaller):
            def stage_all(self):
                staged = super().stage_all()
                second_target = self.write_set[1].target_path
                with open(staged[second_target], "wb") as fh:
                    fh.write(b"corrupted")
                return staged

        installer = FlakyInstaller(write_set)
        with self.assertRaises(installer_mod.InstallError):
            installer.install()

        with open(self.target_a, "r", encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "original-a")
        with open(self.target_b, "r", encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "original-b")


if __name__ == "__main__":
    unittest.main()

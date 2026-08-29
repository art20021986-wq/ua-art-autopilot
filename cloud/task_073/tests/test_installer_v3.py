import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import gate_b_installer_v3 as gi  # noqa: E402


class FakeClient:
    def __init__(self, initial_files):
        self.files = dict(initial_files)
        self.put_calls = []
        self.fail_on_put_for = None

    def get_file_text(self, remote_path):
        return self.files[remote_path]

    def put_file_text(self, remote_path, content):
        if self.fail_on_put_for is not None and remote_path == self.fail_on_put_for:
            raise gi.InstallerV3Error("simulated put failure for {}".format(remote_path))
        self.put_calls.append(remote_path)
        self.files[remote_path] = content


class TestInstallWriteSet(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="task073_installer_test_")
        self.client = FakeClient(
            {
                "/home/Carix/konteyner.py": "OLD_KONTEYNER",
                "/home/Carix/cars_ui.py": "OLD_CARS_UI",
            }
        )

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_successful_install_updates_both_files(self):
        write_set = {
            "konteyner.py": gi.WriteSetEntry(
                remote_path="/home/Carix/konteyner.py",
                new_content="NEW_KONTEYNER",
                preimage_sha256=gi.sha256_text("OLD_KONTEYNER"),
            ),
            "cars_ui.py": gi.WriteSetEntry(
                remote_path="/home/Carix/cars_ui.py",
                new_content="NEW_CARS_UI",
                preimage_sha256=gi.sha256_text("OLD_CARS_UI"),
            ),
        }
        report = gi.install_write_set(self.client, write_set, self.tmp_dir)
        self.assertIsNone(report.error)
        self.assertFalse(report.rolled_back)
        self.assertEqual(self.client.files["/home/Carix/konteyner.py"], "NEW_KONTEYNER")
        self.assertEqual(self.client.files["/home/Carix/cars_ui.py"], "NEW_CARS_UI")

    def test_preimage_drift_blocks_before_any_write(self):
        write_set = {
            "konteyner.py": gi.WriteSetEntry(
                remote_path="/home/Carix/konteyner.py",
                new_content="NEW_KONTEYNER",
                preimage_sha256="deadbeef",
            ),
        }
        report = gi.install_write_set(self.client, write_set, self.tmp_dir)
        self.assertIsNotNone(report.error)
        self.assertEqual(self.client.files["/home/Carix/konteyner.py"], "OLD_KONTEYNER")
        self.assertEqual(len(self.client.put_calls), 0)

    def test_partial_failure_rolls_back_already_installed_file(self):
        self.client.fail_on_put_for = "/home/Carix/cars_ui.py"
        write_set = {
            "konteyner.py": gi.WriteSetEntry(
                remote_path="/home/Carix/konteyner.py",
                new_content="NEW_KONTEYNER",
                preimage_sha256=gi.sha256_text("OLD_KONTEYNER"),
            ),
            "cars_ui.py": gi.WriteSetEntry(
                remote_path="/home/Carix/cars_ui.py",
                new_content="NEW_CARS_UI",
                preimage_sha256=gi.sha256_text("OLD_CARS_UI"),
            ),
        }
        report = gi.install_write_set(self.client, write_set, self.tmp_dir)
        self.assertIsNotNone(report.error)
        self.assertTrue(report.rolled_back)
        self.assertEqual(self.client.files["/home/Carix/konteyner.py"], "OLD_KONTEYNER")
        self.assertEqual(self.client.files["/home/Carix/cars_ui.py"], "OLD_CARS_UI")


if __name__ == "__main__":
    unittest.main()

"""Installer safety checks against a disposable local SQLite/HTML fixture."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import stat
import sys
import tempfile
import types
import unittest
from unittest import mock


HERE = Path(__file__).resolve().parent
INSTALLER = HERE / "crm_folders_install_20260910.py"


def load_module(path):
    module = types.ModuleType("ua122_installer_test_subject")
    module.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), "exec"), module.__dict__)
    return module


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="crm-installer-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.subject = load_module(INSTALLER)
        self.subject.ROOT = self.root
        self.subject.SOURCE = self.root / "cars_ui.py"
        self.subject.CORE = self.root / "ua_crm_catalog_folders.py"
        names = ("cars_list", "card_kb", "register", "card_of", "drop_wait",
                 "_ua082_title_html", "_ua082_title_button")
        self.original = ("# Existing live source must remain byte-for-byte intact.\n"
                         + "\n".join("def %s(*args, **kwargs):\n    pass\n" % name
                                     for name in names)).encode()
        self.subject.SOURCE.write_bytes(self.original)
        self.subject.SOURCE.chmod(0o640)
        self.subject.EXPECTED = hashlib.sha256(self.original).hexdigest()
        (self.root / "video").mkdir()
        self.catalog = self.root / "video/katalog.html"
        self.catalog.write_text(
            '<!doctype html><html><head><title>Каталог — UA ART COMPANY</title>'
            '</head><body>'
            + ''.join('<article data-ua-card="UA-%04d"></article>' % number
                      for number in range(1, 19))
            + '</body></html>', encoding="utf-8")
        self.database = self.root / "crm.db"
        with sqlite3.connect(self.database) as connection:
            connection.execute("CREATE TABLE cars (id INTEGER PRIMARY KEY, "
                               "auto_number TEXT, published INTEGER)")
            connection.executemany("INSERT INTO cars VALUES (?, ?, ?)",
                                   [(number, "UA-%04d" % number, int(number < 19))
                                    for number in range(1, 20)])
        self.data_before = {self.catalog: self.catalog.read_bytes(),
                            self.database: self.database.read_bytes()}

    def invoke(self, *arguments):
        output = io.StringIO()
        with mock.patch.object(sys, "argv", [str(INSTALLER), *arguments]):
            with contextlib.redirect_stdout(output):
                self.subject.main()
        return json.loads(output.getvalue())

    def snapshot(self):
        return {str(path.relative_to(self.root)):
                (path.read_bytes(), stat.S_IMODE(path.stat().st_mode),
                 path.stat().st_mtime_ns)
                for path in self.root.rglob("*") if path.is_file()}

    def assert_business_data_unchanged(self):
        for path, content in self.data_before.items():
            self.assertEqual(path.read_bytes(), content, str(path))

    def test_generated_installer_matches_builder_and_current_sources(self):
        builder = load_module(HERE / "build_installer.py")
        expected = builder.TEMPLATE.replace(
            "__CORE_TEXT__", repr((HERE / "catalog_core.py").read_text()))
        expected = expected.replace(
            "__FRAGMENT__", repr((HERE / "runtime_fragment.py").read_text()))
        self.assertEqual(INSTALLER.read_text(), expected)

    def test_default_preflight_writes_no_files(self):
        before = self.snapshot()
        result = self.invoke()
        self.assertEqual(result["status"], "PREFLIGHT_OK")
        self.assertEqual(result["catalog_count"], 18)
        self.assertEqual(result["unpublished_count"], 1)
        self.assertEqual(result["unpublished_numbers"], ["UA-0019"])
        self.assertEqual(before, self.snapshot())
        self.assertFalse((self.root / "backups").exists())
        self.assertFalse(self.subject.CORE.exists())
        self.assert_business_data_unchanged()

    def test_apply_preserves_prefix_mode_backup_and_business_data(self):
        result = self.invoke("--apply")
        expected = self.original + b"\n\n" + self.subject.FRAGMENT.encode("utf-8")
        self.assertEqual(result["status"], "INSTALLED")
        self.assertEqual(self.subject.SOURCE.read_bytes(), expected)
        self.assertTrue(expected.startswith(self.original))
        self.assertEqual(expected.count(self.subject.MARKER), 1)
        self.assertEqual(stat.S_IMODE(self.subject.SOURCE.stat().st_mode), 0o640)
        self.assertEqual(self.subject.CORE.read_bytes(), self.subject.CORE_TEXT.encode())
        backup = Path(result["backup"])
        self.assertEqual(backup.parent, self.root / "backups/crm_catalog_folders_001")
        self.assertEqual((backup / "cars_ui.py").read_bytes(), self.original)
        manifest = json.loads((backup / "manifest.json").read_text())
        self.assertEqual(manifest["candidate_sha256"], hashlib.sha256(expected).hexdigest())
        self.assertEqual(manifest["source_mode"], 0o640)
        self.assert_business_data_unchanged()

    def test_source_hash_mismatch_refuses_without_writes(self):
        self.subject.SOURCE.write_bytes(self.original + b"\n# Other edit\n")
        before = self.snapshot()
        with self.assertRaisesRegex(RuntimeError, "Source changed"):
            self.invoke("--apply")
        self.assertEqual(before, self.snapshot())

    def test_different_existing_core_refuses_without_writes(self):
        self.subject.CORE.write_text("# Owned by another change\n")
        before = self.snapshot()
        with self.assertRaisesRegex(RuntimeError, "Core path"):
            self.invoke("--apply")
        self.assertEqual(before, self.snapshot())

    def test_repeat_installation_refuses_without_writes(self):
        self.invoke("--apply")
        before = self.snapshot()
        with self.assertRaises(RuntimeError):
            self.invoke("--apply")
        self.assertEqual(before, self.snapshot())

    def test_apply_preserves_source_edited_after_preflight(self):
        preflight = self.subject.preflight
        concurrent = self.original + b"\n# Concurrent source edit\n"

        def change_after_preflight():
            result = preflight()
            self.subject.SOURCE.write_bytes(concurrent)
            return result

        with mock.patch.object(self.subject, "preflight", change_after_preflight):
            with self.assertRaisesRegex(RuntimeError, "Source changed after preflight"):
                self.invoke("--apply")
        self.assertEqual(self.subject.SOURCE.read_bytes(), concurrent)
        self.assertFalse(self.subject.CORE.exists())
        self.assert_business_data_unchanged()

    def test_apply_preserves_source_edited_after_core_write(self):
        atomic_write = self.subject.atomic_write
        concurrent = self.original + b"\n# Source changed during core write\n"

        def change_after_core(path, data, mode=0o600, **options):
            atomic_write(path, data, mode, **options)
            if path == self.subject.CORE:
                self.subject.SOURCE.write_bytes(concurrent)

        with mock.patch.object(self.subject, "atomic_write", change_after_core):
            with self.assertRaisesRegex(RuntimeError, "Source changed before replacement"):
                self.invoke("--apply")
        self.assertEqual(self.subject.SOURCE.read_bytes(), concurrent)
        self.assert_business_data_unchanged()

    def test_apply_preserves_core_created_after_preflight(self):
        preflight = self.subject.preflight
        concurrent = b"# Concurrent core owned by another change\n"

        def change_after_preflight():
            result = preflight()
            self.subject.CORE.write_bytes(concurrent)
            return result

        with mock.patch.object(self.subject, "preflight", change_after_preflight):
            with self.assertRaises(RuntimeError):
                self.invoke("--apply")
        self.assertEqual(self.subject.CORE.read_bytes(), concurrent)
        self.assertEqual(self.subject.SOURCE.read_bytes(), self.original)
        self.assert_business_data_unchanged()

    def test_rollback_restores_exact_source_and_mode(self):
        installed = self.invoke("--apply")
        result = self.invoke("--rollback", installed["backup"])
        self.assertEqual(result["status"], "ROLLED_BACK")
        self.assertEqual(result["source_sha256"], self.subject.EXPECTED)
        self.assertEqual(self.subject.SOURCE.read_bytes(), self.original)
        self.assertEqual(stat.S_IMODE(self.subject.SOURCE.stat().st_mode), 0o640)
        self.assert_business_data_unchanged()

    def test_rollback_refuses_concurrent_source_edit(self):
        installed = self.invoke("--apply")
        self.subject.SOURCE.write_bytes(self.subject.SOURCE.read_bytes()
                                       + b"\n# New independent edit\n")
        before = self.snapshot()
        with self.assertRaisesRegex(RuntimeError, "Rollback hash mismatch"):
            self.invoke("--rollback", installed["backup"])
        self.assertEqual(before, self.snapshot())

    def test_rollback_refuses_tampered_backup(self):
        installed = self.invoke("--apply")
        (Path(installed["backup"]) / "cars_ui.py").write_bytes(b"# Invalid backup\n")
        before = self.snapshot()
        with self.assertRaisesRegex(RuntimeError, "Rollback hash mismatch"):
            self.invoke("--rollback", installed["backup"])
        self.assertEqual(before, self.snapshot())

    def test_rollback_rejects_other_directory_and_apply_combination(self):
        installed = self.invoke("--apply")
        before = self.snapshot()
        with self.assertRaisesRegex(RuntimeError, "Unexpected backup directory"):
            self.invoke("--rollback", str(self.root))
        with self.assertRaisesRegex(RuntimeError, "mutually exclusive"):
            self.invoke("--apply", "--rollback", installed["backup"])
        self.assertEqual(before, self.snapshot())


if __name__ == "__main__":
    unittest.main()

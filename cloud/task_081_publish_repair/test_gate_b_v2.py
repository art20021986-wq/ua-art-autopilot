from __future__ import annotations

import pathlib
import shutil
import sqlite3
import sys
import tempfile
import unittest


HERE = pathlib.Path(__file__).resolve().parent
LIVE_CANDIDATES = (
    HERE / "evidence" / "live_audit_v2" / "sources",
    HERE.parent / "task081_live_audit_v2" / "sources",
)
LIVE = next((path for path in LIVE_CANDIDATES if path.is_dir()), LIVE_CANDIDATES[0])
sys.path.insert(0, str(HERE))

import gate_b_installer_v2 as installer  # noqa: E402
import patcher_v2 as patcher  # noqa: E402


class GateBInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = pathlib.Path(tempfile.mkdtemp(prefix="task081-gate-b-test-"))
        self.root = self.temp / "root"
        self.safe = self.temp / "safe"
        self.root.mkdir()
        self.safe.mkdir()
        for name in patcher.FULL_FILE_SHA256:
            shutil.copy2(LIVE / name, self.root / name)
        for folder_name in ("video", "site"):
            folder = self.root / folder_name
            folder.mkdir()
            links = []
            for index in range(1, 12):
                number = "UA-%04d" % index
                (folder / (number + ".html")).write_text(
                    "<html>%s protected</html>" % number, encoding="utf-8"
                )
                (folder / (number + "-diag.html")).write_text(
                    "<html>%s диагностика protected</html>" % number,
                    encoding="utf-8",
                )
                links.append('<a href="%s.html">%s</a>' % (number, number))
            (folder / "katalog.html").write_text(
                "<html>" + "".join(links) + "</html>", encoding="utf-8"
            )
        database = self.root / "crm.db"
        connection = sqlite3.connect(database)
        connection.execute(
            "CREATE TABLE cars ("
            "id INTEGER PRIMARY KEY, auto_number TEXT UNIQUE, status TEXT, "
            "published INTEGER, publish_pending INTEGER, sea_container TEXT)"
        )
        for index in range(1, 14):
            connection.execute(
                "INSERT INTO cars VALUES (?,?,?,?,?,?)",
                (
                    index,
                    "UA-%04d" % index,
                    "sea_loaded" if index >= 11 else "ua_arrived",
                    1,
                    0,
                    "ONEYSELGF1046602" if index == 13 else "",
                ),
            )
        connection.commit()
        connection.close()

        installer.ROOT = self.root
        installer.SAFE = self.safe
        installer.BACKUP_PARENT = self.safe / "backups_v2"
        installer.LOCK_FILE = self.safe / ".lock"
        installer.DATABASE = database
        installer.PUBLIC_DIRS = (self.root / "video", self.root / "site")
        installer.SHADOW_RECEIPT = self.safe / "shadow.json"
        installer.INSTALL_RECEIPT = self.safe / "install.json"
        installer.ROLLBACK_RECEIPT = self.safe / "rollback.json"

    def tearDown(self):
        shutil.rmtree(self.temp, ignore_errors=True)

    def test_target_discovery_is_bounded_and_stage_is_correct(self):
        database = installer.database_snapshot()
        self.assertEqual(database["quick_check"], "ok")
        self.assertEqual(database["canary"]["status"], "sea_loaded")
        self.assertEqual(installer.repair_targets(database), ["UA-0012", "UA-0013"])

    def test_exact_candidates_build_from_fresh_live_sources(self):
        candidates = installer.build_candidates()
        self.assertEqual(set(candidates), set(patcher.FULL_FILE_SHA256))
        for name, value in candidates.items():
            compile(value.decode("utf-8"), name, "exec")

    def test_outer_backup_restores_code_new_pages_and_catalogs(self):
        before = installer.full_snapshot()
        backup = installer.make_backup(before)
        (self.root / "cars_ui.py").write_text("BROKEN", encoding="utf-8")
        for folder in installer.PUBLIC_DIRS:
            (folder / "katalog.html").write_text("BROKEN CATALOG", encoding="utf-8")
            for number in before["repair_targets"]:
                (folder / (number + ".html")).write_text("NEW", encoding="utf-8")
                (folder / (number + "-diag.html")).write_text("NEW", encoding="utf-8")
        result = installer.restore_backup(backup)
        self.assertTrue(result["verified"])
        self.assertEqual(installer.full_snapshot(), before)
        for folder in installer.PUBLIC_DIRS:
            for number in before["repair_targets"]:
                self.assertFalse((folder / (number + ".html")).exists())
                self.assertFalse((folder / (number + "-diag.html")).exists())

    def test_more_than_five_missing_cards_fails_closed(self):
        for folder in installer.PUBLIC_DIRS:
            for index in range(7, 12):
                number = "UA-%04d" % index
                (folder / (number + ".html")).unlink()
                (folder / (number + "-diag.html")).unlink()
        with self.assertRaises(installer.InstallBlocked):
            installer.repair_targets(installer.database_snapshot())


if __name__ == "__main__":
    unittest.main(verbosity=2)

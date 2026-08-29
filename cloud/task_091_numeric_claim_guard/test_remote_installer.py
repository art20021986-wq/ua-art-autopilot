#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest

from test_patcher import AI_FILTER_FIXTURE, LOCAL_OCR_FIXTURE


class RemoteInstallerTests(unittest.TestCase):
    def test_preflight_install_postcheck_and_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            os.environ["UA_ART_ROOT"] = str(root)
            remote = root / "autopilot_inbox/cloud/task_091_numeric_claim_guard"
            remote.mkdir(parents=True)
            source_root = Path(__file__).resolve().parent
            for name in ("field_claim_guard.py", "patcher.py"):
                shutil.copy2(source_root / name, remote / name)
            (root / "ai_filter.py").write_text(AI_FILTER_FIXTURE, encoding="utf-8")
            (root / "local_ocr.py").write_text(LOCAL_OCR_FIXTURE, encoding="utf-8")

            database = sqlite3.connect(root / "crm.db")
            database.execute(
                "CREATE TABLE cars (id INTEGER PRIMARY KEY, auto_number TEXT, vin TEXT, "
                "year TEXT, engine_cc INTEGER, mileage_km INTEGER, fuel TEXT, "
                "published INTEGER, updated_at TEXT)"
            )
            database.execute(
                "CREATE TABLE audit (id INTEGER PRIMARY KEY AUTOINCREMENT, actor_id INTEGER, "
                "action TEXT, entity_type TEXT, entity_id INTEGER, field TEXT, old_value TEXT, "
                "new_value TEXT, created_at TEXT)"
            )
            database.execute(
                "INSERT INTO cars VALUES(1,'UA-0015','KMHE341DBJA475862','1999',"
                "1999,395459,'LPG',0,NULL)"
            )
            database.execute(
                "INSERT INTO cars VALUES(2,'UA-0001','TESTVIN0000000001','2018',"
                "2000,198000,'LPG',1,NULL)"
            )
            database.commit()
            database.close()

            spec = importlib.util.spec_from_file_location(
                "task091_remote_installer_fixture", source_root / "remote_installer.py"
            )
            module = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            spec.loader.exec_module(module)

            before_ai = (root / "ai_filter.py").read_bytes()
            before_ocr = (root / "local_ocr.py").read_bytes()
            preflight = module.preflight()
            self.assertEqual(preflight["status"], "PASS", preflight["errors"])
            installed = module.install()
            self.assertEqual(installed["status"], "PASS", installed["errors"])
            self.assertTrue(installed["crm_write"])
            checked = module.postcheck()
            self.assertEqual(checked["status"], "PASS", checked["errors"])

            database = sqlite3.connect(root / "crm.db")
            row = database.execute(
                "SELECT year,engine_cc,mileage_km FROM cars WHERE auto_number='UA-0015'"
            ).fetchone()
            other = database.execute(
                "SELECT year,engine_cc,mileage_km FROM cars WHERE auto_number='UA-0001'"
            ).fetchone()
            audits = database.execute("SELECT count(*) FROM audit").fetchone()[0]
            database.close()
            self.assertEqual(row, ("", 1999, 395459))
            self.assertEqual(other, ("2018", 2000, 198000))
            self.assertEqual(audits, 1)

            rolled_back = module.restore_backup(Path(installed["backup_root"]))
            self.assertTrue(rolled_back["restored"])
            self.assertEqual((root / "ai_filter.py").read_bytes(), before_ai)
            self.assertEqual((root / "local_ocr.py").read_bytes(), before_ocr)
            self.assertFalse((root / "field_claim_guard.py").exists())
            database = sqlite3.connect(root / "crm.db")
            restored = database.execute(
                "SELECT year,engine_cc,mileage_km FROM cars WHERE auto_number='UA-0015'"
            ).fetchone()
            database.close()
            self.assertEqual(restored, ("1999", 1999, 395459))


if __name__ == "__main__":
    unittest.main()

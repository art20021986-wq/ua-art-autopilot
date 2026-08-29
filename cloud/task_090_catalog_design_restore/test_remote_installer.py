#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
import pathlib
import shutil
import sqlite3
import tempfile
import unittest

from test_catalog_design_guard import ARTICLE, GOLDEN, rows_13


class RemoteInstallerTests(unittest.TestCase):
    def test_atomic_install_postcheck_and_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            os.environ["UA_ART_ROOT"] = str(root)
            for name in ("video", "site"):
                (root / name).mkdir(parents=True)
            remote = root / "autopilot_inbox/cloud/task_090_catalog_design_restore"
            remote.mkdir(parents=True)
            shutil.copy2(
                pathlib.Path(__file__).with_name("catalog_design_guard.py"),
                remote / "catalog_design_guard.py",
            )

            # The approved backup has the real shell and ten historical article cards.
            approved_cards = []
            for number in range(1, 11):
                code = "UA-%04d" % number
                approved_cards.append(ARTICLE.replace("UA-0001", code))
            approved = GOLDEN.replace(ARTICLE, "\n".join(approved_cards))
            backup_catalog = (
                root / "rezerv_publikacii/TASK083/fixture/files/video/katalog.html"
            )
            backup_catalog.parent.mkdir(parents=True)
            backup_catalog.write_text(approved, encoding="utf-8")

            bare = "<html><head></head><body>13 в подборке</body></html>"
            for path in (root / "video/katalog.html", root / "site/katalog.html"):
                path.write_text(bare, encoding="utf-8")

            master_original = """def obrabotat_obshuyu(html):\n    return html\ndef vse_kody():\n    return []\ndef _ua068_master_row(code):\n    return {}\n"""
            (root / "master_card.py").write_text(master_original, encoding="utf-8")
            publish_original = """class PublishError(RuntimeError):\n    pass\ndef _validate_catalog(source, rows):\n    return {}\ndef _install_catalog(source, target):\n    return {}\ndef _row_map():\n    return {}, ''\ndef _atomic(path, data, mode=None):\n    return None\n"""
            (root / "publish_transaction_guard.py").write_text(
                publish_original, encoding="utf-8"
            )

            rows = rows_13()
            connection = sqlite3.connect(root / "crm.db")
            columns = (
                "id INTEGER PRIMARY KEY, auto_number TEXT, published INTEGER, "
                "status TEXT, brand TEXT, model TEXT, year TEXT, price_uah INTEGER, "
                "mileage_km INTEGER, engine_cc INTEGER, fuel TEXT, gearbox TEXT, "
                "vin TEXT, photos TEXT, videos TEXT"
            )
            connection.execute("CREATE TABLE cars (%s)" % columns)
            for index, row in enumerate(rows, 1):
                connection.execute(
                    "INSERT INTO cars VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        index,
                        row["auto_number"],
                        row["published"],
                        row["status"],
                        row["brand"],
                        row["model"],
                        row["year"],
                        row["price_uah"],
                        row["mileage_km"],
                        row["engine_cc"],
                        row["fuel"],
                        row["gearbox"],
                        row["vin"],
                        row["photos"],
                        row["videos"],
                    ),
                )
                page = (
                    '<html><body><img data-mcf-foto="1" src="/video/stage/%s.webp">'
                    "</body></html>" % row["auto_number"]
                )
                for folder in ("video", "site"):
                    (root / folder / (row["auto_number"] + ".html")).write_text(
                        page, encoding="utf-8"
                    )
            connection.commit()
            connection.close()

            specification = importlib.util.spec_from_file_location(
                "task090_remote_installer_fixture",
                pathlib.Path(__file__).with_name("remote_installer.py"),
            )
            module = importlib.util.module_from_spec(specification)
            assert specification.loader is not None
            specification.loader.exec_module(module)

            installed = module.install()
            self.assertEqual(installed["status"], "PASS", installed.get("errors"))
            checked = module.postcheck()
            self.assertEqual(checked["status"], "PASS", checked.get("errors"))
            self.assertEqual(
                checked["database"]["counts"],
                {"all": 13, "kiev": 3, "georgia": 1, "sea": 7, "korea": 2},
            )
            self.assertIn(module.MASTER_START, (root / "master_card.py").read_text())
            self.assertIn(
                module.PUBLISH_START,
                (root / "publish_transaction_guard.py").read_text(),
            )

            rolled_back = module.restore_backup(
                pathlib.Path(installed["backup_root"])
            )
            self.assertTrue(rolled_back["backup_root"])
            self.assertEqual((root / "video/katalog.html").read_text(), bare)
            self.assertEqual((root / "site/katalog.html").read_text(), bare)
            self.assertEqual((root / "master_card.py").read_text(), master_original)
            self.assertEqual(
                (root / "publish_transaction_guard.py").read_text(),
                publish_original,
            )


if __name__ == "__main__":
    unittest.main()


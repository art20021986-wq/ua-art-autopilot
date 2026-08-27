import os
import shutil
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import discover


class TestDiscover(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, rel, content):
        full = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(content)
        return full

    def test_root_mismatch_blocked(self):
        with self.assertRaises(discover.DiscoveryBlocked):
            discover.run_discovery(root=self.tmp, allowed_root="/home/Carix", registry=[])

    def test_symlink_rejected(self):
        target = self._write("real.html", "<p>hi</p>")
        link_path = os.path.join(self.tmp, "link.html")
        os.symlink(target, link_path)
        with self.assertRaises(discover.DiscoveryBlocked):
            discover.lstat_check(link_path)

    def test_secret_line_redacted(self):
        self._write(
            "stranica.py",
            "API_KEY = 'sk_live_abcdefghijklmnopqrstuvwxyz123456'\nlabel = 'В море'\n",
        )
        receipt = discover.run_discovery(root=self.tmp, allowed_root=self.tmp, registry=["stranica.py"])
        file_entry = receipt["files"][0]
        for occ in file_entry["occurrences"]:
            self.assertNotIn("sk_live_abcdefghijklmnopqrstuvwxyz123456", occ["context"])

    def test_nine_card_registry_present(self):
        ua_files = [p for p in discover.CANDIDATE_REGISTRY if p.startswith("video/public/UA-000")]
        self.assertEqual(len(ua_files), 9)

    def test_classification_of_occurrence(self):
        self._write("video/public/UA-0001.html", '<span>В море</span>')
        receipt = discover.run_discovery(
            root=self.tmp, allowed_root=self.tmp, registry=["video/public/UA-0001.html"]
        )
        occ = receipt["files"][0]["occurrences"][0]
        self.assertIn(occ["classification"], ("USER_FACING_SHORT_STAGE", "USER_FACING_STATUS"))

    def test_sha256_stable(self):
        self._write("stranica.py", "x = 'В море'\n")
        r1 = discover.run_discovery(root=self.tmp, allowed_root=self.tmp, registry=["stranica.py"])
        r2 = discover.run_discovery(root=self.tmp, allowed_root=self.tmp, registry=["stranica.py"])
        self.assertEqual(r1["files"][0]["sha256"], r2["files"][0]["sha256"])

    def test_crm_db_missing_reports_unavailable(self):
        receipt = discover.run_discovery(root=self.tmp, allowed_root=self.tmp, registry=[])
        self.assertFalse(receipt["crm_db"]["available"])

    def test_crm_db_readonly_query(self):
        db_path = os.path.join(self.tmp, "crm.db")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE cars (id TEXT, stage TEXT)")
        conn.executemany("INSERT INTO cars VALUES (?, ?)", [("UA-0001", "sea"), ("UA-0002", "kyiv")])
        conn.commit()
        conn.close()
        receipt = discover.run_discovery(
            root=self.tmp, allowed_root=self.tmp, registry=[], ua_ids=["UA-0001", "UA-0002"]
        )
        self.assertTrue(receipt["crm_db"]["available"])
        self.assertEqual(len(receipt["crm_db"]["rows"]), 2)

    def test_safety_markers_present(self):
        receipt = discover.run_discovery(root=self.tmp, allowed_root=self.tmp, registry=[])
        self.assertEqual(receipt["production_touched"], "NO")
        self.assertEqual(receipt["crm_db_written"], "NO")
        self.assertEqual(receipt["gate_b_executed"], "NO")


if __name__ == "__main__":
    unittest.main()

from contextlib import contextmanager
from pathlib import Path
import sqlite3
import tempfile
import unittest

from public_write_guard import PublicWriteGuard, PublicWriteRejected, advertised_codes


class PublicWriterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "video").mkdir()
        (self.root / "site").mkdir()
        self.db = self.root / "crm.db"
        with sqlite3.connect(self.db) as conn:
            conn.executescript("CREATE TABLE cars(id INTEGER PRIMARY KEY,auto_number TEXT,published INTEGER);"
                               "INSERT INTO cars VALUES(8,'UA-0002',1),(2,'UA-0003',1);"
                               "CREATE TABLE ua_delete_intents(car_code TEXT);")
        self.depth = 0
        self.guard = PublicWriteGuard(root=self.root, db_path=self.db,
            publication_fence=self.fence, require_fence=self.require_fence)

    @contextmanager
    def fence(self):
        self.depth += 1
        try:
            yield
        finally:
            self.depth -= 1

    def require_fence(self):
        if not self.depth:
            raise RuntimeError("FENCE_REQUIRED")

    def retire(self):
        with sqlite3.connect(self.db) as conn:
            conn.execute("INSERT INTO ua_delete_intents VALUES('UA-0002')")
            conn.execute("DELETE FROM cars WHERE id=8")

    def test_stale_direct_and_alias_pages_block_after_crm_row_gone(self):
        self.retire()
        for name in ("UA-0002.html", "UA-0002-diag.html", "UA-0002-ab12cd.html"):
            called = False
            with self.assertRaises(PublicWriteRejected):
                with self.guard.write(self.root / "video" / name, "old page"):
                    called = True
            self.assertFalse(called)

    def test_stale_shared_snapshot_cannot_restore_removed_tile(self):
        self.retire()
        with self.assertRaisesRegex(PublicWriteRejected, "DELETED_CAR"):
            with self.guard.write(self.root / "site/katalog.html", '<a href="UA-0002.html?old=1">Sold</a>'):
                self.fail("Stale rollback must never reach write")

    def test_unrelated_vehicle_writer_retains_fence_through_effect(self):
        self.retire()
        with self.guard.write(self.root / "video/UA-0003.html", "current page"):
            self.assertEqual(self.depth, 1)
        self.assertEqual(self.depth, 0)

    def test_nested_public_alias_is_guarded(self):
        self.retire()
        nested = self.root / "video/legacy"
        nested.mkdir()
        with self.assertRaisesRegex(PublicWriteRejected, "DELETED_CAR"):
            with self.guard.write(nested / "UA-0002.html", "old alias"):
                pass

    def test_missing_or_hidden_current_identity_cannot_be_written(self):
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE cars SET published=0 WHERE id=8")
        with self.assertRaisesRegex(PublicWriteRejected, "CURRENT_PUBLISHED"):
            with self.guard.write(self.root / "video/UA-0002.html", "cached page"):
                pass

    def test_missing_schema_does_not_silently_bypass_guard(self):
        with sqlite3.connect(self.db) as conn:
            conn.execute("DROP TABLE ua_delete_intents")
        with self.assertRaisesRegex(PublicWriteRejected, "SCHEMA_NOT_INSTALLED"):
            with self.guard.write(self.root / "site/index.html", "home"):
                pass

    def test_legacy_asset_remains_allowed_but_script_ad_link_is_detected(self):
        self.assertEqual(advertised_codes('<img src="stage/UA-0002.webp">'), set())
        self.assertEqual(advertised_codes('<script>const url="UA-0002.html";</script>'), {"UA-0002"})
        self.assertEqual(advertised_codes('<a href="UA%2D0002.html">sold</a>'), {"UA-0002"})

    def test_noncanonical_backup_path_cannot_bypass_public_guard(self):
        self.retire()
        (self.root / "backup").mkdir()
        paths = [self.root / "backup/../video/UA-0002.html"]
        (self.root / "backup/link").symlink_to(self.root / "video", target_is_directory=True)
        paths.append(self.root / "backup/link/UA-0002.html")
        for path in paths:
            with self.assertRaisesRegex(PublicWriteRejected, "CANONICAL"):
                with self.guard.write(path, "old page"):
                    pass

    def test_foreign_backup_write_is_not_mistaken_for_public_route(self):
        self.retire()
        with self.guard.write(self.root / "backup/UA-0002.html", "private backup"):
            self.assertEqual(self.depth, 1)

    def test_unrecognized_car_alias_and_symlink_fail_before_effect(self):
        for name in ("UA-00020.html", "UA-0002-new.html"):
            with self.assertRaisesRegex(PublicWriteRejected, "UNBOUND"):
                with self.guard.write(self.root / "video" / name, "page"):
                    pass
        target = self.root / "actual.html"
        target.write_text("page")
        alias = self.root / "video/UA-0003.html"
        alias.symlink_to(target)
        with self.assertRaisesRegex(PublicWriteRejected, "CANONICAL"):
            with self.guard.write(alias, "page"):
                pass


if __name__ == "__main__":
    unittest.main()

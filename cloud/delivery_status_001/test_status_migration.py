"""Exercise real SQLite migration, backup and rollback boundaries."""

from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from status_migration import MigrationError, REMOVED_STATUSES, migrate, rollback


class StatusMigrationTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.database = self.root / "crm.db"
        self.backup = self.root / "before.db"
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("CREATE TABLE cars (id INTEGER PRIMARY KEY, status TEXT, price INTEGER, vin TEXT)")
            connection.executemany("INSERT INTO cars VALUES (?, ?, ?, ?)", [
                (1, "archive", 100, "test-a"), (2, "sold", 200, "test-b"),
                (3, "sea_loaded", 300, "test-c"), (4, None, 400, "test-d"),
            ])
            connection.commit()

    def rows(self, database=None):
        with closing(sqlite3.connect(database or self.database)) as connection:
            return connection.execute("SELECT * FROM cars ORDER BY id").fetchall()

    def write(self, sql, parameters=()):
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute(sql, parameters)
            connection.commit()

    def test_migration_backup_and_idempotence(self):
        before = self.rows()
        receipt = migrate(self.database, self.backup)
        self.assertEqual(receipt["changed_rows"], 2)
        self.assertEqual(self.rows(self.backup), before)
        self.assertEqual(self.backup.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.rows(), [(1, "hidden", 100, "test-a"), (2, "hidden", 200, "test-b")] + before[2:])
        self.assertEqual(migrate(self.database, self.root / "second.db")["changed_rows"], 0)

    def test_rollback_preserves_unrelated_edits_and_is_idempotent(self):
        before = self.rows()
        receipt = migrate(self.database, self.backup)
        self.write("UPDATE cars SET price = 999 WHERE id = 3")
        result = rollback(self.database, self.backup, receipt["backup_sha256"])
        self.assertEqual(result["restored_rows"], 2)
        self.assertEqual(self.rows()[:2], before[:2])
        self.assertEqual(self.rows()[2][2], 999)
        self.assertEqual(rollback(self.database, self.backup, receipt["backup_sha256"])["restored_rows"], 0)

    def test_wal_backup_includes_committed_rows(self):
        with closing(sqlite3.connect(self.database)) as writer:
            writer.execute("PRAGMA journal_mode=WAL")
            writer.execute("UPDATE cars SET price = 555 WHERE id = 1")
            writer.commit()
            receipt = migrate(self.database, self.backup)
            self.assertEqual(self.rows(self.backup)[0], (1, "archive", 555, "test-a"))
            rollback(self.database, self.backup, receipt["backup_sha256"])
            self.assertEqual(self.rows()[0], (1, "archive", 555, "test-a"))

    def test_rollback_rejects_concurrent_status_or_other_field_change_atomically(self):
        receipt = migrate(self.database, self.backup)
        for column, value in (("status", "ua_arrived"), ("price", 777)):
            with self.subTest(column=column):
                self.write("UPDATE cars SET status = 'hidden', price = 200 WHERE id = 2")
                self.write("UPDATE cars SET " + column + " = ? WHERE id = 2", (value,))
                before = self.rows()
                with self.assertRaisesRegex(MigrationError, "ROLLBACK_ROW_CHANGED"):
                    rollback(self.database, self.backup, receipt["backup_sha256"])
                self.assertEqual(self.rows(), before)

    def test_rollback_rejects_missing_row(self):
        receipt = migrate(self.database, self.backup)
        self.write("DELETE FROM cars WHERE id = 2")
        before = self.rows()
        with self.assertRaisesRegex(MigrationError, "ROLLBACK_ROW_CHANGED"):
            rollback(self.database, self.backup, receipt["backup_sha256"])
        self.assertEqual(self.rows(), before)

    def test_bad_backup_identity_cannot_write(self):
        migrate(self.database, self.backup)
        before = self.rows()
        with self.assertRaisesRegex(MigrationError, "BACKUP_IDENTITY_CHANGED"):
            rollback(self.database, self.backup, "0" * 64)
        self.assertEqual(self.rows(), before)

    def test_existing_backup_cannot_be_overwritten(self):
        self.backup.write_bytes(b"keep existing backup")
        before = self.rows()
        with self.assertRaises(FileExistsError):
            migrate(self.database, self.backup)
        self.assertEqual(self.backup.read_bytes(), b"keep existing backup")
        self.assertEqual(self.rows(), before)

    def test_unreviewed_trigger_stops_before_backup_or_update(self):
        self.write("CREATE TRIGGER changed AFTER UPDATE ON cars BEGIN UPDATE cars SET price = 0 WHERE id = NEW.id; END")
        before = self.rows()
        with self.assertRaisesRegex(MigrationError, "CARS_TRIGGERS_REQUIRE_REVIEW"):
            migrate(self.database, self.backup)
        self.assertEqual(self.rows(), before)
        self.assertFalse(self.backup.exists())

    def test_symlink_cannot_redirect_database(self):
        link = self.root / "link.db"
        link.symlink_to(self.database)
        with self.assertRaisesRegex(MigrationError, "UNSAFE_DATABASE_FILE"):
            migrate(link, self.backup)

    def test_standalone_sql_matches_migrator_scope(self):
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("DELETE FROM cars")
            statuses = REMOVED_STATUSES + ("korea", "ferry", "georgia", "kyiv", "hidden", None, "unknown")
            connection.executemany("INSERT INTO cars (id, status) VALUES (?, ?)", enumerate(statuses, 1))
            connection.commit()
        before = self.rows()
        migrate(self.database, self.backup)
        expected = self.rows()
        with closing(sqlite3.connect(self.root / "sql.db")) as connection:
            connection.execute("CREATE TABLE cars (id INTEGER PRIMARY KEY, status TEXT, price INTEGER, vin TEXT)")
            connection.executemany("INSERT INTO cars VALUES (?, ?, ?, ?)", before)
            connection.commit()
            connection.executescript(Path(__file__).with_name("migrate_removed_statuses.sql").read_text())
            self.assertEqual(connection.execute("SELECT * FROM cars ORDER BY id").fetchall(), expected)


if __name__ == "__main__":
    unittest.main()

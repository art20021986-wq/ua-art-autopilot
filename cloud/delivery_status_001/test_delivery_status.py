import sqlite3
import unittest
from pathlib import Path

from delivery_status import HIDDEN, catalog_counts, public_label, public_status


class DeliveryStatusTest(unittest.TestCase):
    def test_active_internal_codes_and_public_codes(self):
        for internal, public in (
            ("kr_bought", "korea"),
            ("sea_loaded", "ferry"),
            ("ge_waiting", "georgia"),
            ("ua_arrived", "kyiv"),
        ):
            self.assertEqual(public_status(internal), public)
            self.assertEqual(public_status(public), public)
            self.assertIsNotNone(public_label(internal))

    def test_removed_unknown_and_malformed_hide_without_exception(self):
        for value in ("sold_transit", "ge_to_kyiv", "sold", "archive",
                      "Продано в пути", "Выехало в Киев", "Продано",
                      "Архив", None, {}, [], 3, "surprise"):
            self.assertEqual(public_status(value), HIDDEN)
            self.assertIsNone(public_label(value))

    def test_counts_exclude_hidden(self):
        self.assertEqual(catalog_counts(["kr_bought", "sea_loaded", "ge_waiting",
                                         "ua_arrived", "sold", "unexpected"]),
                         {"korea": 1, "ferry": 1, "georgia": 1, "kyiv": 1})

    def test_migration_changes_only_removed_values_and_is_idempotent(self):
        connection = sqlite3.connect(":memory:")
        connection.execute("CREATE TABLE cars (id INTEGER PRIMARY KEY, status TEXT)")
        initial = ["kr_bought", "sea_loaded", "ge_waiting", "ua_arrived",
                   "sold_transit", "ge_to_kyiv", "sold", "archive", "unexpected"]
        connection.executemany("INSERT INTO cars (status) VALUES (?)", ((x,) for x in initial))
        connection.commit()
        script = Path(__file__).with_name("migrate_removed_statuses.sql").read_text()
        connection.executescript(script)
        first = [row[0] for row in connection.execute("SELECT status FROM cars ORDER BY id")]
        self.assertEqual(first, initial[:4] + ["hidden"] * 4 + ["unexpected"])
        connection.executescript(script)
        second = [row[0] for row in connection.execute("SELECT status FROM cars ORDER BY id")]
        self.assertEqual(second, first)


if __name__ == "__main__":
    unittest.main()

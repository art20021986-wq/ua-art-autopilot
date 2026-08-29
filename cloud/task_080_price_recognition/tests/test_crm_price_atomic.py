import json
import sqlite3
import tempfile
import threading
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from crm_price_atomic import write_price


def make_db(path, card_count=14):
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE cars (
            id INTEGER PRIMARY KEY,
            auto_number TEXT NOT NULL,
            price_uah INTEGER,
            price_history TEXT,
            status TEXT,
            updated_at TEXT,
            description TEXT
        );
        CREATE TABLE audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_id INTEGER,
            action TEXT NOT NULL,
            entity_type TEXT,
            entity_id INTEGER,
            field TEXT,
            old_value TEXT,
            new_value TEXT,
            created_at TEXT NOT NULL
        );
        """
    )
    for offset in range(card_count):
        cid = offset + 1
        number = "UA-%04d" % (offset + 1)
        con.execute(
            "INSERT INTO cars "
            "(id,auto_number,price_uah,price_history,status,description) "
            "VALUES (?,?,?,?,?,?)",
            (cid, number, None, None, "sea_loaded", "preserve-" + number),
        )
    con.commit()
    con.close()


def connect_factory(path):
    def connect():
        con = sqlite3.connect(path, timeout=2)
        con.row_factory = sqlite3.Row
        return con
    return connect


def now():
    return "2026-08-29T07:30:00"


def rows(path, sql, params=()):
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in con.execute(sql, params).fetchall()]
    finally:
        con.close()


def call(path, **overrides):
    args = {
        "connect": connect_factory(path),
        "now": now,
        "card_id": 1,
        "expected_auto_number": "UA-0001",
        "expected_status": "sea_loaded",
        "expected_old": None,
        "new_value": 11400,
        "actor_id": 77,
        "stage_key": 2,
        "correction": False,
    }
    args.update(overrides)
    return write_price(**args)


def test_empty_price_fill_is_one_atomic_update_and_one_audit():
    with tempfile.TemporaryDirectory() as temp:
        path = str(Path(temp) / "crm.db")
        make_db(path)
        result = call(path)
        assert result.ok and result.reason == "applied"
        card = rows(path, "SELECT * FROM cars WHERE id=1")[0]
        assert card["price_uah"] == 11400
        assert json.loads(card["price_history"]) == {"2": 11400}
        assert card["description"] == "preserve-UA-0001"
        audit = rows(path, "SELECT * FROM audit")
        assert len(audit) == 1
        assert audit[0]["field"] == "price_uah"
        assert audit[0]["old_value"] is None
        assert audit[0]["new_value"] == "11400"


def test_filled_price_requires_correction():
    with tempfile.TemporaryDirectory() as temp:
        path = str(Path(temp) / "crm.db")
        make_db(path)
        assert call(path).ok
        result = call(path, expected_old=11400, new_value=12000, correction=False)
        assert not result.ok and result.reason == "filled"
        assert rows(path, "SELECT price_uah FROM cars WHERE id=1")[0]["price_uah"] == 11400
        assert len(rows(path, "SELECT * FROM audit")) == 1


def test_explicit_correction_updates_stage_history_once():
    with tempfile.TemporaryDirectory() as temp:
        path = str(Path(temp) / "crm.db")
        make_db(path)
        assert call(path).ok
        result = call(path, expected_old=11400, new_value=12000, correction=True)
        assert result.ok
        card = rows(path, "SELECT price_uah,price_history FROM cars WHERE id=1")[0]
        assert card["price_uah"] == 12000
        assert json.loads(card["price_history"]) == {"2": 12000}
        assert len(rows(path, "SELECT * FROM audit")) == 2


def test_stale_expected_value_fails_without_partial_change():
    with tempfile.TemporaryDirectory() as temp:
        path = str(Path(temp) / "crm.db")
        make_db(path)
        assert call(path).ok
        result = call(path, expected_old=9999, new_value=12000, correction=True)
        assert not result.ok and result.reason == "conflict"
        card = rows(path, "SELECT price_uah,price_history FROM cars WHERE id=1")[0]
        assert card["price_uah"] == 11400
        assert json.loads(card["price_history"]) == {"2": 11400}
        assert len(rows(path, "SELECT * FROM audit")) == 1


def test_audit_failure_rolls_back_price_and_history():
    with tempfile.TemporaryDirectory() as temp:
        path = str(Path(temp) / "crm.db")
        make_db(path)
        con = sqlite3.connect(path)
        con.execute(
            "CREATE TRIGGER reject_audit BEFORE INSERT ON audit "
            "BEGIN SELECT RAISE(ABORT,'injected audit failure'); END"
        )
        con.commit()
        con.close()
        result = call(path)
        assert not result.ok and result.reason.startswith("database:")
        card = rows(path, "SELECT price_uah,price_history FROM cars WHERE id=1")[0]
        assert card["price_uah"] is None
        assert card["price_history"] is None
        assert rows(path, "SELECT * FROM audit") == []


def test_readback_mismatch_rolls_back_price_history_and_audit():
    with tempfile.TemporaryDirectory() as temp:
        path = str(Path(temp) / "crm.db")
        make_db(path)
        con = sqlite3.connect(path)
        con.execute(
            "CREATE TRIGGER corrupt_price_history AFTER UPDATE OF price_history ON cars "
            "BEGIN UPDATE cars SET price_history='{}' WHERE id=NEW.id; END"
        )
        con.commit()
        con.close()
        result = call(path)
        assert not result.ok and "readback history" in result.reason
        card = rows(path, "SELECT price_uah,price_history FROM cars WHERE id=1")[0]
        assert card["price_uah"] is None
        assert card["price_history"] is None
        assert rows(path, "SELECT * FROM audit") == []


def test_same_value_is_idempotent_no_second_history_or_audit():
    with tempfile.TemporaryDirectory() as temp:
        path = str(Path(temp) / "crm.db")
        make_db(path)
        assert call(path).ok
        result = call(path, expected_old=11400, new_value=11400, correction=True)
        assert not result.ok and result.reason == "same"
        assert json.loads(rows(path, "SELECT price_history FROM cars WHERE id=1")[0]["price_history"]) == {"2": 11400}
        assert len(rows(path, "SELECT * FROM audit")) == 1


def test_undo_restores_empty_price_and_removes_stage_history():
    with tempfile.TemporaryDirectory() as temp:
        path = str(Path(temp) / "crm.db")
        make_db(path)
        assert call(path).ok
        result = call(
            path,
            expected_old=11400,
            new_value=None,
            correction=True,
            allow_clear=True,
        )
        assert result.ok
        card = rows(path, "SELECT price_uah,price_history FROM cars WHERE id=1")[0]
        assert card["price_uah"] is None
        assert json.loads(card["price_history"]) == {}
        assert len(rows(path, "SELECT * FROM audit")) == 2


def test_identity_mismatch_never_cross_writes():
    with tempfile.TemporaryDirectory() as temp:
        path = str(Path(temp) / "crm.db")
        make_db(path)
        result = call(path, expected_auto_number="UA-9999")
        assert not result.ok and result.reason == "identity_conflict"
        assert rows(path, "SELECT count(*) AS n FROM cars WHERE price_uah IS NOT NULL")[0]["n"] == 0
        assert rows(path, "SELECT * FROM audit") == []


def test_stage_change_fails_without_cross_stage_history():
    with tempfile.TemporaryDirectory() as temp:
        path = str(Path(temp) / "crm.db")
        make_db(path)
        con = sqlite3.connect(path)
        con.execute("UPDATE cars SET status='ua_delivered' WHERE id=1")
        con.commit()
        con.close()
        result = call(path)
        assert not result.ok and result.reason == "stage_conflict"
        card = rows(path, "SELECT price_uah,price_history FROM cars WHERE id=1")[0]
        assert card["price_uah"] is None and card["price_history"] is None
        assert rows(path, "SELECT * FROM audit") == []


def test_connection_failure_returns_bounded_result():
    def broken_connect():
        raise sqlite3.OperationalError("injected connect failure")

    result = write_price(
        connect=broken_connect,
        now=now,
        card_id=1,
        expected_auto_number="UA-0001",
        expected_status="sea_loaded",
        expected_old=None,
        new_value=11400,
        actor_id=77,
        stage_key=2,
        correction=False,
    )
    assert not result.ok and result.reason.startswith("database:")


def test_invalid_history_fails_closed():
    with tempfile.TemporaryDirectory() as temp:
        path = str(Path(temp) / "crm.db")
        make_db(path)
        con = sqlite3.connect(path)
        con.execute("UPDATE cars SET price_history='not-json' WHERE id=1")
        con.commit()
        con.close()
        result = call(path)
        assert not result.ok and result.reason == "invalid_history"
        assert rows(path, "SELECT price_uah FROM cars WHERE id=1")[0]["price_uah"] is None


def test_all_existing_and_future_cards_use_same_writer():
    with tempfile.TemporaryDirectory() as temp:
        path = str(Path(temp) / "crm.db")
        make_db(path, card_count=14)
        for cid in range(1, 15):
            number = "UA-%04d" % cid
            result = call(
                path,
                card_id=cid,
                expected_auto_number=number,
                new_value=10000 + cid,
            )
            assert result.ok
        cards = rows(path, "SELECT id,auto_number,price_uah FROM cars ORDER BY id")
        assert len(cards) == 14
        assert cards[-1] == {
            "id": 14,
            "auto_number": "UA-0014",
            "price_uah": 10014,
        }
        assert len(rows(path, "SELECT * FROM audit")) == 14


def test_two_cards_do_not_cross_write_under_concurrency():
    with tempfile.TemporaryDirectory() as temp:
        path = str(Path(temp) / "crm.db")
        make_db(path)
        barrier = threading.Barrier(2)
        results = []

        def worker(cid, number, value):
            barrier.wait()
            results.append(
                call(
                    path,
                    card_id=cid,
                    expected_auto_number=number,
                    new_value=value,
                )
            )

        threads = [
            threading.Thread(target=worker, args=(1, "UA-0001", 11111)),
            threading.Thread(target=worker, args=(2, "UA-0002", 12222)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert len(results) == 2
        assert all(result.ok for result in results), results
        values = rows(path, "SELECT id,price_uah FROM cars WHERE id IN (1,2) ORDER BY id")
        assert values == [{"id": 1, "price_uah": 11111}, {"id": 2, "price_uah": 12222}]
        assert len(rows(path, "SELECT * FROM audit")) == 2

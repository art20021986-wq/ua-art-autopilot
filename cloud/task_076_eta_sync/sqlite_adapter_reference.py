"""Reference SQLite DbAdapter implementing row-level transactions.

This is a REFERENCE implementation for integration into the real crm.db
access layer. It must be adapted to the exact verified schema (table/column
names) discovered during Gate A read-only audit BEFORE being wired into any
write path. It intentionally never replaces the full database file; it
performs a single row UPDATE inside BEGIN IMMEDIATE, per the task's explicit
requirement: 'DB row-level transaction (не full DB replace)'.

NOT executed against any real database by this delivery.
"""
from __future__ import annotations

import sqlite3
from typing import Optional


class SqliteEtaDbAdapter:
    def __init__(self, db_path: str, table: str = "cars", id_column: str = "car_id"):
        self.db_path = db_path
        self.table = table
        self.id_column = id_column
        self._conn: Optional[sqlite3.Connection] = None

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def begin(self, car_id: str) -> None:
        self._conn = self._connect()
        self._conn.execute("BEGIN IMMEDIATE")

    def write_eta(self, car_id: str, days_to_kyiv: int, eta_manual: str, updated_at: str) -> None:
        assert self._conn is not None, "begin() must be called first"
        cur = self._conn.execute(
            f"UPDATE {self.table} SET days_to_kyiv=?, eta_manual=?, updated_at=? "
            f"WHERE {self.id_column}=?",
            (days_to_kyiv, eta_manual, updated_at, car_id),
        )
        if cur.rowcount != 1:
            raise RuntimeError(
                f"expected exactly 1 row updated for {car_id}, got {cur.rowcount}"
            )

    def read_back(self, car_id: str) -> dict:
        assert self._conn is not None, "begin() must be called first"
        cur = self._conn.execute(
            f"SELECT days_to_kyiv, eta_manual, updated_at FROM {self.table} "
            f"WHERE {self.id_column}=?",
            (car_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else {}

    def rollback(self, car_id: str, previous: dict) -> None:
        assert self._conn is not None, "begin() must be called first"
        if not previous:
            self._conn.rollback()
            self._conn.close()
            self._conn = None
            return
        self._conn.execute(
            f"UPDATE {self.table} SET days_to_kyiv=?, eta_manual=?, updated_at=? "
            f"WHERE {self.id_column}=?",
            (previous.get("days_to_kyiv"), previous.get("eta_manual"),
             previous.get("updated_at"), car_id),
        )
        self._conn.commit()
        self._conn.close()
        self._conn = None

    def commit(self, car_id: str) -> None:
        assert self._conn is not None, "begin() must be called first"
        self._conn.commit()
        self._conn.close()
        self._conn = None

#!/usr/bin/env python3
"""Fail-closed installer for CRM-DB-LOCK-EMERGENCY-001."""
from __future__ import annotations

import ast
import datetime as dt
import hashlib
import json
import os
import pathlib
import shutil
import sqlite3
import stat
import sys
import tempfile


BASE = pathlib.Path("/home/Carix")
DB_PY = BASE / "db.py"
CRM_DB = BASE / "crm.db"
SAFE = BASE / "autopilot_inbox" / "cloud" / "task_064"
BACKUPS = BASE / "backups" / "task_064"
INSTALL_RECEIPT = SAFE / "install_receipt.json"
ROLLBACK_RECEIPT = SAFE / "rollback_receipt.json"
EXPECTED_DB_SHA = "b5089b54646d72cf76f00a0e8cc454d2192d34764469e4f183eee502b9c8b600"
EXPECTED_CLASS_SHA = "591ef89051b168efe9f122e917e8c54eaff7ba88058ac59977801747d3484b5e"
EXPECTED_CONNECT_SHA = "40daadeb50ac5ffdb79918c4c64b0fcabcf91ec2d657e2a47d46c41e3eb2c3a8"
MARKER = "CRM-DB-LOCK-EMERGENCY-001"


HELPERS_AND_CLASS = r'''# CRM-DB-LOCK-EMERGENCY-001: one queue per write transaction.
_UA_FAYL_SOSTOYANIE = _potoki.local()


def _ua_sql_pishet(sql):
    """Conservatively classify SQL; unknown statements enter the write queue."""
    try:
        text = str(sql).lstrip()
        while text.startswith("--"):
            text = text.split("\n", 1)[1].lstrip()
        slovo = text.split(None, 1)[0].upper().rstrip(";") if text else ""
    except Exception:
        return True
    return slovo not in ("", "SELECT", "PRAGMA", "EXPLAIN")


def _ua_fayl_zahvatit(timeout):
    """Re-entrant per-thread registration over one cross-process flock."""
    import fcntl as _ua_fcntl
    import time as _ua_time

    depth = int(getattr(_UA_FAYL_SOSTOYANIE, "depth", 0) or 0)
    if depth:
        _UA_FAYL_SOSTOYANIE.depth = depth + 1
        return

    handle = open(os.path.join(BASE_DIR, ".crm_db.lock"), "a+")
    deadline = _ua_time.monotonic() + float(timeout)
    while True:
        try:
            _ua_fcntl.flock(handle.fileno(), _ua_fcntl.LOCK_EX | _ua_fcntl.LOCK_NB)
            _UA_FAYL_SOSTOYANIE.handle = handle
            _UA_FAYL_SOSTOYANIE.depth = 1
            return
        except BlockingIOError:
            if _ua_time.monotonic() >= deadline:
                handle.close()
                raise sqlite3.OperationalError("CRM database queue timeout")
            _ua_time.sleep(0.05)


def _ua_fayl_otpustit():
    import fcntl as _ua_fcntl

    depth = int(getattr(_UA_FAYL_SOSTOYANIE, "depth", 0) or 0)
    if depth <= 0:
        return
    if depth > 1:
        _UA_FAYL_SOSTOYANIE.depth = depth - 1
        return

    handle = getattr(_UA_FAYL_SOSTOYANIE, "handle", None)
    _UA_FAYL_SOSTOYANIE.depth = 0
    _UA_FAYL_SOSTOYANIE.handle = None
    if handle is None:
        return
    try:
        _ua_fcntl.flock(handle.fileno(), _ua_fcntl.LOCK_UN)
    finally:
        handle.close()


class _UaKursor(sqlite3.Cursor):
    """Cursor path cannot bypass the transaction queue."""

    def _vypolnit(self, method, sql, *args):
        conn = self.connection
        novaya = conn._pered_zapisyu(sql)
        try:
            return method(self, sql, *args)
        except Exception:
            if novaya and not conn.in_transaction:
                conn._otpustit()
            raise

    def execute(self, sql, parameters=()):
        return self._vypolnit(sqlite3.Cursor.execute, sql, parameters)

    def executemany(self, sql, seq_of_parameters):
        return self._vypolnit(sqlite3.Cursor.executemany, sql, seq_of_parameters)

    def executescript(self, sql_script):
        return self._vypolnit(sqlite3.Cursor.executescript, sql_script)


class Soedinenie(sqlite3.Connection):
    """Own the process queue only while a write transaction is active."""

    def _pered_zapisyu(self, sql):
        if not _ua_sql_pishet(sql) or getattr(self, "_ua_zapis_v_ocheredi", False):
            return False
        vzyata = ZAMOK.acquire(timeout=ZAMOK_OZHIDANIE)
        if not vzyata:
            raise sqlite3.OperationalError("CRM thread queue timeout")
        self._ochered_vzyata = True
        try:
            _ua_fayl_zahvatit(ZAMOK_OZHIDANIE)
            self._fayl_zaregistrirovan = True
            self._ua_zapis_v_ocheredi = True
            return True
        except Exception:
            self._ochered_vzyata = False
            try:
                ZAMOK.release()
            except Exception:
                pass
            raise

    def _otpustit(self):
        self._ua_zapis_v_ocheredi = False
        if getattr(self, "_fayl_zaregistrirovan", False):
            self._fayl_zaregistrirovan = False
            try:
                _ua_fayl_otpustit()
            except Exception:
                pass
        if getattr(self, "_ochered_vzyata", False):
            self._ochered_vzyata = False
            try:
                ZAMOK.release()
            except Exception:
                pass

    def cursor(self, factory=None):
        return sqlite3.Connection.cursor(self, factory or _UaKursor)

    def execute(self, sql, parameters=()):
        novaya = self._pered_zapisyu(sql)
        try:
            return sqlite3.Connection.execute(self, sql, parameters)
        except Exception:
            if novaya and not self.in_transaction:
                self._otpustit()
            raise

    def executemany(self, sql, seq_of_parameters):
        novaya = self._pered_zapisyu(sql)
        try:
            return sqlite3.Connection.executemany(self, sql, seq_of_parameters)
        except Exception:
            if novaya and not self.in_transaction:
                self._otpustit()
            raise

    def executescript(self, sql_script):
        novaya = self._pered_zapisyu(sql_script)
        try:
            return sqlite3.Connection.executescript(self, sql_script)
        except Exception:
            if novaya and not self.in_transaction:
                self._otpustit()
            raise

    def _commit_s_povtorom(self):
        import time as _ua_time

        for attempt in range(5):
            try:
                sqlite3.Connection.commit(self)
                return
            except sqlite3.OperationalError as exc:
                text = str(exc).casefold()
                if "locked" not in text and "busy" not in text:
                    raise
                if attempt == 4:
                    raise
                _ua_time.sleep(0.15 * (2 ** attempt))

    def commit(self):
        try:
            self._commit_s_povtorom()
        except Exception:
            try:
                sqlite3.Connection.rollback(self)
            finally:
                self._otpustit()
            raise
        self._otpustit()

    def rollback(self):
        try:
            return sqlite3.Connection.rollback(self)
        finally:
            self._otpustit()

    def close(self):
        try:
            if self.in_transaction:
                sqlite3.Connection.rollback(self)
            sqlite3.Connection.close(self)
        finally:
            self._otpustit()

    def __exit__(self, tip, znachenie, sled):
        try:
            if tip is None:
                self.commit()
            else:
                self.rollback()
        finally:
            try:
                self.close()
            except Exception:
                self._otpustit()
        return False

    def __del__(self):
        self._otpustit()
'''


CONNECT_SOURCE = r'''def connect():
    conn = sqlite3.connect(DB_FILE, timeout=ZAMOK_OZHIDANIE, factory=Soedinenie)
    conn.row_factory = sqlite3.Row
    # Setup pragmas must not hold the transaction queue for a long-lived reader.
    try:
        sqlite3.Connection.execute(conn, "PRAGMA journal_mode=DELETE")
    except Exception:
        pass
    sqlite3.Connection.execute(
        conn, "PRAGMA busy_timeout=%d" % (ZAMOK_OZHIDANIE * 1000)
    )
    sqlite3.Connection.execute(conn, "PRAGMA foreign_keys=ON")
    return conn
'''


class InstallError(RuntimeError):
    pass


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def regular(path: pathlib.Path) -> None:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise InstallError("UNSAFE_FILE:" + path.name)


def atomic_write(path: pathlib.Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(dir=path.parent, delete=False)
    temporary = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_json(path: pathlib.Path, value) -> None:
    atomic_write(
        path,
        (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )


def segment(source: str, node: ast.AST) -> str:
    lines = source.splitlines()
    return "\n".join(lines[node.lineno - 1:node.end_lineno])


def unique_top_level(tree: ast.Module, kind, name: str):
    nodes = [node for node in tree.body if isinstance(node, kind) and node.name == name]
    if len(nodes) != 1:
        raise InstallError("TARGET_INVALID:" + name)
    return nodes[0]


def validate_candidate(source: str) -> None:
    tree = ast.parse(source, "db.py.candidate")
    cls = unique_top_level(tree, ast.ClassDef, "Soedinenie")
    connect_node = unique_top_level(tree, (ast.FunctionDef, ast.AsyncFunctionDef), "connect")
    names = {node.name for node in cls.body if isinstance(node, ast.FunctionDef)}
    required_methods = {"_otpustit", "close", "_commit_s_povtorom", "__exit__", "__del__"}
    if not required_methods.issubset(names):
        raise InstallError("CLASS_CONTRACT_MISSING")
    connect_text = segment(source, connect_node)
    required = (
        MARKER,
        "_ua_fayl_zahvatit",
        "CRM thread queue timeout",
        "_pered_zapisyu",
        "class _UaKursor",
        "_commit_s_povtorom",
    )
    if any(value not in source for value in required):
        raise InstallError("HOTFIX_CONTRACT_MISSING")
    if "if not vzyata" not in source:
        raise InstallError("THREAD_QUEUE_NOT_FAIL_CLOSED")
    if "factory=Soedinenie" not in connect_text or "sqlite3.Connection.execute" not in connect_text:
        raise InstallError("CONNECT_CONTRACT_MISSING")
    compile(source, "db.py.candidate", "exec")


def build_candidate(source: str, enforce_file_hash: bool = True) -> str:
    if MARKER in source:
        validate_candidate(source)
        return source
    if enforce_file_hash and sha_bytes(source.encode("utf-8")) != EXPECTED_DB_SHA:
        raise InstallError("DB_SOURCE_HASH_MISMATCH")

    tree = ast.parse(source, "db.py")
    cls = unique_top_level(tree, ast.ClassDef, "Soedinenie")
    connect_node = unique_top_level(tree, (ast.FunctionDef, ast.AsyncFunctionDef), "connect")
    if sha_bytes(segment(source, cls).encode()) != EXPECTED_CLASS_SHA:
        raise InstallError("DB_CLASS_HASH_MISMATCH")
    if sha_bytes(segment(source, connect_node).encode()) != EXPECTED_CONNECT_SHA:
        raise InstallError("DB_CONNECT_HASH_MISMATCH")

    lines = source.splitlines(keepends=True)
    replacements = [
        (cls, HELPERS_AND_CLASS),
        (connect_node, CONNECT_SOURCE),
    ]
    for node, replacement in sorted(replacements, key=lambda item: item[0].lineno, reverse=True):
        lines[node.lineno - 1:node.end_lineno] = [replacement.rstrip() + "\n\n"]
    candidate = "".join(lines)
    validate_candidate(candidate)
    return candidate


def db_snapshot():
    uri = "file:%s?mode=ro" % CRM_DB
    connection = sqlite3.connect(uri, uri=True, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        quick = connection.execute("PRAGMA quick_check").fetchone()[0]
        if quick != "ok":
            raise InstallError("CRM_QUICK_CHECK_FAILED")
        count = connection.execute("SELECT count(*) FROM cars").fetchone()[0]
        columns = {row[1] for row in connection.execute("PRAGMA table_info(cars)")}
        result = {"quick_check": quick, "cars_count": count}
        if "auto_number" in columns:
            rows = connection.execute(
                "SELECT * FROM cars WHERE auto_number IN ('UA-0009','UA0009')"
            ).fetchall()
            result["ua0009_rows"] = len(rows)
            result["ua0009_sha256"] = sha_bytes(
                json.dumps([dict(row) for row in rows], ensure_ascii=False,
                           sort_keys=True, default=str).encode("utf-8")
            )
        return result
    finally:
        connection.close()


def install() -> int:
    started = utc_now()
    receipt = {
        "task_id": "task_064",
        "contract_id": MARKER,
        "status": "FAIL",
        "mode": "ATOMIC_DB_LAYER_HOTFIX",
        "started_at_utc": started,
        "crm_db_write": False,
        "site_write": False,
        "llm_tokens": 0,
        "errors": [],
    }
    try:
        regular(DB_PY)
        regular(CRM_DB)
        old = DB_PY.read_bytes()
        old_source = old.decode("utf-8")
        receipt["db_py_sha256_before"] = sha_bytes(old)
        receipt["readonly_before"] = db_snapshot()
        candidate_source = build_candidate(old_source)
        candidate = candidate_source.encode("utf-8")
        already = candidate == old
        receipt["already_applied"] = already

        if not already:
            stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup_dir = BACKUPS / stamp
            backup_dir.mkdir(parents=True, exist_ok=False)
            backup = backup_dir / "db.py"
            shutil.copy2(DB_PY, backup)
            regular(backup)
            receipt["backup_path"] = str(backup)
            receipt["backup_sha256"] = sha_bytes(backup.read_bytes())
            mode = stat.S_IMODE(DB_PY.stat().st_mode)
            atomic_write(DB_PY, candidate)
            os.chmod(DB_PY, mode)

        readback = DB_PY.read_bytes()
        validate_candidate(readback.decode("utf-8"))
        if readback != candidate:
            raise InstallError("READBACK_MISMATCH")
        receipt["db_py_sha256_after"] = sha_bytes(readback)
        receipt["readonly_after"] = db_snapshot()
        before = receipt["readonly_before"]
        after = receipt["readonly_after"]
        if before.get("cars_count") != after.get("cars_count"):
            raise InstallError("CARD_COUNT_CHANGED")
        if before.get("ua0009_sha256") != after.get("ua0009_sha256"):
            raise InstallError("UA0009_CHANGED")
        receipt["status"] = "PASS"
    except Exception as exc:
        receipt["errors"].append(type(exc).__name__ + ":" + str(exc))
    receipt["finished_at_utc"] = utc_now()
    atomic_json(INSTALL_RECEIPT, receipt)
    return 0 if receipt["status"] == "PASS" else 1


def rollback() -> int:
    value = json.loads(INSTALL_RECEIPT.read_text(encoding="utf-8"))
    backup = pathlib.Path(value.get("backup_path", ""))
    receipt = {"task_id": "task_064", "status": "FAIL", "errors": []}
    try:
        if BACKUPS not in backup.parents:
            raise InstallError("ROLLBACK_PATH_INVALID")
        regular(backup)
        data = backup.read_bytes()
        if sha_bytes(data) != value.get("backup_sha256"):
            raise InstallError("ROLLBACK_HASH_MISMATCH")
        mode = stat.S_IMODE(DB_PY.stat().st_mode)
        atomic_write(DB_PY, data)
        os.chmod(DB_PY, mode)
        if DB_PY.read_bytes() != data:
            raise InstallError("ROLLBACK_READBACK_MISMATCH")
        receipt.update({"status": "PASS", "restored_sha256": sha_bytes(data)})
    except Exception as exc:
        receipt["errors"].append(type(exc).__name__ + ":" + str(exc))
    atomic_json(ROLLBACK_RECEIPT, receipt)
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(rollback() if len(sys.argv) > 1 and sys.argv[1] == "--rollback" else install())

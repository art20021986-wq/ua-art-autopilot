from __future__ import annotations

import os
import sqlite3
import tempfile
import threading
import unittest

import sqlite_hotfix_installer as hotfix
import sqlite_hotfix_postcheck as postcheck


ORIGINAL_CLASS = '''class Soedinenie(sqlite3.Connection):
    """Берёт очередь при открытии, отпускает при закрытии.

    Выход из with: commit или rollback, затем обязательный close.
    """

    def _otpustit(self):
        if getattr(self, "_ochered_vzyata", False):
            self._ochered_vzyata = False
            try:
                ZAMOK.release()
            except Exception:
                pass

    def close(self):
        try:
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
        self._otpustit()'''


ORIGINAL_CONNECT = '''def connect():
    vzyata = ZAMOK.acquire(timeout=ZAMOK_OZHIDANIE)
    try:
        conn = sqlite3.connect(DB_FILE, timeout=OZHIDANIE_SEK, factory=Soedinenie)
    except Exception:
        if vzyata:
            try:
                ZAMOK.release()
            except Exception:
                pass
        raise
    conn._ochered_vzyata = vzyata
    conn.row_factory = sqlite3.Row
    # WAL на сетевом диске PythonAnywhere ломает блокировки - только DELETE
    try:
        conn.execute("PRAGMA journal_mode=DELETE")
    except Exception:
        pass
    try:
        conn.execute("PRAGMA busy_timeout=%d" % (OZHIDANIE_SEK * 1000))
    except Exception:
        pass
    conn.execute("PRAGMA foreign_keys=ON")
    return conn'''


FIXTURE = '''import os
import sqlite3
import threading as _potoki

BASE_DIR = "."
DB_FILE = "fixture.db"
OZHIDANIE_SEK = 3
ZAMOK = _potoki.RLock()
ZAMOK_OZHIDANIE = 20

{klass}


{connect}
'''.format(klass=ORIGINAL_CLASS, connect=ORIGINAL_CONNECT)


class HotfixTests(unittest.TestCase):
    def candidate_namespace(self, db_path):
        candidate = hotfix.build_candidate(FIXTURE, enforce_file_hash=False)
        self.assertIn(hotfix.MARKER, candidate)
        compile(candidate, "fixture_db.py", "exec")
        namespace = {"__name__": "fixture_db"}
        exec(candidate, namespace)
        namespace["BASE_DIR"] = os.path.dirname(db_path)
        namespace["DB_FILE"] = db_path
        return candidate, namespace

    def test_transform_is_idempotent(self):
        candidate = hotfix.build_candidate(FIXTURE, enforce_file_hash=False)
        self.assertEqual(candidate, hotfix.build_candidate(candidate, enforce_file_hash=False))

    def test_remote_worker_code_compiles(self):
        compile(postcheck.worker_code(), "task064_worker.py", "exec")

    def test_long_lived_reader_does_not_hold_write_queue(self):
        with tempfile.TemporaryDirectory() as folder:
            db_path = os.path.join(folder, "crm.db")
            setup = sqlite3.connect(db_path)
            setup.execute("CREATE TABLE t(id INTEGER PRIMARY KEY, v TEXT)")
            setup.execute("INSERT INTO t(v) VALUES ('ok')")
            setup.commit()
            setup.close()
            _, namespace = self.candidate_namespace(db_path)
            reader = namespace["connect"]()
            self.assertEqual(reader.execute("SELECT v FROM t").fetchone()[0], "ok")
            with namespace["connect"]() as writer:
                writer.execute("UPDATE t SET v=v WHERE 0")
            reader.close()
            self.assertEqual(namespace["_UA_FAYL_SOSTOYANIE"].depth, 0)

    def test_cursor_write_acquires_and_commit_releases_queue(self):
        with tempfile.TemporaryDirectory() as folder:
            db_path = os.path.join(folder, "crm.db")
            setup = sqlite3.connect(db_path)
            setup.execute("CREATE TABLE t(id INTEGER PRIMARY KEY, v TEXT)")
            setup.commit()
            setup.close()
            _, namespace = self.candidate_namespace(db_path)
            connection = namespace["connect"]()
            cursor = connection.cursor()
            cursor.execute("UPDATE t SET v=v WHERE 0")
            self.assertEqual(namespace["_UA_FAYL_SOSTOYANIE"].depth, 1)
            connection.commit()
            self.assertEqual(namespace["_UA_FAYL_SOSTOYANIE"].depth, 0)
            connection.close()

    def test_concurrent_noop_writes_have_no_locked_errors(self):
        with tempfile.TemporaryDirectory() as folder:
            db_path = os.path.join(folder, "crm.db")
            connection = sqlite3.connect(db_path)
            connection.execute("CREATE TABLE t(id INTEGER PRIMARY KEY, v TEXT)")
            connection.execute("INSERT INTO t(v) VALUES ('ok')")
            connection.commit()
            connection.close()
            _, namespace = self.candidate_namespace(db_path)
            errors = []

            def worker():
                try:
                    for _ in range(20):
                        with namespace["connect"]() as current:
                            current.execute("UPDATE t SET v=v WHERE 0")
                except Exception as exc:  # pragma: no cover - assertion captures it
                    errors.append(repr(exc))

            threads = [threading.Thread(target=worker) for _ in range(8)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(30)
            self.assertFalse(any(thread.is_alive() for thread in threads))
            self.assertEqual(errors, [])
            check = sqlite3.connect(db_path)
            try:
                self.assertEqual(check.execute("PRAGMA quick_check").fetchone()[0], "ok")
                self.assertEqual(check.execute("SELECT v FROM t").fetchone()[0], "ok")
            finally:
                check.close()


if __name__ == "__main__":
    unittest.main()

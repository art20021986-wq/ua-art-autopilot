"""SQLite status migration with a private backup and conditional rollback."""

from contextlib import closing
from hashlib import sha256
import os
from pathlib import Path
import sqlite3
import stat
import time


REMOVED_STATUSES = (
    "Продано в пути", "Продано · в пути", "sold_transit",
    "Выехало в Киев", "ge_to_kyiv", "Продано", "sold", "Архив", "archive",
)
_PLACEHOLDERS = ",".join("?" for _ in REMOVED_STATUSES)


class MigrationError(RuntimeError):
    pass


def _regular(path):
    path = Path(path).absolute()
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise MigrationError("UNSAFE_DATABASE_FILE")
    if any(parent.is_symlink() for parent in path.parents):
        raise MigrationError("UNSAFE_DATABASE_DIRECTORY")
    return path


def _open(path, mode):
    return sqlite3.connect(path.as_uri() + "?mode=" + mode,
                           uri=True, timeout=5, isolation_level=None)


def _columns(connection):
    columns = connection.execute("PRAGMA table_info(cars)").fetchall()
    by_name = {row[1]: row for row in columns}
    identity, status = by_name.get("id"), by_name.get("status")
    if (not identity or identity[2].upper() != "INTEGER" or identity[5] != 1
            or not status or status[2].upper() != "TEXT"
            or sum(bool(row[5]) for row in columns) != 1):
        raise MigrationError("CARS_SCHEMA_CHANGED")
    if connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'trigger' AND tbl_name = 'cars'"
    ).fetchone():
        raise MigrationError("CARS_TRIGGERS_REQUIRE_REVIEW")
    return tuple(row[1] for row in columns)


def _rows(connection):
    return connection.execute("SELECT * FROM cars ORDER BY id").fetchall()


def _digest(path):
    digest = sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _backup(database, target, columns, rows):
    target = Path(target).absolute()
    if not target.parent.is_dir() or any(parent.is_symlink() for parent in target.parents):
        raise MigrationError("BACKUP_DIRECTORY_REQUIRED")
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    deadline = time.monotonic() + 60

    def check_progress(status, remaining, total):
        if time.monotonic() >= deadline:
            raise MigrationError("BACKUP_TIMEOUT")

    with closing(_open(database, "ro")) as source, closing(_open(target, "rw")) as saved:
        source.backup(saved, pages=256, progress=check_progress)
        if (saved.execute("PRAGMA quick_check").fetchall() != [("ok",)]
                or _columns(saved) != columns or _rows(saved) != rows):
            raise MigrationError("BACKUP_VERIFICATION_FAILED")
    with target.open("rb") as saved:
        os.fsync(saved.fileno())
    descriptor = os.open(target.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return target, _digest(target)


def migrate(database, backup_file):
    """Back up under the writer lock; change only cars.status."""
    database = _regular(database)
    with closing(_open(database, "rw")) as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            columns = _columns(connection)
            before = _rows(connection)
            status_index = columns.index("status")
            backup, digest = _backup(database, backup_file, columns, before)
            expected = [tuple("hidden" if index == status_index and value in REMOVED_STATUSES
                              else value for index, value in enumerate(row)) for row in before]
            changed = sum(old != new for old, new in zip(before, expected))
            cursor = connection.execute(
                "UPDATE cars SET status = 'hidden' WHERE status IN (" + _PLACEHOLDERS + ")",
                REMOVED_STATUSES,
            )
            if cursor.rowcount != changed or _rows(connection) != expected:
                raise MigrationError("MIGRATION_POSTCONDITION_FAILED")
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
    return {"changed_rows": changed, "backup_path": str(backup), "backup_sha256": digest}


def rollback(database, backup_file, expected_backup_sha256):
    """Restore only migrated statuses; reject concurrent changes to affected rows."""
    database, backup = _regular(database), _regular(backup_file)
    if database == backup or not expected_backup_sha256 or _digest(backup) != expected_backup_sha256:
        raise MigrationError("BACKUP_IDENTITY_CHANGED")
    with closing(_open(backup, "ro")) as saved:
        columns = _columns(saved)
        status_index, id_index = columns.index("status"), columns.index("id")
        targets = [row for row in _rows(saved) if row[status_index] in REMOVED_STATUSES]
    with closing(_open(database, "rw")) as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            if _columns(connection) != columns:
                raise MigrationError("ROLLBACK_SCHEMA_CHANGED")
            pending = []
            for original in targets:
                current = connection.execute("SELECT * FROM cars WHERE id = ?", (original[id_index],)).fetchone()
                migrated = tuple("hidden" if index == status_index else value
                                 for index, value in enumerate(original))
                if current == original:
                    continue
                if current != migrated:
                    raise MigrationError("ROLLBACK_ROW_CHANGED")
                pending.append((original[status_index], original[id_index]))
            connection.executemany(
                "UPDATE cars SET status = ? WHERE id = ? AND status = 'hidden'", pending
            )
            for original in targets:
                current = connection.execute("SELECT * FROM cars WHERE id = ?", (original[id_index],)).fetchone()
                if current != original:
                    raise MigrationError("ROLLBACK_POSTCONDITION_FAILED")
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
    return {"restored_rows": len(pending), "backup_sha256": expected_backup_sha256}

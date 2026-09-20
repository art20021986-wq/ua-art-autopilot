"""Scoped recovery for the private media candidate; never a production gate.

All callers hold the shared publication fence. SQLite rollback uses conditional
updates inside BEGIN IMMEDIATE. File operations anchor every parent with dir_fd
and O_NOFOLLOW. JSON recovery restores only the removed vehicle entry.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import tempfile
import threading

_local = threading.local()


def vehicle_code(value):
    code = str(value or "").strip().upper()
    if not re.fullmatch(r"UA-[0-9]{4,}", code):
        raise RuntimeError("INVALID_MEDIA_VEHICLE_CODE")
    return code


@contextlib.contextmanager
def parent_fd(path):
    """Reject symlinks in every component, including the root supplied by caller."""
    path = os.path.abspath(os.fspath(path))
    parts = Path(path).parts
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd, parts[-1]
    finally:
        os.close(fd)


@contextlib.contextmanager
def open_regular(path):
    with parent_fd(path) as (directory, name):
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise RuntimeError("MEDIA_NONREGULAR_REFUSED")
            yield stream


def read_regular(path):
    with open_regular(path) as stream:
        return stream.read()


def file_digest(path):
    value = hashlib.sha256()
    with open_regular(path) as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            value.update(chunk)
    return value.hexdigest()


def copy_stream(source, destination):
    value = hashlib.sha256()
    with open_regular(source) as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            value.update(chunk)
            destination.write(chunk)
    return value.hexdigest()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def regular_files(root):
    root = os.path.abspath(root)
    # Explicit root check: os.walk(followlinks=False) still follows its root.
    try:
        with parent_fd(os.path.join(root, ".probe")):
            pass
    except FileNotFoundError:
        return []
    result = []
    for current, directories, files in os.walk(root, followlinks=False):
        for name in directories:
            with parent_fd(os.path.join(current, name, ".probe")):
                pass
        for name in files:
            path = os.path.join(current, name)
            with open_regular(path):
                pass
            result.append(path)
    return sorted(result)


def write_private_new(path, data):
    with parent_fd(path) as (directory, name):
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=directory)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(directory)


def backup_exact(paths, root, backup_dir):
    root = os.path.abspath(root)
    entries = []
    for index, path in enumerate(sorted(set(map(os.path.abspath, paths)))):
        if os.path.commonpath((root, path)) != root or path == root:
            raise RuntimeError("MEDIA_BACKUP_PATH_ESCAPE")
        with parent_fd(path) as (directory, name):
            mode = stat.S_IMODE(os.stat(name, dir_fd=directory, follow_symlinks=False).st_mode)
        target = os.path.join(backup_dir, "exact-%06d" % index)
        with parent_fd(target) as (directory, name):
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=directory)
            with os.fdopen(fd, "wb") as stream:
                sha = copy_stream(path, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.fsync(directory)
        if file_digest(target) != sha or file_digest(path) != sha:
            raise RuntimeError("MEDIA_BACKUP_SHA256_MISMATCH")
        entries.append((path, target, sha, os.path.relpath(path, root), mode))
    write_private_new(os.path.join(backup_dir, "media-before.json"),
                      json.dumps(entries, ensure_ascii=False).encode())
    return entries


def restore_exact(entries):
    conflicts = []
    for entry in entries:
        target, backup, expected, relative = entry[:4]
        mode = entry[4] if len(entry) > 4 else 0o644
        temporary = None
        try:
            if file_digest(backup) != expected:
                raise RuntimeError("MEDIA_RESTORE_BACKUP_SHA256_MISMATCH")
            with parent_fd(target) as (directory, name):
                try:
                    current = file_digest(target)
                except FileNotFoundError:
                    current = None
                if current is not None:
                    if current != expected:
                        raise RuntimeError("MEDIA_RESTORE_AFTER_IMAGE_CONFLICT")
                    continue
                temporary = ".ua114-restore-" + os.urandom(16).hex()
                fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=directory)
                try:
                    with os.fdopen(fd, "wb") as stream:
                        copied = copy_stream(backup, stream)
                        if copied != expected:
                            raise RuntimeError("MEDIA_RESTORE_BACKUP_CHANGED")
                        os.fchmod(stream.fileno(), mode)
                        stream.flush()
                        os.fsync(stream.fileno())
                    # Atomic no-replace; concurrent new originals are preserved.
                    os.link(temporary, name, src_dir_fd=directory,
                            dst_dir_fd=directory, follow_symlinks=False)
                    os.fsync(directory)
                finally:
                    os.unlink(temporary, dir_fd=directory)
                    temporary = None
        except Exception:
            conflicts.append("media:" + relative)
    return conflicts


def remove_regular(path):
    with parent_fd(path) as (directory, name):
        mode = os.stat(name, dir_fd=directory, follow_symlinks=False).st_mode
        if not stat.S_ISREG(mode):
            raise RuntimeError("MEDIA_DELETE_NONREGULAR_REFUSED")
        os.unlink(name, dir_fd=directory)
        os.fsync(directory)


def restore_fields(database, cid, before, expected):
    allowed = {"photos", "cover_photo", "hidden_photos", "videos", "video_h",
               "video_v", "condition_photos", "condition_videos"}
    if not set(before) <= allowed or not set(before) <= set(expected):
        raise RuntimeError("FIELD_RECOVERY_CONTRACT")
    conflicts = []
    con = sqlite3.connect(database, timeout=15)
    try:
        con.execute("BEGIN IMMEDIATE")
        for field, value in before.items():
            cursor = con.execute(
                'UPDATE cars SET "' + field + '"=? WHERE id=? AND "' + field + '" IS ?',
                (value, cid, expected[field]))
            if cursor.rowcount != 1:
                conflicts.append(field)
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    return conflicts


def _rows(con, table, code):
    if table == "cars":
        cur = con.execute("SELECT * FROM cars WHERE auto_number=?", (code,))
    else:
        cur = con.execute("SELECT * FROM media WHERE car_id IN "
                          "(SELECT id FROM cars WHERE auto_number=?)", (code,))
    names = [x[0] for x in cur.description]
    return {row[0] if names[0] == "id" else dict(zip(names, row))["id"]:
            dict(zip(names, row)) for row in cur.fetchall()}


class MediaJournal:
    """Capture real media-helper commits inside their SQLite write transaction."""
    def __init__(self, database, code):
        self.database, self.code = database, vehicle_code(code)
        self.pending = {}
        self.changes = []
        self.evidence_directory = None

    def begin(self, con):
        if con.in_transaction:
            raise RuntimeError("MEDIA_TRANSACTION_ALREADY_ACTIVE")
        con.execute("BEGIN IMMEDIATE")
        self.pending[id(con)] = {t: _rows(con, t, self.code) for t in ("cars", "media")}

    def commit(self, con):
        before = self.pending.pop(id(con))
        changes = []
        for table in ("cars", "media"):
            after = _rows(con, table, self.code)
            if set(before[table]) != set(after):
                raise RuntimeError("MEDIA_HELPER_UNEXPECTED_ROW_MEMBERSHIP_CHANGE")
            for key, row in before[table].items():
                if row != after[key]:
                    changes.append((table, key, row, after[key]))
        # Retain intent before commit; a failed commit is reconciled by row CAS.
        self.changes.extend(changes)
        if self.evidence_directory is not None:
            write_private_new(os.path.join(self.evidence_directory,
                "media-commit-" + os.urandom(12).hex() + ".json"),
                json.dumps({"code": self.code, "changes": changes}, ensure_ascii=False).encode())
        con.commit()

    def restore(self):
        conflicts = []
        con = sqlite3.connect(self.database, timeout=15)
        try:
            con.execute("BEGIN IMMEDIATE")
            for table, key, before, after in reversed(self.changes):
                names = list(after)
                cur = con.execute('SELECT * FROM "' + table + '" WHERE id=?', (key,))
                raw = cur.fetchone()
                current = dict(zip([x[0] for x in cur.description], raw)) if raw else None
                if current == before:
                    continue  # A commit failed, or a prior recovery completed.
                if current != after:
                    conflicts.append(table + ":" + str(key))
                    continue
                fields = [n for n in names if before[n] != after[n]]
                quoted = lambda n: '"' + n.replace('"', '""') + '"'
                con.execute('UPDATE "' + table + '" SET ' +
                            ",".join(quoted(n) + "=?" for n in fields) + ' WHERE id=?',
                            [before[n] for n in fields] + [key])
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()
        return conflicts

    @contextlib.contextmanager
    def active(self):
        if getattr(_local, "journal", None) is not None:
            raise RuntimeError("NESTED_MEDIA_JOURNAL")
        _local.journal = self
        try:
            yield self
        finally:
            _local.journal = None


def begin_media(con):
    # The instrumented caller owns rollback/close in its unconditional finally.
    journal = getattr(_local, "journal", None)
    if journal is None:
        raise RuntimeError("MEDIA_JOURNAL_REQUIRED")
    journal.begin(con)


def commit_media(con):
    journal = getattr(_local, "journal", None)
    if journal is None:
        raise RuntimeError("MEDIA_JOURNAL_REQUIRED")
    journal.commit(con)


class CacheEntry:
    """Change one JSON member under the publication fence, preserving other cars."""
    def __init__(self, path, code):
        self.path, self.code = path, vehicle_code(code)
        try:
            self.original = read_regular(path)
        except FileNotFoundError:
            self.original = None
        self.before = json.loads(self.original) if self.original is not None else {}
        if not isinstance(self.before, dict):
            raise RuntimeError("CACHE_NOT_AN_OBJECT")
        self.changed = False

    def _write(self, current_raw, data):
        temporary = ".ua114-cache-" + os.urandom(16).hex()
        with parent_fd(self.path) as (directory, name):
            mode = stat.S_IMODE(os.stat(name, dir_fd=directory, follow_symlinks=False).st_mode)
            payload = (json.dumps(data, ensure_ascii=False) + "\n").encode()
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=directory)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(payload)
                    os.fchmod(stream.fileno(), mode)
                    stream.flush()
                    os.fsync(stream.fileno())
                if read_regular(self.path) != current_raw:
                    raise RuntimeError("CACHE_CONCURRENT_CHANGE")
                os.replace(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
                os.fsync(directory)
            finally:
                try:
                    os.unlink(temporary, dir_fd=directory)
                except FileNotFoundError:
                    pass

    def remove(self):
        if self.code not in self.before:
            return
        after = dict(self.before)
        del after[self.code]
        self.changed = True  # Also reconcile failures after rename/fsync.
        self._write(self.original, after)

    def restore(self):
        if not self.changed:
            return []
        try:
            raw = read_regular(self.path)
            current = json.loads(raw)
            if not isinstance(current, dict):
                raise RuntimeError("CACHE_NOT_AN_OBJECT")
            if self.code in current:
                return [] if current[self.code] == self.before[self.code] else ["cache:" + self.code]
            current[self.code] = self.before[self.code]
            self._write(raw, current)
            return []
        except Exception:
            return ["cache:" + self.code]

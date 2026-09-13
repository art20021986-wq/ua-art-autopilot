"""Bounded CRM/public-page transitions under the existing publication lock.

No import-time writes. Only explicit CRM callbacks call these functions. Deletes
retain media, specification facts and a private row/page backup. Only exact
primary, diagnostic and catalog files are in the write set. Rollback compensates
only our CRM fields; concurrent unrelated CRM edits are never overwritten.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import threading
import uuid

CONTRACT = "UA-ART-SPEC-AUTO-10-RESTORE-001:LIFECYCLE:1"
UID = re.compile(r"UA-[0-9]{4,}\Z")
MAX_FILE = 32 * 1024 * 1024
ARCHIVE_TABLE = "ua_spec_lifecycle_archive"
_ACTIVE_OPERATION = threading.local()


class LifecycleError(RuntimeError):
    pass


def _atomic(path, data, mode=0o600):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".lifecycle-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _safe_path(path, root):
    path, root = Path(path).absolute(), Path(root).absolute()
    if root not in path.parents:
        raise LifecycleError("PATH_OUTSIDE_RUNTIME")
    for part in (path, *path.parents):
        if part.is_symlink():
            raise LifecycleError("LIFECYCLE_SYMLINK_FORBIDDEN:" + str(part))
    if path.exists() and not path.is_file():
        raise LifecycleError("LIFECYCLE_REGULAR_FILE_REQUIRED:" + str(path))
    return path


def _read(path):
    if path.stat().st_size > MAX_FILE:
        raise LifecycleError("LIFECYCLE_FILE_TOO_LARGE")
    return path.read_bytes()


def _connect(guard):
    _safe_path(guard.DB, guard.ROOT)
    connection = sqlite3.connect(str(guard.DB), timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def _json(data):
    return (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def _same_identity(current, before):
    return current is not None and all(
        current.get(field) == before.get(field)
        for field in ("id", "auto_number", "vin", "created_at") if field in before
    )


def _uid_unique(connection, code, card_id, *, absent=False):
    code = str(code).strip().upper()
    rows = connection.execute(
        "SELECT id FROM cars WHERE UPPER(TRIM(auto_number))=?", (code,)
    ).fetchall()
    return not rows if absent else len(rows) == 1 and rows[0][0] == card_id


def _archive_state(guard, operation_id, state):
    connection = _connect(guard)
    try:
        connection.execute("UPDATE ua_spec_lifecycle_archive SET state=? WHERE operation_id=?",
                           (state, operation_id))
        connection.commit()
    finally:
        connection.close()


def validate_publication_identity(connection, code, *, expected_card_id=None, require_published=True):
    """Read-only UID/tombstone gate using the caller's existing CRM connection.

    Does not create tables, change rows, open databases, import the application,
    or mutate connection pragmas. Safe to call under the publication lock from
    the worker or specification reader before reusing UID-bound facts.
    """
    code = str(code or "").strip().upper()
    if not UID.fullmatch(code):
        raise LifecycleError("LIFECYCLE_AUTO_NUMBER_INVALID")
    rows = connection.execute(
        "SELECT id,published FROM cars WHERE UPPER(TRIM(auto_number))=?", (code,)
    ).fetchall()
    if len(rows) != 1:
        raise LifecycleError("LIFECYCLE_CARD_MISSING_OR_DUPLICATE_UID")
    card_id, published = rows[0][0], rows[0][1]
    if expected_card_id is not None and card_id != int(expected_card_id):
        raise LifecycleError("LIFECYCLE_CARD_ID_CHANGED")
    if require_published and published != 1:
        raise LifecycleError("LIFECYCLE_CARD_NOT_PUBLISHED")
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (ARCHIVE_TABLE,)
    ).fetchone()
    if exists:
        unresolved = connection.execute(
            "SELECT operation_id FROM ua_spec_lifecycle_archive WHERE auto_number=? "
            "AND state IN ('APPLIED','ROLLBACK_DB_DONE')", (code,),
        ).fetchall()
        active = getattr(_ACTIVE_OPERATION, "operation_id", None)
        if any(row[0] != active for row in unresolved):
            raise LifecycleError("LIFECYCLE_RECOVERY_REQUIRED")
        retired = connection.execute(
            "SELECT car_id FROM ua_spec_lifecycle_archive WHERE auto_number=? "
            "AND action='delete' AND state='COMPLETED' LIMIT 1", (code,),
        ).fetchone()
        if retired is not None:
            raise LifecycleError("LIFECYCLE_RETIRED_AUTO_NUMBER_REUSED")
    return {"car_id": card_id, "auto_number": code, "published": published}


def _delete_schema_safe(connection):
    # The observed cars/media schema has no cascading relationships. Unknown
    # deletion hooks must be reviewed instead of risking associated data loss.
    for (sql,) in connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='trigger' AND tbl_name='cars'"
    ):
        if re.search(r"\bDELETE\b", str(sql), re.I):
            raise LifecycleError("UNREVIEWED_CAR_DELETE_TRIGGER")
    names = [row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )]
    for name in names:
        quoted = '"' + name.replace('"', '""') + '"'
        for fk in connection.execute("PRAGMA foreign_key_list(" + quoted + ")"):
            if fk[2] == "cars" and fk[6].upper() not in {"NO ACTION", "RESTRICT"}:
                raise LifecycleError("UNREVIEWED_CAR_DELETE_CASCADE:" + name)


class _Snapshot:
    def __init__(self, guard, code, row, action, actor_id):
        self.guard = guard
        self.code = code
        self.operation_id = uuid.uuid4().hex
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.root = Path(guard.ROOT) / "rezerv_publikacii" / "SPEC_LIFECYCLE" / (stamp + "-" + self.operation_id)
        for part in (self.root, *self.root.parents):
            if part.is_symlink():
                raise LifecycleError("LIFECYCLE_BACKUP_SYMLINK_FORBIDDEN")
        self.root.mkdir(parents=True, mode=0o700, exist_ok=False)
        self.files = {}
        for site_root in guard.ROOTS:
            if not Path(site_root).is_dir() or Path(site_root).is_symlink():
                raise LifecycleError("LIFECYCLE_SITE_ROOT_MISSING")
            for name in (code + ".html", code + "-diag.html", "katalog.html"):
                path = _safe_path(Path(site_root) / name, guard.ROOT)
                data = _read(path) if path.is_file() else None
                mode = path.stat().st_mode & 0o777 if data is not None else 0o644
                relative = str(path.relative_to(guard.ROOT))
                self.files[path] = {"data": data, "mode": mode, "relative": relative}
                if data is not None:
                    _atomic(self.root / "files" / relative, data)
        self.report = {
            "contract_id": CONTRACT, "operation_id": self.operation_id,
            "code": code, "action": action, "actor_id": actor_id,
            "created_at": stamp, "state": "PREPARED", "row_before": row,
            "files": {value["relative"]: {
                "exists": value["data"] is not None, "mode": value["mode"],
                "sha256": hashlib.sha256(value["data"]).hexdigest() if value["data"] is not None else None,
            } for value in self.files.values()},
            "media_and_specification_deleted": False,
        }
        self.save()

    def save(self):
        _atomic(self.root / "manifest.json", _json(self.report))

    @classmethod
    def from_archive(cls, guard, archive):
        result = cls.__new__(cls)
        result.guard = guard
        result.root = Path(archive["backup_path"]).absolute()
        base = Path(guard.ROOT) / "rezerv_publikacii" / "SPEC_LIFECYCLE"
        if result.root.parent != base or result.root.is_symlink():
            raise LifecycleError("LIFECYCLE_RECOVERY_BACKUP_SCOPE")
        manifest = _safe_path(result.root / "manifest.json", guard.ROOT)
        result.report = json.loads(_read(manifest))
        result.code = archive["auto_number"]
        result.operation_id = archive["operation_id"]
        if (not UID.fullmatch(result.code)
                or result.report.get("operation_id") != result.operation_id
                or result.report.get("code") != result.code
                or result.report.get("action") != archive["action"]
                or result.report.get("row_before") != json.loads(archive["previous_row_json"])):
            raise LifecycleError("LIFECYCLE_RECOVERY_MANIFEST_MISMATCH")
        expected = {str((Path(root) / name).relative_to(guard.ROOT))
                    for root in guard.ROOTS
                    for name in (result.code + ".html", result.code + "-diag.html", "katalog.html")}
        if set(result.report.get("files", {})) != expected:
            raise LifecycleError("LIFECYCLE_RECOVERY_FILE_SET")
        result.files = {}
        for relative, item in result.report["files"].items():
            path = _safe_path(Path(guard.ROOT) / relative, guard.ROOT)
            data = None
            if item["exists"]:
                stored = _safe_path(result.root / "files" / relative, result.root)
                data = _read(stored)
                if hashlib.sha256(data).hexdigest() != item["sha256"]:
                    raise LifecycleError("LIFECYCLE_RECOVERY_BACKUP_HASH")
            result.files[path] = {"data": data, "mode": item["mode"], "relative": relative}
        return result

    def restore_files(self):
        for path, item in self.files.items():
            _safe_path(path, self.guard.ROOT)
            if item["data"] is None:
                path.unlink(missing_ok=True)
            else:
                _atomic(path, item["data"], item["mode"])
        for path, item in self.files.items():
            if (path.is_file() and _read(path) == item["data"]) if item["data"] is not None else not path.exists():
                continue
            raise LifecycleError("LIFECYCLE_ROLLBACK_READBACK_FAILED:" + str(path))

    def withdraw_pages(self):
        for path in self.files:
            if path.name != "katalog.html":
                _safe_path(path, self.guard.ROOT)
                path.unlink(missing_ok=True)
                directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)


def _archive_schema(connection):
    connection.execute("""CREATE TABLE IF NOT EXISTS ua_spec_lifecycle_archive (
        operation_id TEXT PRIMARY KEY, car_id INTEGER NOT NULL,
        auto_number TEXT NOT NULL, action TEXT NOT NULL, state TEXT NOT NULL,
        previous_row_json TEXT NOT NULL, actor_id INTEGER, created_at TEXT NOT NULL,
        backup_path TEXT NOT NULL
    )""")


def _mutate(guard, card_id, action, actor_id, snapshot, before):
    connection = _connect(guard)
    after_fields = {}
    try:
        connection.execute("BEGIN IMMEDIATE")
        current = connection.execute("SELECT * FROM cars WHERE id=?", (card_id,)).fetchone()
        if current is None or dict(current) != before:
            raise LifecycleError("CRM_CHANGED_BEFORE_LIFECYCLE")
        validate_publication_identity(connection, snapshot.code, expected_card_id=card_id,
                                      require_published=False)
        if action == "delete":
            _delete_schema_safe(connection)
        _archive_schema(connection)
        retired = connection.execute(
            "SELECT car_id FROM ua_spec_lifecycle_archive WHERE auto_number=? "
            "AND action='delete' AND state='COMPLETED' LIMIT 1", (snapshot.code,),
        ).fetchone()
        if retired is not None:
            raise LifecycleError("LIFECYCLE_RETIRED_AUTO_NUMBER_REUSED")
        connection.execute(
            "INSERT INTO ua_spec_lifecycle_archive VALUES(?,?,?,?,?,?,?,?,?)",
            (snapshot.operation_id, card_id, snapshot.code, action, "APPLIED",
             json.dumps(before, ensure_ascii=False, sort_keys=True), actor_id,
             snapshot.report["created_at"], str(snapshot.root)),
        )
        if action == "delete":
            connection.execute("DELETE FROM cars WHERE id=?", (card_id,))
        else:
            after_fields["published"] = int(action == "publish")
            if "publish_pending" in before:
                after_fields["publish_pending"] = 0
            if action == "sold":
                after_fields["status"] = "sold"
            if "updated_at" in before:
                after_fields["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
            assignments = ",".join('"' + field + '"=?' for field in after_fields)
            connection.execute("UPDATE cars SET " + assignments + " WHERE id=?",
                               (*after_fields.values(), card_id))
        snapshot.report["after_fields"] = after_fields
        snapshot.save()  # persisted before the CRM commit; crash recovery uses it
        connection.commit()
        return after_fields
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _compensate(guard, card_id, action, before, after_fields, operation_id):
    connection = _connect(guard)
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT * FROM cars WHERE id=?", (card_id,)).fetchone()
        if action == "delete":
            if row is not None or not _uid_unique(connection, before["auto_number"], card_id, absent=True):
                raise LifecycleError("LIFECYCLE_DELETE_ROLLBACK_ID_REUSED")
            columns = ",".join('"' + key.replace('"', '""') + '"' for key in before)
            marks = ",".join("?" for _ in before)
            connection.execute("INSERT INTO cars (" + columns + ") VALUES (" + marks + ")",
                               tuple(before.values()))
        else:
            current = dict(row) if row is not None else None
            if not _same_identity(current, before) or not _uid_unique(connection, before["auto_number"], card_id):
                raise LifecycleError("LIFECYCLE_ROLLBACK_IDENTITY_CHANGED")
            semantic_fields = {key: value for key, value in after_fields.items() if key != "updated_at"}
            if any(current[field] != value for field, value in semantic_fields.items()):
                raise LifecycleError("LIFECYCLE_ROLLBACK_CONCURRENT_FIELD_CHANGE")
            restore_fields = dict(semantic_fields)
            if "updated_at" in after_fields and current["updated_at"] == after_fields["updated_at"]:
                restore_fields["updated_at"] = after_fields["updated_at"]
            assignments = ",".join('"' + field + '"=?' for field in restore_fields)
            connection.execute("UPDATE cars SET " + assignments + " WHERE id=?",
                               (*(before[field] for field in restore_fields), card_id))
        connection.execute("UPDATE ua_spec_lifecycle_archive SET state='ROLLBACK_DB_DONE' WHERE operation_id=?",
                           (operation_id,))
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def recover_pending(*, guard=None):
    """Roll back interrupted operations, called before writes and by the worker.

    Only APPLIED / ROLLBACK_DB_DONE rows in this helper's own archive are used.
    Identity conflicts or altered backups stop recovery without overwriting them.
    """
    if guard is None:
        import publish_transaction_guard as guard
    if getattr(guard, "LIFECYCLE_REENTRANT_LOCK", False) is not True:
        raise LifecycleError("LIFECYCLE_SHARED_REENTRANT_LOCK_REQUIRED")
    recovered = []
    with guard._exclusive_lock():
        connection = _connect(guard)
        try:
            exists = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                                        (ARCHIVE_TABLE,)).fetchone()
            if not exists:
                return {"status": "PASS", "recovered": []}
            pending = [dict(row) for row in connection.execute(
                "SELECT * FROM ua_spec_lifecycle_archive WHERE state IN ('APPLIED','ROLLBACK_DB_DONE') "
                "ORDER BY created_at,operation_id LIMIT 101"
            )]
        finally:
            connection.close()
        if len(pending) > 100:
            raise LifecycleError("LIFECYCLE_RECOVERY_QUEUE_REQUIRES_REVIEW")
        for archive in pending:
            snapshot = _Snapshot.from_archive(guard, archive)
            before = snapshot.report["row_before"]
            after_fields = snapshot.report.get("after_fields")
            if not isinstance(after_fields, dict):
                raise LifecycleError("LIFECYCLE_RECOVERY_AFTER_FIELDS_MISSING")
            if archive["state"] == "APPLIED":
                _compensate(guard, archive["car_id"], archive["action"], before,
                            after_fields, archive["operation_id"])
            else:
                connection = _connect(guard)
                try:
                    row = connection.execute("SELECT * FROM cars WHERE id=?", (archive["car_id"],)).fetchone()
                    current = dict(row) if row is not None else None
                    if (not _same_identity(current, before)
                            or not _uid_unique(connection, archive["auto_number"], archive["car_id"])
                            or any(current[field] != before[field] for field in after_fields if field != "updated_at")):
                        raise LifecycleError("LIFECYCLE_RECOVERY_ROLLBACK_IDENTITY_CHANGED")
                finally:
                    connection.close()
            snapshot.restore_files()
            snapshot.report["state"] = "ROLLED_BACK"
            snapshot.save()
            _archive_state(guard, snapshot.operation_id, "ROLLED_BACK")
            recovered.append(snapshot.operation_id)
    return {"status": "PASS", "recovered": recovered}


def _transition(card_id, action, actor_id, *, publisher=None, guard=None):
    if action not in {"publish", "hide", "sold", "delete"}:
        raise LifecycleError("LIFECYCLE_ACTION_INVALID")
    if isinstance(card_id, bool) or int(card_id) <= 0:
        raise LifecycleError("LIFECYCLE_CARD_ID_INVALID")
    card_id = int(card_id)
    if guard is None:
        import publish_transaction_guard as guard
    if getattr(guard, "LIFECYCLE_REENTRANT_LOCK", False) is not True:
        raise LifecycleError("LIFECYCLE_SHARED_REENTRANT_LOCK_REQUIRED")
    snapshot, applied = None, False
    with guard._exclusive_lock():
        recover_pending(guard=guard)
        previous_operation = getattr(_ACTIVE_OPERATION, "operation_id", None)
        try:
            connection = _connect(guard)
            try:
                row = connection.execute("SELECT * FROM cars WHERE id=?", (card_id,)).fetchone()
                if row is None:
                    raise LifecycleError("LIFECYCLE_CARD_NOT_FOUND")
                before = dict(row)
            finally:
                connection.close()
            code = str(before.get("auto_number") or "").strip().upper()
            if not UID.fullmatch(code):
                raise LifecycleError("LIFECYCLE_AUTO_NUMBER_INVALID")
            snapshot = _Snapshot(guard, code, before, action, actor_id)
            after_fields = _mutate(guard, card_id, action, actor_id, snapshot, before)
            applied = True
            _ACTIVE_OPERATION.operation_id = snapshot.operation_id
            if action == "publish":
                if publisher is None:
                    import publikaciya
                    publisher = publikaciya.opublikovat
                result = publisher(code)
            else:
                snapshot.withdraw_pages()
                result = guard.rebuild_catalog()
            if not isinstance(result, (tuple, list)) or len(result) < 2 or result[0] is not True:
                raise LifecycleError("LIFECYCLE_PUBLICATION_FAILED:" + str(result)[:1000])
            if action != "publish":
                for path in snapshot.files:
                    if path.name != "katalog.html" and path.exists():
                        raise LifecycleError("WITHDRAWN_PAGE_RECREATED:" + str(path))
                    if path.name == "katalog.html" and code in guard._href_counts(_read(path).decode("utf-8")):
                        raise LifecycleError("WITHDRAWN_CARD_STILL_IN_CATALOG")
            connection = _connect(guard)
            try:
                current = connection.execute("SELECT * FROM cars WHERE id=?", (card_id,)).fetchone()
                if action == "delete":
                    valid = current is None and _uid_unique(connection, code, card_id, absent=True)
                else:
                    valid = current is not None and current["published"] == int(action == "publish")
                    valid = valid and _same_identity(dict(current) if current is not None else None, before)
                    valid = valid and _uid_unique(connection, code, card_id)
                    if action == "sold":
                        valid = valid and current["status"] == "sold"
                if not valid:
                    raise LifecycleError("CRM_CHANGED_DURING_LIFECYCLE")
                connection.execute("UPDATE ua_spec_lifecycle_archive SET state='COMPLETED' WHERE operation_id=?",
                                   (snapshot.operation_id,))
                connection.commit()
            finally:
                connection.close()
            snapshot.report["state"] = "COMPLETED"
            snapshot.save()
            messages = {
                "publish": "Машина видна клиентам. Страницы и каталог проверены.",
                "hide": "Машина скрыта. Карточка убрана из каталога и по прямым ссылкам.",
                "sold": "Отмечено: продана. Карточка убрана с сайта; данные сохранены в CRM.",
                "delete": "Карточка удалена из CRM и с сайта. Медиа, спецификация и резервная копия сохранены.",
            }
            return True, messages[action]
        except Exception as exc:
            errors = []
            if applied:
                try:
                    _compensate(guard, card_id, action, before, after_fields, snapshot.operation_id)
                except Exception as rollback_error:
                    errors.append("CRM: " + str(rollback_error))
            if snapshot is not None and not errors:
                try:
                    snapshot.restore_files()
                except Exception as rollback_error:
                    errors.append("pages: " + str(rollback_error))
                if applied and not errors:
                    _archive_state(guard, snapshot.operation_id, "ROLLED_BACK")
            if snapshot is not None:
                snapshot.report.update({"state": "ROLLBACK_FAILED" if errors else "ROLLED_BACK",
                                        "error": str(exc), "rollback_errors": errors})
                try:
                    snapshot.save()
                except Exception as backup_error:
                    errors.append("backup: " + str(backup_error))
            if errors:
                raise LifecycleError("КРИТИЧНО: требуется восстановление из " + str(snapshot.root) + ": " + "; ".join(errors)) from exc
            return False, "Изменение отменено; прежние данные и страницы сохранены. " + str(exc)
        finally:
            _ACTIVE_OPERATION.operation_id = previous_operation


def set_visibility(card_id, visible, actor_id=None, *, publisher=None, guard=None):
    return _transition(card_id, "publish" if visible else "hide", actor_id, publisher=publisher, guard=guard)


def delete_card(card_id, actor_id=None, *, guard=None):
    return _transition(card_id, "delete", actor_id, guard=guard)


def mark_sold(card_id, actor_id=None, *, guard=None):
    return _transition(card_id, "sold", actor_id, guard=guard)

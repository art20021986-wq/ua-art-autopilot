#!/usr/bin/env python3
"""Approved TASK 049 production installer with atomic rollback.

The installer is bound to one source hash, one Gate-A candidate hash and one
owner approval marker. It never writes crm.db. It backs up cars_ui.py, performs
one same-filesystem atomic replacement, compiles the live readback, verifies
UA-0006 logistics data and the DB hash, and rolls back on any failure.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import sqlite3
import stat
import sys
import tempfile
import urllib.parse

TASK_ID = "task_049"
SOURCE_PATH = pathlib.Path("/home/Carix/cars_ui.py")
DB_PATH = pathlib.Path("/home/Carix/crm.db")
SAFE_ROOT = pathlib.Path("/home/Carix/autopilot_inbox/cloud/bot_logistics")
CANDIDATE_PATH = SAFE_ROOT / "task049_cars_ui.py.candidate"
APPROVAL_PATH = SAFE_ROOT / "task_049_owner_approval.marker"
BACKUP_PATH = SAFE_ROOT / "task049_cars_ui.py.before_gate_b.20260828T045145Z"
EXPECTED_SOURCE_SHA = (
    "06e7da916ea36c4ffaf01c85f59a0574f06d3cdda24aa1f8c242175de726b7"
)
EXPECTED_CANDIDATE_SHA = (
    "3c6f12227e45a3ba936d48d4a12435378045e879fea481def04f3378f6a0f12f"
)
EXPECTED_CONTAINER = "ONEYSELGF1046602"
EXPECTED_SEA_DATE_OUT = "2026-01-24"
MAX_SOURCE_BYTES = 2_000_000
MAX_DB_BYTES = 512 * 1024 * 1024

REQUIRED_APPROVAL = {
    "TASK_ID": TASK_ID,
    "GATE": "B",
    "DECISION": "APPROVE",
    "USER_REPLY": "APPROVE",
    "SOURCE_SHA256": EXPECTED_SOURCE_SHA,
    "CANDIDATE_SHA256": EXPECTED_CANDIDATE_SHA,
    "UA_0006_CONTAINER": EXPECTED_CONTAINER,
    "UA_0006_SEA_DATE_OUT": EXPECTED_SEA_DATE_OUT,
}


class GateBBlocked(RuntimeError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        stat.S_IFMT(info.st_mode),
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def secure_read(path: pathlib.Path, maximum: int) -> tuple[bytes, os.stat_result]:
    before = os.lstat(path)
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise GateBBlocked("not_single_regular_file:" + path.name)
    if not 0 <= before.st_size <= maximum:
        raise GateBBlocked("file_size_out_of_bounds:" + path.name)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    chunks: list[bytes] = []
    total = 0
    try:
        opened = os.fstat(descriptor)
        if _identity(opened) != _identity(before):
            raise GateBBlocked("identity_changed_during_open:" + path.name)
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, maximum + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > maximum:
                raise GateBBlocked("file_size_out_of_bounds:" + path.name)
        opened_after = os.fstat(descriptor)
        path_after = os.lstat(path)
        if _identity(opened_after) != _identity(before) or _identity(path_after) != _identity(before):
            raise GateBBlocked("identity_changed_during_read:" + path.name)
    finally:
        os.close(descriptor)
    return b"".join(chunks), before


def secure_digest(path: pathlib.Path, maximum: int) -> tuple[str, os.stat_result]:
    """Hash one stable regular file without loading it into memory."""
    before = os.lstat(path)
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise GateBBlocked("not_single_regular_file:" + path.name)
    if not 0 <= before.st_size <= maximum:
        raise GateBBlocked("file_size_out_of_bounds:" + path.name)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    digest = hashlib.sha256()
    total = 0
    try:
        opened = os.fstat(descriptor)
        if _identity(opened) != _identity(before):
            raise GateBBlocked("identity_changed_during_open:" + path.name)
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > maximum:
                raise GateBBlocked("file_size_out_of_bounds:" + path.name)
            digest.update(chunk)
        opened_after = os.fstat(descriptor)
        path_after = os.lstat(path)
        if (
            _identity(opened_after) != _identity(before)
            or _identity(path_after) != _identity(before)
        ):
            raise GateBBlocked("identity_changed_during_read:" + path.name)
    finally:
        os.close(descriptor)
    if total != before.st_size:
        raise GateBBlocked("file_size_changed_during_read:" + path.name)
    return digest.hexdigest(), before


def parse_approval(data: bytes) -> dict[str, str]:
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise GateBBlocked("approval_not_utf8") from exc
    result: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        if ":" not in line:
            raise GateBBlocked("approval_line_invalid")
        key, value = line.split(":", 1)
        key = key.strip()
        if key in result:
            raise GateBBlocked("approval_duplicate_key")
        result[key] = value.strip()
    for key, expected in REQUIRED_APPROVAL.items():
        if result.get(key) != expected:
            raise GateBBlocked("approval_field_invalid:" + key)
    return result


def validate_ui(candidate: bytes) -> dict[str, int | bool]:
    try:
        text = candidate.decode("utf-8", errors="strict")
        compile(text, "cars_ui.py.candidate", "exec")
    except (UnicodeDecodeError, SyntaxError) as exc:
        raise GateBBlocked("candidate_compile_failed") from exc
    checks = {
        "outer_hub_labels": text.count("🚢 Этапы и доставка"),
        "card_entry": text.count('callback_data="car_logistics:%d:card" % cid'),
        "editor_entry": text.count('callback_data="car_logistics:%d:edit" % cid'),
        "handler": text.count(
            'logistics_hub, pattern=r"^car_logistics:[0-9]+:(?:card|edit)$"'
        ),
        "old_delivery_button": text.count('InlineKeyboardButton("Срок доставки"'),
        "old_post_stage_button": text.count(
            'InlineKeyboardButton("Изменить срок доставки"'
        ),
        "old_editor_days": text.count('("eta_days", "Дней до прибытия")'),
        "old_editor_container": text.count('("sea_container", "Номер контейнера")'),
    }
    expected = {
        "outer_hub_labels": 2,
        "card_entry": 1,
        "editor_entry": 1,
        "handler": 1,
        "old_delivery_button": 0,
        "old_post_stage_button": 0,
        "old_editor_days": 0,
        "old_editor_container": 0,
    }
    for key, value in expected.items():
        if checks[key] != value:
            raise GateBBlocked("candidate_ui_invariant:" + key)
    checks["compiled"] = True
    return checks


def db_digest() -> str:
    digest, _ = secure_digest(DB_PATH, MAX_DB_BYTES)
    return digest


def verify_db_values() -> None:
    encoded = urllib.parse.quote(str(DB_PATH), safe="/")
    connection = sqlite3.connect(
        f"file:{encoded}?mode=ro", uri=True, timeout=5
    )
    try:
        connection.execute("PRAGMA query_only=ON")
        quick = connection.execute("PRAGMA quick_check").fetchall()
        if quick != [("ok",)]:
            raise GateBBlocked("db_quick_check_failed")
        rows = connection.execute(
            'SELECT "sea_container", "sea_date_out" FROM "cars" '
            'WHERE "auto_number" = ?',
            ("UA-0006",),
        ).fetchall()
        if len(rows) != 1:
            raise GateBBlocked("ua0006_row_count_invalid")
        container, sea_date_out = rows[0]
        if str(container or "").strip() != EXPECTED_CONTAINER:
            raise GateBBlocked("ua0006_container_changed")
        if str(sea_date_out or "").strip()[:10] != EXPECTED_SEA_DATE_OUT:
            raise GateBBlocked("ua0006_sea_date_changed")
        if connection.total_changes != 0:
            raise GateBBlocked("unexpected_db_change_count")
    finally:
        connection.close()


def exclusive_backup(source: bytes, source_info: os.stat_result) -> None:
    if BACKUP_PATH.exists():
        existing, _ = secure_read(BACKUP_PATH, MAX_SOURCE_BYTES)
        if sha256(existing) != EXPECTED_SOURCE_SHA:
            raise GateBBlocked("existing_backup_hash_mismatch")
        return
    descriptor = os.open(
        BACKUP_PATH,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
        stat.S_IMODE(source_info.st_mode),
    )
    try:
        view = memoryview(source)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise GateBBlocked("backup_short_write")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    directory = os.open(
        BACKUP_PATH.parent,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    backup, _ = secure_read(BACKUP_PATH, MAX_SOURCE_BYTES)
    if sha256(backup) != EXPECTED_SOURCE_SHA:
        raise GateBBlocked("backup_readback_hash_mismatch")


def compile_bytes(data: bytes, label: str) -> None:
    try:
        text = data.decode("utf-8", errors="strict")
        compile(text, label, "exec")
    except (UnicodeDecodeError, SyntaxError, ValueError, TypeError) as exc:
        raise GateBBlocked("live_compile_failed") from exc


def atomic_replace_bytes(target: pathlib.Path, data: bytes, mode: int) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix="." + target.name + ".task049.", suffix=".tmp", dir=target.parent
    )
    temporary = pathlib.Path(temporary_name)
    try:
        os.fchmod(descriptor, stat.S_IMODE(mode))
        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise GateBBlocked("atomic_short_write")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, target)
        directory = os.open(target.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary.exists():
            temporary.unlink()


def base_receipt(mode: str) -> dict:
    return {
        "task_id": TASK_ID,
        "mode": mode,
        "status": "BLOCKED",
        "source_path": str(SOURCE_PATH),
        "candidate_path": str(CANDIDATE_PATH),
        "backup_path": str(BACKUP_PATH),
        "production_write": False,
        "crm_write": False,
        "db_write": False,
        "service_restart": False,
        "website_write": False,
        "rollback": False,
        "errors": [],
    }


def install() -> dict:
    receipt = base_receipt("GATE_B_INSTALL")
    replaced = False
    source_info = None
    db_before = ""
    try:
        approval, _ = secure_read(APPROVAL_PATH, 20_000)
        parse_approval(approval)
        source, source_info = secure_read(SOURCE_PATH, MAX_SOURCE_BYTES)
        candidate, _ = secure_read(CANDIDATE_PATH, MAX_SOURCE_BYTES)
        if sha256(source) != EXPECTED_SOURCE_SHA:
            raise GateBBlocked("source_sha_mismatch")
        if sha256(candidate) != EXPECTED_CANDIDATE_SHA:
            raise GateBBlocked("candidate_sha_mismatch")
        checks = validate_ui(candidate)
        db_before = db_digest()
        verify_db_values()
        exclusive_backup(source, source_info)
        atomic_replace_bytes(SOURCE_PATH, candidate, source_info.st_mode)
        replaced = True
        live, _ = secure_read(SOURCE_PATH, MAX_SOURCE_BYTES)
        if sha256(live) != EXPECTED_CANDIDATE_SHA:
            raise GateBBlocked("live_source_readback_hash_mismatch")
        compile_bytes(live, str(SOURCE_PATH))
        verify_db_values()
        db_after = db_digest()
        if db_after != db_before:
            raise GateBBlocked("db_hash_changed")
        receipt.update({
            "status": "PASS",
            "production_write": True,
            "source_sha256_before": EXPECTED_SOURCE_SHA,
            "source_sha256_after": EXPECTED_CANDIDATE_SHA,
            "backup_sha256": EXPECTED_SOURCE_SHA,
            "db_sha256_before": db_before,
            "db_sha256_after": db_after,
            "ua0006_container_preserved": True,
            "ua0006_sea_date_preserved": True,
            "ua0006_container": EXPECTED_CONTAINER,
            "ua0006_sea_date_out": EXPECTED_SEA_DATE_OUT,
            "checks": checks,
            "errors": [],
        })
        return receipt
    except (GateBBlocked, OSError, sqlite3.Error, ValueError, TypeError) as exc:
        error = str(exc) if isinstance(exc, GateBBlocked) else "gate_b_system_failure"
        if replaced and source_info is not None:
            try:
                backup, _ = secure_read(BACKUP_PATH, MAX_SOURCE_BYTES)
                if sha256(backup) != EXPECTED_SOURCE_SHA:
                    raise GateBBlocked("rollback_backup_hash_mismatch")
                atomic_replace_bytes(SOURCE_PATH, backup, source_info.st_mode)
                restored, _ = secure_read(SOURCE_PATH, MAX_SOURCE_BYTES)
                if sha256(restored) != EXPECTED_SOURCE_SHA:
                    raise GateBBlocked("rollback_readback_hash_mismatch")
                compile_bytes(restored, str(SOURCE_PATH))
                receipt.update({
                    "status": "ROLLED_BACK",
                    "production_write": True,
                    "rollback": True,
                    "source_sha256_after": EXPECTED_SOURCE_SHA,
                    "errors": [error],
                })
            except Exception:
                receipt.update({
                    "status": "ROLLBACK_FAILED",
                    "production_write": True,
                    "rollback": False,
                    "errors": [error, "rollback_failed"],
                })
        else:
            receipt["errors"] = [error]
        return receipt


def rollback_after_restart_failure() -> dict:
    receipt = base_receipt("GATE_B_ROLLBACK_AFTER_RESTART_FAILURE")
    try:
        approval, _ = secure_read(APPROVAL_PATH, 20_000)
        parse_approval(approval)
        live, live_info = secure_read(SOURCE_PATH, MAX_SOURCE_BYTES)
        backup, _ = secure_read(BACKUP_PATH, MAX_SOURCE_BYTES)
        if sha256(backup) != EXPECTED_SOURCE_SHA:
            raise GateBBlocked("rollback_backup_hash_mismatch")
        live_hash = sha256(live)
        if live_hash == EXPECTED_SOURCE_SHA:
            receipt.update({
                "status": "PASS",
                "rollback": True,
                "source_sha256_after": EXPECTED_SOURCE_SHA,
            })
            return receipt
        if live_hash != EXPECTED_CANDIDATE_SHA:
            raise GateBBlocked("rollback_live_hash_unknown")
        db_before = db_digest()
        verify_db_values()
        atomic_replace_bytes(SOURCE_PATH, backup, live_info.st_mode)
        restored, _ = secure_read(SOURCE_PATH, MAX_SOURCE_BYTES)
        if sha256(restored) != EXPECTED_SOURCE_SHA:
            raise GateBBlocked("rollback_readback_hash_mismatch")
        compile_bytes(restored, str(SOURCE_PATH))
        verify_db_values()
        db_after = db_digest()
        if db_after != db_before:
            raise GateBBlocked("rollback_db_hash_changed")
        receipt.update({
            "status": "PASS",
            "production_write": True,
            "rollback": True,
            "source_sha256_after": EXPECTED_SOURCE_SHA,
            "db_sha256_before": db_before,
            "db_sha256_after": db_after,
            "ua0006_container_preserved": True,
            "ua0006_sea_date_preserved": True,
            "ua0006_container": EXPECTED_CONTAINER,
            "ua0006_sea_date_out": EXPECTED_SEA_DATE_OUT,
            "errors": [],
        })
    except (GateBBlocked, OSError, sqlite3.Error) as exc:
        receipt["errors"] = [
            str(exc) if isinstance(exc, GateBBlocked) else "rollback_system_failure"
        ]
    return receipt


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args == []:
        receipt = install()
    elif args == ["--rollback-after-restart-failure"]:
        receipt = rollback_after_restart_failure()
    else:
        receipt = base_receipt("INVALID")
        receipt["errors"] = ["invalid_arguments"]
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if receipt["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())

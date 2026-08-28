#!/usr/bin/env python3
"""Fail-closed installer for CRM-AI-CARD-001 / TASK 061."""
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
import tempfile

import patch_payload


BASE = pathlib.Path("/home/Carix")
SAFE = BASE / "autopilot_inbox" / "cloud" / "task_061"
TEAM = BASE / "team_bot.py"
LOCAL_OCR = BASE / "local_ocr.py"
SAFE_OCR = SAFE / "local_ocr.py"
RECEIPT = SAFE / "install_receipt.json"
BACKUPS = BASE / "backups" / "task_061"

EXPECTED_TEAM = "cfb1f52ea820a2e5a3e65a2d4b0e2c99c5c6e35402dd3678a22a7bdd6fb3b09a"
EXPECTED_OCR = "c82c69eb69eccfb901cae56e111155b2cccd49e5ae63a10bb7ad4dafeea724a8"
EXPECTED_FAST = "d2ac2104b2293e3c5cb38930fac6f4de87b9d1d3f35783b1b4e892433fcfd64e"
EXPECTED_FILTER = "7dfd84497c6d3823cd7df54834cb18aecdbc645544ca9709a88c6363a2d35cb6"


class InstallError(RuntimeError):
    pass


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha_file(path):
    return sha_bytes(path.read_bytes())


def utc_now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def regular(path):
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise InstallError("MISSING:" + path.name) from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise InstallError("UNSAFE_FILE:" + path.name)


def atomic_write(path, data):
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


def replace_run_ai_draft(source):
    tree = ast.parse(source)
    nodes = [
        node for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "run_ai_draft"
    ]
    if len(nodes) != 1:
        raise InstallError("RUN_AI_DRAFT_TARGET_INVALID")
    node = nodes[0]
    lines = source.splitlines(keepends=True)
    lines[node.lineno - 1:node.end_lineno] = [patch_payload.RUN_AI_DRAFT_SOURCE.rstrip() + "\n\n"]
    candidate = "".join(lines)
    compile(candidate, "team_bot.py.candidate", "exec")

    parsed = ast.parse(candidate)
    target = next(
        n for n in parsed.body
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "run_ai_draft"
    )
    target_source = ast.get_source_segment(candidate, target) or ""
    forbidden = ("notify_managers", "передан сотруд", "сотруднику", "передал менеджеру")
    if any(value in target_source.casefold() for value in forbidden):
        raise InstallError("OWNER_INTAKE_HANDOFF_REMAINS")
    required = (
        "hard_deadline = started + 15.0",
        "Новая карточка открыта",
        "0 AI-токенов",
        "local_ocr.fields_from_image",
    )
    if any(value not in target_source for value in required):
        raise InstallError("OWNER_INTAKE_CONTRACT_MISSING")
    if "ai.parse_image" in target_source or "ai.parse_message" in target_source:
        raise InstallError("PAID_PHOTO_TEXT_AI_REMAINS")
    return candidate.encode("utf-8")


def site_hashes():
    result = {}
    for root in (BASE / "video", BASE / "site"):
        for name in ("index.html", "katalog.html") + tuple("UA-%04d.html" % n for n in range(1, 11)):
            path = root / name
            if path.exists() and path.is_file() and not path.is_symlink():
                result[str(path)] = sha_file(path)
    return result


def readonly_db_check():
    connection = sqlite3.connect("file:/home/Carix/crm.db?mode=ro", uri=True, timeout=5)
    try:
        quick = connection.execute("PRAGMA quick_check").fetchone()
        if not quick or quick[0] != "ok":
            raise InstallError("CRM_QUICK_CHECK_FAILED")
        tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        result = {"quick_check": "ok", "cars_table": "cars" in tables}
        if "cars" in tables:
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(cars)").fetchall()
            }
            result["cars_columns"] = len(columns)
            if "auto_number" in columns:
                result["ua0009_rows"] = connection.execute(
                    "SELECT count(*) FROM cars WHERE auto_number IN ('UA-0009','UA0009')"
                ).fetchone()[0]
        return result
    finally:
        connection.close()


def runtime_check(ocr_data):
    if not shutil.which("tesseract"):
        raise InstallError("TESSERACT_MISSING")
    try:
        import PIL  # noqa: F401
    except Exception as exc:
        raise InstallError("PIL_MISSING") from exc
    namespace = {}
    exec(compile(ocr_data.decode("utf-8"), "local_ocr.py", "exec"), namespace)
    allowed = {"brand", "model", "year", "vin", "mileage_km", "fuel", "gearbox", "engine_cc"}
    samples = (
        "Kia K5 2018 198 tuc. km LPG 2.0 l Astomat KNAGU416BKA324445",
        "Киа K5 2018, пробег 198 тыс. км, газ 2 л, автомат, KNAGU416BKA324445",
    )
    for sample in samples:
        fields = namespace["fields_from_text"](sample, allowed)
        if set(fields) != allowed or fields.get("engine_cc") != 2000:
            raise InstallError("LOCAL_PARSER_SELFTEST_FAILED")
    if namespace.get("DEFAULT_PHOTO_SECONDS") != 13.5:
        raise InstallError("OCR_BUDGET_INVALID")


def run():
    started = utc_now()
    receipt = {
        "task_id": "task_061", "contract_id": "CRM-AI-CARD-001",
        "status": "BLOCKED", "mode": "OWNER_APPROVED_INSTALL",
        "started_at_utc": started, "finished_at_utc": started, "errors": [],
        "production_write": False, "crm_db_write": False, "site_write": False,
        "service_restarted": False, "rollback_performed": False,
        "already_applied": False, "photo_text_deadline_seconds": 15,
        "photo_ai_tokens": 0, "text_ai_tokens": 0,
        "staff_handoff_removed": False, "auto_open_draft": False,
        "ua0009_publication_performed": False, "ua0009_readonly_check": None,
        "files": {}, "backup_path": None,
    }
    old_team = old_ocr = None
    wrote = False
    before_db = before_site = None
    try:
        for path in (
            TEAM, LOCAL_OCR, BASE / "ai_fast_schema.py", BASE / "ai_filter.py",
            BASE / "crm.db", SAFE_OCR,
        ):
            regular(path)
        if sha_file(BASE / "ai_fast_schema.py") != EXPECTED_FAST:
            raise InstallError("FAST_SCHEMA_DRIFT")
        if sha_file(BASE / "ai_filter.py") != EXPECTED_FILTER:
            raise InstallError("CRM_SCHEMA_DRIFT")

        receipt["ua0009_readonly_check"] = readonly_db_check()
        ocr_data = SAFE_OCR.read_bytes()
        runtime_check(ocr_data)
        old_team = TEAM.read_bytes()
        old_ocr = LOCAL_OCR.read_bytes()

        if b"Open a schema-closed CRM draft" in old_team:
            if sha_file(LOCAL_OCR) != sha_bytes(ocr_data):
                raise InstallError("ALREADY_APPLIED_OCR_DRIFT")
            receipt.update(
                status="PASS", already_applied=True,
                staff_handoff_removed=True, auto_open_draft=True,
            )
            return receipt
        if sha_bytes(old_team) != EXPECTED_TEAM:
            raise InstallError("TEAM_SOURCE_DRIFT")
        if sha_bytes(old_ocr) != EXPECTED_OCR:
            raise InstallError("OCR_SOURCE_DRIFT")

        candidate = replace_run_ai_draft(old_team.decode("utf-8"))
        before_db = sha_file(BASE / "crm.db")
        before_site = site_hashes()
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = BACKUPS / stamp
        backup.mkdir(parents=True, exist_ok=False)
        shutil.copy2(TEAM, backup / "team_bot.py")
        shutil.copy2(LOCAL_OCR, backup / "local_ocr.py")
        if sha_file(backup / "team_bot.py") != EXPECTED_TEAM:
            raise InstallError("TEAM_BACKUP_HASH_MISMATCH")
        if sha_file(backup / "local_ocr.py") != EXPECTED_OCR:
            raise InstallError("OCR_BACKUP_HASH_MISMATCH")
        receipt["backup_path"] = str(backup)

        atomic_write(LOCAL_OCR, ocr_data)
        atomic_write(TEAM, candidate)
        wrote = True
        compile(TEAM.read_text(encoding="utf-8"), str(TEAM), "exec")
        compile(LOCAL_OCR.read_text(encoding="utf-8"), str(LOCAL_OCR), "exec")
        if sha_file(BASE / "crm.db") != before_db:
            raise InstallError("CRM_DB_CHANGED")
        if site_hashes() != before_site:
            raise InstallError("SITE_CHANGED")
        if readonly_db_check().get("quick_check") != "ok":
            raise InstallError("CRM_POSTCHECK_FAILED")

        receipt.update(
            status="PASS", production_write=True,
            staff_handoff_removed=True, auto_open_draft=True,
            files={
                str(TEAM): {"before": EXPECTED_TEAM, "after": sha_file(TEAM)},
                str(LOCAL_OCR): {"before": EXPECTED_OCR, "after": sha_file(LOCAL_OCR)},
            },
        )
        return receipt
    except Exception as exc:
        receipt["errors"].append(
            str(exc)[:200] if isinstance(exc, InstallError) else "UNEXPECTED_INSTALL_ERROR"
        )
        if wrote and old_team is not None and old_ocr is not None:
            try:
                atomic_write(TEAM, old_team)
                atomic_write(LOCAL_OCR, old_ocr)
                receipt["rollback_performed"] = True
                receipt["production_write"] = False
            except Exception:
                receipt["errors"].append("ROLLBACK_FAILED")
        return receipt
    finally:
        receipt["finished_at_utc"] = utc_now()


def main():
    receipt = run()
    atomic_write(
        RECEIPT,
        (json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(),
    )
    print(json.dumps({"status": receipt["status"], "production_write": receipt["production_write"]}))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

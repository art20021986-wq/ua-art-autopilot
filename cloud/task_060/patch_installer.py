#!/usr/bin/env python3
"""Fail-closed installer for TASK 060 token-free CRM intake."""
from __future__ import annotations

import ast
import datetime as dt
import hashlib
import json
import os
import pathlib
import shutil
import stat
import tempfile

import patch_payload


BASE = pathlib.Path("/home/Carix")
SAFE = BASE / "autopilot_inbox" / "cloud" / "task_060"
TEAM = BASE / "team_bot.py"
LOCAL_OCR = BASE / "local_ocr.py"
SAFE_OCR = SAFE / "local_ocr.py"
RECEIPT = SAFE / "install_receipt.json"
BACKUPS = BASE / "backups" / "task_060"
EXPECTED_TEAM = "6f34c77e288946503bed97739e2c77143fdce79e86d0e21dae889c933b00ab78"
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


def regular(path, required=True):
    try:
        info = path.lstat()
    except FileNotFoundError:
        if required:
            raise InstallError("MISSING:" + path.name)
        return False
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise InstallError("UNSAFE_FILE:" + path.name)
    return True


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


def replace_functions(source):
    replacements = {
        "show_menu": patch_payload.SHOW_MENU_SOURCE,
        "intake": patch_payload.INTAKE_SOURCE,
        "run_ai_draft": patch_payload.RUN_AI_DRAFT_SOURCE,
    }
    tree = ast.parse(source)
    found = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in replacements:
            if node.name in found:
                raise InstallError("DUPLICATE_FUNCTION:" + node.name)
            found[node.name] = node
    if set(found) != set(replacements):
        raise InstallError("TARGET_FUNCTION_SET_MISMATCH")
    lines = source.splitlines(keepends=True)
    for name, node in sorted(found.items(), key=lambda item: item[1].lineno, reverse=True):
        lines[node.lineno - 1:node.end_lineno] = [replacements[name].rstrip() + "\n\n"]
    candidate = "".join(lines)
    compile(candidate, "team_bot.py.candidate", "exec")
    parsed = ast.parse(candidate)
    intake = next(n for n in parsed.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "intake")
    intake_source = ast.get_source_segment(candidate, intake) or ""
    if "notify_managers" in intake_source or "Передал менеджеру" in intake_source:
        raise InstallError("STAFF_HANDOFF_REMAINS")
    if candidate.count("Token-free photo/text parser") != 1:
        raise InstallError("LOCAL_OCR_MARKER_INVALID")
    return candidate.encode("utf-8")


def site_hashes():
    result = {}
    for root in (BASE / "video", BASE / "site"):
        for name in ("index.html", "katalog.html") + tuple("UA-%04d.html" % n for n in range(1, 11)):
            path = root / name
            if path.exists() and path.is_file() and not path.is_symlink():
                result[str(path)] = sha_file(path)
    return result


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
    sample = "Kia K5 2018 198 tuc. km LPG 2.0 l automatic KNAGU416BKA324445"
    fields = namespace["fields_from_text"](sample, allowed)
    required = {"brand", "model", "year", "vin", "mileage_km", "fuel", "gearbox", "engine_cc"}
    if set(fields) != required:
        raise InstallError("LOCAL_PARSER_SELFTEST_FAILED")


def run():
    started = utc_now()
    receipt = {
        "task_id": "task_060", "status": "BLOCKED", "mode": "TOKEN_FREE_OCR_INSTALL",
        "started_at_utc": started, "finished_at_utc": started, "errors": [],
        "production_write": False, "crm_db_write": False, "site_write": False,
        "service_restarted": False, "ua0010_published": False,
        "rollback_performed": False, "already_applied": False,
        "token_cost_per_photo": 0, "staff_handoff_removed": False,
        "files": {}, "backup_path": None,
    }
    old_team = old_ocr = None
    ocr_existed = False
    wrote = False
    try:
        for path in (TEAM, BASE / "ai_fast_schema.py", BASE / "ai_filter.py", BASE / "crm.db", SAFE_OCR):
            regular(path)
        if sha_file(BASE / "ai_fast_schema.py") != EXPECTED_FAST:
            raise InstallError("FAST_SCHEMA_DRIFT")
        if sha_file(BASE / "ai_filter.py") != EXPECTED_FILTER:
            raise InstallError("CRM_SCHEMA_DRIFT")
        ocr_data = SAFE_OCR.read_bytes()
        runtime_check(ocr_data)
        old_team = TEAM.read_bytes()
        ocr_existed = regular(LOCAL_OCR, required=False)
        old_ocr = LOCAL_OCR.read_bytes() if ocr_existed else None

        if b"Token-free photo/text parser" in old_team:
            if sha_file(LOCAL_OCR) != sha_bytes(ocr_data):
                raise InstallError("ALREADY_APPLIED_OCR_DRIFT")
            receipt.update(status="PASS", already_applied=True, staff_handoff_removed=True)
            return receipt
        if sha_bytes(old_team) != EXPECTED_TEAM:
            raise InstallError("TEAM_SOURCE_DRIFT")

        candidate = replace_functions(old_team.decode("utf-8"))
        before_db = sha_file(BASE / "crm.db")
        before_site = site_hashes()
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = BACKUPS / stamp
        backup.mkdir(parents=True, exist_ok=False)
        shutil.copy2(TEAM, backup / "team_bot.py")
        if ocr_existed:
            shutil.copy2(LOCAL_OCR, backup / "local_ocr.py")
        if sha_file(backup / "team_bot.py") != EXPECTED_TEAM:
            raise InstallError("BACKUP_HASH_MISMATCH")
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
        receipt.update(
            status="PASS", production_write=True, staff_handoff_removed=True,
            files={
                str(TEAM): {"before": EXPECTED_TEAM, "after": sha_file(TEAM)},
                str(LOCAL_OCR): {"before": sha_bytes(old_ocr) if old_ocr else None, "after": sha_file(LOCAL_OCR)},
            },
        )
        return receipt
    except Exception as exc:
        receipt["errors"].append(str(exc)[:200] if isinstance(exc, InstallError) else "UNEXPECTED_INSTALL_ERROR")
        if wrote and old_team is not None:
            try:
                atomic_write(TEAM, old_team)
                if ocr_existed:
                    atomic_write(LOCAL_OCR, old_ocr)
                else:
                    LOCAL_OCR.unlink(missing_ok=True)
                receipt["rollback_performed"] = True
                receipt["production_write"] = False
            except Exception:
                receipt["errors"].append("ROLLBACK_FAILED")
        return receipt
    finally:
        receipt["finished_at_utc"] = utc_now()


def main():
    receipt = run()
    atomic_write(RECEIPT, (json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode())
    print(json.dumps({"status": receipt["status"], "production_write": receipt["production_write"]}))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

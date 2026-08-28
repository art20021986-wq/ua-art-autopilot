#!/usr/bin/env python3
"""Fail-closed installer for TASK 059 CRM multimodal fast/schema patch."""
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
SAFE = BASE / "autopilot_inbox" / "cloud" / "task_059_ai_fast_schema"
SOURCE_TEAM = BASE / "team_bot.py"
TARGET_HELPER = BASE / "ai_fast_schema.py"
SAFE_HELPER = SAFE / "ai_fast_schema.py"
RECEIPT = SAFE / "task_059_install_receipt.json"
BACKUP_ROOT = BASE / "backups" / "task_059_ai_fast_schema"
EXPECTED_TEAM_SHA256 = "059e3e044a8bb3d4c1fe7ef4b43c40eacb491fb3614e9929e0c01dc7a9de9430"
EXPECTED_AI_SHA256 = "406c625f43d966e6871d766ca2dd825e7e33c019fadb6e287cafdb7803a524ed"
EXPECTED_FILTER_SHA256 = "7dfd84497c6d3823cd7df54834cb18aecdbc645544ca9709a88c6363a2d35cb6"


class InstallError(RuntimeError):
    pass


def utc_now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha_file(path):
    return sha_bytes(path.read_bytes())


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


def replace_functions(source, replacements):
    """Replace exact top-level async functions using AST line boundaries."""
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
        replacement = replacements[name].rstrip() + "\n\n"
        lines[node.lineno - 1 : node.end_lineno] = [replacement]
    candidate = "".join(lines)
    compile(candidate, "team_bot.py.candidate", "exec")
    if candidate.count("Fast schema-closed intake") != 1:
        raise InstallError("RUN_DRAFT_MARKER_INVALID")
    if candidate.count("import ai_fast_schema as fast") != 2:
        raise InstallError("HELPER_IMPORT_COUNT_INVALID")
    function_tree = ast.parse(candidate)
    target_source = {}
    candidate_lines = candidate.splitlines()
    for node in function_tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in replacements:
            target_source[node.name] = "\n".join(candidate_lines[node.lineno - 1 : node.end_lineno])
    run_source = target_source["run_ai_draft"]
    if "ai_filter.autosave" in run_source or "ai.review(" in run_source:
        raise InstallError("OLD_SLOW_OR_AUTOSAVE_PATH_REMAINS")
    for token in ("PHOTO_HARD_SECONDS", "asyncio.wait_for", "✅ Разместить", "clean_data"):
        if token not in run_source:
            raise InstallError("RUN_DRAFT_REQUIREMENT_MISSING:" + token)
    return candidate


def atomic_write(path, data, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(dir=path.parent, prefix="." + path.name + ".", delete=False)
    temporary = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def html_hashes():
    result = {}
    for root in (BASE / "video", BASE / "site"):
        for name in ("index.html", "katalog.html") + tuple("UA-%04d.html" % n for n in range(1, 11)):
            path = root / name
            if path.exists() and path.is_file() and not path.is_symlink():
                result[str(path)] = sha_file(path)
    return result


def run():
    started = utc_now()
    receipt = {
        "task_id": "task_059",
        "mode": "P0_AI_FAST_SCHEMA_INSTALL",
        "status": "BLOCKED",
        "started_at_utc": started,
        "finished_at_utc": started,
        "production_write": False,
        "crm_db_write": False,
        "site_write": False,
        "service_restarted": False,
        "ua0010_published": False,
        "already_applied": False,
        "rollback_performed": False,
        "backup_path": None,
        "files": {},
        "db_sha256_before": None,
        "db_sha256_after": None,
        "site_hashes_unchanged": False,
        "errors": [],
    }
    backup = None
    old_team = None
    old_helper = None
    helper_existed = False
    wrote = False
    try:
        for path in (SOURCE_TEAM, BASE / "ai.py", BASE / "ai_filter.py", BASE / "crm.db", SAFE_HELPER):
            regular(path)
        if sha_file(BASE / "ai.py") != EXPECTED_AI_SHA256:
            raise InstallError("AI_SOURCE_DRIFT")
        if sha_file(BASE / "ai_filter.py") != EXPECTED_FILTER_SHA256:
            raise InstallError("FILTER_SOURCE_DRIFT")
        helper_data = SAFE_HELPER.read_bytes()
        compile(helper_data.decode("utf-8"), "ai_fast_schema.py", "exec")
        old_team = SOURCE_TEAM.read_bytes()
        helper_existed = regular(TARGET_HELPER, required=False)
        old_helper = TARGET_HELPER.read_bytes() if helper_existed else None

        if b"Fast schema-closed intake" in old_team:
            if sha_file(TARGET_HELPER) != sha_bytes(helper_data):
                raise InstallError("ALREADY_APPLIED_HELPER_DRIFT")
            receipt.update(status="PASS", already_applied=True, site_hashes_unchanged=True)
            return receipt
        if sha_bytes(old_team) != EXPECTED_TEAM_SHA256:
            raise InstallError("TEAM_SOURCE_DRIFT")

        candidate_text = replace_functions(
            old_team.decode("utf-8"),
            {
                "run_ai_draft": patch_payload.RUN_AI_DRAFT_SOURCE,
                "ai_save": patch_payload.AI_SAVE_SOURCE,
            },
        )
        candidate_team = candidate_text.encode("utf-8")
        before_site = html_hashes()
        db_before = sha_file(BASE / "crm.db")
        receipt["db_sha256_before"] = db_before

        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = BACKUP_ROOT / stamp
        backup.mkdir(parents=True, exist_ok=False)
        shutil.copy2(SOURCE_TEAM, backup / "team_bot.py")
        if helper_existed:
            shutil.copy2(TARGET_HELPER, backup / "ai_fast_schema.py")
        if sha_file(backup / "team_bot.py") != EXPECTED_TEAM_SHA256:
            raise InstallError("BACKUP_HASH_MISMATCH")
        receipt["backup_path"] = str(backup)

        atomic_write(TARGET_HELPER, helper_data)
        atomic_write(SOURCE_TEAM, candidate_team)
        wrote = True
        compile(SOURCE_TEAM.read_text(encoding="utf-8"), str(SOURCE_TEAM), "exec")
        compile(TARGET_HELPER.read_text(encoding="utf-8"), str(TARGET_HELPER), "exec")

        db_after = sha_file(BASE / "crm.db")
        after_site = html_hashes()
        if db_after != db_before:
            raise InstallError("CRM_DB_CHANGED")
        if after_site != before_site:
            raise InstallError("SITE_CHANGED")
        receipt.update(
            status="PASS",
            production_write=True,
            db_sha256_after=db_after,
            site_hashes_unchanged=True,
            files={
                str(SOURCE_TEAM): {"before": EXPECTED_TEAM_SHA256, "after": sha_file(SOURCE_TEAM)},
                str(TARGET_HELPER): {"before": sha_bytes(old_helper) if old_helper else None, "after": sha_file(TARGET_HELPER)},
            },
        )
        return receipt
    except Exception as exc:
        receipt["errors"].append(str(exc)[:200] if isinstance(exc, InstallError) else "UNEXPECTED_INSTALL_ERROR")
        if wrote and old_team is not None:
            try:
                atomic_write(SOURCE_TEAM, old_team)
                if helper_existed:
                    atomic_write(TARGET_HELPER, old_helper)
                elif TARGET_HELPER.exists():
                    TARGET_HELPER.unlink()
                receipt["rollback_performed"] = True
                receipt["production_write"] = False
            except Exception:
                receipt["errors"].append("ROLLBACK_FAILED")
        return receipt
    finally:
        receipt["finished_at_utc"] = utc_now()


def main():
    receipt = run()
    atomic_write(RECEIPT, (json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    print(json.dumps({"status": receipt["status"], "production_write": receipt["production_write"]}, sort_keys=True))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

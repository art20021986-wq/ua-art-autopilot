#!/usr/bin/env python3
"""Fail-closed production installer for CRM-VOICE-FILL-001 / TASK 062."""
from __future__ import annotations

import ast
import datetime as dt
import hashlib
import importlib.util
import json
import os
import pathlib
import shutil
import sqlite3
import stat
import tempfile

import patch_payload


BASE = pathlib.Path("/home/Carix")
SAFE = BASE / "autopilot_inbox" / "cloud" / "task_062"
CARS = BASE / "cars_ui.py"
TEAM = BASE / "team_bot.py"
DB = BASE / "crm.db"
RECEIPT = SAFE / "install_receipt.json"
BACKUPS = BASE / "backups" / "task_062"

EXPECTED_CARS = "06e7da916ea36c4ffafef01c85f59a0574f06d3cdda24aa1f8c242175de726b7"
EXPECTED_TEAM = "0dddd71ceb64d0397cf94faad994f85494032173cc025adf3e1634da0652abd0"
EXPECTED_OCR = "7eb4de0597fb6064c8e5f7b56c00d673e8d964630481b3fe5511bb20363770b5"
EXPECTED_FAST = "d2ac2104b2293e3c5cb38930fac6f4de87b9d1d3f35783b1b4e892433fcfd64e"
EXPECTED_FILTER = "7dfd84497c6d3823cd7df54834cb18aecdbc645544ca9709a88c6363a2d35cb6"
EXPECTED_AI = "406c625f43d966e6871d766ca2dd825e7e33c019fadb6e287cafdb7803a524ed"


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


def replace_function(source, name, replacement, filename):
    tree = ast.parse(source, filename)
    nodes = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]
    if len(nodes) != 1:
        raise InstallError("TARGET_INVALID:" + filename + ":" + name)
    node = nodes[0]
    lines = source.splitlines(keepends=True)
    lines[node.lineno - 1:node.end_lineno] = [replacement.rstrip() + "\n\n"]
    candidate = "".join(lines)
    compile(candidate, filename + ".candidate", "exec")
    return candidate


def function_source(source, name, filename):
    tree = ast.parse(source, filename)
    nodes = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]
    if len(nodes) != 1:
        raise InstallError("FUNCTION_COUNT_INVALID:" + filename + ":" + name)
    return ast.get_source_segment(source, nodes[0]) or ""


def validate_contract(cars_source, team_source):
    compile(cars_source, "cars_ui.py.contract", "exec")
    compile(team_source, "team_bot.py.contract", "exec")
    catch = function_source(cars_source, "catch_message", "cars_ui.py")
    undo = function_source(cars_source, "voice_undo", "cars_ui.py")
    plan = function_source(cars_source, "voice_change_plan", "cars_ui.py")
    opened = function_source(cars_source, "open_card", "cars_ui.py")
    listed = function_source(cars_source, "cars_list", "cars_ui.py")
    registered = function_source(cars_source, "register", "cars_ui.py")
    menu = function_source(team_source, "menu_cb", "team_bot.py")

    required = (
        "CRM-VOICE-FILL-001", "hard_deadline = started + 15.0",
        "asyncio.to_thread(ai.transcribe", "voice_change_plan",
        "car_voice_active", "Новая карточка автоматически не создаётся",
        "0 LLM-токенов", "crm_voice_seen", "raise ApplicationHandlerStop",
    )
    if any(value not in catch for value in required):
        raise InstallError("VOICE_CONTRACT_MISSING")
    for forbidden in ("create_card", "run_ai_draft", "ai_draft", "ai.parse_message", "ai.parse_image"):
        if forbidden in catch:
            raise InstallError("VOICE_CREATE_PATH_REMAINS:" + forbidden)
    if "car_vundo:" not in registered or "voice_undo" not in registered:
        raise InstallError("UNDO_HANDLER_MISSING")
    if "db.update_card_field" not in undo or "create_card" in undo:
        raise InstallError("UNDO_CONTRACT_INVALID")
    if "override=False" not in plan or "skipped" not in plan:
        raise InstallError("FILL_ONLY_PLAN_INVALID")
    if 'context.user_data["car_voice_active"] = int(cid)' not in opened:
        raise InstallError("OPEN_CARD_BINDING_MISSING")
    for source in (listed, menu):
        if 'pop("car_voice_active", None)' not in source:
            raise InstallError("STALE_CARD_CLEAR_MISSING")


def build_candidates(old_cars, old_team):
    cars = old_cars
    cars = replace_function(cars, "open_card", patch_payload.OPEN_CARD_SOURCE, "cars_ui.py")
    cars = replace_function(cars, "cars_list", patch_payload.CARS_LIST_SOURCE, "cars_ui.py")
    combined = "\n\n".join((
        patch_payload.VOICE_PLAN_SOURCE.rstrip(),
        patch_payload.VOICE_UNDO_SOURCE.rstrip(),
        patch_payload.CATCH_MESSAGE_SOURCE.rstrip(),
    ))
    cars = replace_function(cars, "catch_message", combined, "cars_ui.py")
    cars = replace_function(cars, "register", patch_payload.REGISTER_SOURCE, "cars_ui.py")
    team = replace_function(old_team, "menu_cb", patch_payload.MENU_CB_SOURCE, "team_bot.py")
    validate_contract(cars, team)
    return cars.encode("utf-8"), team.encode("utf-8")


def site_hashes():
    result = {}
    for root in (BASE / "video", BASE / "site"):
        for name in ("index.html", "katalog.html") + tuple("UA-%04d.html" % n for n in range(1, 11)):
            path = root / name
            if path.exists() and path.is_file() and not path.is_symlink():
                result[str(path)] = sha_file(path)
    return result


def state_digest(value):
    return sha_bytes(json.dumps(value, sort_keys=True).encode("utf-8"))


def readonly_db_check():
    connection = sqlite3.connect("file:/home/Carix/crm.db?mode=ro", uri=True, timeout=5)
    connection.row_factory = sqlite3.Row
    try:
        quick = connection.execute("PRAGMA quick_check").fetchone()
        if not quick or quick[0] != "ok":
            raise InstallError("CRM_QUICK_CHECK_FAILED")
        tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "cars" not in tables:
            raise InstallError("CARS_TABLE_MISSING")
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(cars)").fetchall()
        }
        count = connection.execute("SELECT count(*) FROM cars").fetchone()[0]
        result = {"quick_check": "ok", "cars_count": count}
        if "auto_number" in columns:
            rows = connection.execute(
                "SELECT * FROM cars WHERE auto_number IN ('UA-0009','UA0009')"
            ).fetchall()
            result["ua0009_rows"] = len(rows)
            result["ua0009_state_sha256"] = sha_bytes(
                json.dumps([dict(row) for row in rows], ensure_ascii=False,
                           sort_keys=True, default=str).encode("utf-8")
            )
        return result
    finally:
        connection.close()


def parser_selftest():
    namespace = {}
    exec(compile(patch_payload.VOICE_PLAN_SOURCE, "voice_plan.py", "exec"), namespace)
    plan = namespace["voice_change_plan"]
    allowed = {"drive", "color", "mileage_km", "fuel", "gearbox", "year"}
    empty = {"id": 9, "drive": None, "color": "", "mileage_km": 0}
    cases = (
        ({"drive": "fwd"}, "drive", "fwd"),
        ({"drive": "rwd"}, "drive", "rwd"),
        ({"drive": "4wd"}, "drive", "4wd"),
        ({"color": "black"}, "color", "black"),
        ({"color": "white"}, "color", "white"),
        ({"mileage_km": 198000}, "mileage_km", 198000),
        ({"fuel": "LPG"}, "fuel", "LPG"),
        ({"fuel": "diesel"}, "fuel", "diesel"),
        ({"gearbox": "automatic"}, "gearbox", "automatic"),
        ({"year": "2018"}, "year", "2018"),
    )
    for data, field, expected in cases:
        changes, _ = plan(empty, data, allowed, False)
        if not changes or changes[0][0] != field or changes[0][2] != expected:
            raise InstallError("VOICE_PLAN_SELFTEST_FAILED:" + field)
    filled = {"drive": "4wd"}
    changes, skipped = plan(filled, {"drive": "fwd"}, allowed, False)
    if changes or skipped != ["drive"]:
        raise InstallError("FILL_ONLY_SELFTEST_FAILED")
    changes, _ = plan(filled, {"drive": "fwd"}, allowed, True)
    if changes != [("drive", "4wd", "fwd")]:
        raise InstallError("EXPLICIT_OVERRIDE_SELFTEST_FAILED")

    spec = importlib.util.spec_from_file_location("task062_live_ocr", BASE / "local_ocr.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    parsed = module.fields_from_text("привод передний", allowed)
    if parsed.get("drive") != "fwd":
        raise InstallError("VOICE_DRIVE_PARSER_FAILED")


def run():
    started = utc_now()
    receipt = {
        "task_id": "task_062", "contract_id": "CRM-VOICE-FILL-001",
        "status": "BLOCKED", "mode": "OWNER_APPROVED_INSTALL",
        "started_at_utc": started, "finished_at_utc": started, "errors": [],
        "production_write": False, "crm_db_write": False, "site_write": False,
        "service_restarted": False, "rollback_performed": False,
        "already_applied": False, "voice_deadline_seconds": 15,
        "llm_tokens_per_voice": 0, "stt_calls_max_per_voice": 1,
        "automatic_new_card": False, "fill_empty_only": True,
        "explicit_override_supported": True, "deduplication": True, "undo": True,
        "card_count_unchanged": False, "ua0009_unchanged": False,
        "crm_db_sha256_before": None, "crm_db_sha256_after": None,
        "site_state_sha256_before": None, "site_state_sha256_after": None,
        "readonly_before": None, "readonly_after": None,
        "files": {}, "backup_path": None,
    }
    old_cars = old_team = None
    wrote = False
    before_db = before_site = before_read = None
    try:
        dependencies = {
            BASE / "local_ocr.py": EXPECTED_OCR,
            BASE / "ai_fast_schema.py": EXPECTED_FAST,
            BASE / "ai_filter.py": EXPECTED_FILTER,
            BASE / "ai.py": EXPECTED_AI,
        }
        for path in (CARS, TEAM, DB, *dependencies):
            regular(path)
        for path, expected in dependencies.items():
            if sha_file(path) != expected:
                raise InstallError("DEPENDENCY_DRIFT:" + path.name)
        parser_selftest()
        old_cars = CARS.read_bytes()
        old_team = TEAM.read_bytes()
        before_db = sha_file(DB)
        before_site = site_hashes()
        before_read = readonly_db_check()
        receipt["readonly_before"] = before_read
        receipt["crm_db_sha256_before"] = before_db
        receipt["site_state_sha256_before"] = state_digest(before_site)

        if b"CRM-VOICE-FILL-001" in old_cars:
            validate_contract(old_cars.decode("utf-8"), old_team.decode("utf-8"))
            after_read = readonly_db_check()
            receipt.update(
                status="PASS", already_applied=True,
                readonly_after=after_read,
                crm_db_sha256_after=sha_file(DB),
                site_state_sha256_after=state_digest(site_hashes()),
                card_count_unchanged=after_read["cars_count"] == before_read["cars_count"],
                ua0009_unchanged=(after_read.get("ua0009_state_sha256") ==
                                  before_read.get("ua0009_state_sha256")),
                files={
                    str(CARS): {"before": sha_file(CARS), "after": sha_file(CARS)},
                    str(TEAM): {"before": sha_file(TEAM), "after": sha_file(TEAM)},
                },
            )
            return receipt

        if sha_bytes(old_cars) != EXPECTED_CARS:
            raise InstallError("CARS_SOURCE_DRIFT")
        if sha_bytes(old_team) != EXPECTED_TEAM:
            raise InstallError("TEAM_SOURCE_DRIFT")

        candidate_cars, candidate_team = build_candidates(
            old_cars.decode("utf-8"), old_team.decode("utf-8"))
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = BACKUPS / stamp
        backup.mkdir(parents=True, exist_ok=False)
        shutil.copy2(CARS, backup / "cars_ui.py")
        shutil.copy2(TEAM, backup / "team_bot.py")
        if sha_file(backup / "cars_ui.py") != EXPECTED_CARS:
            raise InstallError("CARS_BACKUP_HASH_MISMATCH")
        if sha_file(backup / "team_bot.py") != EXPECTED_TEAM:
            raise InstallError("TEAM_BACKUP_HASH_MISMATCH")
        receipt["backup_path"] = str(backup)

        atomic_write(CARS, candidate_cars)
        atomic_write(TEAM, candidate_team)
        wrote = True
        validate_contract(CARS.read_text(encoding="utf-8"), TEAM.read_text(encoding="utf-8"))
        if sha_file(DB) != before_db:
            raise InstallError("CRM_DB_CHANGED")
        if site_hashes() != before_site:
            raise InstallError("SITE_CHANGED")
        after_read = readonly_db_check()
        if after_read["cars_count"] != before_read["cars_count"]:
            raise InstallError("CARD_COUNT_CHANGED")
        if after_read.get("ua0009_state_sha256") != before_read.get("ua0009_state_sha256"):
            raise InstallError("UA0009_CHANGED")

        receipt.update(
            status="PASS", production_write=True,
            readonly_after=after_read, card_count_unchanged=True, ua0009_unchanged=True,
            crm_db_sha256_after=sha_file(DB),
            site_state_sha256_after=state_digest(site_hashes()),
            files={
                str(CARS): {"before": EXPECTED_CARS, "after": sha_file(CARS)},
                str(TEAM): {"before": EXPECTED_TEAM, "after": sha_file(TEAM)},
            },
        )
        return receipt
    except Exception as exc:
        receipt["errors"].append(
            str(exc)[:240] if isinstance(exc, InstallError) else "UNEXPECTED_INSTALL_ERROR"
        )
        if wrote and old_cars is not None and old_team is not None:
            try:
                atomic_write(CARS, old_cars)
                atomic_write(TEAM, old_team)
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
    print(json.dumps({"status": receipt["status"],
                      "production_write": receipt["production_write"]}))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

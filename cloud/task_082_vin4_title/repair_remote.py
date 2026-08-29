#!/usr/bin/env python3
"""Atomic production installer for CRM-VIN4-TITLE-001.

This script is uploaded to PythonAnywhere and executed there.  It changes only
``/home/Carix/cars_ui.py``.  The CRM database is opened read-only and is never
written by this task.
"""
from __future__ import annotations

import argparse
import ast
import datetime as dt
import hashlib
import html
import json
import os
import pathlib
import re
import shutil
import sqlite3
import tempfile


CONTRACT = "CRM-VIN4-TITLE-001-V1.0"
ROOT = pathlib.Path("/home/Carix")
SOURCE = ROOT / "cars_ui.py"
DATABASE = ROOT / "crm.db"
REMOTE = ROOT / "autopilot_inbox" / "cloud" / "task_082_vin4_title"
RECEIPTS = REMOTE / "receipts"
BACKUPS = ROOT / "backups" / "task_082_vin4_title"
CURRENT_IDS = {"UA-%04d" % number for number in range(1, 14)}
ALLOWED_VIN = frozenset("ABCDEFGHJKLMNPRSTUVWXYZ0123456789")

OLD_RENDER = '    L.append("<b>%s</b>" % (card.get("auto_number") or "#%s" % card.get("id")))\n'
NEW_RENDER = "    L.append(_ua082_title_html(card))\n"
OLD_LIST_LINE = '        lines.append("<b>%s</b> · %s" % (nomer, name))\n'
NEW_LIST_LINE = "        lines.append(_ua082_title_html(card))\n"
OLD_BUTTON = (
    '        rows.append([InlineKeyboardButton("%s · %s" % (nomer, name[:28]),\n'
    '                                          callback_data="car_open:%d" % card["id"])])\n'
)
NEW_BUTTON = (
    "        rows.append([InlineKeyboardButton(_ua082_title_button(card),\n"
    '                                          callback_data="car_open:%d" % card["id"])])\n'
)

HELPERS = r'''
def _ua082_clean(value):
    return " ".join(str(value or "").split())


def _ua082_vin4(card):
    raw = str((card or {}).get("vin") or "").upper()
    normalized = "".join(ch for ch in raw if ch not in " -\t\r\n")
    allowed = frozenset("ABCDEFGHJKLMNPRSTUVWXYZ0123456789")
    if len(normalized) == 17 and all(ch in allowed for ch in normalized):
        return normalized[-4:]
    return "НЕТ"


def _ua082_title_parts(card):
    card = card or {}
    number = _ua082_clean(card.get("auto_number") or ("#%s" % card.get("id")))
    name = " ".join(
        _ua082_clean(value)
        for value in (card.get("brand"), card.get("model"), card.get("year"))
        if _ua082_clean(value)
    ) or "без названия"
    return number, name, _ua082_vin4(card)


def _ua082_title_plain(card):
    number, name, vin4 = _ua082_title_parts(card)
    return "%s · %s · VIN %s" % (number, name, vin4)


def _ua082_title_html(card):
    import html as _ua082_html
    number, name, vin4 = _ua082_title_parts(card)
    return "%s · %s · VIN <b>%s</b>" % (
        _ua082_html.escape(number, quote=True),
        _ua082_html.escape(name, quote=True),
        _ua082_html.escape(vin4, quote=True),
    )


def _ua082_title_button(card):
    number, name, vin4 = _ua082_title_parts(card)
    suffix = " · VIN " + vin4
    prefix = (number + " · " + name).replace("<", "‹").replace(">", "›")
    limit = 64
    if len(prefix) + len(suffix) > limit:
        room = max(1, limit - len(suffix) - 1)
        prefix = prefix[:room].rstrip() + "…"
    return prefix + suffix


'''


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def atomic_bytes(path: pathlib.Path, payload: bytes, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(dir=path.parent, prefix="." + path.name + ".", delete=False)
    temporary = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_json(path: pathlib.Path, value: dict) -> None:
    atomic_bytes(
        path,
        (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        0o600,
    )


def safe_deployment_id(value: str) -> str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{7,79}", value or ""):
        raise RuntimeError("INVALID_DEPLOYMENT_ID")
    return value


def function_source(source: str, name: str) -> str:
    tree = ast.parse(source, filename=str(SOURCE))
    lines = source.splitlines(keepends=True)
    nodes = [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]
    if len(nodes) != 1:
        raise RuntimeError("FUNCTION_NOT_UNIQUE:" + name)
    node = nodes[0]
    return "".join(lines[node.lineno - 1:node.end_lineno])


def patch_source(source: str) -> tuple[str, bool]:
    installed = "def _ua082_title_html(card):" in source
    if installed:
        required = (NEW_RENDER, NEW_LIST_LINE, NEW_BUTTON)
        if any(source.count(item) != 1 for item in required):
            raise RuntimeError("INSTALLED_CONTRACT_DRIFT")
        if any(item in source for item in (OLD_RENDER, OLD_LIST_LINE, OLD_BUTTON)):
            raise RuntimeError("MIXED_OLD_AND_NEW_RENDERERS")
        compile(source, str(SOURCE), "exec")
        return source, False

    # AST proves the three anchors belong to the intended active functions.
    render = function_source(source, "render")
    listing = function_source(source, "cars_list")
    opened = function_source(source, "open_card")
    if OLD_RENDER not in render:
        raise RuntimeError("RENDER_ANCHOR_DRIFT")
    if OLD_LIST_LINE not in listing or OLD_BUTTON not in listing:
        raise RuntimeError("LIST_ANCHOR_DRIFT")
    if 'render(card, staff), parse_mode="HTML"' not in opened:
        raise RuntimeError("OPEN_CARD_HTML_CONTRACT_DRIFT")
    if source.count("def render(card, staff):\n") != 1:
        raise RuntimeError("RENDER_INSERT_ANCHOR_NOT_UNIQUE")

    candidate = source.replace("def render(card, staff):\n", HELPERS + "def render(card, staff):\n", 1)
    for old, new, label in (
        (OLD_RENDER, NEW_RENDER, "render"),
        (OLD_LIST_LINE, NEW_LIST_LINE, "list_text"),
        (OLD_BUTTON, NEW_BUTTON, "list_button"),
    ):
        if candidate.count(old) != 1:
            raise RuntimeError("PATCH_ANCHOR_NOT_UNIQUE:" + label)
        candidate = candidate.replace(old, new, 1)
    compile(candidate, str(SOURCE), "exec")
    again, changed = patch_source(candidate)
    if changed or again != candidate:
        raise RuntimeError("PATCH_NOT_IDEMPOTENT")
    return candidate, True


def helper_namespace(source: str) -> dict:
    tree = ast.parse(source, filename=str(SOURCE))
    wanted = {
        "_ua082_clean", "_ua082_vin4", "_ua082_title_parts",
        "_ua082_title_plain", "_ua082_title_html", "_ua082_title_button",
    }
    nodes = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in wanted
    ]
    if {node.name for node in nodes} != wanted:
        raise RuntimeError("HELPER_SET_INCOMPLETE")
    namespace: dict = {}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "vin4_helpers", "exec"), namespace)
    return namespace


def run_candidate_tests(source: str) -> dict:
    ns = helper_namespace(source)
    title_html = ns["_ua082_title_html"]
    title_plain = ns["_ua082_title_plain"]
    title_button = ns["_ua082_title_button"]
    vin4 = ns["_ua082_vin4"]
    fixture = {
        "id": 9999, "auto_number": "UA-9999", "brand": "Test & Co",
        "model": "Future <Car>", "year": 2030,
        "vin": "a b-c d e f g h j k l m n 1 2 3 4",
    }
    checks = {
        "future_vin4": vin4(fixture) == "1234",
        "future_plain_once": title_plain(fixture).count("VIN 1234") == 1,
        "future_html_bold_once": title_html(fixture).count("VIN <b>1234</b>") == 1,
        "future_html_escaped": "Test &amp; Co" in title_html(fixture) and "&lt;Car&gt;" in title_html(fixture),
        "future_button_no_markup": "<" not in title_button(fixture) and ">" not in title_button(fixture),
        "future_button_limit": len(title_button(fixture)) <= 64,
        "suffix_letters": vin4({"vin": "KMHAA81D1RU12ABCD"}) == "ABCD",
        "invalid_missing": vin4({"vin": ""}) == "НЕТ" and vin4({"vin": "INVALID"}) == "НЕТ",
        "vin_exclusions": vin4({"vin": "12345678901234IOQ"}) == "НЕТ",
        "render_hook_once": source.count(NEW_RENDER) == 1,
        "list_hook_once": source.count(NEW_LIST_LINE) == 1,
        "button_hook_once": source.count(NEW_BUTTON) == 1,
        "callback_preserved": 'callback_data="car_open:%d" % card["id"]' in function_source(source, "cars_list"),
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    if failed:
        raise RuntimeError("CANDIDATE_TESTS_FAILED:" + ",".join(failed))
    return checks


def normalize_vin(value) -> str:
    return "".join(ch for ch in str(value or "").upper() if ch not in " -\t\r\n")


def database_audit() -> dict:
    uri = "file:%s?mode=ro" % DATABASE.as_posix()
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    quick = connection.execute("PRAGMA quick_check").fetchone()[0]
    rows = [dict(row) for row in connection.execute(
        "SELECT id,auto_number,brand,model,year,vin FROM cars ORDER BY id"
    )]
    connection.close()
    examples = []
    current = set()
    valid_current = set()
    for row in rows:
        number = row.get("auto_number") or ("#%s" % row.get("id"))
        vin = normalize_vin(row.get("vin"))
        valid = len(vin) == 17 and all(ch in ALLOWED_VIN for ch in vin)
        if number in CURRENT_IDS:
            current.add(number)
            if valid:
                valid_current.add(number)
        examples.append({
            "id": number,
            "vin4": vin[-4:] if valid else "НЕТ",
            "vin_valid": valid,
        })
    missing = sorted(CURRENT_IDS - current)
    if quick != "ok":
        raise RuntimeError("DB_QUICK_CHECK_FAILED")
    if missing:
        raise RuntimeError("CURRENT_CARDS_MISSING:" + ",".join(missing))
    if valid_current != CURRENT_IDS:
        raise RuntimeError("CURRENT_VIN_INVALID:" + ",".join(sorted(CURRENT_IDS - valid_current)))
    return {
        "sha256": digest(DATABASE.read_bytes()),
        "quick_check": quick,
        "card_count": len(rows),
        "current_count": len(current),
        "valid_current_count": len(valid_current),
        "examples": examples,
    }


def paths(deployment_id: str) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path]:
    backup_root = BACKUPS / deployment_id
    receipt = RECEIPTS / (deployment_id + ".json")
    rollback_receipt = RECEIPTS / (deployment_id + ".rollback.json")
    return backup_root, receipt, rollback_receipt


def deploy(deployment_id: str) -> int:
    backup_root, receipt_path, _ = paths(deployment_id)
    value = {
        "contract": CONTRACT,
        "deployment_id": deployment_id,
        "generated_at_utc": utc_now(),
        "status": "FAIL",
        "production_touched": False,
        "changed_files": [],
        "db_write": False,
        "media_write": False,
        "site_write": False,
        "llm_tokens": 0,
        "rollback": False,
        "errors": [],
    }
    source_before = b""
    try:
        source_before = SOURCE.read_bytes()
        source_text = source_before.decode("utf-8")
        compile(source_text, str(SOURCE), "exec")
        db_before = database_audit()
        candidate_text, changed = patch_source(source_text)
        tests = run_candidate_tests(candidate_text)
        candidate = candidate_text.encode("utf-8")
        source_mode = SOURCE.stat().st_mode & 0o777

        backup_root.mkdir(parents=True, exist_ok=True)
        backup_source = backup_root / "cars_ui.py"
        if backup_source.exists() and backup_source.read_bytes() != source_before:
            raise RuntimeError("BACKUP_PREIMAGE_CONFLICT")
        if not backup_source.exists():
            shutil.copy2(SOURCE, backup_source)
        manifest = {
            "contract": CONTRACT,
            "deployment_id": deployment_id,
            "source_before_sha256": digest(source_before),
            "source_candidate_sha256": digest(candidate),
            "database_sha256": db_before["sha256"],
            "created_at_utc": utc_now(),
        }
        atomic_json(backup_root / "manifest.json", manifest)

        if changed:
            atomic_bytes(SOURCE, candidate, source_mode)
            value["production_touched"] = True
            value["changed_files"] = ["cars_ui.py"]
        installed = SOURCE.read_bytes()
        if installed != candidate:
            raise RuntimeError("ATOMIC_INSTALL_READBACK_MISMATCH")
        compile(installed.decode("utf-8"), str(SOURCE), "exec")
        db_after = database_audit()
        if db_after["sha256"] != db_before["sha256"]:
            raise RuntimeError("DATABASE_CHANGED")
        value.update({
            "status": "PASS_DEPLOYED" if changed else "PASS_ALREADY_INSTALLED",
            "source_before_sha256": digest(source_before),
            "source_after_sha256": digest(installed),
            "backup_path": str(backup_source),
            "database_before": db_before,
            "database_after": db_after,
            "tests": tests,
        })
    except Exception as exc:
        value["errors"].append(type(exc).__name__ + ":" + str(exc))
        if value["production_touched"] and source_before:
            try:
                atomic_bytes(SOURCE, source_before, SOURCE.stat().st_mode & 0o777)
                value["rollback"] = SOURCE.read_bytes() == source_before
                value["production_touched"] = False
            except Exception as rollback_exc:
                value["errors"].append("ROLLBACK_" + type(rollback_exc).__name__ + ":" + str(rollback_exc))
    atomic_json(receipt_path, value)
    print(value["status"])
    return 0 if value["status"].startswith("PASS_") else 1


def rollback(deployment_id: str) -> int:
    backup_root, _, receipt_path = paths(deployment_id)
    value = {
        "contract": CONTRACT,
        "deployment_id": deployment_id,
        "generated_at_utc": utc_now(),
        "status": "FAIL",
        "errors": [],
    }
    try:
        manifest = json.loads((backup_root / "manifest.json").read_text(encoding="utf-8"))
        backup = (backup_root / "cars_ui.py").read_bytes()
        if digest(backup) != manifest.get("source_before_sha256"):
            raise RuntimeError("ROLLBACK_BACKUP_SHA_MISMATCH")
        mode = SOURCE.stat().st_mode & 0o777
        atomic_bytes(SOURCE, backup, mode)
        if SOURCE.read_bytes() != backup:
            raise RuntimeError("ROLLBACK_READBACK_MISMATCH")
        compile(backup.decode("utf-8"), str(SOURCE), "exec")
        value.update({"status": "PASS", "source_sha256": digest(backup)})
    except Exception as exc:
        value["errors"].append(type(exc).__name__ + ":" + str(exc))
    atomic_json(receipt_path, value)
    print("ROLLBACK_" + value["status"])
    return 0 if value["status"] == "PASS" else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--deploy")
    group.add_argument("--rollback")
    args = parser.parse_args()
    if args.deploy:
        return deploy(safe_deployment_id(args.deploy))
    return rollback(safe_deployment_id(args.rollback))


if __name__ == "__main__":
    raise SystemExit(main())

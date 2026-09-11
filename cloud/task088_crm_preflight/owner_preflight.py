#!/usr/bin/env python3
"""Owner-console TASK088 discovery; never imports live code or mutates CRM.

Run using python3.10 -B beside the hash-pinned ui_patch.py/capacity_probe.py.
The single stdout JSON contains no source bytes, credentials or vehicle values.
Its candidate proof is static; it does not claim working bot or price acceptance.
"""
from __future__ import annotations

import argparse
import ast
import datetime as dt
import decimal
import hashlib
import json
import math
import os
import pathlib
import re
import sqlite3
import stat
import subprocess
import time

import capacity_probe
import ui_patch

ROOT = pathlib.Path("/home/Carix")
TASK_ID = "TASK088-GE-PRICE-CRM-PREFLIGHT"
SOURCES = ("cars_ui.py", "cars_schema.py", "db.py", "start_safe.py")
PROTECTED_NAMES = ("site", "video", "publish.py", "publisher.py", "crm_publisher.py", "cars_schema.py", "db.py", "start_safe.py")
SELECTED = frozenset(("apply_value", "catch_message", "auto_catch", "edit_menu", "register", "db", "connect", "ensure_schema", "_ensure_columns"))
LABELS = frozenset(("Цена Украины", "Цена Грузии", "Цена продажи", "цена", "цена Украины", "цена Грузии"))
MAX_SOURCE_BYTES = 16 * 1024 * 1024


class ProbeError(RuntimeError):
    pass


def now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha(value):
    return hashlib.sha256(value).hexdigest()


def read_regular(path, limit=MAX_SOURCE_BYTES):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or path.is_symlink() or info.st_size > limit:
        raise ProbeError("UNSAFE_OR_LARGE_FILE")
    with path.open("rb") as handle:
        value = handle.read(limit + 1)
    if len(value) > limit:
        raise ProbeError("FILE_SIZE")
    return value


def safe_name(value):
    return value if isinstance(value, str) and re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]{0,79}", value) else "<omitted>"


def call_name(node):
    if isinstance(node, ast.Name):
        return safe_name(node.id)
    if isinstance(node, ast.Attribute):
        return call_name(node.value) + "." + safe_name(node.attr)
    return type(node).__name__


def expression_shape(node):
    """Call/registration structure without arbitrary string or numeric constants."""
    if isinstance(node, ast.Call):
        return {"call": call_name(node.func), "args": [expression_shape(arg) for arg in node.args],
                "keywords": {safe_name(item.arg): ({"group": item.value.value} if item.arg == "group" and isinstance(item.value, ast.Constant) and type(item.value.value) is int and abs(item.value.value) < 1000 else expression_shape(item.value)) for item in node.keywords}}
    if isinstance(node, (ast.Name, ast.Attribute)):
        return {"symbol": call_name(node)}
    if isinstance(node, ast.Constant):
        if isinstance(node.value, str) and node.value in {"price_uah", "price_georgia", "car_wait", "car_setf:", "Только число, в долларах."}:
            return {"literal": node.value}
        return {"constant_type": type(node.value).__name__}
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return {type(node).__name__: [expression_shape(item) for item in node.elts]}
    return {"node": type(node).__name__}


def source_shape(payload, filename):
    source = payload.decode("utf-8")
    tree = ast.parse(source, filename)
    functions = []
    selected = {}
    imports = []
    constants = {}
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imports.append({"module": ".".join(safe_name(part) for part in (getattr(node, "module", "") or "").split(".")),
                            "names": [{"name": ".".join(safe_name(part) for part in item.name.split(".")), "alias": safe_name(item.asname) if item.asname else None} for item in node.names]})
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(safe_name(node.name))
            price_prompt = any(isinstance(item, ast.Constant) and item.value == "Только число, в долларах." for item in ast.walk(node))
            if node.name in SELECTED or price_prompt:
                calls = [item for item in ast.walk(node) if isinstance(item, ast.Call)]
                details = {"sha256": sha(ast.get_source_segment(source, node).encode()),
                    "async": isinstance(node, ast.AsyncFunctionDef), "arguments": [safe_name(arg.arg) for arg in node.args.args],
                    "calls": sorted({call_name(item.func) for item in calls}),
                    "registration_calls": [expression_shape(item) for item in calls if call_name(item.func).endswith(("add_handler", "CallbackQueryHandler", "MessageHandler"))],
                    "references_ukraine_price": any(isinstance(item, ast.Constant) and item.value == "price_uah" for item in ast.walk(node)),
                    "references_georgia_price": any(isinstance(item, ast.Constant) and item.value == "price_georgia" for item in ast.walk(node)),
                    "price_prompt": price_prompt}
                selected.setdefault(safe_name(node.name), []).append(details)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in {"EDITABLE", "MONEY", "NUMERIC", "LABELS_ALL"}:
                    try:
                        value = ast.literal_eval(node.value)
                    except (ValueError, TypeError, SyntaxError):
                        constants[target.id] = {"literal": False}
                        continue
                    if target.id == "EDITABLE" and isinstance(value, (list, tuple)):
                        constants[target.id] = [{"field": safe_name(item[0]), "price_label": item[1] if item[1] in LABELS else None} for item in value if isinstance(item, (list, tuple)) and len(item) == 2]
                    elif target.id == "LABELS_ALL" and isinstance(value, dict):
                        constants[target.id] = {key: value[key] if value[key] in LABELS else None for key in ("price_uah", "price_georgia") if key in value}
                    elif isinstance(value, (set, list, tuple)):
                        constants[target.id] = sorted(safe_name(item) for item in value)
    return {"sha256": sha(payload), "bytes": len(payload), "imports": imports, "functions": functions,
            "selected_functions": selected, "field_constants": constants,
            "top_level_nodes": [type(node).__name__ for node in tree.body],
            "top_level_calls": [expression_shape(node.value) for node in tree.body if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)],
            "raw_source_exported": False, "live_module_import_effects": "NOT_VERIFIED"}


def database_probe(root):
    path = root / "crm.db"
    if path.is_symlink() or not path.is_file():
        raise ProbeError("DATABASE_NOT_REGULAR")
    with path.open("rb") as handle:
        header = handle.read(100)
    if header[:16] != b"SQLite format 3\0":
        raise ProbeError("DATABASE_HEADER")
    if (header[18] == 2 or header[19] == 2) and not (root / "crm.db-shm").is_file():
        raise ProbeError("WAL_SHM_REQUIRED_FOR_READ_ONLY_DISCOVERY")
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=3)
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        columns = [{"name": safe_name(row[1]), "type": safe_name(row[2]), "nullable": not bool(row[3]), "primary_key": bool(row[5])}
                   for row in connection.execute("PRAGMA table_info(cars)")]
        names = {item["name"] for item in columns}
        ids = []
        if {"id", "published"}.issubset(names):
            ids = [row[0] for row in connection.execute("SELECT id FROM cars WHERE published = 0 AND typeof(id) = 'integer' ORDER BY id LIMIT 16")]
        objects = [{"type": safe_name(row[0]), "name": safe_name(row[1]), "table": safe_name(row[2]), "definition_sha256": sha((row[3] or "").encode())}
                   for row in connection.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name")]
        connection.rollback()
    finally:
        connection.close()
    return {"status": "PASS", "measurement": "LIVE_SQLITE_READ_ONLY_TRANSACTION_WAL_AWARE", "columns": columns,
            "schema_objects": objects, "unpublished_candidate_ids": ids, "selected_test_car_id": None,
            "db_writes": 0, "sqlite_read_coordination": "EXISTING_SHM_READMARKS_MAY_CHANGE", "vehicle_values_exported": False, "price_commit_acceptance": "NOT_PERFORMED"}


def owner_quota_capacity(root, account_quota_gib):
    limit = decimal.Decimal(str(account_quota_gib))
    if not limit.is_finite() or limit <= 0 or limit > 1000000:
        raise ProbeError("OWNER_QUOTA_INVALID")
    total = int(limit * 1024 ** 3)
    paths = ("/tmp", str(root), "/var/www")
    command = ["du", "-s", "-B", "1", "--", *paths]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=45, check=False)
    if completed.returncode != 0:
        raise ProbeError("OWNER_QUOTA_USAGE_READ_FAILED")
    sizes = {}
    for line in completed.stdout.splitlines():
        parts = line.split(None, 1)
        if len(parts) != 2 or parts[1] not in paths or not parts[0].isdigit() or parts[1] in sizes:
            raise ProbeError("OWNER_QUOTA_USAGE_FORMAT")
        sizes[parts[1]] = int(parts[0])
    if set(sizes) != set(paths):
        raise ProbeError("OWNER_QUOTA_USAGE_INCOMPLETE")
    used = sum(sizes.values())
    if used > total:
        raise ProbeError("OWNER_QUOTA_EXCEEDED")
    return {"total_bytes": total, "used_bytes": used, "free_bytes": total - used,
            "owner_supplied_current_dashboard_quota_gib": str(limit),
            "usage_scope": ["/tmp", "/home/Carix", "/var/www"],
            "measurement": "OWNER_CURRENT_FILES_DASHBOARD_QUOTA_AND_FRESH_TARGET_DU"}


def storage_probe(root, quota_module=capacity_probe, account_quota_gib=None):
    quota_module.TARGET = str(root)
    mount = quota_module.target_mount()
    quota = quota_module.nfs_rquota_probe(mount)
    base = {"target_environment": "production", "task_id": TASK_ID, "read_only": True,
            "measured_at": now(), "measurement": "NFS_RQUOTA_V1_ACCOUNT_HARD_QUOTA"}
    if quota.get("status") == "PASS" and quota.get("active") is True and type(quota.get("block_hard_limit")) is int and quota["block_hard_limit"] > 0:
        total, used, free = (quota.get(key) for key in ("total_bytes", "used_bytes", "free_bytes"))
        if all(type(value) is int for value in (total, used, free)) and total > 0 and 0 <= used <= total and free == total - used:
            return {**base, "status": "PASS", "gate_eligible": True, "total_bytes": total, "used_bytes": used, "free_bytes": free}
    if account_quota_gib is not None:
        measured = owner_quota_capacity(root, account_quota_gib)
        return {**base, **measured, "measured_at": now(), "status": "PASS", "gate_eligible": True}
    volume = os.statvfs(root)
    return {**base, "status": "NOT_VERIFIED", "gate_eligible": False, "quota_status": "UNAVAILABLE_OR_INVALID",
            "owner_current_dashboard_quota_required": True,
            "diagnostic_global_volume_only": {"total_bytes": volume.f_blocks * volume.f_frsize,
                                               "free_bytes": volume.f_bavail * volume.f_frsize}}


def protected_probe(root):
    result = {}
    started = time.monotonic()
    hashed_bytes = 0
    entries_seen = 0

    def check_budget():
        if entries_seen > 20000 or hashed_bytes > 128 * 1024 * 1024 or time.monotonic() - started > 20:
            raise ProbeError("PROTECTED_HASH_BUDGET")

    for name in PROTECTED_NAMES:
        path = root / name
        digest = hashlib.sha256()
        files = 0
        try:
            check_budget()
            if not path.exists():
                continue
            pending = [path]
            while pending:
                check_budget()
                item = pending.pop()
                info = item.lstat()
                if stat.S_ISLNK(info.st_mode):
                    raise ProbeError("PROTECTED_SYMLINK")
                if stat.S_ISDIR(info.st_mode):
                    # Bound enumeration itself; never materialize an entire rglob.
                    children = []
                    with os.scandir(item) as directory:
                        for entry in directory:
                            entries_seen += 1
                            check_budget()
                            children.append(item / entry.name)
                    pending.extend(sorted(children, reverse=True))
                elif stat.S_ISREG(info.st_mode):
                    files += 1
                    file_hash = hashlib.sha256()
                    with item.open("rb") as handle:
                        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                            hashed_bytes += len(chunk)
                            check_budget()
                            file_hash.update(chunk)
                    digest.update(str(item.relative_to(root)).encode() + b"\0" + file_hash.digest())
                else:
                    raise ProbeError("PROTECTED_SPECIAL_FILE")
            result[name] = {"status": "PASS", "path": str(path), "files": files, "tree_sha256": digest.hexdigest()}
        except Exception as exc:
            result[name] = {"status": "NOT_VERIFIED", "path": str(path), "files_observed": files,
                            "complete": False, "error_type": type(exc).__name__}
            if isinstance(exc, ProbeError) and str(exc) in {"PROTECTED_HASH_BUDGET", "PROTECTED_SYMLINK", "PROTECTED_SPECIAL_FILE"}:
                result[name]["diagnostic_code"] = str(exc)
    return result


def guard_probe(root):
    path = root / ".crm_guard_status.json"
    if not path.exists():
        return {"status": "ABSENT"}
    value = json.loads(read_regular(path, 1024 * 1024))
    heartbeats = value.get("heartbeat_age_seconds", {})
    safe_heartbeats = {name: stamp for name, stamp in heartbeats.items() if name in {"crm_bot", "client_bot", "guard"} and type(stamp) in (int, float) and math.isfinite(stamp) and stamp >= 0} if isinstance(heartbeats, dict) else {}
    pid = value.get("pid")
    return {"status": "OBSERVED_ONLY", "file_age_seconds": max(0, round(time.time() - path.stat().st_mtime, 3)),
            "pid": pid if type(pid) is int and pid > 0 else None, "heartbeat_age_seconds": safe_heartbeats,
            "keys": sorted(safe_name(key) for key in value), "bot_runtime_acceptance": "NOT_PERFORMED"}


def collect(root=ROOT, account_quota_gib=None):
    root = pathlib.Path(root).absolute()
    result = {"task_id": TASK_ID, "observed_at": now(), "read_only": True, "site_changes": 0, "db_writes": 0,
              "bot_restarts": 0, "live_modules_imported": False, "crm_prices_acceptance": "NOT_PERFORMED"}
    payloads = {}
    result["sources"] = {}
    for name in SOURCES:
        try:
            payload = read_regular(root / name)
            payloads[name] = payload
            result["sources"][name] = source_shape(payload, name)
        except Exception as exc:
            result["sources"][name] = {"status": "NOT_VERIFIED", "error_type": type(exc).__name__}
    try:
        original = payloads["cars_ui.py"]
        candidate, metadata = ui_patch.patch_text(original.decode("utf-8"))
        result["candidate"] = {"status": "PASS_STATIC_ONLY", "source_before_sha256": sha(original),
                               "source_after_sha256": sha(candidate.encode()), "live_bot_verified": False,
                               "ui_acceptance": "NOT_PERFORMED"}
    except Exception as exc:
        code = "UNCLASSIFIED"
        anchor = None
        if isinstance(exc, ui_patch.PatchRefused):
            parts = str(exc).split(":", 1)
            first = parts[0]
            if first in {"ALREADY_OR_PARTIALLY_PATCHED_REQUIRES_FRESH_REVIEW", "APPLY_SIGNATURE_DRIFT", "CATCH_INPUT_ANCHOR", "UA_LABEL_DRIFT", "EDITABLE_LABEL_DRIFT", "SET_DRIFT", "EDIT_MENU_CALLBACK_CONVENTION", "EDIT_MENU_MARKUP_SIGNATURE", "ANCHOR_COUNT", "PARTIAL_CANDIDATE", "PARTIAL_UI_PATCH"}:
                code = first
            elif re.fullmatch(r"(?:FUNCTION|ASSIGNMENT)_COUNT", first):
                code = first
            elif re.fullmatch(r"ANCHOR_COUNT_[0-9]{1,4}", first):
                code = first
            if len(parts) == 2 and parts[1] in {"apply_value", "auto_catch", "catch_message", "edit_menu", "catch_message_not_wait", "LABELS_ALL", "UA_LABEL_KEY", "EDITABLE", "EDITABLE_UA", "MONEY", "NUMERIC", "PRICE_PROMPT", "PRICE_PROMPT_COMPARE", "EDIT_MENU_MARKUP", "input_text =", "thinking =", 'wait = context.user_data.get("car_wait")'}:
                anchor = parts[1]
        result["candidate"] = {"status": "NOT_VERIFIED", "error_type": type(exc).__name__, "diagnostic_code": code, "diagnostic_anchor": anchor, "live_bot_verified": False}
    for key, probe in (("database", database_probe), ("storage", lambda target: storage_probe(target, account_quota_gib=account_quota_gib)), ("protected", protected_probe), ("guard", guard_probe)):
        try:
            result[key] = probe(root)
        except Exception as exc:
            result[key] = {"status": "NOT_VERIFIED", "error_type": type(exc).__name__}
    result["source_consistency"] = "PASS" if len(payloads) == len(SOURCES) and all("sha256" in item for item in result["sources"].values()) else "PARTIAL"
    for name, payload in payloads.items():
        try:
            if sha(read_regular(root / name)) != sha(payload):
                result["source_consistency"] = "DRIFT"
        except Exception:
            result["source_consistency"] = "NOT_VERIFIED"
    result["finished_at"] = now()
    return result


def quota_input_gib(value):
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(GB|GiB)\s*", value)
    if not match:
        raise ProbeError("QUOTA_UNIT_REQUIRED_GB_OR_GiB")
    amount = decimal.Decimal(match.group(1))
    scale = 1000 ** 3 if match.group(2) == "GB" else 1024 ** 3
    return str(amount * scale / decimal.Decimal(1024 ** 3))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    quota_args = parser.add_mutually_exclusive_group()
    quota_args.add_argument("--account-quota-gib", help="Current quota in exact GiB (1024^3 bytes); never reuse historical quota.")
    quota_args.add_argument("--account-quota", help="Current displayed quota with explicit GB or GiB unit.")
    args = parser.parse_args(argv)
    quota = args.account_quota_gib
    if args.account_quota is not None:
        try:
            quota = quota_input_gib(args.account_quota)
        except ProbeError:
            parser.error("Quota must include GB or GiB, for example: 35 GB")
    result = collect(account_quota_gib=quota)
    if args.account_quota is not None:
        result["owner_current_dashboard_quota_input"] = args.account_quota.strip()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

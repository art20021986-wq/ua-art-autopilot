#!/usr/bin/env python3
"""Fail-closed recovery for an exact TASK099 partial install."""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import pathlib
import re
import subprocess
import sys
from typing import Any


TASK = pathlib.Path("/home/Carix/autopilot_inbox/cloud/task_099_site_crm_repair")
ROOT = pathlib.Path("/home/Carix")
IDS = tuple("UA-%04d" % number for number in range(1, 17))
CONTRACT = "UA-ART-16-SITE-CRM-COMPLETION-099-V1"

sys.path.insert(0, str(TASK))
import task099_remote as base


class Blocked(RuntimeError):
    pass


@contextlib.contextmanager
def task_lock_nonblocking():
    TASK.mkdir(parents=True, exist_ok=True)
    with (TASK / "task099.lock").open("a+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise Blocked("TASK099_LOCK_BUSY") from exc
        yield


def backup_inventory() -> list[dict[str, Any]]:
    root = (TASK / "backups").resolve()
    result = []
    if not root.is_dir():
        return result
    for child in sorted(root.iterdir()):
        resolved = child.resolve()
        if not child.is_dir() or resolved.parent != root or not re.fullmatch(r"\d{8}T\d{6}Z", child.name):
            continue
        total = 0
        files = 0
        for path in child.rglob("*"):
            if path.is_file():
                files += 1
                total += path.stat().st_size
        result.append({
            "name": child.name, "path": str(resolved), "manifest": (child / "manifest.json").is_file(),
            "bytes": total, "files": files,
        })
    return result


def database_state() -> dict[str, Any]:
    cars_sha, count, identifiers = base.cars_hash(base.DB)
    with base.connect(base.DB, True) as conn:
        counts = {}
        for name in base.TABLES:
            counts[name] = int(conn.execute('SELECT COUNT(*) FROM "' + name + '"').fetchone()[0]) if base.table_exists(conn, name) else 0
        by_uid = {}
        manual = 0
        prices = 0
        ids = []
        if base.table_exists(conn, "additional_specification"):
            rows = conn.execute(
                """
                SELECT a.id,a.car_uid,a.field_key,a.field_value,a.is_price_field,
                       COALESCE(m.is_manual,0) AS is_manual
                  FROM additional_specification a
                  LEFT JOIN additional_specification_meta m
                    ON m.car_uid=a.car_uid AND m.field_key=a.field_key
                 ORDER BY a.id
                """
            ).fetchall()
            for row in rows:
                ids.append(int(row["id"]))
                uid = str(row["car_uid"])
                by_uid[uid] = by_uid.get(uid, 0) + 1
                manual += int(row["is_manual"] or 0)
                prices += int(row["is_price_field"] or 0)
                if base.PRICE_RE.search(str(row["field_key"])) or base.PRICE_RE.search(str(row["field_value"])):
                    prices += 1
        run = None
        if base.table_exists(conn, "additional_specification_import_runs"):
            row = conn.execute(
                "SELECT * FROM additional_specification_import_runs WHERE run_id LIKE 'production-%' ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
            run = dict(row) if row else None
    return {
        "cars_sha256": cars_sha, "cars_count": count, "cars_ids": identifiers,
        "table_counts": counts, "additional_by_uid": by_uid, "additional_ids": ids,
        "manual_rows": manual, "price_violations": prices, "latest_production_run": run,
        "quick_check": base.quick_check(base.DB),
    }


def public_state() -> dict[str, Any]:
    result = {}
    for uid in IDS:
        path = ROOT / "video" / (uid + ".html")
        source = path.read_text(encoding="utf-8") if path.is_file() else ""
        result[uid] = {
            "sha256": base.sha_bytes(source.encode()),
            "additional_blocks": source.count("<!--UA099_ADD_SPEC_START-->"),
            "clean_vin_blocks": source.count("<!--UA099_CLEAN_VIN_START-->"),
            "carhistory": bool(re.search(r"carhistory\.kr|Проверить VIN", source, re.I)),
        }
    return result


def probe() -> dict[str, Any]:
    expected = base.read_json(TASK / "expected_live.json")
    shadow = base.read_json(TASK / "shadow_receipt.json")
    current = {name: base.sha_file(path) for name, path in base.CODE.items()}
    disk = os.statvfs(str(ROOT))
    return {
        "contract_id": CONTRACT, "status": "PASS", "mode": "PROBE", "lock_free": True,
        "expected_live": expected, "shadow": shadow, "source_sha256": current,
        "helper_sha256": base.sha_file(base.HELPER), "database": database_state(),
        "public": public_state(), "backups": backup_inventory(),
        "disk": {"free_bytes": disk.f_bavail * disk.f_frsize, "total_bytes": disk.f_blocks * disk.f_frsize},
        "finished_at_utc": base.utc_now(),
    }


def select_backup(expected: dict[str, Any], cars_sha256: str, inventory: list[dict[str, Any]]) -> pathlib.Path:
    expected_sha = expected.get("source_sha256") or {}
    for item in reversed(inventory):
        if not item.get("manifest"):
            continue
        path = pathlib.Path(str(item["path"])).resolve()
        manifest = base.read_json(path / "manifest.json")
        records = manifest.get("files") or {}
        valid = True
        for name in base.CODE:
            record = records.get(name) or {}
            if record.get("sha256") != expected_sha.get(name):
                valid = False
        scope = manifest.get("crm_scope_backup") or {}
        if scope.get("cars_sha256") != cars_sha256:
            valid = False
        if valid:
            return path
    raise Blocked("EXACT_PREINSTALL_BACKUP_NOT_FOUND")


def require_exact_partial(state: dict[str, Any]) -> tuple[pathlib.Path, dict[str, Any]]:
    expected = state.get("expected_live") or {}
    shadow = state.get("shadow") or {}
    shadow_gate = shadow.get("gate") or {}
    database = state.get("database") or {}
    if expected.get("contract_id") != CONTRACT or expected.get("status") != "PASS":
        raise Blocked("EXPECTED_LIVE_INVALID")
    if shadow.get("contract_id") != CONTRACT or shadow.get("status") != "PASS":
        raise Blocked("SHADOW_INVALID")
    patched = shadow.get("patched") or {}
    for name in base.CODE:
        if state.get("source_sha256", {}).get(name) != (patched.get(name) or {}).get("after"):
            raise Blocked("PARTIAL_SOURCE_MISMATCH:" + name)
    if database.get("quick_check") != "ok" or database.get("cars_count") != 16 or database.get("cars_ids") != list(IDS):
        raise Blocked("PARTIAL_CARS_REGISTRY")
    if database.get("cars_sha256") != shadow_gate.get("cars_sha256"):
        raise Blocked("PARTIAL_PRIMARY_HASH")
    counts = database.get("table_counts") or {}
    if counts.get("additional_specification") != 18 or counts.get("additional_specification_meta") != 18:
        raise Blocked("PARTIAL_ADDITIONAL_COUNTS")
    if database.get("additional_by_uid") != {"UA-0015": 18}:
        raise Blocked("PARTIAL_ADDITIONAL_SCOPE")
    if database.get("manual_rows") != 0 or database.get("price_violations") != 0:
        raise Blocked("PARTIAL_MANUAL_OR_PRICE")
    run = database.get("latest_production_run") or {}
    if run.get("status") != "PASS" or int(run.get("inserted_count") or 0) != 18:
        raise Blocked("PARTIAL_IMPORT_RUN")
    backup = select_backup(expected, database["cars_sha256"], state.get("backups") or [])
    return backup, run


def isolated_publish(uid: str, timeout: int = 150) -> dict[str, Any]:
    script = (
        "import json,publikaciya;"
        "r=publikaciya.opublikovat(%r,proba=False);"
        "print('__UA099_RESULT__'+json.dumps({'ok':r[0] is True,'detail':str(r[1])[:600]},ensure_ascii=False))"
    ) % uid
    try:
        result = subprocess.run(
            ["python3.10", "-c", script], cwd=str(ROOT), capture_output=True,
            text=True, timeout=timeout, env=dict(os.environ),
        )
    except subprocess.TimeoutExpired as exc:
        raise Blocked("PUBLISH_TIMEOUT:" + uid) from exc
    marker = next((line[len("__UA099_RESULT__"):]
                   for line in reversed(result.stdout.splitlines()) if line.startswith("__UA099_RESULT__")), None)
    if result.returncode != 0 or not marker:
        raise Blocked("PUBLISH_PROCESS_FAIL:%s:%s" % (uid, (result.stderr or result.stdout)[-500:]))
    value = json.loads(marker)
    if value.get("ok") is not True:
        raise Blocked("PUBLISH_FAIL:%s:%s" % (uid, value.get("detail")))
    return {"uid": uid, **value}


def isolated_catalog(timeout: int = 180) -> dict[str, Any]:
    script = (
        "import json,publikaciya;"
        "r=publikaciya.obnovit_katalog();"
        "print('__UA099_RESULT__'+json.dumps({'ok':r[0] is True,'detail':str(r[1])[:600]},ensure_ascii=False))"
    )
    try:
        result = subprocess.run(["python3.10", "-c", script], cwd=str(ROOT), capture_output=True,
                                text=True, timeout=timeout, env=dict(os.environ))
    except subprocess.TimeoutExpired as exc:
        raise Blocked("CATALOG_TIMEOUT") from exc
    marker = next((line[len("__UA099_RESULT__"):]
                   for line in reversed(result.stdout.splitlines()) if line.startswith("__UA099_RESULT__")), None)
    if result.returncode != 0 or not marker:
        raise Blocked("CATALOG_PROCESS_FAIL:" + (result.stderr or result.stdout)[-500:])
    value = json.loads(marker)
    if value.get("ok") is not True:
        raise Blocked("CATALOG_FAIL:" + str(value.get("detail")))
    return value


def resume() -> dict[str, Any]:
    state = probe()
    backup, run = require_exact_partial(state)
    database = state["database"]
    migration = {
        "run_id": run["run_id"], "inserted_count": 18,
        "inserted_ids": database["additional_ids"],
        "per_uid": {uid: (18 if uid == "UA-0015" else 0) for uid in IDS},
        "cars_sha256_before": database["cars_sha256"], "cars_sha256_after": database["cars_sha256"],
        "main_fields_changed": False,
    }
    try:
        published = []
        for uid in IDS:
            base.atomic_json(TASK / "partial_resume_progress.json", {
                "contract_id": CONTRACT, "status": "RUNNING", "mode": "INSTALL",
                "completed_ids": [item["uid"] for item in published],
                "current_uid": uid, "updated_at_utc": base.utc_now(),
            })
            published.append(isolated_publish(uid))
        catalog = isolated_catalog()
        sys.path.insert(0, str(ROOT))
        import importlib
        sys.modules.pop("ua_additional_spec", None)
        helper = importlib.import_module("ua_additional_spec")
        pages = base.validate_pages(helper)
        current_hash, count, identifiers = base.cars_hash(base.DB)
        if current_hash != database["cars_sha256"] or count != 16 or identifiers != list(IDS):
            raise Blocked("PRIMARY_CHANGED_DURING_RECOVERY")
        receipt = {
            "contract_id": CONTRACT, "status": "PASS", "mode": "INSTALL",
            "recovery_mode": "EXACT_PARTIAL_RESUME", "production_write": True,
            "live_crm_write": True, "main_fields_changed": False, "media_changed": False,
            "explicit_republish": True, "autopublication": False,
            "backup_root": str(backup), "gate": state["expected_live"],
            "patched": state["shadow"]["patched"], "migration": migration,
            "publisher_probes": [], "publisher": published, "catalog": catalog,
            "pages": pages, "cars_sha256_after": current_hash, "finished_at_utc": base.utc_now(),
        }
        base.atomic_json(TASK / "install_receipt.json", receipt)
        base.atomic_json(TASK / "partial_resume_progress.json", {
            "contract_id": CONTRACT, "status": "PASS", "mode": "INSTALL",
            "completed_ids": list(IDS), "current_uid": None,
            "updated_at_utc": base.utc_now(),
        })
        return receipt
    except Exception:
        base.restore_files(backup)
        base.rollback_import({"migration": migration})
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("probe", "resume", "postcheck", "rollback"))
    args = parser.parse_args()
    receipt = TASK / ("partial_" + args.mode + "_receipt.json")
    expected_mode = {
        "probe": "PROBE", "resume": "INSTALL",
        "postcheck": "POSTCHECK", "rollback": "ROLLBACK",
    }[args.mode]
    if receipt.is_file():
        try:
            existing = base.read_json(receipt)
        except Exception:
            existing = {}
        if existing.get("status") == "PASS" and existing.get("mode") == expected_mode:
            print(json.dumps({"status": "PASS", "mode": expected_mode, "reused": True}))
            return 0
    value = {"contract_id": CONTRACT, "status": "FAIL", "mode": args.mode.upper(), "errors": []}
    try:
        with task_lock_nonblocking():
            value = {
                "probe": probe,
                "resume": resume,
                "postcheck": base.postcheck,
                "rollback": base.rollback,
            }[args.mode]()
    except Blocked as exc:
        if str(exc) == "TASK099_LOCK_BUSY":
            # A sibling fallback is already doing the work.  Do not replace
            # its future PASS receipt with a synthetic lock failure.
            print(json.dumps({"status": "WAITING", "mode": expected_mode, "lock_busy": True}))
            return 75
        value["errors"].append(type(exc).__name__ + ":" + str(exc)[:1400])
        value["finished_at_utc"] = base.utc_now()
    except Exception as exc:
        value["errors"].append(type(exc).__name__ + ":" + str(exc)[:1400])
        value["finished_at_utc"] = base.utc_now()
    base.atomic_json(receipt, value)
    print(json.dumps({"status": value.get("status"), "mode": value.get("mode"), "errors": value.get("errors")}, ensure_ascii=False))
    return 0 if value.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

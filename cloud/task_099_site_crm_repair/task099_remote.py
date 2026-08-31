#!/usr/bin/env python3
"""Remote shadow/install/postcheck/rollback worker for TASK099."""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import pathlib
import re
import shutil
import sqlite3
import sys
import tempfile
import time
import urllib.error
import urllib.request
from typing import Any


CONTRACT = "UA-ART-16-SITE-CRM-COMPLETION-099-V1"
ROOT = pathlib.Path("/home/Carix")
TASK = ROOT / "autopilot_inbox/cloud/task_099_site_crm_repair"
TASK096 = ROOT / "autopilot_inbox/cloud/task_096_tech_spec_ai_crm"
DATA096 = TASK096 / "data_enrichment"
DB = ROOT / "crm.db"
HELPER = ROOT / "ua_additional_spec.py"
CODE = {
    "cars_ui.py": ROOT / "cars_ui.py",
    "master_card.py": ROOT / "master_card.py",
    "publikaciya.py": ROOT / "publikaciya.py",
}
IDS = tuple("UA-%04d" % number for number in range(1, 17))
PUBLIC_ROOTS = (ROOT / "video", ROOT / "site")
PRICE_RE = re.compile(
    r"(?:[$€£₴₽₩¥]|\b(?:price|cost|purchase|auction|wholesale|dealer|margin|markup|"
    r"закуп|себесто|цена|вартість|낙찰|경매|금액|만원)\b)", re.I,
)
TABLES = (
    "primary_field_registry", "price_denylist", "additional_specification",
    "additional_specification_meta", "additional_specification_rejections",
    "additional_specification_audit", "additional_specification_import_runs",
)


class Blocked(RuntimeError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha_file(path: pathlib.Path) -> str | None:
    return sha_bytes(path.read_bytes()) if path.is_file() else None


def atomic_bytes(path: pathlib.Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".tmp", dir=str(path.parent))
    temporary = pathlib.Path(raw)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_json(path: pathlib.Path, value: Any) -> None:
    atomic_bytes(path, (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n").encode())


def read_json(path: pathlib.Path) -> dict[str, Any]:
    if not path.is_file():
        raise Blocked("MISSING:" + path.name)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Blocked("INVALID_JSON:" + path.name)
    return value


@contextlib.contextmanager
def locked():
    TASK.mkdir(parents=True, exist_ok=True)
    with (TASK / "task099.lock").open("a+") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def connect(path: pathlib.Path, readonly: bool = False) -> sqlite3.Connection:
    if readonly:
        conn = sqlite3.connect("file:" + str(path.resolve()) + "?mode=ro", uri=True, timeout=30)
        conn.execute("PRAGMA query_only=ON")
    else:
        conn = sqlite3.connect(str(path.resolve()), timeout=30)
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def quick_check(path: pathlib.Path) -> str:
    with connect(path, True) as conn:
        return str(conn.execute("PRAGMA quick_check").fetchone()[0])


def cars_hash_conn(conn: sqlite3.Connection) -> tuple[str, int, list[str]]:
    digest = hashlib.sha256()
    columns = [str(row[1]) for row in conn.execute("PRAGMA table_info(cars)")]
    if "auto_number" not in columns:
        raise Blocked("AUTO_NUMBER_COLUMN_MISSING")
    rows = conn.execute("SELECT * FROM cars ORDER BY auto_number").fetchall()
    identifiers = [str(row["auto_number"] or "") for row in rows]
    digest.update(json.dumps(columns, ensure_ascii=False).encode())
    for row in rows:
        digest.update(repr(tuple(row)).encode("utf-8", "backslashreplace"))
    return digest.hexdigest(), len(rows), identifiers


def cars_hash(path: pathlib.Path) -> tuple[str, int, list[str]]:
    with connect(path, True) as conn:
        return cars_hash_conn(conn)


def sqlite_backup(source: pathlib.Path, target: pathlib.Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with connect(source, True) as src, connect(target, False) as dst:
        src.backup(dst)
        dst.commit()
    if quick_check(target) != "ok":
        raise Blocked("BACKUP_QUICK_CHECK_FAIL")


def require_task096() -> tuple[pathlib.Path, dict[str, Any], dict[str, Any]]:
    canary = read_json(DATA096 / "receipt_canary.json")
    batch = read_json(DATA096 / "receipt_batch.json")
    if canary.get("status") != "PASS" or canary.get("phase") != "DATA_CANARY":
        raise Blocked("TASK096_CANARY_NOT_PASS")
    if int(canary.get("ua0015_additional_rows") or 0) < 8:
        raise Blocked("TASK096_CANARY_ROWS_LT_8")
    if batch.get("status") != "PASS" or batch.get("phase") != "DATA_BATCH":
        raise Blocked("TASK096_BATCH_NOT_PASS")
    if sorted(set(batch.get("processed_uids") or [])) != list(IDS):
        raise Blocked("TASK096_BATCH_SCOPE")
    name = str(batch.get("sandbox_db_name") or "")
    if not re.fullmatch(r"crm_task096_sandbox_[A-Za-z0-9_.-]+\.db", name):
        raise Blocked("TASK096_SANDBOX_NAME")
    path = (TASK096 / "sandbox" / name).resolve()
    if TASK096.resolve() not in path.parents or not path.is_file():
        raise Blocked("TASK096_SANDBOX_MISSING")
    if quick_check(path) != "ok":
        raise Blocked("TASK096_SANDBOX_QUICK_CHECK")
    return path, canary, batch


def require_live_gate() -> dict[str, Any]:
    gate = read_json(TASK / "expected_live.json")
    if gate.get("contract_id") != CONTRACT or gate.get("status") != "PASS":
        raise Blocked("EXPECTED_LIVE_GATE")
    expected = gate.get("source_sha256") or {}
    for name, path in CODE.items():
        if expected.get(name) != sha_file(path):
            raise Blocked("LIVE_SOURCE_DRIFT:" + name)
    current_hash, count, identifiers = cars_hash(DB)
    if count != 16 or identifiers != list(IDS) or quick_check(DB) != "ok":
        raise Blocked("LIVE_CRM_REGISTRY")
    with connect(DB, True) as conn:
        existing = [name for name in TABLES if table_exists(conn, name)]
    if existing:
        raise Blocked("LIVE_ADDITIONAL_TABLES_UNEXPECTED:" + ",".join(existing))
    return {"source_sha256": expected, "cars_sha256": current_hash, "row_count": count}


SCHEMA = """
CREATE TABLE IF NOT EXISTS primary_field_registry(
 car_uid TEXT NOT NULL,field_key TEXT NOT NULL,normalized_value TEXT NOT NULL,
 PRIMARY KEY(car_uid,field_key));
CREATE TABLE IF NOT EXISTS price_denylist(denylist_key TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS additional_specification(
 id INTEGER PRIMARY KEY AUTOINCREMENT,car_uid TEXT NOT NULL,field_key TEXT NOT NULL,
 field_value TEXT NOT NULL,normalized_value TEXT NOT NULL,
 source TEXT NOT NULL CHECK(source IN ('AI','INDEXATION')),
 source_url TEXT,confidence REAL DEFAULT 0.0,
 is_price_field INTEGER NOT NULL DEFAULT 0 CHECK(is_price_field=0),
 created_at TEXT NOT NULL DEFAULT(datetime('now')),UNIQUE(car_uid,field_key));
CREATE INDEX IF NOT EXISTS idx_addspec_car ON additional_specification(car_uid);
CREATE INDEX IF NOT EXISTS idx_addspec_key ON additional_specification(field_key);
CREATE TABLE IF NOT EXISTS additional_specification_meta(
 car_uid TEXT NOT NULL,field_key TEXT NOT NULL,label_ru TEXT NOT NULL,
 category TEXT NOT NULL,unit TEXT,evidence_count INTEGER NOT NULL DEFAULT 1,
 source_domains_json TEXT NOT NULL DEFAULT '[]',verification_status TEXT NOT NULL DEFAULT 'VERIFIED',
 model_match_score REAL NOT NULL DEFAULT 0.0,is_manual INTEGER NOT NULL DEFAULT 0 CHECK(is_manual IN(0,1)),
 is_visible INTEGER NOT NULL DEFAULT 1 CHECK(is_visible IN(0,1)),
 updated_at TEXT NOT NULL DEFAULT(datetime('now')),PRIMARY KEY(car_uid,field_key));
CREATE TABLE IF NOT EXISTS additional_specification_rejections(
 id INTEGER PRIMARY KEY AUTOINCREMENT,car_uid TEXT NOT NULL,field_key TEXT NOT NULL,
 reason TEXT NOT NULL,rejected_at TEXT NOT NULL DEFAULT(datetime('now')));
CREATE TABLE IF NOT EXISTS additional_specification_audit(
 id INTEGER PRIMARY KEY AUTOINCREMENT,car_uid TEXT NOT NULL,field_key TEXT NOT NULL,
 action TEXT NOT NULL,old_value TEXT,new_value TEXT,actor_id INTEGER,
 changed_at TEXT NOT NULL DEFAULT(datetime('now')));
CREATE TABLE IF NOT EXISTS additional_specification_import_runs(
 run_id TEXT PRIMARY KEY,source_contract TEXT NOT NULL,started_at TEXT NOT NULL,
 finished_at TEXT,status TEXT NOT NULL,inserted_count INTEGER NOT NULL DEFAULT 0,
 processed_uids_json TEXT NOT NULL DEFAULT '[]');
"""


def migrate(target: pathlib.Path, source: pathlib.Path, run_id: str) -> dict[str, Any]:
    inserted_ids = []
    per_uid = {uid: 0 for uid in IDS}
    with connect(source, True) as src:
        for required in ("additional_specification", "additional_specification_meta"):
            if not table_exists(src, required):
                raise Blocked("SANDBOX_TABLE_MISSING:" + required)
        rows = src.execute(
            """
            SELECT a.car_uid,a.field_key,a.field_value,a.normalized_value,a.source,
                   a.source_url,a.confidence,a.is_price_field,
                   m.label_ru,m.category,m.unit,m.evidence_count,m.source_domains_json,
                   m.verification_status,m.model_match_score,m.is_manual
              FROM additional_specification a
              JOIN additional_specification_meta m
                ON m.car_uid=a.car_uid AND m.field_key=a.field_key
             ORDER BY a.car_uid,a.field_key
            """
        ).fetchall()
        primary = src.execute(
            "SELECT car_uid,field_key,normalized_value FROM primary_field_registry"
        ).fetchall() if table_exists(src, "primary_field_registry") else []
    with connect(target, False) as conn:
        conn.executescript("BEGIN IMMEDIATE;\n" + SCHEMA)
        before_hash, before_count, before_ids = cars_hash_conn(conn)
        conn.execute(
            "INSERT INTO additional_specification_import_runs"
            "(run_id,source_contract,started_at,status) VALUES(?,?,?,'RUNNING')",
            (run_id, "TECH-SPEC-AI-CRM-017-V3.0-TASK096-DATA-ENRICHMENT", utc_now()),
        )
        for item in primary:
            uid, key, normalized = str(item[0]), str(item[1]), str(item[2])
            if uid in IDS and not PRICE_RE.search(key):
                conn.execute(
                    "INSERT OR IGNORE INTO primary_field_registry VALUES(?,?,?)",
                    (uid, key, normalized),
                )
        for key in (
            "purchase_price", "cost_price", "auction_price", "wholesale_price",
            "dealer_price", "buy_price", "acquisition_price", "internal_price",
            "закупочная_цена", "оптовая_цена", "аукционная_цена", "себестоимость",
        ):
            conn.execute("INSERT OR IGNORE INTO price_denylist VALUES(?)", (key,))
        for row in rows:
            item = dict(row)
            uid = str(item["car_uid"])
            key = str(item["field_key"])
            label = str(item["label_ru"])
            value = str(item["field_value"])
            unit = str(item["unit"] or "")
            if uid not in IDS:
                raise Blocked("SANDBOX_UID_OUT_OF_SCOPE:" + uid)
            if int(item["is_price_field"] or 0) != 0 or any(PRICE_RE.search(v) for v in (key, label, value, unit)):
                raise Blocked("PRICE_FACT_REJECTED:" + uid + ":" + key)
            category = str(item["category"])
            if category not in (
                "engine", "dynamics", "consumption", "dimensions", "capacity", "weight",
                "suspension", "brakes", "steering", "wheels", "ecology", "additional",
            ):
                raise Blocked("CATEGORY_REJECTED:" + category)
            cursor = conn.execute(
                """
                INSERT INTO additional_specification
                (car_uid,field_key,field_value,normalized_value,source,source_url,confidence,is_price_field)
                VALUES(?,?,?,?,?,?,?,0)
                """,
                (uid, key, value, str(item["normalized_value"]), str(item["source"]),
                 item["source_url"], float(item["confidence"] or 0.0)),
            )
            inserted_ids.append(int(cursor.lastrowid))
            conn.execute(
                """
                INSERT INTO additional_specification_meta
                (car_uid,field_key,label_ru,category,unit,evidence_count,source_domains_json,
                 verification_status,model_match_score,is_manual,is_visible,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,1,datetime('now'))
                """,
                (uid, key, label, category, unit, int(item["evidence_count"] or 1),
                 str(item["source_domains_json"] or "[]"), str(item["verification_status"]),
                 float(item["model_match_score"] or 0.0), int(item["is_manual"] or 0)),
            )
            per_uid[uid] += 1
        conn.execute(
            "UPDATE additional_specification_import_runs SET finished_at=?,status='PASS',"
            "inserted_count=?,processed_uids_json=? WHERE run_id=?",
            (utc_now(), len(inserted_ids), json.dumps(list(IDS)), run_id),
        )
        after_hash, after_count, after_ids = cars_hash_conn(conn)
        if (before_hash, before_count, before_ids) != (after_hash, after_count, after_ids):
            conn.rollback()
            raise Blocked("PRIMARY_CARS_CHANGED")
        if str(conn.execute("PRAGMA quick_check").fetchone()[0]) != "ok":
            conn.rollback()
            raise Blocked("TARGET_QUICK_CHECK_FAIL")
        conn.commit()
    return {
        "run_id": run_id, "inserted_count": len(inserted_ids), "inserted_ids": inserted_ids,
        "per_uid": per_uid, "cars_sha256_before": before_hash, "cars_sha256_after": after_hash,
        "main_fields_changed": False,
    }


def public_targets() -> list[pathlib.Path]:
    result = []
    for root in PUBLIC_ROOTS:
        for uid in IDS:
            result += [root / (uid + ".html"), root / (uid + "-diag.html")]
        result += [root / "katalog.html", root / "index.html"]
    return result


def make_backup() -> pathlib.Path:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = TASK / "backups" / stamp
    if backup.exists():
        raise Blocked("BACKUP_COLLISION")
    backup.mkdir(parents=True)
    sqlite_backup(DB, backup / "crm.db")
    manifest = {"created_at_utc": utc_now(), "files": {}}
    targets = list(CODE.values()) + [HELPER] + public_targets()
    for path in targets:
        relative = str(path.relative_to(ROOT))
        record = {"existed": path.is_file(), "sha256": sha_file(path)}
        if path.is_file():
            copy = backup / "files" / relative
            copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, copy)
        manifest["files"][relative] = record
    atomic_json(backup / "manifest.json", manifest)
    return backup


def restore_files(backup: pathlib.Path) -> dict[str, Any]:
    manifest = read_json(backup / "manifest.json")
    restored = []
    removed = []
    for relative, record in (manifest.get("files") or {}).items():
        target = (ROOT / relative).resolve()
        if ROOT.resolve() not in target.parents:
            raise Blocked("RESTORE_PATH_SCOPE")
        if record.get("existed"):
            source = backup / "files" / relative
            atomic_bytes(target, source.read_bytes())
            restored.append(relative)
        elif target.is_file():
            target.unlink()
            removed.append(relative)
    return {"restored": restored, "removed_new": removed}


def rollback_import(install: dict[str, Any]) -> dict[str, Any]:
    migration = install.get("migration") or {}
    ids = [int(value) for value in migration.get("inserted_ids") or []]
    preserved_manual = []
    removed = []
    if not ids:
        return {"removed_imported_rows": [], "preserved_manual_rows": []}
    with connect(DB, False) as conn:
        conn.execute("BEGIN IMMEDIATE")
        for spec_id in ids:
            row = conn.execute(
                """
                SELECT a.car_uid,a.field_key,COALESCE(m.is_manual,0)
                  FROM additional_specification a
                  LEFT JOIN additional_specification_meta m
                    ON m.car_uid=a.car_uid AND m.field_key=a.field_key
                 WHERE a.id=?
                """, (spec_id,),
            ).fetchone()
            if not row:
                continue
            if int(row[2] or 0) == 1:
                preserved_manual.append(spec_id)
                continue
            conn.execute("DELETE FROM additional_specification_meta WHERE car_uid=? AND field_key=?", (row[0], row[1]))
            conn.execute("DELETE FROM additional_specification WHERE id=?", (spec_id,))
            removed.append(spec_id)
        conn.commit()
    return {"removed_imported_rows": removed, "preserved_manual_rows": preserved_manual}


def patch_sources(destination: pathlib.Path | None = None) -> dict[str, Any]:
    sys.path.insert(0, str(TASK))
    import task099_patches as patches
    outputs = {}
    for name, path in CODE.items():
        source = path.read_text(encoding="utf-8")
        if name == "cars_ui.py":
            changed = patches.patch_cars_ui(source)
        elif name == "master_card.py":
            changed = patches.patch_master(source)
        else:
            changed = patches.patch_publikaciya(source)
        target = (destination / name) if destination else path
        atomic_bytes(target, changed.encode("utf-8"))
        outputs[name] = {"before": sha_bytes(source.encode()), "after": sha_bytes(changed.encode())}
    helper_target = (destination / "ua_additional_spec.py") if destination else HELPER
    atomic_bytes(helper_target, (TASK / "ua_additional_spec.py").read_bytes())
    for path in list((destination or ROOT) / name for name in CODE) + [helper_target]:
        compile(path.read_text(encoding="utf-8"), path.name, "exec")
    return outputs


def synthetic_html(uid: str) -> str:
    return (
        "<!doctype html><html><head></head><body>"
        "<div class='blok'><div class='zag'>Коротко</div><table class='kratko'>"
        "<tr><td class='k'>VIN</td><td>TESTVIN</td></tr></table></div>"
        "<!--UA068-VIN-START--><a href='https://www.carhistory.kr/x'>Проверить VIN</a><!--UA068-VIN-END-->"
        "<!--UA068-STAGE-START--><div data-ua-stage='2'>Путь автомобиля</div><!--UA068-STAGE-END-->"
        "<a class='mcf-diag-cta' href='%s-diag.html'>Открыть комплексную диагностику</a>"
        "</body></html>" % uid
    )


def shadow() -> dict[str, Any]:
    source_db, canary, batch = require_task096()
    gate = require_live_gate()
    folder = TASK / "shadow"
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    shadow_db = folder / "crm.db"
    sqlite_backup(DB, shadow_db)
    run_id = "shadow-" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    migration = migrate(shadow_db, source_db, run_id)
    patched = patch_sources(folder)
    old = os.environ.get("UA_ART_CRM_DB")
    os.environ["UA_ART_CRM_DB"] = str(shadow_db)
    try:
        sys.path.insert(0, str(folder))
        import importlib
        helper = importlib.import_module("ua_additional_spec")
        contracts = {}
        for uid in IDS:
            rendered = helper.inject_public_spec(synthetic_html(uid), uid)
            errors = helper.public_contract_errors(rendered, uid)
            if errors:
                raise Blocked("SHADOW_PUBLIC_CONTRACT:" + uid + ":" + ";".join(errors))
            contracts[uid] = {"additional_rows": len(helper.fetch_specs(uid)), "errors": []}
    finally:
        if old is None:
            os.environ.pop("UA_ART_CRM_DB", None)
        else:
            os.environ["UA_ART_CRM_DB"] = old
    return {
        "contract_id": CONTRACT, "status": "PASS", "mode": "SHADOW",
        "production_write": False, "live_crm_write": False, "public_write": False,
        "gate": gate, "task096_canary_rows": canary.get("ua0015_additional_rows"),
        "task096_processed": batch.get("processed_uids"), "migration": migration,
        "patched": patched, "contracts": contracts, "finished_at_utc": utc_now(),
    }


def validate_pages(helper) -> dict[str, Any]:
    pages = {}
    for uid in IDS:
        path = ROOT / "video" / (uid + ".html")
        if not path.is_file():
            raise Blocked("PUBLIC_CARD_MISSING:" + uid)
        source = path.read_text(encoding="utf-8")
        errors = helper.public_contract_errors(source, uid)
        if errors:
            raise Blocked("PUBLIC_CARD_CONTRACT:" + uid + ":" + ";".join(errors))
        pages[uid] = {
            "sha256": sha_bytes(source.encode()),
            "additional_rows": len(helper.fetch_specs(uid)),
            "additional_blocks": source.count(helper.START),
            "clean_vin_blocks": source.count(helper.VIN_START),
            "external_vin_cta": bool(re.search(r"carhistory\.kr|Проверить VIN", source, re.I)),
        }
    return pages


def install() -> dict[str, Any]:
    source_db, canary, batch = require_task096()
    gate = require_live_gate()
    shadow_receipt = read_json(TASK / "shadow_receipt.json")
    if shadow_receipt.get("status") != "PASS" or shadow_receipt.get("mode") != "SHADOW":
        raise Blocked("SHADOW_NOT_PASS")
    backup = make_backup()
    migration = None
    pages = None
    try:
        patched = patch_sources(None)
        run_id = "production-" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        migration = migrate(DB, source_db, run_id)
        sys.path.insert(0, str(ROOT))
        import importlib
        for name in ("ua_additional_spec", "master_card", "publikaciya"):
            sys.modules.pop(name, None)
        helper = importlib.import_module("ua_additional_spec")
        publisher = importlib.import_module("publikaciya")
        probes = []
        for uid in IDS:
            ok, detail = publisher.opublikovat(uid, proba=True)
            probes.append({"uid": uid, "ok": ok is True, "detail": str(detail)[:400]})
            if ok is not True:
                raise Blocked("PUBLISH_PROBE_FAIL:" + uid + ":" + str(detail)[:300])
        published = []
        for uid in IDS:
            ok, detail = publisher.opublikovat(uid, proba=False)
            published.append({"uid": uid, "ok": ok is True, "detail": str(detail)[:400]})
            if ok is not True:
                raise Blocked("PUBLISH_FAIL:" + uid + ":" + str(detail)[:300])
        ok, detail = publisher.obnovit_katalog()
        if ok is not True:
            raise Blocked("CATALOG_REBUILD_FAIL:" + str(detail)[:300])
        pages = validate_pages(helper)
        after_hash, count, identifiers = cars_hash(DB)
        if count != 16 or identifiers != list(IDS) or quick_check(DB) != "ok":
            raise Blocked("PRIMARY_CARS_REGISTRY_AFTER_INSTALL")
        return {
            "contract_id": CONTRACT, "status": "PASS", "mode": "INSTALL",
            "production_write": True, "live_crm_write": True, "main_fields_changed": False,
            "media_changed": False, "explicit_republish": True, "autopublication": False,
            "backup_root": str(backup), "gate": gate, "patched": patched,
            "migration": migration, "publisher_probes": probes, "publisher": published,
            "catalog": {"ok": True, "detail": str(detail)[:400]}, "pages": pages,
            "cars_sha256_after": after_hash, "finished_at_utc": utc_now(),
        }
    except Exception:
        restore_files(backup)
        if migration:
            rollback_import({"migration": migration})
        raise


def get_public(url: str) -> tuple[int, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "ua-art-task099-postcheck/1"}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return int(response.status), response.read(6_000_001).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read(6_000_001).decode("utf-8", "replace")


def postcheck() -> dict[str, Any]:
    install_value = read_json(TASK / "install_receipt.json")
    if install_value.get("status") != "PASS":
        raise Blocked("INSTALL_RECEIPT_NOT_PASS")
    if quick_check(DB) != "ok":
        raise Blocked("LIVE_DB_QUICK_CHECK")
    if sha_file(CODE["cars_ui.py"]) != (install_value.get("patched") or {}).get("cars_ui.py", {}).get("after"):
        raise Blocked("CRM_PATCH_DRIFT")
    if sha_file(CODE["master_card.py"]) != (install_value.get("patched") or {}).get("master_card.py", {}).get("after"):
        raise Blocked("MASTER_PATCH_DRIFT")
    if sha_file(CODE["publikaciya.py"]) != (install_value.get("patched") or {}).get("publikaciya.py", {}).get("after"):
        raise Blocked("PUBLISHER_PATCH_DRIFT")
    sys.path.insert(0, str(ROOT))
    import importlib
    sys.modules.pop("ua_additional_spec", None)
    helper = importlib.import_module("ua_additional_spec")
    files = validate_pages(helper)
    public = {}
    for uid in IDS:
        status, source = get_public("https://www.uaart.com.ua/video/%s.html?v=%d" % (uid, int(time.time())))
        errors = helper.public_contract_errors(source, uid) if status == 200 else ["HTTP_%d" % status]
        if errors:
            raise Blocked("PUBLIC_HTTP_CONTRACT:" + uid + ":" + ";".join(errors))
        public[uid] = {"status": status, "sha256": sha_bytes(source.encode()), "errors": []}
    status, catalog = get_public("https://www.uaart.com.ua/video/katalog.html?v=%d" % int(time.time()))
    unique = sorted(set(re.findall(r"(?:^|/)(UA-[0-9]{4})\.html", catalog, re.I)))
    if status != 200 or unique != list(IDS):
        raise Blocked("PUBLIC_CATALOG_16_CONTRACT")
    current_hash, count, identifiers = cars_hash(DB)
    if count != 16 or identifiers != list(IDS):
        raise Blocked("PRIMARY_CARS_POSTCHECK_REGISTRY")
    return {
        "contract_id": CONTRACT, "status": "PASS", "mode": "POSTCHECK",
        "production_write": False, "crm_write": False, "public_write": False,
        "main_fields_changed": False, "media_changed": False, "files": files,
        "public": public, "catalog_unique_ids": unique, "cars_sha256": current_hash,
        "finished_at_utc": utc_now(),
    }


def rollback() -> dict[str, Any]:
    install_value = read_json(TASK / "install_receipt.json")
    backup = pathlib.Path(str(install_value.get("backup_root") or "")).resolve()
    if TASK.resolve() not in backup.parents or not (backup / "manifest.json").is_file():
        raise Blocked("ROLLBACK_BACKUP_SCOPE")
    files = restore_files(backup)
    database = rollback_import(install_value)
    current_hash, count, identifiers = cars_hash(DB)
    if count != 16 or identifiers != list(IDS):
        raise Blocked("ROLLBACK_PRIMARY_REGISTRY")
    return {
        "contract_id": CONTRACT, "status": "PASS", "mode": "ROLLBACK",
        "files": files, "database": database, "main_fields_changed": False,
        "media_changed": False, "cars_sha256": current_hash, "finished_at_utc": utc_now(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("shadow", "install", "postcheck", "rollback"))
    args = parser.parse_args()
    receipt = TASK / (args.mode + "_receipt.json")
    value = {"contract_id": CONTRACT, "status": "FAIL", "mode": args.mode.upper(), "errors": []}
    try:
        with locked():
            value = {"shadow": shadow, "install": install, "postcheck": postcheck, "rollback": rollback}[args.mode]()
    except Exception as exc:
        value["errors"].append(type(exc).__name__ + ":" + str(exc)[:1000])
        value["finished_at_utc"] = utc_now()
    atomic_json(receipt, value)
    print(json.dumps({"status": value.get("status"), "mode": value.get("mode"), "errors": value.get("errors")}, ensure_ascii=False))
    return 0 if value.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

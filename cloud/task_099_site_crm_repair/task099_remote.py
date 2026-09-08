#!/usr/bin/env python3
"""Remote shadow/install/postcheck/rollback worker for TASK099."""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import gzip
import hashlib
import importlib.util
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
TASK108_GUARD = "TASK108-NONEMPTY-SPEC-AND-PUBLIC-HYGIENE-V1"
ROOT = pathlib.Path("/home/Carix")
TASK = ROOT / "autopilot_inbox/cloud/task_099_site_crm_repair"
TASK096 = ROOT / "autopilot_inbox/cloud/task_096_tech_spec_ai_crm"
DATA096 = TASK096 / "data_enrichment"
DB = ROOT / "crm.db"
HELPER = ROOT / "ua_additional_spec.py"
HOME_GUARD = TASK / "home_counter_guard.py"
CODE = {
    "cars_ui.py": ROOT / "cars_ui.py",
    "master_card.py": ROOT / "master_card.py",
    "publikaciya.py": ROOT / "publikaciya.py",
    "publish_transaction_guard.py": ROOT / "publish_transaction_guard.py",
}
# Recovery lineage pinned from the successful, immutable evidence artifact of
# workflow 33377236680.  A failed idempotent re-run can replace the live
# install receipt with a FAIL receipt even though production was never changed.
# This mapping permits only that exact previously verified TASK099 install;
# any byte of genuine source drift still fails closed.
VERIFIED_PRIOR_INSTALL = {
    "workflow_run_id": "33377236680",
    "artifact_sha256": "8a94df8e6e17b248ac07f79d6e39b09fe258bfa63640f82df7420278481e053b",
    "before": {
        "cars_ui.py": "85176c4ee2c31c63e5e24ec8537cc3f6f1a96caf35669269a5236a8b61172f15",
        "master_card.py": "db8349c24ff20e94d7fd3a09d626518e74cc8eee2fba85f0d42fc0f0982baf74",
        "publikaciya.py": "3daa821c85938fa6dcb39d13beabc59c7d793b852a99e14d69d0b931294b619a",
        "publish_transaction_guard.py": "73cfe1a01b6e705587f574c4a1407291941da76dbe15a1fe577f90f874a1644e",
    },
    "after": {
        "cars_ui.py": "0fb6993bb3b9737bbd0e78a7def376ac9c5ba872683af0fe4ce41ddb4c91d8ad",
        "master_card.py": "61cfd310a7cc9c857c09da775a74352b5d1b60bbe373fc14d39d9d984558e791",
        "publikaciya.py": "29f391985885889781458d05b9bf4d882437083455098258d91abca2d367277c",
        "publish_transaction_guard.py": "ce6bd00338fbdc38b91f9554ea7baab3b8e921ffe6c1035aa4aba0186e2b549d",
    },
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
ADDITIONAL_STATE_TABLES = (
    "additional_specification", "additional_specification_meta",
    "additional_specification_rejections", "additional_specification_audit",
    "additional_specification_import_runs",
)
TASK096_SOURCE_CONTRACT = "TECH-SPEC-AI-CRM-017-V3.0-TASK096-DATA-ENRICHMENT"
SPEC_UNIT_TOKENS = {
    "mm", "cm", "m", "km", "kg", "l", "kw", "hp", "rpm",
    "мм", "см", "м", "км", "кг", "л", "квт", "лс", "обмин",
}
SPEC_GENERIC_TOKENS = {
    "auto", "car", "vehicle", "body", "overall",
    "авто", "автомобиль", "автомобиля", "машина", "машины",
    "общий", "общая", "общее", "габаритный", "габаритная",
}
SPEC_KEY_ALIASES = {
    "length": {"length", "overall_length", "vehicle_length", "body_length"},
    "width": {"width", "overall_width", "vehicle_width", "body_width"},
    "height": {"height", "overall_height", "vehicle_height", "body_height"},
    "wheelbase": {"wheelbase", "wheel_base"},
    "front_track": {"front_track", "track_front", "front_tread", "tread_front"},
    "rear_track": {"rear_track", "track_rear", "rear_tread", "tread_rear"},
    "max_power": {"max_power", "maximum_power", "engine_power", "power_output"},
    "max_torque": {"max_torque", "maximum_torque", "engine_torque", "torque_output"},
}
HOME_ROOTS = (ROOT / "video", ROOT / "site")
WA_START = "<!-- TASK099-WHATSAPP-OPACITY:START -->"
WA_END = "<!-- TASK099-WHATSAPP-OPACITY:END -->"
WA_SCRIPT = r'''<!-- TASK099-WHATSAPP-OPACITY:START -->
<script id="task099-whatsapp-opacity">
(function(){
"use strict";
function apply(){
  var nodes=[].slice.call(document.querySelectorAll('a[href*="wa.me"],a[href*="whatsapp.com"]'));
  var fixed=nodes.filter(function(a){
    var s=getComputedStyle(a), r=a.getBoundingClientRect();
    return s.position==="fixed" && r.width>=40 && r.height>=40 && r.width<=120 && r.height<=120;
  });
  if(fixed.length===1){fixed[0].style.opacity="0.90";fixed[0].setAttribute("data-task099-opacity","0.90");}
}
if(document.readyState==="loading"){document.addEventListener("DOMContentLoaded",apply,{once:true});}else{apply();}
}());
</script>
<!-- TASK099-WHATSAPP-OPACITY:END -->'''


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


def _table_snapshot(conn: sqlite3.Connection, name: str) -> list[dict[str, Any]]:
    if not table_exists(conn, name):
        return []
    return [dict(row) for row in conn.execute('SELECT * FROM "' + name + '" ORDER BY rowid')]


def inspect_replaceable_additional_state(conn: sqlite3.Connection) -> dict[str, Any]:
    """Accept only a previous non-manual TASK099 import as upgrade input."""
    rows = {name: _table_snapshot(conn, name) for name in ADDITIONAL_STATE_TABLES}
    specs = rows["additional_specification"]
    meta = rows["additional_specification_meta"]
    audit = rows["additional_specification_audit"]
    if audit:
        raise Blocked("EXISTING_ADDITIONAL_AUDIT_REQUIRES_OPERATOR_REVIEW")
    if any(int(item.get("is_manual") or 0) != 0 for item in meta):
        raise Blocked("EXISTING_ADDITIONAL_MANUAL_ROW_REQUIRES_OPERATOR_REVIEW")
    for item in specs:
        if (str(item.get("car_uid") or "") not in IDS
                or int(item.get("is_price_field") or 0) != 0
                or str(item.get("source") or "") not in ("AI", "INDEXATION")):
            raise Blocked("EXISTING_ADDITIONAL_ROW_OUT_OF_TASK099_SCOPE")
    spec_keys = {(str(item.get("car_uid")), str(item.get("field_key"))) for item in specs}
    meta_keys = {(str(item.get("car_uid")), str(item.get("field_key"))) for item in meta}
    if spec_keys != meta_keys:
        raise Blocked("EXISTING_ADDITIONAL_META_MISMATCH")
    for item in rows["additional_specification_rejections"]:
        if str(item.get("car_uid") or "") not in IDS:
            raise Blocked("EXISTING_ADDITIONAL_REJECTION_OUT_OF_SCOPE")
    for item in rows["additional_specification_import_runs"]:
        if (str(item.get("source_contract") or "") != TASK096_SOURCE_CONTRACT
                or str(item.get("status") or "") != "PASS"):
            raise Blocked("EXISTING_ADDITIONAL_IMPORT_NOT_TASK099")
    counts = {name: len(items) for name, items in rows.items()}
    return {"present": any(counts.values()), "counts": counts, "rows": rows}


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


def _spec_words(value: Any) -> list[str]:
    words = re.findall(r"[a-zа-яёіїєґ0-9]+", str(value or "").casefold().replace("ё", "е"))
    return [
        word for word in words
        if word not in SPEC_UNIT_TOKENS and word not in SPEC_GENERIC_TOKENS
    ]


def _spec_property_key(item: dict[str, Any]) -> str:
    key_words = _spec_words(str(item.get("field_key") or "").replace("_", " "))
    key = "_".join(key_words)
    for canonical, aliases in SPEC_KEY_ALIASES.items():
        if key in aliases or "_".join(sorted(key_words)) in {
            "_".join(sorted(alias.split("_"))) for alias in aliases
        }:
            return canonical
    label_words = _spec_words(item.get("label_ru"))
    if not label_words:
        return key
    # Word order must not make "Задняя колея" and "Колея задняя"
    # different properties.
    return "label:" + "_".join(sorted(label_words))


def _spec_value_key(value: Any) -> str:
    text = str(value or "").casefold().replace("ё", "е").replace("\u00a0", " ")
    text = text.replace(",", ".")
    text = re.sub(r"(?<=\d)\s+(?=\d)", "", text)
    return re.sub(r"[^a-zа-яіїєґ0-9.]+", "", text)


def dedupe_spec_rows(rows: list[sqlite3.Row]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        item = dict(row)
        signature = (str(item.get("car_uid") or ""), str(item.get("category") or ""),
                     _spec_property_key(item))
        groups.setdefault(signature, []).append(item)
    accepted = []
    rejected = []
    for signature, candidates in sorted(groups.items()):
        manual = [item for item in candidates if int(item.get("is_manual") or 0) == 1]
        pool = manual or candidates
        values = {_spec_value_key(item.get("field_value")) for item in pool}
        if len(values) != 1:
            raise Blocked(
                "SEMANTIC_SPEC_CONFLICT:%s:%s" % (signature[0], signature[2])
            )
        chosen = sorted(
            pool,
            key=lambda item: (
                -int(item.get("is_manual") or 0),
                -int(item.get("evidence_count") or 0),
                -float(item.get("confidence") or 0.0),
                -float(item.get("model_match_score") or 0.0),
                str(item.get("field_key") or ""),
            ),
        )[0]
        accepted.append(chosen)
        for item in candidates:
            if item is chosen:
                continue
            rejected.append({
                "car_uid": signature[0],
                "field_key": str(item.get("field_key") or ""),
                "kept_field_key": str(chosen.get("field_key") or ""),
                "semantic_property": signature[2],
                "reason": "SEMANTIC_DUPLICATE",
            })
    return accepted, rejected


def require_task096() -> tuple[pathlib.Path, dict[str, Any], dict[str, Any], str]:
    canary_path = DATA096 / "receipt_canary.json"
    batch_path = DATA096 / "receipt_batch.json"
    if ((canary_path.exists() and not canary_path.is_file())
            or (batch_path.exists() and not batch_path.is_file())):
        raise Blocked("TASK096_RECEIPT_PATH_TYPE")
    gate = read_json(TASK / "expected_live.json")
    pinned_canary = gate.get("task096_canary_fallback")
    pinned_batch = gate.get("task096_batch_fallback")
    if not isinstance(pinned_canary, dict) or not isinstance(pinned_batch, dict):
        raise Blocked("TASK096_PINNED_FALLBACK_MISSING")
    canary_live = canary_path.is_file()
    batch_live = batch_path.is_file()
    canary = read_json(canary_path) if canary_live else pinned_canary
    batch = read_json(batch_path) if batch_live else pinned_batch
    evidence_source = (
        "LIVE_TASK096_RECEIPTS" if canary_live and batch_live else
        "PINNED_COMMITTED_TASK096_EVIDENCE" if not canary_live and not batch_live else
        "MIXED_VALID_LIVE_AND_PINNED_TASK096_EVIDENCE"
    )
    if canary.get("status") != "PASS" or canary.get("phase") != "DATA_CANARY":
        raise Blocked("TASK096_CANARY_NOT_PASS")
    if int(canary.get("ua0015_additional_rows") or 0) < 8:
        raise Blocked("TASK096_CANARY_ROWS_LT_8")
    if batch.get("status") != "PASS" or batch.get("phase") != "DATA_BATCH":
        raise Blocked("TASK096_BATCH_NOT_PASS")
    if sorted(set(batch.get("processed_uids") or [])) != list(IDS):
        raise Blocked("TASK096_BATCH_SCOPE")
    name = str(batch.get("sandbox_db_name") or "")
    if name != str(gate.get("task096_sandbox_db_name") or ""):
        raise Blocked("TASK096_PINNED_SANDBOX_MISMATCH")
    if str(canary.get("sandbox_db_name") or "") != name:
        raise Blocked("TASK096_RECEIPT_SANDBOX_MISMATCH")
    if not re.fullmatch(r"crm_task096_sandbox_[A-Za-z0-9_.-]+\.db", name):
        raise Blocked("TASK096_SANDBOX_NAME")
    path = (TASK096 / "sandbox" / name).resolve()
    if TASK096.resolve() not in path.parents or not path.is_file():
        raise Blocked("TASK096_SANDBOX_MISSING")
    if quick_check(path) != "ok":
        raise Blocked("TASK096_SANDBOX_QUICK_CHECK")
    return path, canary, batch, evidence_source


def verified_prior_install_matches(expected: dict[str, Any], current: dict[str, Any]) -> bool:
    return (
        expected == VERIFIED_PRIOR_INSTALL["before"]
        and current == VERIFIED_PRIOR_INSTALL["after"]
    )


def require_live_gate() -> dict[str, Any]:
    gate = read_json(TASK / "expected_live.json")
    if gate.get("contract_id") != CONTRACT or gate.get("status") != "PASS":
        raise Blocked("EXPECTED_LIVE_GATE")
    expected = gate.get("source_sha256") or {}
    current = {name: sha_file(path) for name, path in CODE.items()}
    source_mode = "EXPECTED_ORIGINAL"
    prior_install = None
    prior_shadow_gate = None
    mismatched = [name for name in CODE if expected.get(name) != current.get(name)]
    if mismatched:
        receipt_path = TASK / "install_receipt.json"
        prior_install = read_json(receipt_path) if receipt_path.is_file() else None
        patched = (prior_install or {}).get("patched") or {}
        valid_prior = (
            isinstance(prior_install, dict)
            and prior_install.get("contract_id") == CONTRACT
            and prior_install.get("status") == "PASS"
            and prior_install.get("mode") == "INSTALL"
            and prior_install.get("main_fields_changed") is False
            and prior_install.get("media_changed") is False
            and all(
                (patched.get(name) or {}).get("before") == expected.get(name)
                and (patched.get(name) or {}).get("after") == current.get(name)
                for name in CODE
            )
        )
        # API.run("install") removes install_receipt.json before launching the
        # remote command so it can wait for the new receipt.  On an approved
        # idempotent re-run that deletion must not make our own installed
        # TASK099 patch look like foreign source drift.  The immediately
        # preceding shadow receipt already validated the old install receipt;
        # accept it only while it is fresh and every source hash is still
        # exactly the idempotent hash observed by that shadow run.
        shadow_path = TASK / "shadow_receipt.json"
        prior_shadow = read_json(shadow_path) if shadow_path.is_file() else None
        shadow_gate = (prior_shadow or {}).get("gate") or {}
        shadow_patched = (prior_shadow or {}).get("patched") or {}
        shadow_age = None
        try:
            shadow_finished = dt.datetime.fromisoformat(
                str((prior_shadow or {}).get("finished_at_utc") or "").replace("Z", "+00:00")
            )
            shadow_age = (dt.datetime.now(dt.timezone.utc) - shadow_finished).total_seconds()
        except (TypeError, ValueError):
            pass
        valid_shadow_reentry = (
            not valid_prior
            and isinstance(prior_shadow, dict)
            and prior_shadow.get("contract_id") == CONTRACT
            and prior_shadow.get("status") == "PASS"
            and prior_shadow.get("mode") == "SHADOW"
            and prior_shadow.get("production_write") is False
            and prior_shadow.get("live_crm_write") is False
            and shadow_gate.get("source_mode") == "PRIOR_TASK099_INSTALL"
            and shadow_gate.get("source_sha256") == expected
            and shadow_age is not None and 0 <= shadow_age <= 7200
            and all(
                (shadow_patched.get(name) or {}).get("before") == current.get(name)
                and (shadow_patched.get(name) or {}).get("after") == current.get(name)
                for name in CODE
            )
        )
        valid_verified_prior = verified_prior_install_matches(expected, current)
        if not valid_prior and not valid_shadow_reentry and not valid_verified_prior:
            raise Blocked("LIVE_SOURCE_DRIFT:" + ",".join(mismatched))
        if valid_shadow_reentry:
            prior_shadow_gate = shadow_gate
        source_mode = "PRIOR_TASK099_INSTALL"
    current_hash, count, identifiers = cars_hash(DB)
    if count != 16 or identifiers != list(IDS) or quick_check(DB) != "ok":
        raise Blocked("LIVE_CRM_REGISTRY")
    with connect(DB, True) as conn:
        existing = [name for name in TABLES if table_exists(conn, name)]
        additional_state = inspect_replaceable_additional_state(conn)
        residual_counts = additional_state["counts"]
    nonempty = {name: value for name, value in residual_counts.items() if value}
    live_content_rows = (
        int(residual_counts.get("additional_specification") or 0)
        + int(residual_counts.get("additional_specification_meta") or 0)
        + int(residual_counts.get("additional_specification_audit") or 0)
    )
    if live_content_rows and source_mode != "PRIOR_TASK099_INSTALL":
        raise Blocked("LIVE_ADDITIONAL_DATA_UNEXPECTED:" + json.dumps(nonempty, sort_keys=True))
    return {
        "source_sha256": expected, "cars_sha256": current_hash, "row_count": count,
        "clean_rollback_schema": existing, "residual_data_counts": residual_counts,
        "source_mode": source_mode,
        "prior_task099_install_run_id": (
            str((prior_install or {}).get("run_id") or "") if prior_install else
            str((prior_shadow_gate or {}).get("prior_task099_install_run_id") or "")
            if prior_shadow_gate else
            str(VERIFIED_PRIOR_INSTALL["workflow_run_id"])
            if mismatched and verified_prior_install_matches(expected, current) else None
        ),
    }


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


def prepare_additional_target(conn: sqlite3.Connection, run_id: str) -> dict[str, Any]:
    state = inspect_replaceable_additional_state(conn)
    if not state["present"]:
        return {"replaced": False, "counts": state["counts"], "snapshot_path": None}
    safe_run_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", run_id)
    snapshot_path = (TASK / ("prior_additional_" + safe_run_id + ".json")).resolve()
    if TASK.resolve() not in snapshot_path.parents:
        raise Blocked("ADDITIONAL_SNAPSHOT_PATH_SCOPE")
    snapshot = {
        "contract_id": CONTRACT,
        "created_at_utc": utc_now(),
        "run_id": run_id,
        "tables": state["rows"],
    }
    atomic_json(snapshot_path, snapshot)
    snapshot_sha = sha_file(snapshot_path)
    for name in (
        "additional_specification_audit", "additional_specification_rejections",
        "additional_specification_meta", "additional_specification",
        "additional_specification_import_runs",
    ):
        conn.execute('DELETE FROM "' + name + '"')
    return {
        "replaced": True,
        "counts": state["counts"],
        "snapshot_path": str(snapshot_path),
        "snapshot_sha256": snapshot_sha,
    }


def migrate(target: pathlib.Path, source: pathlib.Path, run_id: str) -> dict[str, Any]:
    inserted_ids = []
    per_uid = {uid: 0 for uid in IDS}
    with connect(source, True) as src:
        for required in ("additional_specification", "additional_specification_meta"):
            if not table_exists(src, required):
                raise Blocked("SANDBOX_TABLE_MISSING:" + required)
        source_rows = src.execute(
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
    rows, semantic_rejections = dedupe_spec_rows(list(source_rows))
    with connect(target, False) as conn:
        conn.executescript("BEGIN IMMEDIATE;\n" + SCHEMA)
        prior_additional = prepare_additional_target(conn, run_id)
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
        for rejection in semantic_rejections:
            conn.execute(
                "INSERT INTO additional_specification_rejections"
                "(car_uid,field_key,reason) VALUES(?,?,?)",
                (rejection["car_uid"], rejection["field_key"],
                 "SEMANTIC_DUPLICATE_OF:" + rejection["kept_field_key"]),
            )
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
        "source_row_count": len(source_rows),
        "semantic_duplicates_rejected": len(semantic_rejections),
        "semantic_rejections": semantic_rejections,
        "prior_additional": prior_additional,
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


def prune_completed_task_backups() -> list[str]:
    """Remove obsolete TASK099 recovery copies after a clean live gate.

    A quota failure can interrupt ``make_backup`` before ``manifest.json`` is
    written.  Those incomplete copies are still task-owned, can consume most
    of the quota, and are not usable for rollback.  The caller has already
    proved that live code and the protected CRM registry are back at the clean
    baseline, so only exact timestamp-named children of TASK099/backups are
    eligible here.
    """
    root = (TASK / "backups").resolve()
    removed = []
    if not root.is_dir():
        return removed
    for child in sorted(root.iterdir()):
        resolved = child.resolve()
        if not child.is_dir() or resolved.parent != root:
            continue
        if not re.fullmatch(r"\d{8}T\d{6}Z", child.name):
            continue
        state = "complete" if (child / "manifest.json").is_file() else "incomplete"
        shutil.rmtree(child)
        removed.append(child.name + ":" + state)
    return removed


def prune_redundant_publisher_backups(outer_backup: pathlib.Path) -> dict[str, Any]:
    """Remove only old publisher-owned copies after a complete outer backup.

    The live HTML, CRM and media are never targets.  TASK099's gzip backup is
    the current rollback authority and must describe every public target and
    every patched source before any obsolete copy is removed.
    """
    manifest = read_json(outer_backup / "manifest.json")
    records = manifest.get("files") or {}
    required = [str(path.relative_to(ROOT)) for path in list(CODE.values()) + [HELPER] + public_targets()]
    missing = [relative for relative in required if relative not in records]
    if missing:
        raise Blocked("OUTER_BACKUP_SCOPE_INCOMPLETE:" + ",".join(missing[:8]))

    roots = [
        ((ROOT / "rezerv_publikacii" / "TASK083").resolve(), r"\d{8}T\d{6}Z-[0-9a-f]{12}"),
        ((ROOT / "rezerv_publikacii").resolve(), r"UA-[0-9]{4,}_(?:URGENT_CATALOG_)?\d{8}_\d{6}"),
    ]
    removed = []
    reclaimed = 0
    for root, pattern in roots:
        if not root.is_dir():
            continue
        for child in sorted(root.iterdir()):
            resolved = child.resolve()
            if not child.is_dir() or resolved.parent != root or not re.fullmatch(pattern, child.name):
                continue
            size = sum(path.stat().st_size for path in child.rglob("*") if path.is_file())
            shutil.rmtree(child)
            removed.append(str(child.relative_to(ROOT)))
            reclaimed += size
    return {"removed": removed, "reclaimed_bytes": reclaimed, "live_media_removed": False}


def remove_shadow_copy() -> bool:
    folder = (TASK / "shadow").resolve()
    if folder.is_dir() and folder.parent == TASK.resolve():
        shutil.rmtree(folder)
        return True
    return False


def make_backup() -> pathlib.Path:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = TASK / "backups" / stamp
    if backup.exists():
        raise Blocked("BACKUP_COLLISION")
    backup.mkdir(parents=True)
    cars_digest, cars_count, cars_ids = cars_hash(DB)
    manifest = {
        "created_at_utc": utc_now(), "files": {},
        "crm_scope_backup": {
            "mode": "LOGICAL_AFFECTED_TABLES_PLUS_PRIMARY_HASH",
            "cars_sha256": cars_digest, "cars_row_count": cars_count, "cars_ids": cars_ids,
            "primary_database_file_replacement_on_rollback": False,
        },
    }
    targets = list(CODE.values()) + [HELPER] + public_targets()
    for path in targets:
        relative = str(path.relative_to(ROOT))
        record = {"existed": path.is_file(), "sha256": sha_file(path)}
        if path.is_file():
            stored_relative = "files/" + relative + ".gz"
            copy = backup / stored_relative
            payload = gzip.compress(path.read_bytes(), compresslevel=9, mtime=0)
            atomic_bytes(copy, payload)
            record.update({
                "storage": "gzip-v1", "stored_relative": stored_relative,
                "stored_bytes": len(payload),
            })
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
            if record.get("storage") == "gzip-v1":
                stored = str(record.get("stored_relative") or "")
                source = (backup / stored).resolve()
                if backup.resolve() not in source.parents or not source.is_file():
                    raise Blocked("RESTORE_GZIP_SCOPE:" + relative)
                data = gzip.decompress(source.read_bytes())
            else:
                source = backup / "files" / relative
                data = source.read_bytes()
            if sha_bytes(data) != record.get("sha256"):
                raise Blocked("RESTORE_SHA_MISMATCH:" + relative)
            atomic_bytes(target, data)
            restored.append(relative)
        elif target.is_file():
            target.unlink()
            removed.append(relative)
    return {"restored": restored, "removed_new": removed}


def rollback_import(install: dict[str, Any]) -> dict[str, Any]:
    migration = install.get("migration") or {}
    ids = [int(value) for value in migration.get("inserted_ids") or []]
    prior = migration.get("prior_additional") or {}
    preserved_manual = []
    removed = []
    if not ids and not prior.get("replaced"):
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
        restored_prior = {}
        if prior.get("replaced"):
            snapshot_path = pathlib.Path(str(prior.get("snapshot_path") or "")).resolve()
            if (TASK.resolve() not in snapshot_path.parents or not snapshot_path.is_file()
                    or sha_file(snapshot_path) != prior.get("snapshot_sha256")):
                conn.rollback()
                raise Blocked("ADDITIONAL_ROLLBACK_SNAPSHOT_INVALID")
            snapshot = read_json(snapshot_path)
            if snapshot.get("contract_id") != CONTRACT or not isinstance(snapshot.get("tables"), dict):
                conn.rollback()
                raise Blocked("ADDITIONAL_ROLLBACK_SNAPSHOT_CONTRACT")
            manual_keys = {
                (str(row[0]), str(row[1]))
                for row in conn.execute(
                    "SELECT car_uid,field_key FROM additional_specification_meta WHERE is_manual=1"
                ).fetchall()
            }
            conn.execute(
                "DELETE FROM additional_specification WHERE NOT EXISTS ("
                "SELECT 1 FROM additional_specification_meta m "
                "WHERE m.car_uid=additional_specification.car_uid "
                "AND m.field_key=additional_specification.field_key AND m.is_manual=1)"
            )
            conn.execute("DELETE FROM additional_specification_meta WHERE is_manual=0")
            conn.execute("DELETE FROM additional_specification_rejections")
            conn.execute("DELETE FROM additional_specification_import_runs")
            if not manual_keys:
                conn.execute("DELETE FROM additional_specification_audit")
            restored_prior = {name: 0 for name in ADDITIONAL_STATE_TABLES}
            for name in (
                "additional_specification", "additional_specification_meta",
                "additional_specification_rejections", "additional_specification_audit",
                "additional_specification_import_runs",
            ):
                for item in (snapshot["tables"].get(name) or []):
                    if name in ("additional_specification", "additional_specification_meta"):
                        pair = (str(item.get("car_uid")), str(item.get("field_key")))
                        if pair in manual_keys:
                            continue
                    columns = list(item)
                    if not columns:
                        continue
                    quoted = ",".join('"' + column.replace('"', '""') + '"' for column in columns)
                    placeholders = ",".join("?" for _ in columns)
                    conn.execute(
                        'INSERT OR IGNORE INTO "' + name + '" (' + quoted + ") VALUES (" + placeholders + ")",
                        tuple(item[column] for column in columns),
                    )
                    restored_prior[name] += 1
        conn.commit()
    return {
        "removed_imported_rows": removed,
        "preserved_manual_rows": preserved_manual,
        "restored_prior_rows": restored_prior,
    }


def load_home_guard():
    if not HOME_GUARD.is_file():
        raise Blocked("HOME_COUNTER_GUARD_MISSING")
    spec = importlib.util.spec_from_file_location("task099_home_counter_guard", HOME_GUARD)
    if not spec or not spec.loader:
        raise Blocked("HOME_COUNTER_GUARD_IMPORT")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def homepage_contract() -> tuple[Any, dict[str, int], list[str], dict[str, Any]]:
    guard = load_home_guard()
    with connect(DB, True) as conn:
        rows = [dict(row) for row in conn.execute(
            "SELECT * FROM cars WHERE published=1 ORDER BY auto_number,id"
        ).fetchall()]
    counts = guard.counts_from_rows(rows)
    ids = sorted(str(row.get("auto_number") or "").strip().upper() for row in rows)
    if counts.get("all") != 16 or ids != list(IDS):
        raise Blocked("HOME_CRM_16_CONTRACT")
    catalog_path = ROOT / "video" / "katalog.html"
    catalog_source = catalog_path.read_text(encoding="utf-8")
    # Use the approved catalog design guard as the single parser.  In the
    # restored catalog the card identity lives in a nested VIN block while
    # the stage lives on the enclosing <article>; requiring both attributes
    # on one opening tag incorrectly reported an empty catalog after a valid
    # 16-card publish.
    sys.path.insert(0, str(ROOT))
    import catalog_design_guard as catalog_guard
    golden = catalog_guard.GOLDEN_PATH.read_text(encoding="utf-8")
    catalog_audit = catalog_guard.audit_catalog(catalog_source, rows, golden)
    catalog = {
        "status": catalog_audit.get("status"),
        "errors": list(catalog_audit.get("errors") or []),
        "counts": dict(catalog_audit.get("counts") or {}),
        "ids": sorted(str(value).upper() for value in (catalog_audit.get("ids") or [])),
        "shell_fingerprint": catalog_audit.get("shell_fingerprint"),
    }
    if catalog["status"] != "PASS":
        raise Blocked(
            "HOME_CATALOG_DESIGN_CONTRACT:"
            + json.dumps(catalog, ensure_ascii=False, sort_keys=True)[:1600]
        )
    if catalog["counts"] != counts or catalog["ids"] != ids:
        raise Blocked(
            "HOME_CRM_CATALOG_MISMATCH:"
            + json.dumps({"crm": counts, "catalog": catalog}, ensure_ascii=False, sort_keys=True)
        )
    return guard, counts, ids, catalog


def patch_whatsapp_opacity(source: str) -> str:
    region = re.compile(re.escape(WA_START) + r"[\s\S]*?" + re.escape(WA_END))
    if region.search(source):
        return region.sub(WA_SCRIPT, source, count=1)
    endings = list(re.finditer(r"</body\s*>", source, re.I))
    if len(endings) != 1:
        raise Blocked("HOME_BODY_END_COUNT:%d" % len(endings))
    match = endings[0]
    return source[:match.start()] + WA_SCRIPT + "\n" + source[match.start():]


def homepage_source_errors(guard, source: str, counts: dict[str, int]) -> list[str]:
    audit = guard.audit_home(source, counts)
    errors = list(audit.get("errors") or []) if audit.get("status") != "PASS" else []
    if source.count('id="task099-whatsapp-opacity"') != 1:
        errors.append("WHATSAPP_OPACITY_SCRIPT_COUNT")
    if 'style.opacity="0.90"' not in source:
        errors.append("WHATSAPP_OPACITY_VALUE")
    return errors


def sync_homepages() -> dict[str, Any]:
    guard, counts, ids, catalog = homepage_contract()
    changed = []
    audits = {}
    skipped_incompatible = {}
    for root in HOME_ROOTS:
        path = root / "index.html"
        if not path.is_file():
            if root == ROOT / "video":
                raise Blocked("VIDEO_HOME_MISSING")
            continue
        source = path.read_text(encoding="utf-8")
        try:
            patched = patch_whatsapp_opacity(guard.patch_home(source, counts))
        except guard.HomeCounterError as exc:
            # TASK100 authorizes /site/index.html only when it is compatible
            # with the approved homepage shell.  It is a secondary legacy
            # root and must not block the canonical /video homepage.  The
            # canonical public homepage remains strictly fail-closed.
            if root != ROOT / "video":
                skipped_incompatible[str(path.relative_to(ROOT))] = str(exc)
                continue
            raise Blocked(
                "VIDEO_HOME_PATCH_CONTRACT:"
                + str(exc)
                + ":stage_card_tokens=%d" % source.count("stage-card")
            ) from exc
        errors = homepage_source_errors(guard, patched, counts)
        if errors:
            raise Blocked("HOME_PATCH_CONTRACT:" + str(path) + ":" + ";".join(errors))
        if patched != source:
            atomic_bytes(path, patched.encode("utf-8"))
            changed.append(str(path.relative_to(ROOT)))
        audits[str(path.relative_to(ROOT))] = {
            "sha256": sha_file(path), "errors": [],
        }
    return {
        "status": "PASS", "counts": counts, "ids": ids, "catalog": catalog,
        "changed_files": changed, "audits": audits, "whatsapp_opacity": 0.90,
        "skipped_incompatible_secondary_homepages": skipped_incompatible,
        "crm_write": False, "media_write": False,
    }


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
        elif name == "publikaciya.py":
            changed = patches.patch_publikaciya(source)
        else:
            changed = patches.patch_publish_transaction_guard(source)
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
        "<a class='dejstvie kn_kupit' href='#'>Устаревший CTA</a>"
        "<a class='mcf-diag-cta' href='%s-diag.html'>Открыть комплексную диагностику</a>"
        "</body></html>" % uid
    )


def shadow() -> dict[str, Any]:
    source_db, canary, batch, task096_source = require_task096()
    gate = require_live_gate()
    pruned = prune_completed_task_backups()
    folder = TASK / "shadow"
    remove_shadow_copy()
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
        empty_spec_cards = [
            uid for uid, result in contracts.items()
            if int(result.get("additional_rows") or 0) <= 0
        ]
        if empty_spec_cards:
            raise Blocked("SHADOW_EMPTY_ADDITIONAL_SPEC:" + ",".join(empty_spec_cards))
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
        "task096_evidence_source": task096_source,
        "patched": patched, "contracts": contracts, "finished_at_utc": utc_now(),
        "pruned_completed_task099_backups": pruned,
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
    source_db, canary, batch, task096_source = require_task096()
    gate = require_live_gate()
    shadow_receipt = read_json(TASK / "shadow_receipt.json")
    if shadow_receipt.get("status") != "PASS" or shadow_receipt.get("mode") != "SHADOW":
        raise Blocked("SHADOW_NOT_PASS")
    if shadow_receipt.get("task108_guard") != TASK108_GUARD:
        raise Blocked("SHADOW_TASK108_GUARD_MISSING")
    shadow_contracts = shadow_receipt.get("contracts") or {}
    empty_shadow_cards = [
        uid for uid in IDS
        if int((shadow_contracts.get(uid) or {}).get("additional_rows") or 0) <= 0
    ]
    if empty_shadow_cards:
        raise Blocked("SHADOW_EMPTY_ADDITIONAL_SPEC:" + ",".join(empty_shadow_cards))
    shadow_removed_before_backup = remove_shadow_copy()
    backup = make_backup()
    migration = None
    pages = None
    try:
        publisher_backup_prune = prune_redundant_publisher_backups(backup)
        patched = patch_sources(None)
        run_id = "production-" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        migration = migrate(DB, source_db, run_id)
        sys.path.insert(0, str(ROOT))
        import importlib
        for name in ("ua_additional_spec", "master_card", "publikaciya"):
            sys.modules.pop(name, None)
        helper = importlib.import_module("ua_additional_spec")
        publisher = importlib.import_module("publikaciya")
        guard = importlib.import_module("publish_transaction_guard")
        base_publish = getattr(publisher, "_UA083_BASE_PUBLISH", None)
        if not callable(base_publish):
            raise Blocked("BOUNDED_BASE_PUBLISHER_MISSING")
        probes = []
        for uid in IDS:
            ok, detail = base_publish(uid, proba=True)
            probes.append({"uid": uid, "ok": ok is True, "detail": str(detail)[:400]})
            if ok is not True:
                raise Blocked("PUBLISH_PROBE_FAIL:" + uid + ":" + str(detail)[:300])
        legacy_root = pathlib.Path(str(getattr(publisher, "REZERV_KORE", ROOT / "rezerv_publikacii"))).resolve()
        legacy_before = {child.name for child in legacy_root.iterdir()} if legacy_root.is_dir() else set()
        legacy_removed = []

        def bounded_base_publish(uid: str, proba: bool = False):
            before = {child.name for child in legacy_root.iterdir()} if legacy_root.is_dir() else set()
            result = base_publish(uid, proba=proba)
            if (not proba and isinstance(result, (tuple, list)) and result and result[0] is True
                    and legacy_root == (ROOT / "rezerv_publikacii").resolve() and legacy_root.is_dir()):
                for child in sorted(legacy_root.iterdir()):
                    resolved = child.resolve()
                    if (child.name not in before and child.is_dir() and resolved.parent == legacy_root
                            and re.fullmatch(re.escape(uid) + r"_\d{8}_\d{6}", child.name)):
                        shutil.rmtree(child)
                        legacy_removed.append(child.name)
            return result

        ok, detail, batch_evidence = guard.publish_batch(bounded_base_publish, list(IDS), proba=False)
        if ok is not True:
            raise Blocked("PUBLISH_BATCH_FAIL:" + str(detail)[:500])
        published = [
            {"uid": uid, "ok": bool((batch_evidence.get("base_results") or {}).get(uid, {}).get("ok")),
             "detail": str((batch_evidence.get("base_results") or {}).get(uid, {}).get("message") or "")[:400]}
            for uid in IDS
        ]
        if not all(item["ok"] for item in published):
            raise Blocked("PUBLISH_BATCH_RESULT_SET")
        if legacy_root.is_dir() and legacy_root == (ROOT / "rezerv_publikacii").resolve():
            for child in sorted(legacy_root.iterdir()):
                resolved = child.resolve()
                if (child.name not in legacy_before and child.is_dir() and resolved.parent == legacy_root
                        and re.fullmatch(r"UA-[0-9]{4,}_\d{8}_\d{6}", child.name)):
                    shutil.rmtree(child)
                    legacy_removed.append(child.name)
        homepage = sync_homepages()
        pages = validate_pages(helper)
        after_hash, count, identifiers = cars_hash(DB)
        if count != 16 or identifiers != list(IDS) or quick_check(DB) != "ok":
            raise Blocked("PRIMARY_CARS_REGISTRY_AFTER_INSTALL")
        return {
            "contract_id": CONTRACT, "status": "PASS", "mode": "INSTALL",
            "production_write": True, "live_crm_write": True, "main_fields_changed": False,
            "media_changed": False, "explicit_republish": True, "autopublication": False,
            "backup_root": str(backup), "gate": gate, "patched": patched,
            "task096_evidence_source": task096_source,
            "shadow_copy_removed_before_backup": shadow_removed_before_backup,
            "migration": migration, "publisher_probes": probes, "publisher": published,
            "catalog": {"ok": True, "detail": str(detail)[:400]}, "pages": pages,
            "homepage": homepage,
            "publisher_batch": batch_evidence,
            "publisher_backup_prune": publisher_backup_prune,
            "transient_legacy_backups_removed": legacy_removed,
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
    for name, path in CODE.items():
        if sha_file(path) != (install_value.get("patched") or {}).get(name, {}).get("after"):
            raise Blocked("SOURCE_PATCH_DRIFT:" + name)
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
    # The approved catalog deliberately has two links per card (photo and
    # arrow).  Counting hrefs as cards caused a false rollback after a valid
    # 16-card install.  Validate the rendered public HTML with the same
    # design contract that built it, and allow a bounded propagation window.
    import catalog_design_guard as catalog_guard
    with connect(DB, True) as conn:
        catalog_rows = [dict(row) for row in conn.execute(
            "SELECT * FROM cars WHERE published=1 ORDER BY auto_number,id"
        ).fetchall()]
    golden = catalog_guard.GOLDEN_PATH.read_text(encoding="utf-8")
    catalog_attempts = []
    catalog_audit = None
    catalog = ""
    status = None
    for attempt in range(1, 7):
        status, catalog = get_public(
            "https://www.uaart.com.ua/video/katalog.html?v=%d-%d"
            % (int(time.time()), attempt)
        )
        try:
            audit = catalog_guard.audit_catalog(catalog, catalog_rows, golden)
        except Exception as exc:
            audit = {"status": "FAIL", "errors": [type(exc).__name__ + ":" + str(exc)[:300]]}
        ids = [str(value).upper() for value in audit.get("ids") or []]
        ok = status == 200 and audit.get("status") == "PASS" and sorted(ids) == list(IDS)
        catalog_attempts.append({
            "attempt": attempt, "http_status": status, "audit_status": audit.get("status"),
            "ids": ids, "errors": list(audit.get("errors") or []), "pass": ok,
        })
        catalog_audit = audit
        if ok:
            break
        if attempt < 6:
            time.sleep(10)
    else:
        raise Blocked(
            "PUBLIC_CATALOG_16_CONTRACT:"
            + json.dumps(catalog_attempts[-1], ensure_ascii=False, sort_keys=True)[:1200]
        )
    catalog_ids = [value.upper() for value in re.findall(
        r"href\s*=\s*['\"](?:https?://[^'\"]+)?(?:[^'\"]*/)?"
        r"(UA-[0-9]{4})\.html(?:\?[^'\"]*)?['\"]", catalog, re.I,
    )]
    catalog_counts = {uid: catalog_ids.count(uid) for uid in sorted(set(catalog_ids))}
    unique = sorted(set(catalog_ids))
    home_guard, home_counts, home_ids, home_catalog = homepage_contract()
    home_local = {}
    skipped_secondary = set(
        (((install_value.get("homepage") or {})
          .get("skipped_incompatible_secondary_homepages") or {}).keys())
    )
    for root in HOME_ROOTS:
        path = root / "index.html"
        if not path.is_file():
            continue
        relative_home = str(path.relative_to(ROOT))
        if relative_home in skipped_secondary:
            home_local[relative_home] = {
                "status": "SKIPPED_INCOMPATIBLE_SECONDARY",
                "sha256": sha_file(path),
                "errors": [],
            }
            continue
        source = path.read_text(encoding="utf-8")
        errors = homepage_source_errors(home_guard, source, home_counts)
        if errors:
            raise Blocked("HOME_LOCAL_CONTRACT:" + str(path) + ":" + ";".join(errors))
        home_local[relative_home] = {"status": "PASS", "sha256": sha_file(path), "errors": []}
    home_attempts = []
    home_status = None
    public_home = ""
    home_public_errors = []
    for attempt in range(1, 7):
        home_status, public_home = get_public(
            "https://www.uaart.com.ua/video/index.html?v=%d-%d"
            % (int(time.time()), attempt)
        )
        home_public_errors = (
            homepage_source_errors(home_guard, public_home, home_counts)
            if home_status == 200 else ["HTTP_%d" % home_status]
        )
        home_attempts.append({
            "attempt": attempt, "http_status": home_status,
            "errors": list(home_public_errors), "pass": not home_public_errors,
        })
        if not home_public_errors:
            break
        if attempt < 6:
            time.sleep(10)
    else:
        raise Blocked("HOME_PUBLIC_CONTRACT:" + ";".join(home_public_errors))
    current_hash, count, identifiers = cars_hash(DB)
    if count != 16 or identifiers != list(IDS):
        raise Blocked("PRIMARY_CARS_POSTCHECK_REGISTRY")
    return {
        "contract_id": CONTRACT, "status": "PASS", "mode": "POSTCHECK",
        "production_write": False, "crm_write": False, "public_write": False,
        "main_fields_changed": False, "media_changed": False, "files": files,
        "public": public, "catalog_unique_ids": unique, "catalog_href_counts": catalog_counts,
        "catalog_design_audit": catalog_audit, "catalog_attempts": catalog_attempts,
        "homepage": {
            "status": "PASS", "counts": home_counts, "ids": home_ids,
            "catalog": home_catalog, "local": home_local,
            "public_http_status": home_status,
            "public_sha256": sha_bytes(public_home.encode()),
            "public_attempts": home_attempts,
            "whatsapp_opacity": 0.90, "errors": [],
        },
        "cars_sha256": current_hash,
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
    expected_mode = args.mode.upper()

    def existing_result() -> dict[str, Any] | None:
        if not receipt.is_file():
            return None
        try:
            candidate = read_json(receipt)
        except Exception:
            return None
        if (
            candidate.get("contract_id") == CONTRACT
            and candidate.get("mode") == expected_mode
            and candidate.get("task108_guard") == TASK108_GUARD
        ):
            return candidate
        return None

    existing = existing_result()
    if existing is not None:
        print(json.dumps({"status": existing.get("status"), "mode": expected_mode, "reused": True}))
        return 0 if existing.get("status") == "PASS" else 1
    value = {"contract_id": CONTRACT, "status": "FAIL", "mode": args.mode.upper(), "errors": []}
    try:
        with locked():
            existing = existing_result()
            if existing is not None:
                value = existing
            else:
                value = {"shadow": shadow, "install": install, "postcheck": postcheck, "rollback": rollback}[args.mode]()
    except Exception as exc:
        value["errors"].append(type(exc).__name__ + ":" + str(exc)[:1000])
        value["finished_at_utc"] = utc_now()
    value["task108_guard"] = TASK108_GUARD
    atomic_json(receipt, value)
    print(json.dumps({"status": value.get("status"), "mode": value.get("mode"), "errors": value.get("errors")}, ensure_ascii=False))
    return 0 if value.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""TASK 096 DATA-ENRICHMENT remote sandbox applier.

This program is intentionally bounded to the closed TASK 096 directory.  It may
read the live CRM only through SQLite read-only/query-only mode for verification.
All schema changes and enrichment writes are made only to the latest TASK 096
sandbox copy.  It never imports production application modules, never restarts a
service, and never writes to site/bot/public paths.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import os
import pathlib
import re
import sqlite3
import tempfile
from typing import Any, Iterable

CONTRACT_ID = "TECH-SPEC-AI-CRM-017-V3.0-TASK096-DATA-ENRICHMENT"
TASK_ID = "task_096"
ROOT = pathlib.Path("/home/Carix/autopilot_inbox/cloud/task_096_tech_spec_ai_crm").resolve()
DATA_DIR = (ROOT / "data_enrichment").resolve()
SANDBOX_DIR = (ROOT / "sandbox").resolve()
LIVE_DB = pathlib.Path("/home/Carix/crm.db")
CARD_RE = re.compile(r"^UA[-‑–—]?0*(\d{1,4})$", re.IGNORECASE)
KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
URL_RE = re.compile(r"^https://[A-Za-z0-9.-]+(?:/[^\s]*)?$")
CURRENCY_RE = re.compile(
    r"(?:[$€£₴₽₩¥]|\b(?:usd|eur|uah|rub|krw|грн|доллар|долар|цена|вартість|price|cost|auction|wholesale|dealer)\b)",
    re.IGNORECASE,
)
PRICE_KEY_RE = re.compile(
    r"(?:price|cost|auction|wholesale|dealer|purchase|acquisition|margin|markup|закуп|себесто|оптов|аукцион|цена|вартість)",
    re.IGNORECASE,
)
SAFE_CONTEXT_TOKENS = {
    "brand", "make", "model", "year", "generation", "body", "type", "engine",
    "volume", "displacement", "fuel", "transmission", "gearbox", "drive", "color",
    "colour", "vin", "mileage", "odometer", "power", "trim", "grade", "series",
    "modification", "car_uid", "uid", "code", "card",
}
FORBIDDEN_CONTEXT_TOKENS = {
    "price", "cost", "auction", "wholesale", "dealer", "purchase", "acquisition",
    "margin", "markup", "client", "phone", "email", "telegram", "whatsapp",
    "address", "comment", "note", "description", "contract", "deposit", "payment",
    "container", "eta", "arrival",
}
STATIC_PRIMARY_KEYS = {
    "brand", "make", "model", "year", "generation", "body", "body_type", "mileage",
    "odometer", "engine", "engine_displacement", "displacement", "volume", "fuel",
    "fuel_type", "transmission", "gearbox", "drive", "drive_type", "color", "colour",
    "vin", "price", "sale_price", "stage", "status", "container", "container_number",
    "eta", "arrival_date", "commercial_terms", "description",
}
PRIMARY_ALIAS_GROUPS = (
    {"brand", "make", "manufacturer"},
    {"model", "vehicle_model"},
    {"year", "model_year", "production_year"},
    {"generation", "series", "platform_generation"},
    {"body", "body_type", "vehicle_type"},
    {"mileage", "odometer", "odometer_reading"},
    {"engine", "engine_name", "engine_type"},
    {"engine_displacement", "displacement", "engine_volume", "volume"},
    {"fuel", "fuel_type"},
    {"transmission", "gearbox", "gearbox_type"},
    {"drive", "drive_type", "drivetrain"},
    {"color", "colour", "exterior_color"},
    {"vin", "vin_code"},
    {"price", "sale_price", "public_price"},
    {"stage", "status", "logistics_stage"},
    {"container", "container_number"},
    {"eta", "arrival_date", "days_to_arrival"},
)
ALLOWED_CATEGORIES = {
    "engine", "dynamics", "consumption", "dimensions", "capacity", "weight",
    "suspension", "brakes", "steering", "wheels", "ecology", "additional",
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def atomic_text(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix="." + path.name + ".",
        suffix=".tmp", delete=False,
    )
    tmp = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def atomic_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n")


def ensure_under(path: pathlib.Path, root: pathlib.Path) -> pathlib.Path:
    resolved = path.resolve()
    if resolved != root and root not in resolved.parents:
        raise RuntimeError("PATH_OUTSIDE_APPROVED_ROOT")
    return resolved


def canonical_uid(value: Any) -> str | None:
    text = str(value or "").strip().replace("‑", "-").replace("–", "-").replace("—", "-")
    match = CARD_RE.fullmatch(text)
    if not match:
        return None
    return f"UA-{int(match.group(1)):04d}"


def norm_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9а-яёіїєґ]+", "_", text, flags=re.IGNORECASE)
    return re.sub(r"_+", "_", text).strip("_")


def norm_value(value: Any) -> str:
    text = str(value or "").strip().lower().replace("ё", "е")
    text = re.sub(r"\s+", " ", text)
    return text


def sha256_json(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def connect_ro(path: pathlib.Path) -> sqlite3.Connection:
    uri = "file:" + str(path.resolve()) + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def connect_rw(path: pathlib.Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path.resolve()), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    return row is not None


def find_sandbox() -> pathlib.Path:
    ensure_under(SANDBOX_DIR, ROOT)
    candidates = sorted(
        [p for p in SANDBOX_DIR.glob("crm_task096_sandbox_*.db") if p.is_file()],
        key=lambda p: (p.stat().st_mtime_ns, p.name),
        reverse=True,
    )
    if not candidates:
        raise RuntimeError("TASK096_SANDBOX_DB_NOT_FOUND")
    return ensure_under(candidates[0], SANDBOX_DIR)


def cars_columns(conn: sqlite3.Connection) -> list[str]:
    if not table_exists(conn, "cars"):
        raise RuntimeError("CARS_TABLE_MISSING")
    return [str(row[1]) for row in conn.execute("PRAGMA table_info(cars)").fetchall()]


def detect_uid_column(conn: sqlite3.Connection, columns: list[str]) -> str:
    preferred = ["car_uid", "uid", "code", "card_id", "internal_id", "slug", "id"]
    ordered = [c for c in preferred if c in columns] + [c for c in columns if c not in preferred]
    for column in ordered:
        quoted = '"' + column.replace('"', '""') + '"'
        try:
            rows = conn.execute(f"SELECT {quoted} FROM cars WHERE {quoted} IS NOT NULL LIMIT 80").fetchall()
        except sqlite3.Error:
            continue
        matches = sum(1 for row in rows if canonical_uid(row[0]))
        if matches >= min(2, max(1, len(rows))):
            return column
    raise RuntimeError("CAR_UID_COLUMN_NOT_FOUND")


def cars_snapshot(conn: sqlite3.Connection) -> dict[str, Any]:
    columns = cars_columns(conn)
    quoted = ",".join('"' + c.replace('"', '""') + '"' for c in columns)
    rows = [dict(row) for row in conn.execute(f"SELECT {quoted} FROM cars ORDER BY rowid").fetchall()]
    return {"columns": columns, "rows": rows, "sha256": sha256_json({"columns": columns, "rows": rows})}


def live_snapshot() -> dict[str, Any]:
    if not LIVE_DB.is_file():
        raise RuntimeError("LIVE_CRM_DB_MISSING")
    with connect_ro(LIVE_DB) as conn:
        conn.execute("PRAGMA query_only=ON")
        quick = conn.execute("PRAGMA quick_check").fetchone()[0]
        snap = cars_snapshot(conn)
        return {
            "opened_mode": "ro",
            "query_only": True,
            "connection_total_changes": conn.total_changes,
            "quick_check": quick,
            "cars_sha256": snap["sha256"],
            "row_count": len(snap["rows"]),
        }


def safe_context_value(column: str, value: Any) -> tuple[str, Any] | None:
    key = norm_key(column)
    if any(token in key for token in FORBIDDEN_CONTEXT_TOKENS):
        return None
    if not any(token in key for token in SAFE_CONTEXT_TOKENS):
        return None
    if value is None or str(value).strip() == "":
        return None
    if "vin" in key:
        vin = re.sub(r"[^A-Za-z0-9]", "", str(value).upper())
        if len(vin) >= 7:
            return "vin_hint", {"wmi": vin[:3], "last4": vin[-4:], "length": len(vin)}
        return None
    text = str(value).strip()
    if CURRENCY_RE.search(text):
        return None
    return key, text[:300]


def export_context() -> dict[str, Any]:
    sandbox = find_sandbox()
    live_before = live_snapshot()
    with connect_ro(sandbox) as conn:
        columns = cars_columns(conn)
        uid_col = detect_uid_column(conn, columns)
        quoted_uid = '"' + uid_col.replace('"', '""') + '"'
        rows = conn.execute("SELECT rowid AS __rowid__, * FROM cars ORDER BY rowid").fetchall()
        registry: dict[str, set[str]] = {}
        if table_exists(conn, "primary_field_registry"):
            for row in conn.execute("SELECT car_uid, field_key FROM primary_field_registry"):
                uid = canonical_uid(row[0])
                if uid:
                    registry.setdefault(uid, set()).add(norm_key(row[1]))
        cars: list[dict[str, Any]] = []
        for row in rows:
            uid = canonical_uid(row[uid_col])
            if not uid:
                continue
            fields: dict[str, Any] = {}
            for column in columns:
                item = safe_context_value(column, row[column])
                if item:
                    fields[item[0]] = item[1]
            cars.append({
                "car_uid": uid,
                "fields": fields,
                "primary_field_keys": sorted(registry.get(uid, set()) | STATIC_PRIMARY_KEYS),
            })
        cars.sort(key=lambda item: item["car_uid"])
        quick = conn.execute("PRAGMA quick_check").fetchone()[0]
    live_after = live_snapshot()
    if live_before["cars_sha256"] != live_after["cars_sha256"]:
        raise RuntimeError("LIVE_CRM_CHANGED_DURING_CONTEXT_EXPORT")
    result = {
        "contract_id": CONTRACT_ID,
        "task_id": TASK_ID,
        "phase": "CONTEXT_EXPORT",
        "status": "PASS",
        "created_at_utc": utc_now(),
        "sandbox_db_name": sandbox.name,
        "sandbox_quick_check": quick,
        "cards": cars,
        "cards_found": [item["car_uid"] for item in cars],
        "production_touched": False,
        "live_crm_write": False,
        "main_fields_changed": False,
        "public_path_write": False,
        "services_restarted": False,
        "autopublication": False,
        "purchase_price_extracted": False,
        "purchase_price_logged": False,
        "purchase_price_uploaded": False,
        "production_authorized": False,
    }
    atomic_json(DATA_DIR / "car_context.json", result)
    return result


def ensure_enrichment_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS additional_specification_meta (
            car_uid TEXT NOT NULL,
            field_key TEXT NOT NULL,
            label_ru TEXT NOT NULL,
            category TEXT NOT NULL,
            unit TEXT,
            evidence_count INTEGER NOT NULL DEFAULT 1,
            source_domains_json TEXT NOT NULL DEFAULT '[]',
            verification_status TEXT NOT NULL DEFAULT 'VERIFIED',
            model_match_score REAL NOT NULL DEFAULT 0.0,
            is_manual INTEGER NOT NULL DEFAULT 0 CHECK (is_manual IN (0,1)),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (car_uid, field_key)
        );
        CREATE TABLE IF NOT EXISTS data_enrichment_runs (
            run_id TEXT PRIMARY KEY,
            mode TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            status TEXT NOT NULL,
            processed_uids_json TEXT NOT NULL DEFAULT '[]',
            inserted_count INTEGER NOT NULL DEFAULT 0,
            rejected_count INTEGER NOT NULL DEFAULT 0,
            production_touched INTEGER NOT NULL DEFAULT 0 CHECK (production_touched = 0)
        );
        """
    )


def primary_keys_for(conn: sqlite3.Connection, uid: str) -> set[str]:
    keys = set(STATIC_PRIMARY_KEYS)
    if table_exists(conn, "primary_field_registry"):
        for row in conn.execute("SELECT field_key FROM primary_field_registry WHERE car_uid=?", (uid,)):
            keys.add(norm_key(row[0]))
    expanded = set(keys)
    for group in PRIMARY_ALIAS_GROUPS:
        if keys & group:
            expanded |= group
    return expanded


def is_primary_collision(field_key: str, primary_keys: set[str]) -> bool:
    key = norm_key(field_key)
    if key in primary_keys:
        return True
    for group in PRIMARY_ALIAS_GROUPS:
        if key in group and primary_keys & group:
            return True
    return False


def source_domains(urls: Iterable[str]) -> list[str]:
    domains: set[str] = set()
    for url in urls:
        match = re.match(r"^https://([^/]+)", url)
        if match:
            domains.add(match.group(1).lower().removeprefix("www."))
    return sorted(domains)


def record_rejection(conn: sqlite3.Connection, uid: str, key: str, reason: str) -> None:
    conn.execute(
        "INSERT INTO additional_specification_rejections(car_uid, field_key, reason) VALUES(?,?,?)",
        (uid, key[:128], reason[:128]),
    )


def render_preview(conn: sqlite3.Connection, uid: str) -> str:
    rows = conn.execute(
        """
        SELECT a.field_key, a.field_value, m.label_ru, m.category, m.unit
        FROM additional_specification a
        LEFT JOIN additional_specification_meta m
          ON m.car_uid=a.car_uid AND m.field_key=a.field_key
        WHERE a.car_uid=?
        ORDER BY CASE COALESCE(m.category,'additional')
          WHEN 'engine' THEN 1 WHEN 'dynamics' THEN 2 WHEN 'consumption' THEN 3
          WHEN 'dimensions' THEN 4 WHEN 'capacity' THEN 5 WHEN 'weight' THEN 6
          WHEN 'suspension' THEN 7 WHEN 'brakes' THEN 8 WHEN 'steering' THEN 9
          WHEN 'wheels' THEN 10 WHEN 'ecology' THEN 11 ELSE 12 END,
          COALESCE(m.label_ru, a.field_key)
        """,
        (uid,),
    ).fetchall()
    groups: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        groups.setdefault(str(row["category"] or "additional"), []).append(row)
    titles = {
        "engine": "Двигатель", "dynamics": "Динамика", "consumption": "Расход",
        "dimensions": "Размеры", "capacity": "Вместимость", "weight": "Масса",
        "suspension": "Подвеска", "brakes": "Тормоза", "steering": "Рулевое управление",
        "wheels": "Колёса", "ecology": "Экология", "additional": "Дополнительно",
    }
    sections: list[str] = []
    for category, items in groups.items():
        lines = []
        for row in items:
            label = html.escape(str(row["label_ru"] or row["field_key"]))
            value = html.escape(str(row["field_value"]))
            lines.append(f"<div class='spec-row'><dt>{label}</dt><dd>{value}</dd></div>")
        sections.append(
            "<section><h2>%s</h2><dl>%s</dl></section>" % (html.escape(titles.get(category, category)), "".join(lines))
        )
    empty = "<p class='empty'>Подтверждённые дополнительные характеристики пока не найдены.</p>" if not sections else ""
    return """<!doctype html>
<html lang='ru'><head><meta charset='utf-8'><meta name='robots' content='noindex,nofollow'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>UA-0015 — Дополнительная спецификация — SANDBOX</title>
<style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#11100d;color:#f4ead4;font:16px/1.45 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}.wrap{max-width:980px;margin:auto;padding:28px}.guard{border:1px solid #b28a45;background:#211b12;padding:12px 16px;border-radius:12px;color:#e9c985}.card{margin-top:18px;border:1px solid #4c402d;border-radius:18px;background:#17140f;box-shadow:0 18px 60px rgba(0,0,0,.28);overflow:hidden}.head{padding:26px 28px;border-bottom:1px solid #3b3225}.eyebrow{letter-spacing:.16em;text-transform:uppercase;color:#c9a65e;font-size:12px}.head h1{margin:8px 0 0;font-family:Georgia,serif;font-weight:500;font-size:34px}.content{padding:10px 28px 30px}section{padding:18px 0;border-bottom:1px solid #30291f}section:last-child{border-bottom:0}h2{font:500 21px Georgia,serif;color:#d8b873;margin:0 0 10px}.spec-row{display:grid;grid-template-columns:minmax(180px,1fr) minmax(180px,1.2fr);gap:18px;padding:9px 0}dt{color:#bdb3a2}dd{margin:0;text-align:right;font-weight:600}.empty{padding:28px 0;color:#bdb3a2}@media(max-width:640px){.wrap{padding:14px}.head,.content{padding-left:18px;padding-right:18px}.head h1{font-size:27px}.spec-row{grid-template-columns:1fr;gap:3px}dd{text-align:left}}
</style></head><body><main class='wrap'><div class='guard'>SANDBOX · Не опубликовано · Рабочая CRM, бот и сайт не изменены</div>
<article class='card'><header class='head'><div class='eyebrow'>UA ART · Technical data canary</div><h1>UA-0015 · Дополнительная спецификация</h1></header>
<div class='content'>%s%s</div></article></main></body></html>""" % ("".join(sections), empty)


def apply_candidate(candidate_path: pathlib.Path, expected_mode: str) -> dict[str, Any]:
    candidate_path = ensure_under(candidate_path, DATA_DIR)
    raw = json.loads(candidate_path.read_text(encoding="utf-8"))
    if raw.get("contract_id") != CONTRACT_ID:
        raise RuntimeError("CANDIDATE_CONTRACT_MISMATCH")
    if raw.get("mode") != expected_mode:
        raise RuntimeError("CANDIDATE_MODE_MISMATCH")
    cars = raw.get("cars")
    if not isinstance(cars, list):
        raise RuntimeError("CANDIDATE_CARS_INVALID")
    requested = [canonical_uid(item.get("car_uid")) for item in cars if isinstance(item, dict)]
    if expected_mode == "canary" and requested != ["UA-0015"]:
        raise RuntimeError("CANARY_SCOPE_MUST_BE_UA0015_ONLY")
    if expected_mode == "batch":
        allowed = {f"UA-{n:04d}" for n in range(1, 17)}
        if any(uid not in allowed for uid in requested if uid):
            raise RuntimeError("BATCH_SCOPE_OUTSIDE_UA0001_UA0016")

    sandbox = find_sandbox()
    live_before = live_snapshot()
    run_id = f"{expected_mode}-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    inserted = 0
    rejected = 0
    processed: list[str] = []
    per_car: list[dict[str, Any]] = []

    with connect_rw(sandbox) as conn:
        ensure_enrichment_tables(conn)
        before = cars_snapshot(conn)
        columns = before["columns"]
        uid_col = detect_uid_column(conn, columns)
        existing_uids = {
            canonical_uid(row[0]) for row in conn.execute(
                'SELECT "' + uid_col.replace('"', '""') + '" FROM cars'
            ).fetchall()
        }
        conn.execute(
            "INSERT INTO data_enrichment_runs(run_id,mode,started_at,status) VALUES(?,?,?,?)",
            (run_id, expected_mode, utc_now(), "RUNNING"),
        )
        for car in cars:
            if not isinstance(car, dict):
                continue
            uid = canonical_uid(car.get("car_uid"))
            if not uid or uid not in existing_uids:
                rejected += 1
                continue
            match_score = float((car.get("match") or {}).get("score") or 0.0)
            status = str(car.get("status") or "MATCHED")
            facts = car.get("facts") if isinstance(car.get("facts"), list) else []
            primary_keys = primary_keys_for(conn, uid)
            car_inserted = 0
            car_rejected = 0
            if status == "NO_CONFIDENT_MATCH":
                facts = []
            for fact in facts:
                if not isinstance(fact, dict):
                    car_rejected += 1
                    rejected += 1
                    continue
                key = norm_key(fact.get("field_key"))
                label = str(fact.get("label_ru") or key).strip()[:120]
                category = norm_key(fact.get("category") or "additional")
                display_value = str(fact.get("display_value") or fact.get("value") or "").strip()
                unit = str(fact.get("unit") or "").strip()[:40]
                confidence = float(fact.get("confidence") or 0.0)
                urls = [str(url).strip() for url in (fact.get("source_urls") or []) if isinstance(url, str)]
                reason: str | None = None
                if not KEY_RE.fullmatch(key):
                    reason = "INVALID_FIELD_KEY"
                elif PRICE_KEY_RE.search(key) or CURRENCY_RE.search(display_value):
                    reason = "PRICE_FIELD_FORBIDDEN"
                elif is_primary_collision(key, primary_keys):
                    reason = "MANUAL_FIELD_PROTECTED"
                elif category not in ALLOWED_CATEGORIES:
                    reason = "INVALID_CATEGORY"
                elif not display_value or len(display_value) > 500:
                    reason = "INVALID_VALUE"
                elif confidence < 0.78 or match_score < 0.82:
                    reason = "LOW_CONFIDENCE"
                elif not urls or any(not URL_RE.fullmatch(url) for url in urls):
                    reason = "SOURCE_EVIDENCE_MISSING"
                elif any(CURRENCY_RE.search(url) for url in urls):
                    reason = "PRICE_SOURCE_URL_FORBIDDEN"
                if reason:
                    record_rejection(conn, uid, key or "invalid", reason)
                    car_rejected += 1
                    rejected += 1
                    continue
                manual = conn.execute(
                    "SELECT is_manual FROM additional_specification_meta WHERE car_uid=? AND field_key=?",
                    (uid, key),
                ).fetchone()
                if manual and int(manual[0]) == 1:
                    record_rejection(conn, uid, key, "MANUAL_FIELD_PROTECTED")
                    car_rejected += 1
                    rejected += 1
                    continue
                source_url = urls[0]
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO additional_specification
                    (car_uid,field_key,field_value,normalized_value,source,source_url,confidence,is_price_field)
                    VALUES(?,?,?,?,?,?,?,0)
                    """,
                    (uid, key, display_value, norm_value(display_value), "AI", source_url, confidence),
                )
                if cursor.rowcount == 0:
                    record_rejection(conn, uid, key, "DUPLICATE")
                    car_rejected += 1
                    rejected += 1
                    continue
                conn.execute(
                    """
                    INSERT INTO additional_specification_meta
                    (car_uid,field_key,label_ru,category,unit,evidence_count,source_domains_json,
                     verification_status,model_match_score,is_manual,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,0,datetime('now'))
                    ON CONFLICT(car_uid,field_key) DO UPDATE SET
                      label_ru=excluded.label_ru,
                      category=excluded.category,
                      unit=excluded.unit,
                      evidence_count=excluded.evidence_count,
                      source_domains_json=excluded.source_domains_json,
                      verification_status=excluded.verification_status,
                      model_match_score=excluded.model_match_score,
                      updated_at=datetime('now')
                    WHERE additional_specification_meta.is_manual=0
                    """,
                    (
                        uid, key, label, category, unit, len(urls),
                        json.dumps(source_domains(urls), ensure_ascii=False), "VERIFIED", match_score,
                    ),
                )
                car_inserted += 1
                inserted += 1
            processed.append(uid)
            per_car.append({
                "car_uid": uid,
                "status": status,
                "match_score": match_score,
                "facts_received": len(facts),
                "inserted": car_inserted,
                "rejected": car_rejected,
            })
        after = cars_snapshot(conn)
        if before["sha256"] != after["sha256"]:
            conn.rollback()
            raise RuntimeError("SANDBOX_MAIN_CARS_CHANGED")
        quick = conn.execute("PRAGMA quick_check").fetchone()[0]
        if quick != "ok":
            conn.rollback()
            raise RuntimeError("SANDBOX_QUICK_CHECK_FAIL")
        conn.execute(
            """
            UPDATE data_enrichment_runs
               SET finished_at=?, status='PASS', processed_uids_json=?, inserted_count=?, rejected_count=?
             WHERE run_id=?
            """,
            (utc_now(), json.dumps(processed), inserted, rejected, run_id),
        )
        conn.commit()
        preview = render_preview(conn, "UA-0015")
        total_rows = conn.execute("SELECT COUNT(*) FROM additional_specification").fetchone()[0]
        ua0015_rows = conn.execute(
            "SELECT COUNT(*) FROM additional_specification WHERE car_uid='UA-0015'"
        ).fetchone()[0]

    live_after = live_snapshot()
    if live_before["cars_sha256"] != live_after["cars_sha256"]:
        raise RuntimeError("LIVE_CRM_CHANGED_DURING_SANDBOX_APPLY")
    preview_path = DATA_DIR / "ua0015_preview.html"
    atomic_text(preview_path, preview)
    result = {
        "contract_id": CONTRACT_ID,
        "task_id": TASK_ID,
        "phase": "DATA_CANARY" if expected_mode == "canary" else "DATA_BATCH",
        "mode": expected_mode,
        "status": "PASS",
        "started_from_candidate": candidate_path.name,
        "finished_at_utc": utc_now(),
        "sandbox_db_name": sandbox.name,
        "sandbox_quick_check": "ok",
        "processed_uids": processed,
        "per_car": per_car,
        "inserted_count": inserted,
        "rejected_count": rejected,
        "additional_spec_total_rows": int(total_rows),
        "ua0015_additional_rows": int(ua0015_rows),
        "ua0015_preview_relative_path": "data_enrichment/ua0015_preview.html",
        "production_touched": False,
        "live_crm_write": False,
        "main_fields_changed": False,
        "public_path_write": False,
        "bot_code_changed": False,
        "services_restarted": False,
        "autopublication": False,
        "purchase_price_extracted": False,
        "purchase_price_logged": False,
        "purchase_price_uploaded": False,
        "production_authorized": False,
        "source_urls_exposed_in_preview": False,
    }
    receipt_name = "receipt_canary.json" if expected_mode == "canary" else "receipt_batch.json"
    atomic_json(DATA_DIR / receipt_name, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("export", "apply-canary", "apply-batch"))
    parser.add_argument("--candidate")
    args = parser.parse_args()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        if args.command == "export":
            result = export_context()
        else:
            if not args.candidate:
                raise RuntimeError("CANDIDATE_PATH_REQUIRED")
            mode = "canary" if args.command == "apply-canary" else "batch"
            result = apply_candidate(pathlib.Path(args.candidate), mode)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as exc:
        mode = "export" if args.command == "export" else ("canary" if args.command == "apply-canary" else "batch")
        result = {
            "contract_id": CONTRACT_ID,
            "task_id": TASK_ID,
            "phase": "CONTEXT_EXPORT" if mode == "export" else ("DATA_CANARY" if mode == "canary" else "DATA_BATCH"),
            "mode": mode,
            "status": "FAIL",
            "finished_at_utc": utc_now(),
            "errors": [type(exc).__name__ + ":" + str(exc)[:700]],
            "production_touched": False,
            "live_crm_write": False,
            "main_fields_changed": False,
            "public_path_write": False,
            "bot_code_changed": False,
            "services_restarted": False,
            "autopublication": False,
            "purchase_price_extracted": False,
            "purchase_price_logged": False,
            "purchase_price_uploaded": False,
            "production_authorized": False,
        }
        name = "car_context.json" if mode == "export" else ("receipt_canary.json" if mode == "canary" else "receipt_batch.json")
        atomic_json(DATA_DIR / name, result)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

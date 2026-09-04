#!/usr/bin/env python3
"""Automatic VIN-triggered additional-specification service for UA ART.

The live CRM is opened read-only.  Enrichment, provenance, job state and
operator edits live in a separate SQLite sidecar.  A valid VIN already saved
by the existing CRM flow creates one idempotent job for this policy version.

Only already-published cards may be refreshed automatically.  This service
never creates the initial public listing and never changes price, status or
any other primary CRM field.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import re
import sqlite3
import threading
import time
from typing import Any, Callable, Iterable

import source_policy


MAIN_DB = pathlib.Path(os.environ.get("UA_ART_CRM_DB", "/home/Carix/crm.db"))
SPEC_DB = pathlib.Path(os.environ.get("UA_ART_SPEC_DB", "/home/Carix/vin_specs.db"))
SCAN_SECONDS = max(15, int(os.environ.get("UA_ART_VIN_SCAN_SECONDS", "30")))
MAX_ATTEMPTS = 3
WORKER_NAME = "uaart-vin-spec-v2"
CARD_RE = re.compile(r"^UA[-‑–—]?0*(\d{1,6})$", re.IGNORECASE)

_worker_lock = threading.Lock()
_worker: threading.Thread | None = None
_stop_event = threading.Event()


class ServiceError(RuntimeError):
    pass


def utc_now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def canonical_uid(value: Any) -> str | None:
    text = str(value or "").strip().replace("‑", "-").replace("–", "-").replace("—", "-")
    match = CARD_RE.fullmatch(text)
    return "UA-%04d" % int(match.group(1)) if match else None


def _connect(path: pathlib.Path, readonly: bool) -> sqlite3.Connection:
    if readonly:
        conn = sqlite3.connect("file:" + str(path.resolve()) + "?mode=ro", uri=True, timeout=30)
        conn.execute("PRAGMA query_only=ON")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path.resolve()), timeout=30)
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def connect_main() -> sqlite3.Connection:
    if not MAIN_DB.is_file():
        raise ServiceError("MAIN_CRM_MISSING")
    return _connect(MAIN_DB, True)


def connect_spec(readonly: bool = False) -> sqlite3.Connection:
    return _connect(SPEC_DB, readonly)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def ensure_schema() -> None:
    with connect_spec(False) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS additional_specification (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                car_uid TEXT NOT NULL,
                field_key TEXT NOT NULL,
                field_value TEXT NOT NULL,
                normalized_value TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'AUTO',
                source_url TEXT,
                confidence REAL NOT NULL DEFAULT 0.0,
                is_price_field INTEGER NOT NULL DEFAULT 0 CHECK(is_price_field=0),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(car_uid, field_key)
            );
            CREATE TABLE IF NOT EXISTS additional_specification_meta (
                car_uid TEXT NOT NULL,
                field_key TEXT NOT NULL,
                label_ru TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'additional',
                unit TEXT NOT NULL DEFAULT '',
                evidence_count INTEGER NOT NULL DEFAULT 0,
                source_domains_json TEXT NOT NULL DEFAULT '[]',
                source_urls_json TEXT NOT NULL DEFAULT '[]',
                verification_status TEXT NOT NULL DEFAULT 'VERIFIED',
                model_match_score REAL NOT NULL DEFAULT 0.0,
                is_manual INTEGER NOT NULL DEFAULT 0,
                is_visible INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(car_uid, field_key)
            );
            CREATE TABLE IF NOT EXISTS additional_specification_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                car_uid TEXT NOT NULL,
                field_key TEXT NOT NULL,
                action TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT,
                actor_id INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS additional_specification_rejections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                car_uid TEXT NOT NULL,
                field_key TEXT,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS vin_spec_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                car_id INTEGER,
                car_uid TEXT NOT NULL,
                vin TEXT NOT NULL,
                policy_version TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                attempts INTEGER NOT NULL DEFAULT 0,
                facts_count INTEGER NOT NULL DEFAULT 0,
                source_status_json TEXT NOT NULL DEFAULT '{}',
                last_error TEXT,
                requested_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                site_sync_status TEXT NOT NULL DEFAULT 'NOT_REQUIRED',
                site_sync_detail TEXT,
                UNIQUE(car_uid, vin, policy_version)
            );
            CREATE INDEX IF NOT EXISTS vin_spec_jobs_status_idx
                ON vin_spec_jobs(status, requested_at, id);
            CREATE TABLE IF NOT EXISTS vin_spec_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        conn.commit()
    try:
        os.chmod(SPEC_DB, 0o600)
    except OSError:
        pass


def _quoted(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [str(row[1]) for row in conn.execute("PRAGMA table_info(" + _quoted(table) + ")")]


def _pick(row: dict[str, Any], *names: str) -> Any:
    lowered = {str(key).casefold(): value for key, value in row.items()}
    for name in names:
        value = lowered.get(name.casefold())
        if value is not None and str(value).strip() != "":
            return value
    return None


def _engine_cc(row: dict[str, Any]) -> int | None:
    value = _pick(
        row, "engine_cc", "displacement", "engine_displacement", "obem",
        "engine_volume", "volume", "dvigatel", "engine",
    )
    text = str(value or "").replace(" ", "").replace(",", ".")
    match = re.search(r"(?<!\d)(\d{3,4})(?!\d)", text)
    if match:
        number = int(match.group(1))
        return number if 500 <= number <= 9000 else None
    match = re.search(r"(?<!\d)([0-9](?:\.[0-9])?)(?:l|л|литр)", text, re.I)
    if match:
        return int(round(float(match.group(1)) * 1000))
    return None


def _published(row: dict[str, Any]) -> bool:
    value = _pick(row, "published", "is_published", "opublikovano", "public")
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes", "да", "так", "published"}
    return bool(value)


def _card_from_row(row: dict[str, Any]) -> dict[str, Any] | None:
    uid = canonical_uid(_pick(row, "auto_number", "car_uid", "uid", "code", "slug"))
    raw_vin = _pick(row, "vin", "vin_code")
    if not uid or not raw_vin:
        return None
    try:
        vin = source_policy.normalize_vin(raw_vin)
    except source_policy.SourcePolicyError:
        return None
    year = _pick(row, "year", "model_year", "god", "production_year")
    if year:
        match = re.search(r"(?:19|20)\d{2}", str(year))
        year = match.group(0) if match else str(year).strip()
    fuel = _pick(row, "fuel", "fuel_type", "toplivo")
    engine_text = _pick(row, "engine", "dvigatel")
    if not fuel and engine_text:
        token = re.search(r"(дизель|diesel|бензин|gasoline|lpg|lpi|газ|hybrid|гибрид)", str(engine_text), re.I)
        fuel = token.group(1) if token else None
    return {
        "car_id": _pick(row, "id"),
        "car_uid": uid,
        "vin": vin,
        "brand": _pick(row, "brand", "make", "marka", "manufacturer"),
        "model": _pick(row, "model", "vehicle_model"),
        "year": year,
        "fuel": fuel,
        "engine_cc": _engine_cc(row),
        "transmission": _pick(row, "transmission", "gearbox", "korobka", "kpp"),
        "published": _published(row),
    }


def read_cards() -> list[dict[str, Any]]:
    with connect_main() as conn:
        if not _table_exists(conn, "cars"):
            raise ServiceError("CARS_TABLE_MISSING")
        rows = [dict(row) for row in conn.execute("SELECT rowid AS __rowid__, * FROM cars ORDER BY rowid")]
        if conn.total_changes != 0:
            raise ServiceError("MAIN_CRM_WRITE_GUARD")
    cards = [card for row in rows if (card := _card_from_row(row)) is not None]
    return sorted(cards, key=lambda item: item["car_uid"])


def _safe_text(value: Any, maximum: int = 500) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text or len(text) > maximum or source_policy.PRICE_RE.search(text):
        raise ServiceError("UNSAFE_ADDITIONAL_VALUE")
    return text


def migrate_legacy_once() -> dict[str, int]:
    """Copy old additional rows out of crm.db without ever writing crm.db."""
    ensure_schema()
    with connect_spec(False) as side:
        done = side.execute(
            "SELECT value FROM vin_spec_state WHERE key='legacy_migration_v1'"
        ).fetchone()
        if done:
            return {"facts": 0, "meta": 0}
    copied_facts = copied_meta = 0
    with connect_main() as main, connect_spec(False) as side:
        if not _table_exists(main, "additional_specification"):
            side.execute(
                "INSERT OR REPLACE INTO vin_spec_state(key,value,updated_at) VALUES(?,?,?)",
                ("legacy_migration_v1", "NO_TABLE", utc_now()),
            )
            side.commit()
            return {"facts": 0, "meta": 0}
        fact_columns = set(_columns(main, "additional_specification"))
        for raw in main.execute("SELECT * FROM additional_specification"):
            row = dict(raw)
            uid = canonical_uid(row.get("car_uid"))
            key = str(row.get("field_key") or "").strip()
            value = str(row.get("field_value") or "").strip()
            if not uid or not key or not value or row.get("is_price_field") or source_policy.PRICE_RE.search(key + " " + value):
                continue
            cursor = side.execute(
                """INSERT OR IGNORE INTO additional_specification
                   (car_uid,field_key,field_value,normalized_value,source,source_url,confidence,is_price_field,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    uid, key, value,
                    str(row.get("normalized_value") or value.casefold()),
                    str(row.get("source") or "LEGACY"),
                    row.get("source_url") if "source_url" in fact_columns else None,
                    float(row.get("confidence") or 0.0), 0,
                    str(row.get("created_at") or utc_now()),
                ),
            )
            copied_facts += max(0, cursor.rowcount)
        if _table_exists(main, "additional_specification_meta"):
            meta_columns = set(_columns(main, "additional_specification_meta"))
            for raw in main.execute("SELECT * FROM additional_specification_meta"):
                row = dict(raw)
                uid = canonical_uid(row.get("car_uid"))
                key = str(row.get("field_key") or "").strip()
                if not uid or not key or source_policy.PRICE_RE.search(key):
                    continue
                cursor = side.execute(
                    """INSERT OR IGNORE INTO additional_specification_meta
                       (car_uid,field_key,label_ru,category,unit,evidence_count,
                        source_domains_json,source_urls_json,verification_status,
                        model_match_score,is_manual,is_visible,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        uid, key, str(row.get("label_ru") or key),
                        str(row.get("category") or "additional"),
                        str(row.get("unit") or ""), int(row.get("evidence_count") or 0),
                        str(row.get("source_domains_json") or "[]"),
                        str(row.get("source_urls_json") or "[]") if "source_urls_json" in meta_columns else "[]",
                        str(row.get("verification_status") or "VERIFIED"),
                        float(row.get("model_match_score") or 0.0),
                        int(row.get("is_manual") or 0), int(row.get("is_visible") if row.get("is_visible") is not None else 1),
                        str(row.get("created_at") or utc_now()), str(row.get("updated_at") or utc_now()),
                    ),
                )
                copied_meta += max(0, cursor.rowcount)
        side.execute(
            "INSERT OR REPLACE INTO vin_spec_state(key,value,updated_at) VALUES(?,?,?)",
            ("legacy_migration_v1", json.dumps({"facts": copied_facts, "meta": copied_meta}), utc_now()),
        )
        side.commit()
    return {"facts": copied_facts, "meta": copied_meta}


def enqueue_card(card: dict[str, Any], *, force: bool = False) -> bool:
    uid = canonical_uid(card.get("car_uid"))
    vin = source_policy.normalize_vin(card.get("vin"))
    if not uid:
        raise ServiceError("INVALID_CARD_UID")
    ensure_schema()
    now = utc_now()
    with connect_spec(False) as conn:
        prior = conn.execute(
            """SELECT vin FROM vin_spec_jobs WHERE car_uid=? AND vin<>?
               AND status<>'SUPERSEDED' ORDER BY id DESC LIMIT 1""",
            (uid, vin),
        ).fetchone()
        if prior:
            # A corrected/replaced VIN must never inherit facts from the old
            # vehicle.  Automated rows are removed; operator rows are hidden
            # and explicitly require review before they can be shown again.
            conn.execute(
                """DELETE FROM additional_specification WHERE car_uid=? AND field_key NOT IN
                   (SELECT field_key FROM additional_specification_meta
                    WHERE car_uid=? AND is_manual=1)""",
                (uid, uid),
            )
            conn.execute(
                """UPDATE additional_specification_meta SET is_visible=0,
                   verification_status='VIN_CHANGED_REVIEW',updated_at=?
                   WHERE car_uid=? AND is_manual=1""",
                (now, uid),
            )
            conn.execute(
                "UPDATE vin_spec_jobs SET status='SUPERSEDED',finished_at=? WHERE car_uid=? AND vin<>? AND status<>'SUPERSEDED'",
                (now, uid, vin),
            )
            conn.execute(
                """INSERT INTO additional_specification_audit
                   (car_uid,field_key,action,old_value,new_value)
                   VALUES(?,?,?,?,?)""",
                (uid, "__vin__", "VIN_SUPERSEDED", str(prior["vin"]), vin),
            )
        row = conn.execute(
            "SELECT id,status,attempts FROM vin_spec_jobs WHERE car_uid=? AND vin=? AND policy_version=?",
            (uid, vin, source_policy.POLICY_VERSION),
        ).fetchone()
        if row:
            if force:
                conn.execute(
                    """UPDATE vin_spec_jobs SET status='PENDING',attempts=0,last_error=NULL,
                       requested_at=?,started_at=NULL,finished_at=NULL,
                       site_sync_status='NOT_REQUIRED',site_sync_detail=NULL WHERE id=?""",
                    (now, int(row["id"])),
                )
                conn.commit()
                return True
            if row["status"] == "FAILED" and int(row["attempts"]) < MAX_ATTEMPTS:
                conn.execute(
                    "UPDATE vin_spec_jobs SET status='PENDING',requested_at=?,last_error=NULL WHERE id=?",
                    (now, int(row["id"])),
                )
                conn.commit()
                return True
            return False
        conn.execute(
            """INSERT INTO vin_spec_jobs
               (car_id,car_uid,vin,policy_version,status,requested_at)
               VALUES(?,?,?,?,?,?)""",
            (card.get("car_id"), uid, vin, source_policy.POLICY_VERSION, "PENDING", now),
        )
        conn.commit()
    return True


def scan_new_vins() -> dict[str, Any]:
    ensure_schema()
    # Retired policy jobs must not delay the current automatic backfill.
    with connect_spec(False) as conn:
        conn.execute(
            """UPDATE vin_spec_jobs SET status='SUPERSEDED',finished_at=?
               WHERE policy_version<>? AND status IN ('PENDING','RUNNING')""",
            (utc_now(), source_policy.POLICY_VERSION),
        )
        conn.commit()
    cards = read_cards()
    queued = 0
    for card in cards:
        queued += int(enqueue_card(card))
    return {"valid_vins": len(cards), "queued": queued, "card_uids": [item["car_uid"] for item in cards]}


def _claim() -> dict[str, Any] | None:
    ensure_schema()
    with connect_spec(False) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """SELECT * FROM vin_spec_jobs
               WHERE status='PENDING' AND attempts<? AND policy_version=?
               ORDER BY attempts,requested_at,id LIMIT 1""",
            (MAX_ATTEMPTS, source_policy.POLICY_VERSION),
        ).fetchone()
        if not row:
            conn.commit()
            return None
        updated = conn.execute(
            """UPDATE vin_spec_jobs SET status='RUNNING',attempts=attempts+1,
               started_at=?,last_error=NULL WHERE id=? AND status='PENDING'""",
            (utc_now(), int(row["id"])),
        )
        conn.commit()
        return dict(conn.execute("SELECT * FROM vin_spec_jobs WHERE id=?", (int(row["id"]),)).fetchone()) if updated.rowcount == 1 else None


def _current_card(uid: str, vin: str) -> dict[str, Any] | None:
    for card in read_cards():
        if card["car_uid"] == uid and card["vin"] == vin:
            return card
    return None


def _store_facts(uid: str, facts: Iterable[dict[str, Any]]) -> int:
    written = 0
    with connect_spec(False) as conn:
        conn.execute("BEGIN IMMEDIATE")
        for fact in facts:
            key = str(fact.get("field_key") or "").strip()
            try:
                value = _safe_text(fact.get("display_value"))
                label = _safe_text(fact.get("label_ru"), 120)
            except ServiceError:
                conn.execute(
                    "INSERT INTO additional_specification_rejections(car_uid,field_key,reason) VALUES(?,?,?)",
                    (uid, key or None, "UNSAFE_VALUE"),
                )
                continue
            if not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", key) or key in source_policy.BLOCKED_PRIMARY_KEYS:
                conn.execute(
                    "INSERT INTO additional_specification_rejections(car_uid,field_key,reason) VALUES(?,?,?)",
                    (uid, key or None, "PRIMARY_OR_INVALID_KEY"),
                )
                continue
            domains = [str(item) for item in fact.get("source_domains") or [] if str(item) in source_policy.SOURCE_DOMAINS]
            urls = [str(item) for item in fact.get("source_urls") or [] if source_policy.source_domain(str(item)) in domains]
            if not domains or not urls:
                conn.execute(
                    "INSERT INTO additional_specification_rejections(car_uid,field_key,reason) VALUES(?,?,?)",
                    (uid, key, "NO_ALLOWED_PROVENANCE"),
                )
                continue
            manual = conn.execute(
                "SELECT is_manual FROM additional_specification_meta WHERE car_uid=? AND field_key=?",
                (uid, key),
            ).fetchone()
            if manual and int(manual[0] or 0) == 1:
                continue
            conn.execute(
                """INSERT INTO additional_specification
                   (car_uid,field_key,field_value,normalized_value,source,source_url,confidence,is_price_field)
                   VALUES(?,?,?,?,?,?,?,0)
                   ON CONFLICT(car_uid,field_key) DO UPDATE SET
                     field_value=excluded.field_value,normalized_value=excluded.normalized_value,
                     source=excluded.source,source_url=excluded.source_url,
                     confidence=excluded.confidence,is_price_field=0""",
                (
                    uid, key, value, value.casefold(), "AUTO_10SRC", urls[0],
                    min(1.0, max(0.0, float(fact.get("confidence") or 0.0))),
                ),
            )
            conn.execute(
                """INSERT INTO additional_specification_meta
                   (car_uid,field_key,label_ru,category,unit,evidence_count,
                    source_domains_json,source_urls_json,verification_status,
                    model_match_score,is_manual,is_visible,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(car_uid,field_key) DO UPDATE SET
                    label_ru=excluded.label_ru,category=excluded.category,unit=excluded.unit,
                    evidence_count=excluded.evidence_count,
                    source_domains_json=excluded.source_domains_json,
                    source_urls_json=excluded.source_urls_json,
                    verification_status=excluded.verification_status,
                    model_match_score=excluded.model_match_score,
                    updated_at=excluded.updated_at""",
                (
                    uid, key, label, str(fact.get("category") or "additional"),
                    str(fact.get("unit") or "")[:40], int(fact.get("evidence_count") or len(domains)),
                    json.dumps(domains, ensure_ascii=False), json.dumps(urls, ensure_ascii=False),
                    "VERIFIED_10SRC", float(fact.get("confidence") or 0.0), 0, 1, utc_now(),
                ),
            )
            written += 1
        conn.commit()
    return written


def _refresh_published(card: dict[str, Any]) -> tuple[str, str]:
    if not card.get("published"):
        return "NOT_REQUIRED", "карточка ещё не опубликована"
    try:
        import publikaciya
        result = publikaciya.opublikovat(card["car_uid"])
        if isinstance(result, tuple):
            ok, detail = result[0], result[1] if len(result) > 1 else ""
        else:
            ok, detail = bool(result), str(result)
        return ("PASS", str(detail)[:500]) if ok is True else ("FAIL", str(detail)[:500])
    except Exception as exc:  # publication is recorded but never hides stored facts
        return "FAIL", type(exc).__name__ + ":" + str(exc)[:400]


def process_one(*, enricher: Callable[[dict[str, Any]], dict[str, Any]] = source_policy.enrich) -> dict[str, Any] | None:
    job = _claim()
    if not job:
        return None
    uid, vin = str(job["car_uid"]), str(job["vin"])
    try:
        card = _current_card(uid, vin)
        if not card:
            raise ServiceError("CARD_OR_VIN_CHANGED")
        result = enricher(card)
        facts = list(result.get("facts") or [])
        written = _store_facts(uid, facts)
        status = "READY" if result.get("status") == "READY" and written >= 1 else "NEEDS_REVIEW"
        # A partial set may still contain individually verified facts (for
        # example, official vPIC identity details).  Publish those facts while
        # keeping NEEDS_REVIEW visible to the operator; never invent values to
        # make a card look complete.
        sync_status, sync_detail = _refresh_published(card) if written >= 1 else ("NOT_REQUIRED", "нет подтверждённых фактов")
        with connect_spec(False) as conn:
            conn.execute(
                """UPDATE vin_spec_jobs SET status=?,facts_count=?,source_status_json=?,
                   finished_at=?,site_sync_status=?,site_sync_detail=?,last_error=NULL WHERE id=?""",
                (
                    status, written, json.dumps(result.get("sources") or {}, ensure_ascii=False),
                    utc_now(), sync_status, sync_detail, int(job["id"]),
                ),
            )
            conn.commit()
        return {"car_uid": uid, "status": status, "facts": written, "site_sync": sync_status}
    except Exception as exc:
        final = "FAILED" if int(job.get("attempts") or 0) >= MAX_ATTEMPTS else "PENDING"
        with connect_spec(False) as conn:
            conn.execute(
                "UPDATE vin_spec_jobs SET status=?,last_error=?,finished_at=? WHERE id=?",
                (final, type(exc).__name__ + ":" + str(exc)[:500], utc_now(), int(job["id"])),
            )
            conn.commit()
        return {"car_uid": uid, "status": final, "error": type(exc).__name__}


def card_state(value: Any) -> dict[str, Any]:
    uid = canonical_uid(value)
    if not uid or not SPEC_DB.is_file():
        return {"status": "NOT_QUEUED", "facts_count": 0, "site_sync_status": "NOT_REQUIRED"}
    with connect_spec(True) as conn:
        row = conn.execute(
            """SELECT status,facts_count,attempts,last_error,site_sync_status,site_sync_detail,
               requested_at,finished_at FROM vin_spec_jobs WHERE car_uid=?
               ORDER BY id DESC LIMIT 1""",
            (uid,),
        ).fetchone()
    return dict(row) if row else {"status": "NOT_QUEUED", "facts_count": 0, "site_sync_status": "NOT_REQUIRED"}


def retry_card(value: Any) -> bool:
    uid = canonical_uid(value)
    if not uid:
        return False
    card = next((item for item in read_cards() if item["car_uid"] == uid), None)
    return enqueue_card(card, force=True) if card else False


def process_backlog(limit: int | None = None, *, enricher: Callable[[dict[str, Any]], dict[str, Any]] = source_policy.enrich) -> list[dict[str, Any]]:
    scan_new_vins()
    result: list[dict[str, Any]] = []
    while limit is None or len(result) < limit:
        item = process_one(enricher=enricher)
        if item is None:
            break
        result.append(item)
    return result


def _worker_loop() -> None:
    while not _stop_event.is_set():
        try:
            migrate_legacy_once()
            scan_new_vins()
            process_one()
        except Exception:
            # Deliberately fail the current cycle only; each job keeps its own
            # retry/error state and the CRM bot must remain available.
            pass
        _stop_event.wait(SCAN_SECONDS)


def start_worker() -> bool:
    global _worker
    with _worker_lock:
        if _worker is not None and _worker.is_alive():
            return False
        _stop_event.clear()
        ensure_schema()
        migrate_legacy_once()
        _worker = threading.Thread(target=_worker_loop, name=WORKER_NAME, daemon=True)
        _worker.start()
        return True


def stop_worker(timeout: float = 5.0) -> None:
    _stop_event.set()
    thread = _worker
    if thread and thread.is_alive():
        thread.join(timeout=max(0.0, timeout))


if __name__ == "__main__":
    if MAIN_DB.is_file():
        print(json.dumps({"scan": scan_new_vins(), "processed": process_backlog()}, ensure_ascii=False, indent=2))
    else:
        assert canonical_uid("UA-5") == "UA-0005"
        assert source_policy.normalize_vin("WDDMH0BBXDV171918") == "WDDMH0BBXDV171918"
        print("UA111_VIN_SPEC_SERVICE_SELFTEST_PASS")

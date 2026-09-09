#!/usr/bin/env python3
"""Automatic VIN-triggered additional-specification service for UA ART.

Collection opens the live CRM read-only. Enrichment, provenance, job state and
operator edits live in a separate SQLite sidecar.  A valid VIN already saved
by the existing CRM flow creates one idempotent job for this policy version.

Only already-published cards may be refreshed automatically. Collection never
creates the initial public listing or changes primary CRM fields. Before
startup/publication, the reviewed lifecycle helper may compensate an archived
interrupted transaction under the shared lock; this is recorded crash recovery.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import logging
import json
import os
import pathlib
import re
import sqlite3
import threading
import time
import uuid
import weakref
from typing import Any, Callable, Iterable

import source_policy


MAIN_DB = pathlib.Path(os.environ.get("UA_ART_CRM_DB", "/home/Carix/crm.db"))
SPEC_DB = pathlib.Path(
    os.environ.get("UA_ART_SPEC_DB", "/home/Carix/vin_specs_task111_v3.db")
)
SCAN_SECONDS = max(15, int(os.environ.get("UA_ART_VIN_SCAN_SECONDS", "30")))
MAX_ATTEMPTS = 3
STALE_JOB_SECONDS = max(300, int(os.environ.get("UA_ART_VIN_STALE_SECONDS", "1800")))
WORKER_NAME = "uaart-spec-auto10-restore"
MAX_SYNC_ATTEMPTS = 3
RETRY_SECONDS = max(15, int(os.environ.get("UA_ART_SPEC_RETRY_SECONDS", "60")))
RECONCILE_SECONDS = max(60, int(os.environ.get("UA_ART_SPEC_RECONCILE_SECONDS", "300")))
BACKLOG_SECONDS = 1.0
LOGGER = logging.getLogger(__name__)
IDENTITY_FIELDS = ("car_id", "vin", "brand", "model", "year", "fuel", "engine_cc", "transmission")
CARD_RE = re.compile(r"^UA[-‑–—]?0*(\d{1,6})$", re.IGNORECASE)
SEMANTIC_LABEL_GENERIC_TOKENS = {
    "auto", "car", "vehicle", "body", "overall",
    "авто", "автомобиль", "автомобиля", "машина", "машины",
    "общий", "общая", "общее", "габаритный", "габаритная",
}

_worker_lock = threading.Lock()
_worker: threading.Thread | None = None
_stop_event = threading.Event()


class ServiceError(RuntimeError):
    pass


class _ManagedConnection(sqlite3.Connection):
    """Preserve SQLite transaction semantics and release resources on context exit.

    The stdlib Connection context manager commits/rolls back but does not close.
    Error tracebacks can retain those open handles; on NFS this also prevents
    temporary database files from being removed until garbage collection.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._managed_cursors = weakref.WeakSet()
        self._managed_closed = False

    def cursor(self, *args, **kwargs):
        cursor = super().cursor(*args, **kwargs)
        self._managed_cursors.add(cursor)
        return cursor

    def _statement(self, method, args, kwargs):
        cursor = self.cursor()
        try:
            return getattr(cursor, method)(*args, **kwargs)
        except BaseException:
            cursor.close()
            raise

    def execute(self, *args, **kwargs):
        return self._statement("execute", args, kwargs)

    def executemany(self, *args, **kwargs):
        return self._statement("executemany", args, kwargs)

    def executescript(self, *args, **kwargs):
        return self._statement("executescript", args, kwargs)

    def close(self):
        if self._managed_closed:
            return
        try:
            # sqlite3_close_v2 alone leaves a zombie handle while a retained
            # cursor has an unfinished statement. Finalize those cursors first.
            for cursor in list(self._managed_cursors):
                cursor.close()
        finally:
            super().close()
            self._managed_closed = True
            self._managed_cursors.clear()

    def __exit__(self, exception_type, exception, traceback):
        try:
            return super().__exit__(exception_type, exception, traceback)
        finally:
            self.close()


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
    conn = None
    try:
        if readonly:
            conn = sqlite3.connect("file:" + str(path.resolve()) + "?mode=ro", uri=True,
                                   timeout=30, factory=_ManagedConnection)
            conn.execute("PRAGMA query_only=ON")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(path.resolve()), timeout=30, factory=_ManagedConnection)
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=30000")
            # The production home directory is NFS-backed. SQLite WAL relies
            # on shared memory; rollback journals with FULL sync are retained.
            conn.execute("PRAGMA synchronous=FULL")
        conn.row_factory = sqlite3.Row
        return conn
    except BaseException:
        if conn is not None:
            conn.close()
        raise


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
        # Additive migration: preserve task111 rows and operator audit history.
        existing = set(_columns(conn, "vin_spec_jobs"))
        for name, declaration in {
            "input_hash": "TEXT NOT NULL DEFAULT ''",
            "generation": "INTEGER NOT NULL DEFAULT 0",
            "claim_token": "TEXT",
            "next_attempt_at": "TEXT",
            "site_sync_attempts": "INTEGER NOT NULL DEFAULT 0",
            "site_sync_next_at": "TEXT",
            "site_sync_token": "TEXT",
            "site_sync_started_at": "TEXT",
        }.items():
            if name not in existing:
                conn.execute("ALTER TABLE vin_spec_jobs ADD COLUMN " + name + " " + declaration)
        audit_columns = set(_columns(conn, "additional_specification_audit"))
        if "spec_audit_json" not in audit_columns:
            conn.execute("ALTER TABLE additional_specification_audit ADD COLUMN spec_audit_json TEXT NOT NULL DEFAULT '{}'")
        meta_columns = set(_columns(conn, "additional_specification_meta"))
        if "source_evidence_json" not in meta_columns:
            conn.execute("ALTER TABLE additional_specification_meta ADD COLUMN source_evidence_json TEXT NOT NULL DEFAULT '{}'")
        conn.commit()
    try:
        os.chmod(SPEC_DB, 0o600)
    except OSError as exc:
        LOGGER.warning("Cannot restrict sidecar mode: %s", type(exc).__name__)


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
        vin = normalize_identity(raw_vin)
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
    import card_lifecycle
    with connect_main() as conn:
        if not _table_exists(conn, "cars"):
            raise ServiceError("CARS_TABLE_MISSING")
        rows = [dict(row) for row in conn.execute("SELECT rowid AS __rowid__, * FROM cars ORDER BY rowid")]
        cards = []
        for row in rows:
            card = _card_from_row(row)
            if card is None:
                continue
            try:
                card_lifecycle.validate_publication_identity(conn, card["car_uid"],
                    expected_card_id=card["car_id"], require_published=False)
            except card_lifecycle.LifecycleError as exc:
                # Preserve rows/facts for review, but never select one of
                # duplicate or retired UIDs arbitrarily for either queue.
                LOGGER.warning("Specification identity excluded: %s %s", card["car_uid"], str(exc))
                continue
            cards.append(card)
        if conn.total_changes != 0:
            raise ServiceError("MAIN_CRM_WRITE_GUARD")
    return sorted(cards, key=lambda item: item["car_uid"])


def _safe_text(value: Any, maximum: int = 500) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text or len(text) > maximum or source_policy.PRICE_RE.search(text):
        raise ServiceError("UNSAFE_ADDITIONAL_VALUE")
    return text


def _semantic_label_signature(value: Any) -> str:
    words = re.findall(
        r"[a-zа-яёіїєґ0-9]+", str(value or "").casefold().replace("ё", "е")
    )
    return " ".join(sorted(
        word for word in words if word not in SEMANTIC_LABEL_GENERIC_TOKENS
    ))


def _hide_semantic_duplicates(conn: sqlite3.Connection, uid: str) -> int:
    """Keep one visible row per semantic label, with operator data first.

    Legacy/manual rows can use a different field key from the audited V3
    catalogue (for example, ``overall_width`` versus ``width``).  Both rows
    remain in the sidecar and audit trail, but the automatic duplicate is
    hidden so the public contract stays unambiguous.
    """
    rows = [dict(row) for row in conn.execute(
        """SELECT a.id,a.field_key,a.confidence,m.label_ru,m.is_manual,
                  m.evidence_count,m.is_visible
             FROM additional_specification a
             JOIN additional_specification_meta m
               ON m.car_uid=a.car_uid AND m.field_key=a.field_key
            WHERE a.car_uid=? AND a.is_price_field=0 AND m.is_visible=1
            ORDER BY m.is_manual DESC,a.confidence DESC,m.evidence_count DESC,a.id""",
        (uid,),
    )]
    keepers: dict[str, dict[str, Any]] = {}
    hidden = 0
    for row in rows:
        signature = _semantic_label_signature(row.get("label_ru"))
        if not signature or signature not in keepers:
            if signature:
                keepers[signature] = row
            continue
        keeper = keepers[signature]
        conn.execute(
            """UPDATE additional_specification_meta
                  SET is_visible=0,verification_status='SEMANTIC_DUPLICATE_HIDDEN',
                      updated_at=? WHERE car_uid=? AND field_key=?""",
            (utc_now(), uid, str(row["field_key"])),
        )
        conn.execute(
            """INSERT INTO additional_specification_audit
               (car_uid,field_key,action,old_value,new_value)
               VALUES(?,?,?,?,?)""",
            (
                uid, str(row["field_key"]), "SEMANTIC_DUPLICATE_HIDDEN",
                str(row.get("label_ru") or ""), str(keeper["field_key"]),
            ),
        )
        hidden += 1
    return hidden


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


def normalize_identity(value: Any) -> str:
    normalizer = getattr(source_policy, "normalize_identity", source_policy.normalize_vin)
    return normalizer(value)


def input_fingerprint(card: dict[str, Any]) -> str:
    payload = {key: re.sub(r"\s+", " ", str(card.get(key) or "")).strip().casefold()
               for key in IDENTITY_FIELDS}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _later(seconds: int) -> str:
    return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=seconds)).replace(
        microsecond=0).isoformat().replace("+00:00", "Z")


def _record_state(key: str, value: Any) -> None:
    with connect_spec(False) as conn:
        conn.execute("INSERT OR REPLACE INTO vin_spec_state(key,value,updated_at) VALUES(?,?,?)",
                     (key, json.dumps(value, ensure_ascii=False), utc_now()))


def _block_identity_context(conn: sqlite3.Connection, card: dict[str, Any],
                            row: sqlite3.Row, issues: list[str]) -> bool:
    """Fence both queues while preserving fact values and all operator flags."""
    detail = "IDENTITY_CONTEXT_REQUIRES_REVIEW:" + ",".join(issues)
    fingerprint = input_fingerprint(card)
    if (row["status"] == "NEEDS_REVIEW" and row["site_sync_status"] == "NEEDS_REVIEW"
            and row["last_error"] == detail and row["input_hash"] == fingerprint):
        return False
    facts = [dict(item) for item in conn.execute("""SELECT a.*, m.is_manual, m.is_visible,
        m.verification_status FROM additional_specification a JOIN additional_specification_meta m
        ON a.car_uid=m.car_uid AND a.field_key=m.field_key WHERE a.car_uid=?""", (card["car_uid"],))]
    conn.execute("""INSERT INTO additional_specification_audit
        (car_uid,field_key,action,old_value,new_value,spec_audit_json) VALUES(?,?,?,?,?,?)""",
        (card["car_uid"], "__identity__", "IDENTITY_CONTEXT_BLOCKED", row["status"], "NEEDS_REVIEW",
         json.dumps({"issues": issues, "input_hash": fingerprint, "preserved_facts": facts,
                     "fact_values_and_operator_flags_changed": False}, ensure_ascii=False)))
    conn.execute("""UPDATE vin_spec_jobs SET status='NEEDS_REVIEW',site_sync_status='NEEDS_REVIEW',
        last_error=?,site_sync_detail=?,input_hash=?,car_id=?,generation=generation+1,
        claim_token=NULL,site_sync_token=NULL,next_attempt_at=NULL,site_sync_next_at=NULL,
        started_at=NULL,site_sync_started_at=NULL,finished_at=? WHERE id=?""",
        (detail, detail, fingerprint, card.get("car_id"), utc_now(), row["id"]))
    return True


def enqueue_card(card: dict[str, Any], *, force: bool = False) -> bool:
    uid = canonical_uid(card.get("car_uid"))
    vin = normalize_identity(card.get("vin"))
    if not uid:
        raise ServiceError("INVALID_CARD_UID")
    ensure_schema()
    now, fingerprint = utc_now(), input_fingerprint(card)
    issues = source_policy.identity_context_issues(card)
    with connect_spec(False) as conn:
        conn.execute("BEGIN IMMEDIATE")
        prior = conn.execute(
            "SELECT vin FROM vin_spec_jobs WHERE car_uid=? AND vin<>? AND status<>'SUPERSEDED' ORDER BY id DESC LIMIT 1",
            (uid, vin)).fetchone()
        row = conn.execute(
            "SELECT * FROM vin_spec_jobs WHERE car_uid=? AND vin=? AND policy_version=?",
            (uid, vin, source_policy.POLICY_VERSION)).fetchone()
        if issues:
            # An existing READY row and legacy visible/manual facts cannot
            # bypass current identity validation. Keep every fact/flag intact.
            if prior:
                conn.execute("""UPDATE vin_spec_jobs SET status='SUPERSEDED',finished_at=?,claim_token=NULL,
                    site_sync_token=NULL,site_sync_status='SUPERSEDED'
                    WHERE car_uid=? AND vin<>? AND status<>'SUPERSEDED'""", (now, uid, vin))
            if row is None:
                conn.execute("""INSERT INTO vin_spec_jobs
                    (car_id,car_uid,vin,policy_version,status,requested_at,input_hash,site_sync_status)
                    VALUES(?,?,?,?,?,?,?,?)""", (card.get("car_id"), uid, vin,
                    source_policy.POLICY_VERSION, "PENDING", now, fingerprint, "PENDING"))
                row = conn.execute("SELECT * FROM vin_spec_jobs WHERE id=last_insert_rowid()").fetchone()
            blocked = _block_identity_context(conn, card, row, issues)
            conn.commit()
            return blocked
        changed = bool(row and row["input_hash"] and row["input_hash"] != fingerprint)
        if prior or changed:
            # Retain historical values for audit, but never show another VIN's
            # or another significant vehicle context's facts as current facts.
            conn.execute("""UPDATE additional_specification_meta SET is_visible=0,
                verification_status='IDENTITY_CHANGED_REVIEW',updated_at=? WHERE car_uid=?""", (now, uid))
            conn.execute("""INSERT INTO additional_specification_audit
                (car_uid,field_key,action,old_value,new_value) VALUES(?,?,?,?,?)""",
                (uid, "__identity__", "IDENTITY_SUPERSEDED",
                 str(prior["vin"]) if prior else str(row["input_hash"]), fingerprint))
        if prior:
            conn.execute("""UPDATE vin_spec_jobs SET status='SUPERSEDED',finished_at=?,claim_token=NULL,
                site_sync_token=NULL,site_sync_status='SUPERSEDED' WHERE car_uid=? AND vin<>? AND status<>'SUPERSEDED'""",
                (now, uid, vin))
        if row:
            # A pre-upgrade row is re-evaluated once. Force never steals an
            # active unexpired claim; context changes invalidate it explicitly.
            if force and row["status"] == "RUNNING" and not changed:
                return False
            reset = force or changed or not row["input_hash"] or row["status"] == "SUPERSEDED"
            if reset:
                conn.execute("""UPDATE vin_spec_jobs SET status='PENDING',attempts=0,last_error=NULL,
                    input_hash=?,car_id=?,generation=generation+1,claim_token=NULL,next_attempt_at=NULL,
                    facts_count=(SELECT COUNT(*) FROM additional_specification_meta WHERE car_uid=? AND is_visible=1),
                    requested_at=?,started_at=NULL,finished_at=NULL,site_sync_status='PENDING',
                    site_sync_detail=NULL,site_sync_attempts=0,site_sync_next_at=NULL,
                    site_sync_token=NULL,site_sync_started_at=NULL WHERE id=?""",
                    (fingerprint, card.get("car_id"), uid, now, int(row["id"])))
                conn.commit()
                return True
            return False
        conn.execute("""INSERT INTO vin_spec_jobs
            (car_id,car_uid,vin,policy_version,status,requested_at,input_hash,site_sync_status)
            VALUES(?,?,?,?,?,?,?,?)""",
            (card.get("car_id"), uid, vin, source_policy.POLICY_VERSION, "PENDING", now, fingerprint,
             "PENDING" if card.get("published") else "NOT_REQUIRED"))
        conn.commit()
    return True


def scan_new_vins() -> dict[str, Any]:
    ensure_schema()
    # Retired policy jobs must not delay the current automatic backfill.
    with connect_spec(False) as conn:
        conn.execute(
            """UPDATE vin_spec_jobs SET status='SUPERSEDED',finished_at=?
               WHERE policy_version<>? AND status IN ('PENDING','RUNNING','PROCESSING')""",
            (utc_now(), source_policy.POLICY_VERSION),
        )
        conn.commit()
    cards = read_cards()
    queued = 0
    for card in cards:
        queued += int(enqueue_card(card))
    retired = _retire_absent_jobs(cards)
    return {"valid_vins": len(cards), "queued": queued, "retired": retired,
            "card_uids": [item["car_uid"] for item in cards]}


def _retire_absent_jobs(cards: list[dict[str, Any]]) -> int:
    """Invalidate both claims for removed/renamed identities; retain fact history.

    This never deletes or creates a site page. A missing CRM identity is not a
    request to regenerate it. Re-insertion is a new enqueue/generation decision.
    """
    current = {(card["car_uid"], card["vin"], card["car_id"]) for card in cards}
    with connect_spec(False) as conn:
        conn.execute("BEGIN IMMEDIATE")
        stale_ids = [row["id"] for row in conn.execute("""SELECT id,car_uid,vin,car_id FROM vin_spec_jobs
            WHERE policy_version=? AND (status<>'SUPERSEDED' OR site_sync_status<>'SUPERSEDED')""",
            (source_policy.POLICY_VERSION,)) if (row["car_uid"], row["vin"], row["car_id"]) not in current]
        for job_id in stale_ids:
            conn.execute("""UPDATE vin_spec_jobs SET status='SUPERSEDED',site_sync_status='SUPERSEDED',
                last_error='CRM_IDENTITY_REMOVED_OR_REPLACED',site_sync_detail='CRM_IDENTITY_REMOVED_OR_REPLACED',
                claim_token=NULL,site_sync_token=NULL,started_at=NULL,site_sync_started_at=NULL,
                next_attempt_at=NULL,site_sync_next_at=NULL,finished_at=? WHERE id=?""", (utc_now(), job_id))
        conn.commit()
    return len(stale_ids)


def requeue_all_current_vins() -> dict[str, Any]:
    """Queue every currently valid VIN for a complete, idempotent backfill.

    This is intentionally stronger than the periodic scanner: it also resets
    READY, FAILED and interrupted RUNNING/PROCESSING jobs for the current
    policy.  Stored manual specification rows remain untouched and continue to
    win in _store_facts().
    """
    cards = read_cards()
    queued = 0
    for card in cards:
        queued += int(enqueue_card(card, force=True))
    return {
        "valid_vins": len(cards),
        "queued": queued,
        "card_uids": [item["car_uid"] for item in cards],
    }


def recover_interrupted_jobs(stale_after_seconds: int = STALE_JOB_SECONDS) -> int:
    """Recover expired ownership without replenishing either retry budget."""
    ensure_schema()
    cutoff = _later(-max(0, int(stale_after_seconds)))
    with connect_spec(False) as conn:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.execute("""UPDATE vin_spec_jobs SET
            status=CASE WHEN attempts>=? THEN 'FAILED' ELSE 'PENDING' END,
            claim_token=NULL,requested_at=?,started_at=NULL,finished_at=NULL,
            last_error='INTERRUPTED_RETRY',next_attempt_at=?
            WHERE policy_version=? AND status IN ('RUNNING','PROCESSING')
            AND (started_at IS NULL OR started_at<=?)""",
            (MAX_ATTEMPTS, utc_now(), _later(RETRY_SECONDS), source_policy.POLICY_VERSION, cutoff))
        recovered = max(0, int(cursor.rowcount))
        conn.execute("""UPDATE vin_spec_jobs SET site_sync_token=NULL,site_sync_started_at=NULL,
            site_sync_status=CASE WHEN site_sync_attempts>=? THEN 'FAILED' ELSE 'PENDING' END,
            site_sync_detail='INTERRUPTED_RETRY',site_sync_next_at=?
            WHERE site_sync_status='RUNNING' AND (site_sync_started_at IS NULL OR site_sync_started_at<=?)""",
            (MAX_SYNC_ATTEMPTS, _later(RETRY_SECONDS), cutoff))
        conn.commit()
        return recovered


def _claim() -> dict[str, Any] | None:
    ensure_schema()
    with connect_spec(False) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("""SELECT * FROM vin_spec_jobs WHERE status='PENDING' AND attempts<?
            AND policy_version=? AND (next_attempt_at IS NULL OR next_attempt_at<=?)
            ORDER BY attempts,requested_at,id LIMIT 1""",
            (MAX_ATTEMPTS, source_policy.POLICY_VERSION, utc_now())).fetchone()
        if not row:
            return None
        token = uuid.uuid4().hex
        conn.execute("""UPDATE vin_spec_jobs SET status='RUNNING',attempts=attempts+1,
            started_at=?,last_error=NULL,claim_token=? WHERE id=?""", (utc_now(), token, int(row["id"])))
        claimed = dict(conn.execute("SELECT * FROM vin_spec_jobs WHERE id=?", (int(row["id"]),)).fetchone())
        conn.commit()
        return claimed


def _owns(conn: sqlite3.Connection, job: dict[str, Any]) -> bool:
    return conn.execute("""SELECT 1 FROM vin_spec_jobs WHERE id=? AND status='RUNNING'
        AND claim_token=? AND input_hash=?""",
        (job["id"], job.get("claim_token"), job.get("input_hash"))).fetchone() is not None


def _current_card(uid: str, vin: str) -> dict[str, Any] | None:
    for card in read_cards():
        if card["car_uid"] == uid and card["vin"] == vin:
            return card
    return None


def _store_facts(uid: str, facts: Iterable[dict[str, Any]], *, job: dict[str, Any] | None = None) -> int:
    written = 0
    with connect_spec(False) as conn:
        conn.execute("BEGIN IMMEDIATE")
        if job is not None and not _owns(conn, job):
            raise ServiceError("STALE_JOB_CLAIM")
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
            before = conn.execute("""SELECT a.field_value,a.source,a.source_url,a.confidence,
                m.label_ru,m.category,m.unit,m.source_domains_json,m.source_urls_json,m.source_evidence_json
                FROM additional_specification a LEFT JOIN additional_specification_meta m
                ON a.car_uid=m.car_uid AND a.field_key=m.field_key
                WHERE a.car_uid=? AND a.field_key=?""", (uid, key)).fetchone()
            if before is not None and before["field_value"] != value:
                snapshot = {
                    "before": dict(before),
                    "after": {"field_value": value, "label_ru": label, "source": "AUTO_10SRC",
                        "source_url": urls[0], "source_domains": domains, "source_urls": urls,
                        "confidence": min(1.0, max(0.0, float(fact.get("confidence") or 0.0))),
                        "evidence_origins": fact.get("evidence_origins") or [],
                        "provenance": fact.get("provenance") or []},
                    "policy_version": source_policy.POLICY_VERSION,
                    "input_hash": job.get("input_hash") if job else None,
                }
                conn.execute("""INSERT INTO additional_specification_audit
                    (car_uid,field_key,action,old_value,new_value,spec_audit_json)
                    VALUES(?,?,?,?,?,?)""", (uid, key, "AUTO_REPLACED", before["field_value"], value,
                        json.dumps(snapshot, ensure_ascii=False)))
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
                    is_visible=CASE WHEN additional_specification_meta.verification_status='IDENTITY_CHANGED_REVIEW'
                        THEN 1 ELSE additional_specification_meta.is_visible END,
                    updated_at=excluded.updated_at""",
                (
                    uid, key, label, str(fact.get("category") or "additional"),
                    str(fact.get("unit") or "")[:40], int(fact.get("evidence_count") or len(domains)),
                    json.dumps(domains, ensure_ascii=False), json.dumps(urls, ensure_ascii=False),
                    "VERIFIED_10SRC", float(fact.get("confidence") or 0.0), 0, 1, utc_now(),
                ),
            )
            conn.execute("""UPDATE additional_specification_meta SET source_evidence_json=?
                WHERE car_uid=? AND field_key=?""",
                (json.dumps({"evidence_origins": fact.get("evidence_origins") or [],
                             "provenance": fact.get("provenance") or []}, ensure_ascii=False), uid, key))
            written += 1
        _hide_semantic_duplicates(conn, uid)
        conn.commit()
    return written


def _visible_facts(uid: str) -> list[dict[str, Any]]:
    with connect_spec(True) as conn:
        rows = [dict(row) for row in conn.execute("""SELECT a.*, m.label_ru, m.category, m.unit,
            m.is_manual, m.is_visible, m.verification_status, m.source_domains_json, m.source_urls_json, m.source_evidence_json
            FROM additional_specification a JOIN additional_specification_meta m
            ON a.car_uid=m.car_uid AND a.field_key=m.field_key
            WHERE a.car_uid=? AND a.is_price_field=0 AND m.is_visible=1
            ORDER BY m.category,a.field_key""", (uid,))]
    for row in rows:
        row["display_value"] = row["field_value"]
    return rows


def _refresh_published(card: dict[str, Any], *, publisher: Callable[[str], Any] | None = None,
                       sleeper: Callable[[float], Any] = time.sleep) -> tuple[str, str]:
    """Compatibility helper; generic full-card publishing is never implicit."""
    if not card.get("published"):
        return "NOT_REQUIRED", "карточка ещё не опубликована"
    if publisher is None:
        return "FAIL", "EXPLICIT_SPEC_RECONCILER_REQUIRED"
    try:
        result = publisher(card["car_uid"])
        ok, detail = (result[0], result[1]) if isinstance(result, tuple) else (bool(result), str(result))
        return ("PASS" if ok is True else "FAIL"), str(detail)[:500]
    except Exception as exc:
        return "FAIL", (type(exc).__name__ + ":" + str(exc))[:500]


def _has_transient_source_error(value: Any) -> bool:
    if isinstance(value, dict):
        if value.get("status") in {"FAIL", "TIMEOUT", "RETRY", "FETCH_FAIL", "DISCOVERY_FAIL"}:
            return True
        return any(_has_transient_source_error(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_transient_source_error(item) for item in value)
    return False


def _process_claimed(job: dict[str, Any], *,
    enricher: Callable[[dict[str, Any]], dict[str, Any]] = source_policy.enrich) -> dict[str, Any]:
    uid, vin = str(job["car_uid"]), str(job["vin"])
    try:
        card = _current_card(uid, vin)
        if not card or input_fingerprint(card) != job["input_hash"]:
            raise ServiceError("CARD_OR_CONTEXT_CHANGED")
        issues = source_policy.identity_context_issues(card)
        if issues:
            enqueue_card(card)
            return {"car_uid": uid, "status": "NEEDS_REVIEW", "written": 0,
                    "site_sync": "NEEDS_REVIEW", "identity_context_issues": issues}
        result = enricher(card)
        current = _current_card(uid, vin)
        if not current or input_fingerprint(current) != job["input_hash"]:
            if current:
                enqueue_card(current)
            raise ServiceError("CARD_OR_CONTEXT_CHANGED")
        written = _store_facts(uid, list(result.get("facts") or []), job=job)
        retained = len(_visible_facts(uid))
        sources = result.get("sources") or {}
        transient = _has_transient_source_error(sources)
        status = "READY" if result.get("status") == "READY" and retained else "NEEDS_REVIEW"
        if transient and int(job["attempts"]) < MAX_ATTEMPTS:
            status = "PENDING"
        with connect_spec(False) as conn:
            conn.execute("BEGIN IMMEDIATE")
            if not _owns(conn, job):
                raise ServiceError("STALE_JOB_CLAIM")
            conn.execute("""UPDATE vin_spec_jobs SET status=?,facts_count=?,source_status_json=?,
                finished_at=?,claim_token=NULL,next_attempt_at=?,
                site_sync_status=CASE WHEN site_sync_status='RUNNING' THEN site_sync_status
                    WHEN site_sync_attempts>=3 THEN 'FAILED' ELSE ? END,
                last_error=? WHERE id=?""",
                (status, retained, json.dumps(sources, ensure_ascii=False), utc_now(),
                 _later(RETRY_SECONDS * int(job["attempts"])) if status == "PENDING" else None,
                 "PENDING" if current.get("published") else "NOT_REQUIRED",
                 "SOURCE_RETRY_PENDING" if status == "PENDING" else (
                     "SOURCE_ERRORS_EXHAUSTED" if transient else None), int(job["id"])))
            conn.commit()
        return {"car_uid": uid, "status": status, "facts": retained, "written": written,
                "site_sync": "PENDING" if current.get("published") else "NOT_REQUIRED"}
    except Exception as exc:
        final = "FAILED" if int(job.get("attempts") or 0) >= MAX_ATTEMPTS else "PENDING"
        stale = isinstance(exc, ServiceError) and str(exc) in {"CARD_OR_CONTEXT_CHANGED", "STALE_JOB_CLAIM"}
        with connect_spec(False) as conn:
            conn.execute("BEGIN IMMEDIATE")
            if _owns(conn, job):
                if stale:
                    final = "SUPERSEDED"
                conn.execute("""UPDATE vin_spec_jobs SET status=?,last_error=?,finished_at=?,claim_token=NULL,
                    next_attempt_at=?,
                    site_sync_status=CASE WHEN ? THEN 'SUPERSEDED' ELSE site_sync_status END,
                    site_sync_token=CASE WHEN ? THEN NULL ELSE site_sync_token END,
                    site_sync_next_at=CASE WHEN ? THEN NULL ELSE site_sync_next_at END
                    WHERE id=?""",
                    (final, type(exc).__name__ + ":" + str(exc)[:500], utc_now(),
                     None if stale else _later(RETRY_SECONDS * max(1, int(job.get("attempts") or 0))),
                     stale, stale, stale, int(job["id"])))
                conn.commit()
            else:
                final = "STALE_DISCARDED"
        return {"car_uid": uid, "status": final, "error": type(exc).__name__ + ":" + str(exc)[:120]}


def process_one(*, enricher: Callable[[dict[str, Any]], dict[str, Any]] = source_policy.enrich) -> dict[str, Any] | None:
    job = _claim()
    return _process_claimed(job, enricher=enricher) if job else None


def reconcile_published_cards() -> int:
    """Schedule read/repair verification periodically, without refetching sources.

    Exhausted publication failures require an explicit retry or changed vehicle
    context. Successful checks get a fresh bounded budget on the next interval.
    """
    cards = read_cards()
    _retire_absent_jobs(cards)
    count = 0
    with connect_spec(False) as conn:
        conn.execute("BEGIN IMMEDIATE")
        for card in cards:
            issues = source_policy.identity_context_issues(card)
            if issues:
                row = conn.execute("SELECT * FROM vin_spec_jobs WHERE car_uid=? AND vin=? AND policy_version=?",
                    (card["car_uid"], card["vin"], source_policy.POLICY_VERSION)).fetchone()
                if row:
                    _block_identity_context(conn, card, row, issues)
                continue
            if not card.get("published"):
                conn.execute("""UPDATE vin_spec_jobs SET site_sync_status='NOT_REQUIRED',site_sync_token=NULL
                    WHERE car_uid=? AND policy_version=? AND site_sync_status<>'NOT_REQUIRED'""",
                    (card["car_uid"], source_policy.POLICY_VERSION))
                continue
            cursor = conn.execute("""UPDATE vin_spec_jobs SET site_sync_status='PENDING',
                site_sync_attempts=0,site_sync_token=NULL WHERE car_uid=? AND vin=? AND input_hash=?
                AND policy_version=? AND status NOT IN ('SUPERSEDED','RUNNING','PROCESSING')
                AND site_sync_status IN ('PASS','UNCHANGED','NOT_REQUIRED')
                AND (site_sync_next_at IS NULL OR site_sync_next_at<=?)""",
                (card["car_uid"], card["vin"], input_fingerprint(card), source_policy.POLICY_VERSION, utc_now()))
            count += max(0, cursor.rowcount)
        conn.commit()
    return count


def recover_lifecycle_pending(*, guard=None) -> dict[str, Any]:
    """Recover interrupted lifecycle transactions before any worker writes.

    The preliminary archive lookup is read-only. No application guard import
    occurs when no recovery is pending (including isolated unit fixtures).
    Actual compensation is delegated to the reviewed lifecycle helper under
    the existing shared reentrant publication lock and matching CRM database.
    """
    import card_lifecycle
    with connect_main() as conn:
        if not _table_exists(conn, card_lifecycle.ARCHIVE_TABLE):
            return {"status": "PASS", "recovered": []}
        pending = conn.execute("SELECT 1 FROM ua_spec_lifecycle_archive "
            "WHERE state IN ('APPLIED','ROLLBACK_DB_DONE') LIMIT 1").fetchone()
    if not pending:
        return {"status": "PASS", "recovered": []}
    if guard is None:
        import publish_transaction_guard as guard
    if pathlib.Path(guard.DB).resolve() != MAIN_DB.resolve():
        raise ServiceError("LIFECYCLE_RECOVERY_CRM_DATABASE_MISMATCH")
    if (getattr(guard, "LIFECYCLE_REENTRANT_LOCK", False) is not True or
            pathlib.Path(guard.LOCK).resolve() != pathlib.Path(guard.ROOT).resolve()/".ua_art_publish_transaction.lock"):
        raise ServiceError("LIFECYCLE_RECOVERY_SHARED_LOCK_MISMATCH")
    result = card_lifecycle.recover_pending(guard=guard)
    if result.get("status") != "PASS":
        raise ServiceError("LIFECYCLE_RECOVERY_NOT_VERIFIED")
    return result


def sync_one(*, reconciler: Callable[[dict[str, Any], list[dict[str, Any]]], dict[str, Any]] | None = None,
             lifecycle_guard=None) -> dict[str, Any] | None:
    """Claim one durable publication attempt; the reconciler must verify output."""
    recover_lifecycle_pending(guard=lifecycle_guard)
    ensure_schema()
    with connect_spec(False) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("""SELECT * FROM vin_spec_jobs WHERE policy_version=?
            AND site_sync_status='PENDING' AND site_sync_attempts<?
            AND status NOT IN ('SUPERSEDED','RUNNING','PROCESSING')
            AND (status<>'PENDING' OR EXISTS (SELECT 1 FROM additional_specification_meta m
                WHERE m.car_uid=vin_spec_jobs.car_uid AND m.is_visible=1))
            AND (site_sync_next_at IS NULL OR site_sync_next_at<=?)
            ORDER BY COALESCE(site_sync_next_at,''),id LIMIT 1""",
            (source_policy.POLICY_VERSION, MAX_SYNC_ATTEMPTS, utc_now())).fetchone()
        if not row:
            return None
        job, token = dict(row), uuid.uuid4().hex
        conn.execute("""UPDATE vin_spec_jobs SET site_sync_status='RUNNING',site_sync_token=?,
            site_sync_started_at=?,site_sync_attempts=site_sync_attempts+1 WHERE id=?""",
            (token, utc_now(), job["id"]))
        conn.commit()
    status, detail = "FAIL", "NOT_EXECUTED"
    card = _current_card(job["car_uid"], job["vin"])
    try:
        if not card or input_fingerprint(card) != job["input_hash"]:
            status, detail = "SUPERSEDED", "CARD_OR_CONTEXT_CHANGED"
        elif source_policy.identity_context_issues(card):
            enqueue_card(card)
            return {"car_uid": job["car_uid"], "status": "NEEDS_REVIEW", "attempt": 0,
                    "detail": "IDENTITY_CONTEXT_REQUIRES_REVIEW"}
        elif not card.get("published"):
            status, detail = "NOT_REQUIRED", "карточка ещё не опубликована"
        else:
            if reconciler is None:
                from spec_publication import reconcile_published
                reconciler = reconcile_published
            result = reconciler(card, _visible_facts(job["car_uid"]))
            status, detail = str(result.get("status") or "FAIL"), str(result.get("detail") or "")[:500]
            if status not in {"PASS", "UNCHANGED", "FAIL", "NOT_REQUIRED"}:
                status, detail = "FAIL", "INVALID_RECONCILER_RESULT"
            latest = _current_card(job["car_uid"], job["vin"])
            if not latest or input_fingerprint(latest) != job["input_hash"]:
                status, detail = "SUPERSEDED", "CARD_OR_CONTEXT_CHANGED_DURING_SYNC"
            elif not latest.get("published"):
                status, detail = "NOT_REQUIRED", "CARD_UNPUBLISHED_DURING_SYNC"
    except Exception as exc:
        status, detail = "FAIL", (type(exc).__name__ + ":" + str(exc))[:500]
    attempt = int(job.get("site_sync_attempts") or 0) + 1
    durable_status = ("PENDING" if attempt < MAX_SYNC_ATTEMPTS else "FAILED") if status == "FAIL" else status
    next_at = _later(RECONCILE_SECONDS if status in {"PASS", "UNCHANGED"} else RETRY_SECONDS * attempt)
    with connect_spec(False) as conn:
        cursor = conn.execute("""UPDATE vin_spec_jobs SET site_sync_status=?,site_sync_detail=?,
            site_sync_next_at=?,site_sync_token=NULL,site_sync_started_at=NULL
            WHERE id=? AND site_sync_token=? AND input_hash=?""",
            (durable_status, detail, next_at, job["id"], token, job["input_hash"]))
        if cursor.rowcount and status == "SUPERSEDED":
            # Fence the collection half as well; an absent identity must not
            # remain READY/PENDING while only publication is retired.
            conn.execute("""UPDATE vin_spec_jobs SET status='SUPERSEDED',claim_token=NULL,
                next_attempt_at=NULL,site_sync_next_at=NULL,finished_at=? WHERE id=?""",
                (utc_now(), job["id"]))
        conn.commit()
    return {"car_uid": job["car_uid"], "status": durable_status if cursor.rowcount else "STALE_DISCARDED",
            "attempt": attempt, "detail": detail}


def process_card_now(value: Any, *, enricher: Callable[[dict[str, Any]], dict[str, Any]] = source_policy.enrich) -> dict[str, Any] | None:
    """Explicit operator retry. It cannot take an active worker's claim."""
    uid = canonical_uid(value)
    card = next((item for item in read_cards() if item["car_uid"] == uid), None)
    if not card or not enqueue_card(card, force=True):
        return None
    # Claim only this card atomically; do not accidentally process another row.
    with connect_spec(False) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("""SELECT * FROM vin_spec_jobs WHERE car_uid=? AND vin=? AND policy_version=?
            AND status='PENDING' AND input_hash=?""",
            (uid, card["vin"], source_policy.POLICY_VERSION, input_fingerprint(card))).fetchone()
        if not row:
            return None
        conn.execute("""UPDATE vin_spec_jobs SET status='RUNNING',attempts=attempts+1,started_at=?,claim_token=?
            WHERE id=?""", (utc_now(), uuid.uuid4().hex, row["id"]))
        job = dict(conn.execute("SELECT * FROM vin_spec_jobs WHERE id=?", (row["id"],)).fetchone())
        conn.commit()
    return _process_claimed(job, enricher=enricher)


def card_state(value: Any) -> dict[str, Any]:
    uid = canonical_uid(value)
    if not uid or not SPEC_DB.is_file():
        return {"status": "NOT_QUEUED", "facts_count": 0, "site_sync_status": "NOT_REQUIRED"}
    with connect_spec(True) as conn:
        row = conn.execute(
            """SELECT status,facts_count,attempts,last_error,site_sync_status,site_sync_detail,
               requested_at,finished_at,next_attempt_at,site_sync_attempts,site_sync_next_at,input_hash
               FROM vin_spec_jobs WHERE car_uid=? AND policy_version=? AND status<>'SUPERSEDED'
               ORDER BY id DESC LIMIT 1""",
            (uid, source_policy.POLICY_VERSION),
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


def worker_cycle(*, lifecycle_guard=None) -> dict[str, Any]:
    """One measurable cycle; at most one enrichment or one publication job."""
    ensure_schema()
    _record_state("worker_heartbeat", {"status": "RUNNING", "at": utc_now()})
    try:
        lifecycle_recovery = recover_lifecycle_pending(guard=lifecycle_guard)
        migrate_legacy_once()
        recovered = recover_interrupted_jobs()
        scan = scan_new_vins()
        reconcile_published_cards()
        # Alternate busy queues durably: old-card reconciliation must never
        # starve newly created cards, including across worker restarts.
        with connect_spec(True) as conn:
            row = conn.execute("SELECT value FROM vin_spec_state WHERE key='worker_last_kind'").fetchone()
        last_kind = json.loads(row[0]) if row else None
        kinds = ("enrichment", "sync") if last_kind == "sync" else ("sync", "enrichment")
        result, kind = None, None
        for candidate in kinds:
            result = process_one() if candidate == "enrichment" else sync_one()
            if result is not None:
                kind = candidate
                _record_state("worker_last_kind", kind)
                break
        state = {"status": "OK", "at": utc_now(), "scan": scan, "recovered": recovered,
                 "lifecycle_recovery": lifecycle_recovery,
                 "job": result, "job_kind": kind}
        _record_state("worker_heartbeat", state)
        return state
    except Exception as exc:
        state = {"status": "ERROR", "at": utc_now(), "error": type(exc).__name__ + ":" + str(exc)[:500]}
        LOGGER.exception("Specification worker cycle failed")
        _record_state("worker_heartbeat", state)
        return state


def _worker_loop() -> None:
    while not _stop_event.is_set():
        delay = SCAN_SECONDS
        try:
            result = worker_cycle()
            # Drain a backlog promptly, but retain a stop-aware delay and do
            # one claim per cycle. Empty/error/exhausted queues poll normally.
            if result.get("status") == "OK" and result.get("job") is not None:
                delay = BACKLOG_SECONDS
        except Exception:
            # A full/unavailable sidecar may prevent durable heartbeat writes.
            # Keep the CRM alive, emit an error, and retry after the poll delay.
            LOGGER.exception("Specification worker state unavailable")
        _stop_event.wait(delay)


def start_worker(*, lifecycle_guard=None) -> bool:
    global _worker
    with _worker_lock:
        if _worker is not None and _worker.is_alive():
            return False
        _stop_event.clear()
        try:
            ensure_schema()
            _record_state("worker_heartbeat", {"status": "STARTING", "at": utc_now()})
            recover_lifecycle_pending(guard=lifecycle_guard)
            migrate_legacy_once()
            recover_interrupted_jobs()
        except Exception as exc:
            LOGGER.exception("Specification worker startup failed")
            try:
                _record_state("worker_heartbeat", {"status": "ERROR", "phase": "STARTUP", "at": utc_now(),
                    "error": type(exc).__name__ + ":" + str(exc)[:500]})
            except Exception:
                LOGGER.exception("Cannot persist specification startup error")
            return False
        _worker = threading.Thread(target=_worker_loop, name=WORKER_NAME, daemon=True)
        _worker.start()
        return True


def stop_worker(timeout: float = 5.0) -> None:
    _stop_event.set()
    thread = _worker
    if thread and thread.is_alive():
        thread.join(timeout=max(0.0, timeout))


if __name__ == "__main__":
    raise SystemExit("Import the service from the reviewed CRM integration; offline tests do not start it.")

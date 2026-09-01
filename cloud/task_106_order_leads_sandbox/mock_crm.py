"""Isolated contract harness for UA-ORDER-LEAD-CONTRACT-001.

This module never opens a production path. A caller must provide an existing
SQLite connection, normally ``sqlite3.connect(':memory:')`` or a temporary test
database. It intentionally has no code for creating or publishing automobiles.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping


LANGUAGES = ("uk", "ru", "ka")
COUNTRIES = ("korea", "japan", "usa", "europe", "china", "canada", "uae", "georgia")
SOURCE_CHANNELS = ("site", "telegram_bot", "whatsapp", "manager")


class ContractError(ValueError):
    """Raised when a request is invalid and must not be persisted."""


@dataclass(frozen=True)
class IngestResult:
    status: str
    request_id: str
    display_number: str
    client_id: int
    order_request_id: int


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _text(value: Any, *, field: str, minimum: int = 0, maximum: int = 4000) -> str:
    result = "" if value is None else str(value).strip()
    if len(result) < minimum or len(result) > maximum:
        raise ContractError(f"invalid {field}")
    return result


def _phone(value: Any) -> str:
    raw = "" if value is None else str(value).strip()
    if not raw:
        return ""
    plus = raw.startswith("+")
    digits = re.sub(r"\D", "", raw)
    if len(digits) < 7 or len(digits) > 15:
        raise ContractError("invalid phone")
    return ("+" if plus else "") + digits


def normalize_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    if int(payload.get("contract_version", 0)) != 1:
        raise ContractError("unsupported contract_version")

    lang = str(payload.get("lang") or "uk").strip().lower()
    if lang not in LANGUAGES:
        raise ContractError("unknown lang")

    country = str(payload.get("order_country_code") or "").strip().lower()
    if country not in COUNTRIES:
        raise ContractError("unknown order_country_code")

    source = str(payload.get("source_channel") or "").strip().lower()
    if source not in SOURCE_CHANNELS:
        raise ContractError("unknown source_channel")

    normalized = {
        "contract_version": 1,
        "request_id": _text(payload.get("request_id"), field="request_id", minimum=8, maximum=80),
        "source_event_id": _text(payload.get("source_event_id"), field="source_event_id", maximum=160) or None,
        "source_channel": source,
        "source_url": _text(payload.get("source_url"), field="source_url", maximum=1000) or None,
        "lang": lang,
        "client_name": _text(payload.get("client_name"), field="client_name", minimum=2, maximum=80),
        "phone": _phone(payload.get("phone")) or None,
        "whatsapp": _phone(payload.get("whatsapp")) or None,
        "telegram_username": _text(payload.get("telegram_username"), field="telegram_username", maximum=64) or None,
        "tg_user_id": _text(payload.get("tg_user_id"), field="tg_user_id", maximum=40) or None,
        "order_country_code": country,
        "order_country_label": _text(payload.get("order_country_label"), field="order_country_label", maximum=80) or None,
        "requested_model": _text(payload.get("requested_model"), field="requested_model", maximum=160) or None,
        "other_model": _text(payload.get("other_model"), field="other_model", maximum=160) or None,
        "vehicle_type": _text(payload.get("vehicle_type"), field="vehicle_type", maximum=80) or None,
        "budget_bucket": _text(payload.get("budget_bucket"), field="budget_bucket", minimum=1, maximum=80),
        "budget_min": payload.get("budget_min"),
        "budget_max": payload.get("budget_max"),
        "currency": str(payload.get("currency") or "USD").upper(),
        "delivery_country": _text(payload.get("delivery_country"), field="delivery_country", minimum=2, maximum=80),
        "delivery_city": _text(payload.get("delivery_city"), field="delivery_city", minimum=2, maximum=80),
        "current_country": _text(payload.get("current_country"), field="current_country", maximum=80) or None,
        "current_city": _text(payload.get("current_city"), field="current_city", maximum=80) or None,
        "contact_preference": _text(payload.get("contact_preference"), field="contact_preference", maximum=20) or None,
        "comment": _text(payload.get("comment"), field="comment", maximum=4000) or None,
        "consent_at": _text(payload.get("consent_at"), field="consent_at", minimum=10, maximum=40),
        "created_at": _text(payload.get("created_at"), field="created_at", maximum=40) or utc_now(),
    }

    if not (normalized["requested_model"] or normalized["other_model"] or normalized["vehicle_type"]):
        raise ContractError("requested_model or vehicle_type required")
    if not (normalized["phone"] or normalized["whatsapp"] or normalized["tg_user_id"] or normalized["telegram_username"]):
        raise ContractError("at least one contact required")
    if source == "site" and not (normalized["phone"] or normalized["whatsapp"] or normalized["telegram_username"] or normalized["tg_user_id"]):
        raise ContractError("site contact required")
    if normalized["currency"] not in ("USD", "EUR", "UAH", "GEL"):
        raise ContractError("unsupported currency")
    for key in ("budget_min", "budget_max"):
        value = normalized[key]
        if value is not None and (not isinstance(value, int) or value < 0):
            raise ContractError(f"invalid {key}")
    return normalized


def initialize_mock_schema(connection: sqlite3.Connection, schema_sql: str) -> None:
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            telegram TEXT,
            whatsapp TEXT,
            tg_user_id TEXT,
            country TEXT,
            city TEXT,
            preferred_language TEXT,
            consent_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT
        );
        CREATE INDEX IF NOT EXISTS ix_clients_phone ON clients(phone);
        CREATE INDEX IF NOT EXISTS ix_clients_tg_user_id ON clients(tg_user_id);
        """
    )
    connection.executescript(schema_sql)


def _find_or_create_client(connection: sqlite3.Connection, data: Mapping[str, Any]) -> int:
    row = None
    if data["tg_user_id"]:
        row = connection.execute("SELECT id FROM clients WHERE tg_user_id = ? ORDER BY id LIMIT 1", (data["tg_user_id"],)).fetchone()
    if row is None and data["phone"]:
        row = connection.execute("SELECT id FROM clients WHERE phone = ? ORDER BY id LIMIT 1", (data["phone"],)).fetchone()
    if row is None and data["whatsapp"]:
        row = connection.execute("SELECT id FROM clients WHERE whatsapp = ? ORDER BY id LIMIT 1", (data["whatsapp"],)).fetchone()
    if row is not None:
        return int(row[0])

    cursor = connection.execute(
        """INSERT INTO clients
           (name, phone, telegram, whatsapp, tg_user_id, country, city,
            preferred_language, consent_at, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data["client_name"], data["phone"], data["telegram_username"], data["whatsapp"],
            data["tg_user_id"], data["current_country"], data["current_city"], data["lang"],
            data["consent_at"], data["created_at"],
        ),
    )
    return int(cursor.lastrowid)


def _existing(connection: sqlite3.Connection, data: Mapping[str, Any]) -> sqlite3.Row | None:
    connection.row_factory = sqlite3.Row
    row = connection.execute("SELECT * FROM order_requests WHERE request_id = ?", (data["request_id"],)).fetchone()
    if row is None and data["source_event_id"]:
        row = connection.execute("SELECT * FROM order_requests WHERE source_event_id = ?", (data["source_event_id"],)).fetchone()
    return row


def ingest(connection: sqlite3.Connection, payload: Mapping[str, Any]) -> IngestResult:
    data = normalize_payload(payload)
    try:
        connection.execute("BEGIN IMMEDIATE")
        duplicate = _existing(connection, data)
        if duplicate is not None:
            connection.commit()
            return IngestResult("duplicate", duplicate["request_id"], duplicate["display_number"], duplicate["client_id"], duplicate["id"])

        client_id = _find_or_create_client(connection, data)
        safe_payload = dict(data)
        safe_payload.pop("phone", None)
        safe_payload.pop("whatsapp", None)
        safe_payload.pop("tg_user_id", None)
        safe_payload.pop("telegram_username", None)
        columns = (
            "request_id", "client_id", "source_event_id", "source_channel", "source_url", "lang",
            "order_country_code", "order_country_label", "requested_model", "other_model", "vehicle_type",
            "budget_bucket", "budget_min", "budget_max", "currency", "delivery_country", "delivery_city",
            "current_country", "current_city", "comment", "contact_preference", "payload_json", "created_at"
        )
        values = (
            data["request_id"], client_id, data["source_event_id"], data["source_channel"], data["source_url"], data["lang"],
            data["order_country_code"], data["order_country_label"], data["requested_model"], data["other_model"], data["vehicle_type"],
            data["budget_bucket"], data["budget_min"], data["budget_max"], data["currency"], data["delivery_country"], data["delivery_city"],
            data["current_country"], data["current_city"], data["comment"], data["contact_preference"],
            json.dumps(safe_payload, ensure_ascii=False, sort_keys=True), data["created_at"]
        )
        placeholders = ",".join("?" for _ in columns)
        cursor = connection.execute(f"INSERT INTO order_requests ({','.join(columns)}) VALUES ({placeholders})", values)
        order_request_id = int(cursor.lastrowid)
        display_number = f"OR-{order_request_id:06d}"
        connection.execute("UPDATE order_requests SET display_number = ? WHERE id = ?", (display_number, order_request_id))
        connection.commit()
        return IngestResult("created", data["request_id"], display_number, client_id, order_request_id)
    except Exception:
        connection.rollback()
        raise


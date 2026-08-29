#!/usr/bin/env python3
"""Permanent stage-owned payload policy for UA ART CRM and public cards."""
from __future__ import annotations

import re
from typing import Iterable, Mapping


CONTRACT_ID = "UA-0011-STAGE-PAYLOAD-RESET-005-V1.0"
TRIGGER_UPDATE = "ua_stage_payload_guard_korea_update_v1"
TRIGGER_INSERT = "ua_stage_payload_guard_korea_insert_v1"

SEA_FIELDS = (
    "sea_container",
    "sea_date_out",
    "sea_port_from",
)
ETA_FIELDS = (
    "days_to_kyiv",
    "eta_manual",
)
GEORGIA_FIELDS = (
    "ge_arrived",
    "ge_port",
    "ge_released",
    "ge_to_kyiv_at",
)
KOREA_RESET_FIELDS = SEA_FIELDS + ETA_FIELDS + GEORGIA_FIELDS


class StagePayloadError(RuntimeError):
    """Fail-closed stage contract violation."""


def _status(value: object) -> str:
    return str(value or "").strip().casefold()


def stage_number(value: object) -> int | None:
    """Return the canonical public stage, without guessing unknown states."""
    status = _status(value)
    if status.startswith(("kr_", "korea")):
        return 1
    if status.startswith(("sea_", "ferry", "more", "ocean")):
        return 2
    if status.startswith(("ge_", "georgia")):
        return 3
    if status.startswith(("ua_", "kyiv", "kiev")):
        return 4
    return None


def cleanup_fields_for_transition(
    old_status: object,
    new_status: object,
    available_fields: Iterable[str],
) -> tuple[str, ...]:
    """Fields to clear atomically when the destination stage actually changes."""
    old_stage = stage_number(old_status)
    new_stage = stage_number(new_status)
    if new_stage is None:
        raise StagePayloadError("UNKNOWN_DESTINATION_STAGE")
    if old_stage == new_stage:
        return ()
    available = set(available_fields)
    if new_stage == 1:
        wanted = KOREA_RESET_FIELDS
    elif new_stage == 2:
        # A new sea leg must receive a fresh ETA; later-stage timestamps are stale.
        wanted = ETA_FIELDS + GEORGIA_FIELDS
    elif new_stage == 3:
        # Ferry ETA cannot become the Georgia-to-Kyiv ETA.
        wanted = ETA_FIELDS + GEORGIA_FIELDS
    else:
        # Arrival in Kyiv has no remaining public countdown.
        wanted = ETA_FIELDS
    return tuple(field for field in wanted if field in available)


def public_projection(card: Mapping | None) -> dict:
    """Return a stage-aware view; stored history can never leak into another stage."""
    value = dict(card or {})
    stage = stage_number(value.get("status") or value.get("stage"))
    if stage is None:
        return value
    if stage == 1:
        hidden = KOREA_RESET_FIELDS
    elif stage == 2:
        hidden = GEORGIA_FIELDS
    elif stage == 3:
        hidden = SEA_FIELDS
    else:
        hidden = SEA_FIELDS + ETA_FIELDS + GEORGIA_FIELDS
    for field in hidden:
        if field in value:
            value[field] = None
    return value


def diagnostic_placeholder_html(code: str) -> str:
    """Return the complete diagnostic companion page when no report exists yet."""
    if not re.fullmatch(r"UA-[0-9]{4,}", str(code or "")):
        raise StagePayloadError("INVALID_DIAGNOSTIC_CODE")
    return (
        "<!doctype html><html lang='ru'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Комплексная диагностика %s</title></head><body>"
        "<h1>Комплексная диагностика %s</h1>"
        "<p>Материалы комплексной диагностики ожидаются.</p>"
        "<a href='%s.html'>Вернуться к автомобилю</a></body></html>"
        % (code, code, code)
    )


def _quoted(names: Iterable[str]) -> list[str]:
    allowed = set(KOREA_RESET_FIELDS) | {"status"}
    result = []
    for name in names:
        if name not in allowed:
            raise StagePayloadError("UNSAFE_COLUMN:" + str(name))
        result.append('"%s"' % name)
    return result


def install_korea_triggers(connection, available_fields: Iterable[str]) -> dict:
    """Install DB-level defense for direct SQL and legacy writer paths."""
    available = set(available_fields)
    if "status" not in available:
        raise StagePayloadError("STATUS_COLUMN_MISSING")
    reset = [field for field in KOREA_RESET_FIELDS if field in available]
    if not reset:
        raise StagePayloadError("RESET_COLUMNS_MISSING")
    quoted = _quoted(reset)
    assignments = ", ".join("%s=NULL" % name for name in quoted)
    watched = ", ".join(['"status"'] + quoted)
    korea = (
        "(lower(trim(COALESCE(NEW.status,''))) LIKE 'kr_%' "
        "OR lower(trim(COALESCE(NEW.status,''))) LIKE 'korea%')"
    )
    nonempty = " OR ".join(
        "(NEW.%s IS NOT NULL AND trim(CAST(NEW.%s AS TEXT))<>'')" % (name, name)
        for name in quoted
    )
    connection.execute('DROP TRIGGER IF EXISTS "%s"' % TRIGGER_UPDATE)
    connection.execute('DROP TRIGGER IF EXISTS "%s"' % TRIGGER_INSERT)
    connection.execute(
        'CREATE TRIGGER "%s" AFTER UPDATE OF %s ON cars '
        "WHEN %s AND (%s) BEGIN UPDATE cars SET %s WHERE id=NEW.id; END"
        % (TRIGGER_UPDATE, watched, korea, nonempty, assignments)
    )
    connection.execute(
        'CREATE TRIGGER "%s" AFTER INSERT ON cars '
        "WHEN %s AND (%s) BEGIN UPDATE cars SET %s WHERE id=NEW.id; END"
        % (TRIGGER_INSERT, korea, nonempty, assignments)
    )
    return {"update": TRIGGER_UPDATE, "insert": TRIGGER_INSERT, "fields": reset}


def trigger_names() -> tuple[str, str]:
    return TRIGGER_UPDATE, TRIGGER_INSERT


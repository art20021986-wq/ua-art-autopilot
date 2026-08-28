#!/usr/bin/env python3
"""Zero-LLM runtime guard for the UA ART Telegram CRM.

The module is deliberately stdlib-only and fail-open for business actions:
telemetry failures never make a callback, voice command, or media enqueue fail.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import fcntl
import hashlib
import json
import os
import pathlib
import shutil
import sqlite3
import threading
import time
import urllib.parse
import urllib.request
import uuid


CONTRACT_ID = "CRM-ONLINE-GUARD-001-V1.3"
ROOT = pathlib.Path("/home/Carix")
STATUS_PATH = ROOT / ".crm_guard_status.json"
EVENT_PATH = ROOT / ".crm_guard_events.jsonl"
EVENT_LOCK_PATH = ROOT / ".crm_guard_events.lock"
MEDIA_LEDGER_PATH = ROOT / ".crm_media_receipts.jsonl"
MEDIA_LEDGER_LOCK = ROOT / ".crm_media_receipts.lock"
FIELD_SPOOL_PATH = ROOT / ".crm_field_spool.jsonl"
FIELD_SPOOL_LOCK = ROOT / ".crm_field_spool.lock"
RESTART_PATH = ROOT / ".crm_guard_restarts.json"
SPOOL_PATH = ROOT / ".crm_media_spool.jsonl"
DB_PATH = ROOT / "crm.db"
TOKEN_FILES = {"client": ROOT / "bot_token.txt", "crm": ROOT / "team_token.txt"}
ACTION_LIMIT_SECONDS = 5.0
_LOCK = threading.RLock()
_ACTIVE: dict[str, dict] = {}
_HEARTBEATS: dict[str, float] = {}
_LAST: dict[str, object] = {}
_CIRCUITS: dict[str, dict] = {}
_THREAD: threading.Thread | None = None
_STOP = threading.Event()
_STARTED_MONOTONIC = time.monotonic()


def _utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _atomic_json(path: pathlib.Path, value: dict) -> None:
    temporary = path.with_name(".%s.%s.tmp" % (path.name, uuid.uuid4().hex))
    data = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        offset = 0
        while offset < len(data):
            offset += os.write(descriptor, data[offset:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)


def _append_json(path: pathlib.Path, lock_path: pathlib.Path, value: dict) -> None:
    data = (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    with open(lock_path, "a+", encoding="utf-8") as guard:
        fcntl.flock(guard.fileno(), fcntl.LOCK_EX)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(descriptor, data)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
            fcntl.flock(guard.fileno(), fcntl.LOCK_UN)


def _safe_event(kind: str, **fields) -> None:
    try:
        row = {"at": _utc(), "contract_id": CONTRACT_ID, "kind": str(kind)}
        for key, value in fields.items():
            if value is not None and key not in {"token", "text", "voice", "file_id"}:
                row[str(key)] = value
        _append_json(EVENT_PATH, EVENT_LOCK_PATH, row)
    except Exception:
        pass


def _status_snapshot() -> dict:
    now = time.monotonic()
    with _LOCK:
        active = {
            key: {
                "action": item["action"],
                "age_seconds": round(max(0.0, now - item["started"]), 3),
                "card_id": item.get("card_id"),
            }
            for key, item in _ACTIVE.items()
        }
        heartbeats = {
            key: round(max(0.0, now - value), 3)
            for key, value in _HEARTBEATS.items()
        }
        last = dict(_LAST)
    return {
        "contract_id": CONTRACT_ID,
        "generated_at_utc": _utc(),
        "pid": os.getpid(),
        "llm_tokens": 0,
        "active": active,
        "heartbeat_age_seconds": heartbeats,
        "last": last,
    }


def _write_status(extra: dict | None = None) -> None:
    try:
        value = _status_snapshot()
        if extra:
            value.update(extra)
        _atomic_json(STATUS_PATH, value)
    except Exception:
        pass


def start_operation(action: str, card_id=None, event_id=None) -> tuple[str, float]:
    started = time.monotonic()
    token = uuid.uuid4().hex
    with _LOCK:
        _ACTIVE[token] = {
            "action": str(action), "started": started,
            "card_id": int(card_id) if card_id is not None else None,
            "event_id_sha256": hashlib.sha256(str(event_id or token).encode()).hexdigest(),
            "deadline_reported": False,
        }
    return token, started


def finish_operation(token: str, status: str = "ok", detail: str = "") -> float:
    finished = time.monotonic()
    with _LOCK:
        item = _ACTIVE.pop(token, None)
    if not item:
        return 0.0
    elapsed = max(0.0, finished - item["started"])
    bounded_detail = str(detail or "")[:160]
    _safe_event(
        "operation",
        action=item["action"], card_id=item.get("card_id"),
        status=str(status), elapsed_seconds=round(elapsed, 3),
        over_five_seconds=elapsed > ACTION_LIMIT_SECONDS,
        detail=bounded_detail,
    )
    with _LOCK:
        _LAST["operation"] = {
            "action": item["action"], "status": str(status),
            "elapsed_seconds": round(elapsed, 3), "at": _utc(),
        }
    return elapsed


def record_timing(action: str, elapsed_seconds: float, status: str = "ok",
                  card_id=None, detail: str = "") -> None:
    """Record bounded operational telemetry without retaining user content."""
    elapsed = max(0.0, float(elapsed_seconds or 0.0))
    _safe_event(
        "timing", action=str(action), card_id=card_id, status=str(status),
        elapsed_seconds=round(elapsed, 3),
        over_five_seconds=elapsed > ACTION_LIMIT_SECONDS,
        detail=str(detail or "")[:160],
    )
    with _LOCK:
        _LAST[str(action)] = {
            "status": str(status), "elapsed_seconds": round(elapsed, 3),
            "at": _utc(),
        }


def heartbeat(component: str) -> None:
    with _LOCK:
        _HEARTBEATS[str(component)] = time.monotonic()


def circuit_allows(component: str) -> bool:
    """Bounded local breaker; it never calls an LLM or mutates CRM data."""
    now = time.monotonic()
    with _LOCK:
        state = _CIRCUITS.get(str(component)) or {}
        return now >= float(state.get("open_until", 0.0) or 0.0)


def circuit_result(component: str, ok: bool) -> None:
    name = str(component)
    now = time.monotonic()
    with _LOCK:
        state = dict(_CIRCUITS.get(name) or {})
        if ok:
            state = {"failures": 0, "open_until": 0.0}
        else:
            failures = int(state.get("failures", 0) or 0) + 1
            state = {
                "failures": failures,
                "open_until": now + 15.0 if failures >= 3 else 0.0,
            }
        _CIRCUITS[name] = state
    if not ok and state.get("open_until"):
        _safe_event("circuit_open", component=name, seconds=15, status="degraded")


async def safe_callback_answer(query, action: str, card_id=None) -> tuple[str, float]:
    token, started = start_operation(action, card_id, getattr(query, "id", None))
    try:
        await asyncio.wait_for(query.answer(), timeout=0.75)
        _safe_event("callback_ack", action=action, card_id=card_id,
                    elapsed_seconds=round(time.monotonic() - started, 3), status="ok")
    except Exception as exc:
        _safe_event("callback_ack", action=action, card_id=card_id,
                    elapsed_seconds=round(time.monotonic() - started, 3),
                    status="continued", detail=type(exc).__name__)
    return token, started


def remaining(started: float, reserve: float = 0.25) -> float:
    return max(0.05, ACTION_LIMIT_SECONDS - reserve - (time.monotonic() - started))


def media_receipt_key(card_id, target, unique_id) -> str:
    raw = "%s\0%s\0%s" % (int(card_id), str(target), str(unique_id))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _media_keys_locked() -> set[str]:
    try:
        lines = MEDIA_LEDGER_PATH.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return set()
    result = set()
    for line in lines[-20000:]:
        try:
            value = json.loads(line)
            if value.get("key"):
                result.add(str(value["key"]))
        except Exception:
            pass
    return result


def media_seen(key: str) -> bool:
    try:
        with open(MEDIA_LEDGER_LOCK, "a+", encoding="utf-8") as guard:
            fcntl.flock(guard.fileno(), fcntl.LOCK_SH)
            try:
                return str(key) in _media_keys_locked()
            finally:
                fcntl.flock(guard.fileno(), fcntl.LOCK_UN)
    except Exception:
        return False


def media_mark(key: str, card_id, target) -> None:
    try:
        with open(MEDIA_LEDGER_LOCK, "a+", encoding="utf-8") as guard:
            fcntl.flock(guard.fileno(), fcntl.LOCK_EX)
            try:
                keys = _media_keys_locked()
                if str(key) in keys:
                    return
                row = {"key": str(key), "card_id": int(card_id),
                       "target": str(target), "saved_at": int(time.time())}
                descriptor = os.open(
                    MEDIA_LEDGER_PATH, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
                try:
                    data = (json.dumps(row, separators=(",", ":")) + "\n").encode()
                    os.write(descriptor, data)
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            finally:
                fcntl.flock(guard.fileno(), fcntl.LOCK_UN)
    except Exception:
        pass


def _safe_json_value(value):
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except Exception:
        return str(value)


def _field_rows_unlocked() -> list[dict]:
    try:
        lines = FIELD_SPOOL_PATH.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    rows = []
    for line in lines:
        try:
            item = json.loads(line)
            if isinstance(item, dict) and item.get("key"):
                rows.append(item)
        except Exception:
            pass
    return rows


def _field_rows() -> list[dict]:
    try:
        with open(FIELD_SPOOL_LOCK, "a+", encoding="utf-8") as guard:
            fcntl.flock(guard.fileno(), fcntl.LOCK_SH)
            try:
                return _field_rows_unlocked()
            finally:
                fcntl.flock(guard.fileno(), fcntl.LOCK_UN)
    except Exception:
        return []


def enqueue_field_update(table, card_id, field, new_value, actor_id,
                         expected_old=None, correction=False, mode="set") -> dict:
    """Durably accept one scalar CRM write without spending LLM tokens."""
    table = str(table or "")
    field = str(field or "")
    mode = str(mode) if str(mode) in {"set", "cas", "audit"} else "set"
    plain_field = field.replace("_", "")
    if (table not in {"cars", "clients"} or not field
            or not (field[0].isalpha() or field[0] == "_")
            or not plain_field.isalnum()):
        raise ValueError("invalid field queue target")
    row = {
        "table": table, "card_id": int(card_id), "field": field,
        "new_value": _safe_json_value(new_value),
        "expected_old": _safe_json_value(expected_old),
        "actor_id": int(actor_id), "correction": bool(correction),
        "mode": mode, "accepted_at": int(time.time()),
    }
    identity = json.dumps(
        {key: value for key, value in row.items() if key != "accepted_at"},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    row["key"] = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    with open(FIELD_SPOOL_LOCK, "a+", encoding="utf-8") as guard:
        fcntl.flock(guard.fileno(), fcntl.LOCK_EX)
        try:
            if row["key"] in {item.get("key") for item in _field_rows_unlocked()}:
                return {"state": "duplicate", "key": row["key"]}
            descriptor = os.open(
                FIELD_SPOOL_PATH, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                data = (json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
                os.write(descriptor, data)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        finally:
            fcntl.flock(guard.fileno(), fcntl.LOCK_UN)
    _safe_event("field_queued", table=table, card_id=int(card_id), field=field, mode=mode)
    return {"state": "accepted", "key": row["key"]}


def _field_spool_state() -> dict:
    rows = _field_rows()
    now = int(time.time())
    ages = [max(0, now - int(row.get("accepted_at") or now)) for row in rows]
    return {"queued": len(rows), "oldest_age_seconds": max(ages) if ages else 0}


def _field_remove(keys) -> None:
    done = {str(key) for key in keys}
    if not done:
        return
    with open(FIELD_SPOOL_LOCK, "a+", encoding="utf-8") as guard:
        fcntl.flock(guard.fileno(), fcntl.LOCK_EX)
        try:
            rows = [row for row in _field_rows_unlocked() if str(row.get("key")) not in done]
            temporary = FIELD_SPOOL_PATH.with_name(".%s.%s.tmp" % (
                FIELD_SPOOL_PATH.name, uuid.uuid4().hex))
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                for row in rows:
                    os.write(descriptor, (json.dumps(
                        row, ensure_ascii=False, separators=(",", ":")) + "\n").encode())
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            os.replace(temporary, FIELD_SPOOL_PATH)
        finally:
            fcntl.flock(guard.fileno(), fcntl.LOCK_UN)


def _attempt_field_recovery(state: dict) -> dict:
    if state.get("queued", 0) <= 0:
        return {"attempted": False}
    done = []
    terminal = {"same", "filled", "conflict", "missing_card", "unknown", "invalid", "empty"}
    try:
        import db
        import cars_ui
        for row in _field_rows()[:25]:
            try:
                if row.get("mode") == "cas":
                    ok, reason = cars_ui._v168_cas_write(
                        row["card_id"], row["field"], row.get("expected_old"),
                        row.get("new_value"), row["actor_id"],
                        bool(row.get("correction")), _queue_on_busy=False)
                    if ok or reason in terminal:
                        done.append(row["key"])
                    elif reason == "busy":
                        break
                elif row.get("mode") == "audit":
                    db.log_action(
                        row["actor_id"], "card_edit", row["table"], row["card_id"],
                        row["field"], row.get("expected_old"), row.get("new_value"))
                    done.append(row["key"])
                else:
                    db.update_card_field(
                        row["table"], row["card_id"], row["field"],
                        row.get("new_value"), row["actor_id"], _queue_on_busy=False)
                    done.append(row["key"])
            except Exception as exc:
                lowered = str(exc).casefold()
                if any(word in lowered for word in ("locked", "busy", "queue timeout")):
                    break
                _safe_event("field_recovery", status="error", card_id=row.get("card_id"),
                            field=row.get("field"), detail=type(exc).__name__)
                break
        _field_remove(done)
        if done:
            _safe_event("field_recovery", status="ok", processed=len(done))
        return {"attempted": True, "processed": len(done),
                "remaining": _field_spool_state().get("queued", 0)}
    except Exception as exc:
        _safe_event("field_recovery", status="error", detail=type(exc).__name__)
        return {"attempted": True, "processed": len(done), "error": type(exc).__name__}


def _spool_state() -> dict:
    rows = []
    bad = 0
    try:
        lines = SPOOL_PATH.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        lines = []
    for line in lines:
        try:
            rows.append(json.loads(line))
        except Exception:
            bad += 1
    now = int(time.time())
    ages = [max(0, now - int(row.get("accepted_at") or now)) for row in rows]
    return {"queued": len(rows), "invalid_lines": bad,
            "oldest_age_seconds": max(ages) if ages else 0}


def _db_state() -> dict:
    started = time.monotonic()
    last = None
    for attempt in range(3):
        try:
            con = sqlite3.connect("file:%s?mode=ro" % DB_PATH, uri=True, timeout=0.8)
            try:
                quick = con.execute("PRAGMA quick_check").fetchone()[0]
                return {"quick_check": quick,
                        "latency_seconds": round(time.monotonic() - started, 3),
                        "attempts": attempt + 1}
            finally:
                con.close()
        except Exception as exc:
            last = exc
            if attempt < 2:
                time.sleep(0.12 * (attempt + 1))
    return {"quick_check": "error", "error": type(last).__name__ if last else "Unknown"}


def _token_health() -> dict:
    result = {}
    token_hashes = {}
    for name, path in TOKEN_FILES.items():
        token = ""
        started = time.monotonic()
        last = None
        for attempt in range(2):
            try:
                token = path.read_text(encoding="utf-8").strip()
                token_hashes[name] = hashlib.sha256(token.encode()).hexdigest()
                url = "https://api.telegram.org/bot%s/getMe" % urllib.parse.quote(token, safe=":")
                with urllib.request.urlopen(url, timeout=3.0) as response:
                    value = json.loads(response.read(100_000).decode("utf-8"))
                if value.get("ok"):
                    result[name] = {"ok": True,
                                    "latency_seconds": round(time.monotonic() - started, 3),
                                    "attempts": attempt + 1}
                    break
                last = RuntimeError("telegram_not_ok")
            except Exception as exc:
                last = exc
            if attempt == 0:
                time.sleep(0.2)
        if name not in result:
            result[name] = {"ok": False, "error": type(last).__name__ if last else "Unknown"}
    result["tokens_distinct"] = token_hashes.get("client") != token_hashes.get("crm")
    return result


def _restart_budget_available() -> bool:
    now = int(time.time())
    try:
        value = json.loads(RESTART_PATH.read_text(encoding="utf-8"))
        recent = [int(item) for item in value.get("times", []) if now - int(item) < 900]
    except Exception:
        recent = []
    if len(recent) >= 3:
        return False
    recent.append(now)
    try:
        _atomic_json(RESTART_PATH, {"times": recent, "updated_at_utc": _utc()})
    except Exception:
        return False
    return True


def _attempt_spool_recovery(state: dict) -> dict:
    if state.get("queued", 0) <= 0 or state.get("oldest_age_seconds", 0) <= 5:
        return {"attempted": False}
    try:
        import cars_ui
        value = cars_ui._v165_spool_drain(100)
        _safe_event("autorecovery", action="media_spool_drain", status="ok",
                    processed=value.get("processed"), remaining=value.get("remaining"))
        return {"attempted": True, "result": value}
    except Exception as exc:
        _safe_event("autorecovery", action="media_spool_drain", status="error",
                    detail=type(exc).__name__)
        return {"attempted": True, "error": type(exc).__name__}


def _supervisor_loop() -> None:
    last_db = 0.0
    last_tokens = 0.0
    last_recovery = 0.0
    last_field_recovery = 0.0
    token_state = {}
    db_state = {}
    last_stale_report = {}
    while not _STOP.wait(1.0):
        now = time.monotonic()
        heartbeat("guard")
        overdue = []
        with _LOCK:
            for key, item in _ACTIVE.items():
                age = now - item["started"]
                if age > ACTION_LIMIT_SECONDS and not item.get("deadline_reported"):
                    item["deadline_reported"] = True
                    overdue.append((key, item["action"], item.get("card_id"), age))
            stale_heartbeats = {
                name: round(now - stamp, 3)
                for name, stamp in _HEARTBEATS.items()
                if name in {"crm_bot", "client_bot"} and now - stamp > 7.0
            }
        for _key, action, card_id, age in overdue:
            _safe_event("p0_deadline", action=action, card_id=card_id,
                        elapsed_seconds=round(age, 3))
        for component, age in stale_heartbeats.items():
            if now - float(last_stale_report.get(component, 0.0)) >= 15.0:
                last_stale_report[component] = now
                _safe_event("p0_heartbeat", component=component,
                            elapsed_seconds=age, status="stale")
        spool = _spool_state()
        recovery = {"attempted": False}
        if spool["oldest_age_seconds"] > 5 and now - last_recovery > 2:
            last_recovery = now
            recovery = _attempt_spool_recovery(spool)
            spool = _spool_state()
        field_spool = _field_spool_state()
        field_recovery = {"attempted": False}
        if field_spool["queued"] > 0 and now - last_field_recovery > 1:
            last_field_recovery = now
            field_recovery = _attempt_field_recovery(field_spool)
            field_spool = _field_spool_state()
        if now - last_db >= 5:
            last_db = now
            db_state = _db_state()
            if db_state.get("quick_check") not in ("ok",):
                _safe_event("p0_db", status="error", detail=db_state.get("error", "quick_check"))
        if now - last_tokens >= 30:
            last_tokens = now
            token_state = _token_health()
            if not token_state.get("tokens_distinct") or any(
                    not token_state.get(name, {}).get("ok") for name in ("client", "crm")):
                _safe_event("p0_bot_health", status="error")
        try:
            disk = shutil.disk_usage(ROOT)
            disk_free = disk.free
        except Exception:
            disk_free = None
        extra = {"db": db_state, "spool": spool, "field_spool": field_spool,
                 "bots": token_state, "disk_free_bytes": disk_free,
                 "last_recovery": recovery, "last_field_recovery": field_recovery}
        _write_status(extra)


def start_supervisor() -> bool:
    global _THREAD
    with _LOCK:
        if _THREAD is not None and _THREAD.is_alive():
            return False
        _STOP.clear()
        _THREAD = threading.Thread(target=_supervisor_loop,
                                   name="crm-online-guard", daemon=True)
        _THREAD.start()
    _safe_event("guard_start", status="ok", pid=os.getpid(), llm_tokens=0)
    return True


def stop_supervisor() -> None:
    _STOP.set()


def health() -> dict:
    return _status_snapshot()

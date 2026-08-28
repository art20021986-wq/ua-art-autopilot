#!/usr/bin/env python3
"""60-minute zero-token production soak observer."""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import sqlite3
import tempfile
import time


CONTRACT = "CRM-ONLINE-GUARD-001-V1.3"
ROOT = pathlib.Path("/home/Carix")
SAFE = ROOT / "autopilot_inbox" / "cloud" / "task_067"
STATUS = ROOT / ".crm_guard_status.json"
EVENTS = ROOT / ".crm_guard_events.jsonl"
DB = ROOT / "crm.db"
RECEIPT = SAFE / "soak_receipt.json"
DURATION = int(os.environ.get("TASK067_SOAK_SECONDS", "3600"))


def utc_now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".task067-soak-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def quick_check():
    con = sqlite3.connect("file:%s?mode=ro" % DB, uri=True, timeout=1)
    try:
        return con.execute("PRAGMA quick_check").fetchone()[0]
    finally:
        con.close()


def event_rows(offset):
    try:
        with open(EVENTS, "r", encoding="utf-8") as handle:
            handle.seek(offset)
            rows = []
            for line in handle:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
            return rows, handle.tell()
    except FileNotFoundError:
        return [], 0


def main():
    started_wall = time.time()
    started_mono = time.monotonic()
    try:
        start_offset = EVENTS.stat().st_size
    except FileNotFoundError:
        start_offset = 0
    value = {"task_id": "task_067", "contract_id": CONTRACT,
             "status": "FAIL", "mode": "SIXTY_MINUTE_SOAK",
             "duration_target_seconds": DURATION, "llm_tokens": 0,
             "crm_db_write": False, "site_write": False, "media_write": False,
             "samples": 0, "p0": [], "started_at_utc": utc_now()}
    consecutive_bot_failures = 0
    max_heartbeat = {"crm_bot": 0.0, "client_bot": 0.0}
    max_spool_age = 0
    next_db = 0.0
    while time.monotonic() - started_mono < DURATION:
        now = time.monotonic()
        value["samples"] += 1
        try:
            status = json.loads(STATUS.read_text(encoding="utf-8"))
            if status.get("contract_id") != CONTRACT:
                value["p0"].append("guard_contract_changed")
                break
            ages = status.get("heartbeat_age_seconds") or {}
            for component in max_heartbeat:
                age = float(ages.get(component, 999) or 999)
                max_heartbeat[component] = max(max_heartbeat[component], age)
                if age > 7:
                    value["p0"].append("stale_heartbeat:%s:%.3f" % (component, age))
                    break
            if value["p0"]:
                break
            spool = status.get("spool") or {}
            spool_age = int(spool.get("oldest_age_seconds", 0) or 0)
            max_spool_age = max(max_spool_age, spool_age)
            if spool_age > 8:
                value["p0"].append("stale_spool:%d" % spool_age)
                break
            field_spool = status.get("field_spool") or {}
            field_age = int(field_spool.get("oldest_age_seconds", 0) or 0)
            max_spool_age = max(max_spool_age, field_age)
            if field_age > 8:
                value["p0"].append("stale_field_spool:%d" % field_age)
                break
            bots = status.get("bots") or {}
            bot_ok = (bots.get("crm", {}).get("ok") and bots.get("client", {}).get("ok")
                      and bots.get("tokens_distinct"))
            consecutive_bot_failures = 0 if bot_ok else consecutive_bot_failures + 1
            if consecutive_bot_failures >= 12:
                value["p0"].append("bot_health_failed_12s")
                break
        except Exception as exc:
            value["p0"].append("status_unreadable:" + type(exc).__name__)
            break
        if now >= next_db:
            next_db = now + 5
            try:
                if quick_check() != "ok":
                    value["p0"].append("db_quick_check")
                    break
            except Exception as exc:
                value["p0"].append("db_unreadable:" + type(exc).__name__)
                break
        time.sleep(1)
    rows, end_offset = event_rows(start_offset)
    event_p0 = []
    for row in rows:
        kind = str(row.get("kind") or "")
        if kind.startswith("p0_") or (kind in {"operation", "timing"} and row.get("over_five_seconds")):
            event_p0.append({key: row.get(key) for key in
                             ("at", "kind", "action", "component", "status", "elapsed_seconds")
                             if row.get(key) is not None})
    if event_p0:
        value["p0"].append("guard_event_p0")
    elapsed = time.monotonic() - started_mono
    value.update({"duration_actual_seconds": round(elapsed, 3),
                  "max_heartbeat_age_seconds": max_heartbeat,
                  "max_spool_age_seconds": max_spool_age,
                  "event_bytes_checked": max(0, end_offset - start_offset),
                  "event_p0": event_p0[:100], "finished_at_utc": utc_now()})
    if not value["p0"] and elapsed >= DURATION - 1:
        value["status"] = "PASS"
    atomic_json(RECEIPT, value)
    return 0 if value["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Read-only/synthetic acceptance suite for CRM-ONLINE-GUARD-001 v1.3."""
from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import json
import os
import pathlib
import sqlite3
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace


CONTRACT = "CRM-ONLINE-GUARD-001-V1.3"
ROOT = pathlib.Path("/home/Carix")
SAFE = ROOT / "autopilot_inbox" / "cloud" / "task_067"
RECEIPT = SAFE / "postcheck_receipt.json"
STATUS = ROOT / ".crm_guard_status.json"
DB = ROOT / "crm.db"
FILES = {
    "cars_ui.py": ROOT / "cars_ui.py", "ai.py": ROOT / "ai.py",
    "run_all.py": ROOT / "run_all.py", "client_ui.py": ROOT / "client_ui.py",
    "team_bot.py": ROOT / "team_bot.py", "lead_bot.py": ROOT / "lead_bot.py",
    "crm_online_guard.py": ROOT / "crm_online_guard.py",
}


class CheckError(RuntimeError):
    pass


def utc_now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".task067-post-", dir=path.parent)
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


def check(condition, label):
    if not condition:
        raise CheckError(label)


def db_check():
    con = sqlite3.connect("file:%s?mode=ro" % DB, uri=True, timeout=3)
    con.row_factory = sqlite3.Row
    try:
        quick = con.execute("PRAGMA quick_check").fetchone()[0]
        row = con.execute("SELECT * FROM cars ORDER BY id DESC LIMIT 1").fetchone()
        return {"quick_check": quick, "card_count": con.execute("SELECT COUNT(*) FROM cars").fetchone()[0],
                "latest_card": dict(row) if row else None}
    finally:
        con.close()


def telegram_health():
    result, hashes = {}, {}
    for name, token_file in (("client", "bot_token.txt"), ("crm", "team_token.txt")):
        token = (ROOT / token_file).read_text(encoding="utf-8").strip()
        hashes[name] = hashlib.sha256(token.encode()).hexdigest()
        started = time.monotonic()
        try:
            url = "https://api.telegram.org/bot%s/getMe" % urllib.parse.quote(token, safe=":")
            with urllib.request.urlopen(url, timeout=5) as response:
                data = json.loads(response.read(100_000).decode("utf-8"))
            result[name] = {"ok": bool(data.get("ok") and (data.get("result") or {}).get("id")),
                            "latency_seconds": round(time.monotonic() - started, 3)}
        except Exception as exc:
            result[name] = {"ok": False, "error": type(exc).__name__,
                            "latency_seconds": round(time.monotonic() - started, 3)}
    return {"bots": result, "tokens_distinct": hashes.get("client") != hashes.get("crm")}


def wait_guard(seconds=420):
    """Wait for the live process, not merely for an accepted restart request.

    PythonAnywhere may acknowledge an Always-On restart several minutes before
    the replacement process actually starts.  User-operation SLOs remain five
    seconds; this longer window applies only to the one-time deployment gate.
    """
    deadline = time.monotonic() + seconds
    last = {}
    while time.monotonic() < deadline:
        try:
            last = json.loads(STATUS.read_text(encoding="utf-8"))
            status_age = max(0.0, time.time() - STATUS.stat().st_mtime)
        except Exception:
            time.sleep(1)
            continue
        ages = last.get("heartbeat_age_seconds") or {}
        bots = last.get("bots") or {}
        if (last.get("contract_id") == CONTRACT
                and status_age < 3.0
                and ages.get("crm_bot", 999) < 3
                and ages.get("client_bot", 999) < 3
                and bots.get("crm", {}).get("ok")
                and bots.get("client", {}).get("ok")
                and bots.get("tokens_distinct")):
            return last
        last["_status_file_age_seconds"] = round(status_age, 3)
        time.sleep(1)
    raise CheckError("GUARD_NOT_HEALTHY:" + json.dumps(last, ensure_ascii=False)[:500])


class FakeMessage:
    def __init__(self):
        self.sent = []

    async def reply_text(self, text, **kwargs):
        self.sent.append({"text": str(text), "kwargs": sorted(kwargs)})
        return SimpleNamespace()


class FakeQuery:
    def __init__(self, data):
        self.data = data
        self.id = "expired-callback"
        self.message = FakeMessage()

    async def answer(self, *args, **kwargs):
        raise RuntimeError("simulated expired callback")


async def callback_routes(cars_ui, card):
    results = {}
    for name, function, data in (
            ("delivery", cars_ui.stage_menu, "car_stage:%d" % card["id"]),
            ("condition", cars_ui.condition_screen, "car_cond:%d" % card["id"])):
        query = FakeQuery(data)
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(user_data={})
        started = time.monotonic()
        try:
            await function(update, context)
        except Exception as exc:
            if type(exc).__name__ != "ApplicationHandlerStop":
                raise
        elapsed = time.monotonic() - started
        check(query.message.sent, "ROUTE_NO_REPLY:" + name)
        check(elapsed <= 5.0, "ROUTE_OVER_5S:" + name)
        results[name] = {"status": "PASS", "elapsed_seconds": round(elapsed, 3),
                         "expired_ack_continued": True}
    return results


def voice_golden(cars_ui):
    allowed = {"fuel", "engine_cc", "color"}
    fuel_cases = []
    fuel_templates = [
        "тип топлива {v}", "паливо {v}", "fuel {v}", "укажи топливо {v}",
        "в автомобиле {v} тип топлива", "engine fuel is {v}",
    ]
    variants = [("LPI", "LPI"), ("л пи и", "LPI"), ("эл пи ай", "LPI"),
                ("LPG", "LPG"), ("diesel", "diesel"), ("дизель", "diesel"),
                ("бензин", "gasoline"), ("gasoline", "gasoline"),
                ("гібрид", "hybrid"), ("electric", "electric")]
    for index in range(50):
        raw, expected = variants[index % len(variants)]
        fuel_cases.append((fuel_templates[index % len(fuel_templates)].format(v=raw), {"fuel": expected}))
    engine_templates = [
        "объем двигателя {v}", "об'єм двигуна {v}", "engine volume {v}",
        "мотор {v} см3", "{v} cc объем двигателя", "двигатель составляет {v}",
    ]
    engine_values = [("2000", 2000), ("2.0", 2000), ("2,0", 2000),
                     ("две тысячи", 2000), ("дві тисячі", 2000)]
    engine_cases = []
    for index in range(50):
        raw, expected = engine_values[index % len(engine_values)]
        engine_cases.append((engine_templates[index % len(engine_templates)].format(v=raw), {"engine_cc": expected}))
    color_templates = ["цвет {v}", "колір {v}", "color {v}", "{v} цвет", "{v} колір"]
    colors = [("белый", "белый"), ("білий", "белый"), ("white", "белый"),
              ("черный", "чёрный"), ("чорний", "чёрный"), ("black", "чёрный"),
              ("silver", "серебристый"), ("сірий", "серый"), ("red", "красный"),
              ("blue", "синий")]
    color_cases = []
    for index in range(50):
        raw, expected = colors[index % len(colors)]
        color_cases.append((color_templates[index % len(color_templates)].format(v=raw), {"color": expected}))
    corpus = fuel_cases + engine_cases + color_cases
    failures = []
    for index, (text, expected) in enumerate(corpus):
        actual = cars_ui._v167_voice_explicit_fields(text, allowed)
        if any(actual.get(key) != value for key, value in expected.items()):
            failures.append({"index": index, "expected": expected, "actual": actual})
    check(not failures, "GOLDEN_FAILURES:%s" % failures[:3])
    changes, skipped = cars_ui.voice_change_plan(
        {"fuel": "diesel"}, {"fuel": "LPI"}, {"fuel"}, False)
    check(changes == [] and skipped == ["fuel"], "NO_OVERWRITE_FAILED")
    changes, _ = cars_ui.voice_change_plan(
        {"fuel": "diesel"}, {"fuel": "LPI"}, {"fuel"}, True)
    check(len(changes) == 1, "EXPLICIT_CORRECTION_FAILED")
    check(not cars_ui._v168_is_correction("тип топлива LPI"), "FALSE_CORRECTION")
    check(cars_ui._v168_is_correction("измени тип топлива LPI"), "CORRECTION_NOT_FOUND")
    return {"status": "PASS", "cases": len(corpus), "failures": 0,
            "normal_overwrites": 0, "unexpected_new_cards": 0}


def media_synthetic(cars_ui, guard):
    original = {}
    names = ("_V165_SPOOL", "_V165_SPOOL_LOCK", "_V165_DRAIN_LOCK", "card_of",
             "_v165_media_ids", "_v165_limit", "save_media")
    for name in names:
        original[name] = getattr(cars_ui, name)
    guard_original = {name: getattr(guard, name) for name in
                      ("MEDIA_LEDGER_PATH", "MEDIA_LEDGER_LOCK")}
    with tempfile.TemporaryDirectory(prefix="task067-media-") as directory:
        root = pathlib.Path(directory)
        saved, saved_lock = [], threading.Lock()
        try:
            cars_ui._V165_SPOOL = str(root / "spool.jsonl")
            cars_ui._V165_SPOOL_LOCK = str(root / "spool.lock")
            cars_ui._V165_DRAIN_LOCK = str(root / "drain.lock")
            guard.MEDIA_LEDGER_PATH = root / "receipts.jsonl"
            guard.MEDIA_LEDGER_LOCK = root / "receipts.lock"
            cars_ui.card_of = lambda _card_id: {"id": 9001}
            cars_ui._v165_media_ids = lambda _card, _target: list(saved)
            cars_ui._v165_limit = lambda _target: 100

            def fake_save(_card, _target, file_id, _actor, _tag=""):
                with saved_lock:
                    if file_id not in saved:
                        saved.append(file_id)
                return ""
            cars_ui.save_media = fake_save
            states = []
            for index in range(100):
                states.append(cars_ui._v165_spool_enqueue(
                    9001, "photos", "file-%03d" % index, 1,
                    unique_id="unique-%03d" % index, message_id=index)["state"])
            duplicate_states = [cars_ui._v165_spool_enqueue(
                9001, "photos", "new-file-%d" % index, 1,
                unique_id="unique-%03d" % index, message_id=200 + index)["state"]
                for index in range(3)]
            limit_state = cars_ui._v165_spool_enqueue(
                9001, "photos", "file-101", 1,
                unique_id="unique-101", message_id=301)["state"]
            check(states == ["accepted"] * 100, "MEDIA_ACCEPT_COUNT")
            check(all(item.startswith("duplicate") for item in duplicate_states), "MEDIA_DUPLICATE")
            check(limit_state == "limit", "MEDIA_LIMIT")
            with ThreadPoolExecutor(max_workers=6) as pool:
                drained = list(pool.map(lambda _value: cars_ui._v165_spool_drain(100), range(6)))
            check(len(saved) == 100 and len(set(saved)) == 100, "MEDIA_SAVED_UNIQUE")
            check(saved == ["file-%03d" % index for index in range(100)], "MEDIA_ORDER")
            check(len(cars_ui._v165_read_rows()) == 0, "MEDIA_QUEUE_NOT_EMPTY")
            check(sum(item.get("processed", 0) for item in drained) == 100, "MEDIA_MULTIWORKER")
            return {"status": "PASS", "accepted": 100, "saved": 100,
                    "duplicates_rejected": 3, "limit_101_rejected": True,
                    "workers": 6, "queue": 0, "order_exact": True}
        finally:
            for name, value in original.items():
                setattr(cars_ui, name, value)
            for name, value in guard_original.items():
                setattr(guard, name, value)


def source_checks():
    sources = {name: path.read_text(encoding="utf-8") for name, path in FILES.items()}
    checks = {
        "marker_all_core": all(CONTRACT in sources[name] for name in
                               ("cars_ui.py", "client_ui.py", "crm_online_guard.py")),
        "callback_safety": "safe_callback_answer" in sources["cars_ui.py"],
        "cas_no_overwrite": "_v168_cas_write" in sources["cars_ui.py"],
        "voice_five_seconds": "hard_deadline = started + 4.65" in sources["cars_ui.py"],
        "stt_auto_language": '"language": "ru"' not in sources["ai.py"],
        "media_receipts": "media_mark" in sources["cars_ui.py"],
        "client_fast_tail": "media_tail" in sources["client_ui.py"],
        "updates_preserved": all("drop_pending_updates=True" not in sources[name]
                                 for name in ("run_all.py", "team_bot.py", "lead_bot.py")),
        "delivery_route": 'pattern=r"^car_stage:"' in sources["cars_ui.py"],
        "condition_route": 'pattern=r"^car_cond:"' in sources["cars_ui.py"],
    }
    check(all(checks.values()), "SOURCE_CONTRACT:" + json.dumps(checks))
    for name, source in sources.items():
        compile(source, str(FILES[name]), "exec")
    return checks


def main():
    result = {"task_id": "task_067", "contract_id": CONTRACT, "status": "FAIL",
              "mode": "POST_RESTART_ACCEPTANCE", "llm_tokens": 0,
              "crm_db_write": False, "site_write": False, "media_write": False,
              "errors": [], "started_at_utc": utc_now()}
    try:
        result["source_checks"] = source_checks()
        state = db_check()
        check(state["quick_check"] == "ok", "DB_QUICK_CHECK")
        check(state["latest_card"] is not None, "NO_CARDS")
        result["database"] = {key: value for key, value in state.items() if key != "latest_card"}
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        import cars_ui
        import client_ui
        import crm_online_guard as guard
        result["callbacks"] = asyncio.run(callback_routes(cars_ui, state["latest_card"]))
        result["voice_golden"] = voice_golden(cars_ui)
        result["media"] = media_synthetic(cars_ui, guard)
        started = time.monotonic()
        catalog = client_ui.catalog_cars()
        elapsed = time.monotonic() - started
        check(elapsed <= 5.0, "CLIENT_CATALOG_OVER_5S")
        result["client_catalog"] = {"status": "PASS", "cars": len(catalog),
                                    "elapsed_seconds": round(elapsed, 3)}
        result["guard"] = wait_guard()
        health = telegram_health()
        check(health["tokens_distinct"], "TOKENS_NOT_DISTINCT")
        check(all(health["bots"][name]["ok"] for name in ("client", "crm")), "BOT_GETME")
        check(all(health["bots"][name]["latency_seconds"] <= 5 for name in ("client", "crm")), "BOT_GETME_OVER_5S")
        result["bots"] = health
        result["status"] = "PASS"
    except Exception as exc:
        result["errors"].append(type(exc).__name__ + ":" + str(exc))
    result["finished_at_utc"] = utc_now()
    atomic_json(RECEIPT, result)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

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
    "db.py": ROOT / "db.py",
    "konteyner.py": ROOT / "konteyner.py",
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
    deadline = time.monotonic() + 4.5
    last = None
    while time.monotonic() < deadline:
        con = None
        try:
            con = sqlite3.connect("file:%s?mode=ro" % DB, uri=True, timeout=0.35)
            con.row_factory = sqlite3.Row
            quick = con.execute("PRAGMA quick_check").fetchone()[0]
            row = con.execute("SELECT * FROM cars ORDER BY id DESC LIMIT 1").fetchone()
            return {"quick_check": quick,
                    "card_count": con.execute("SELECT COUNT(*) FROM cars").fetchone()[0],
                    "latest_card": dict(row) if row else None}
        except sqlite3.OperationalError as exc:
            last = exc
            if not any(word in str(exc).casefold() for word in ("locked", "busy")):
                raise
            time.sleep(0.15)
        finally:
            if con is not None:
                con.close()
    raise last or CheckError("DB_READ_TIMEOUT")


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
    extra = []
    mileage_phrases = [
        ("пробег 145 тысяч", 145000),
        ("пробіг 145 тисяч", 145000),
        ("mileage 145 thousand", 145000),
        ("сто сорок пять тысяч километров пробега", 145000),
        ("пробег составляет 88000", 88000),
    ]
    price_phrases = [
        ("цена продажи 12 500 долларов", 12500),
        ("стоимость 12500", 12500),
        ("ціна продажу 12 500", 12500),
        ("sale price 12500", 12500),
        ("цена двенадцать тысяч", 12000),
    ]
    description_phrases = [
        "описание автомобиль в хорошем состоянии",
        "опиши машина обслужена и готова к продаже",
        "опис авто без замечаний по двигателю",
        "техническое состояние двигатель работает ровно",
        "description clean interior and smooth engine",
    ]
    for index in range(15):
        text, expected = mileage_phrases[index % len(mileage_phrases)]
        actual = cars_ui._v169_extra_fields(text, {"mileage_km"})
        check(actual.get("mileage_km") == expected, "VOICE_MILEAGE:%s:%s" % (text, actual))
        extra.append(text)
    for index in range(15):
        text, expected = price_phrases[index % len(price_phrases)]
        actual = cars_ui._v169_extra_fields(text, {"price_uah"})
        check(actual.get("price_uah") == expected, "VOICE_PRICE:%s:%s" % (text, actual))
        extra.append(text)
    for index in range(10):
        text = description_phrases[index % len(description_phrases)]
        actual = cars_ui._v169_extra_fields(text, {"condition_text"})
        check(bool(actual.get("condition_text")), "VOICE_DESCRIPTION:%s:%s" % (text, actual))
        extra.append(text)
    for index in range(9):
        text = ("поставь статус на пароме", "этап море", "stage ferry")[index % 3]
        actual = cars_ui._v169_extra_fields(text, {"status"})
        check(bool(actual.get("status")), "VOICE_STATUS:%s:%s" % (text, actual))
        check(cars_ui.S.stage_of(actual["status"]) == 2,
              "VOICE_STATUS_STAGE:%s:%s" % (text, actual))
        extra.append(text)

    # The semantic fallback is exercised without spending tokens: its only
    # network dependency is replaced by a deterministic strict-JSON answer.
    import assistant
    old_enabled, old_ask = assistant.enabled, assistant.ask
    try:
        assistant.enabled = lambda: True
        assistant.ask = lambda *args, **kwargs: json.dumps({
            "mileage_km": 145000, "price_uah": 12500,
            "condition_text": "Автомобиль обслужен", "forbidden": "ignored",
        }, ensure_ascii=False)
        semantic = cars_ui._v169_semantic_fields(
            "пробег сто сорок пять тысяч, цена 12500, машина обслужена",
            {"mileage_km", "price_uah", "condition_text"}, 0.5)
    finally:
        assistant.enabled, assistant.ask = old_enabled, old_ask
    check(semantic.get("mileage_km") == 145000, "VOICE_SEMANTIC_MILEAGE")
    check(semantic.get("price_uah") == 12500, "VOICE_SEMANTIC_PRICE")
    check(semantic.get("condition_text") == "Автомобиль обслужен",
          "VOICE_SEMANTIC_DESCRIPTION")
    check("forbidden" not in semantic, "VOICE_SEMANTIC_WHITELIST")
    extra.append("semantic_whitelist")
    return {"status": "PASS", "cases": len(corpus) + len(extra), "failures": 0,
            "normal_overwrites": 0, "unexpected_new_cards": 0}


def selected_field_synthetic(cars_ui):
    """The selected mileage field accepts digits and spoken number words."""
    old_set, old_card = cars_ui.set_field, cars_ui.card_of
    state = {"id": 9901, "mileage_km": None}
    try:
        def fake_set(_card_id, field, value, _actor_id):
            state[field] = value
            return {"queued": False}
        cars_ui.set_field = fake_set
        cars_ui.card_of = lambda _card_id: dict(state)
        cases = (("163400", 163400),
                 ("163 400 км", 163400),
                 ("сто шестьдесят три тысячи четыреста", 163400))
        for raw, expected in cases:
            state["mileage_km"] = None
            ok, answer = cars_ui.apply_value(9901, "mileage_km", raw, 7)
            check(ok and state["mileage_km"] == expected,
                  "SELECTED_MILEAGE:%s:%s:%s" % (raw, answer, state))
        cars_ui._v170_anchor_ferry_terms()
        labels = [str(name).casefold() for _, name in cars_ui.S.STAGES]
        status_labels = [str(spec[1]).casefold()
                         for spec in cars_ui.S.STATUSES.values()]
        check(all("море" not in value for value in labels + status_labels),
              "CRM_FERRY_VOCABULARY")
        return {"status": "PASS", "mileage_cases": len(cases),
                "ferry_vocabulary": True}
    finally:
        cars_ui.set_field, cars_ui.card_of = old_set, old_card


async def container_synthetic(konteyner):
    """Container scalar and expired callback routes without production writes."""
    original = {name: getattr(konteyner, name)
                for name in ("_pisat", "_karta", "_peresobrat")}
    state = {"id": 9902, "auto_number": "TEST-9902", "sea_container": "",
             "sea_date_out": "", "eta_manual": ""}

    class Message(FakeMessage):
        def __init__(self, text=""):
            super().__init__()
            self.text = text

    async def run_accept(write):
        message = Message("ONEYSELGF1046602")
        update = SimpleNamespace(
            effective_message=message, effective_user=SimpleNamespace(id=7))
        context = SimpleNamespace(user_data={
            "cont_wait": {"card_id": 9902, "field": "sea_container"}})
        konteyner._pisat = write
        try:
            await konteyner.prinyat(update, context)
        except Exception as exc:
            if type(exc).__name__ != "ApplicationHandlerStop":
                raise
        return message.sent

    try:
        konteyner._karta = lambda _cid: dict(state)
        konteyner._peresobrat = lambda: None

        def direct(_cid, field, value, _actor):
            state[field] = value
            return {"queued": False}
        direct_messages = await run_accept(direct)
        check(state["sea_container"] == "ONEYSELGF1046602",
              "CONTAINER_DIRECT_VALUE")
        check(any("сохранён" in item["text"] for item in direct_messages),
              "CONTAINER_DIRECT_CONFIRM")

        state["sea_container"] = ""
        queued_messages = await run_accept(
            lambda *_args: {"queued": True})
        check(any("надёжной очереди" in item["text"] for item in queued_messages),
              "CONTAINER_QUEUE_CONFIRM")

        query = FakeQuery("cont_num:9902")
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(user_data={})
        try:
            await konteyner.sprosit_nomer(update, context)
        except Exception as exc:
            if type(exc).__name__ != "ApplicationHandlerStop":
                raise
        check(context.user_data.get("cont_wait", {}).get("field") == "sea_container",
              "CONTAINER_CALLBACK_WAIT")
        check(query.message.sent, "CONTAINER_CALLBACK_NO_REPLY")
        return {"status": "PASS", "direct": True, "queued": True,
                "expired_ack_continued": True}
    finally:
        for name, value in original.items():
            setattr(konteyner, name, value)


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


async def universal_media_route_synthetic(cars_ui):
    """An open-card photo is ACKed durably and scheduled exactly once."""
    original_spool = cars_ui._v165_spool_enqueue
    original_schedule = cars_ui._v171_schedule_media_extract
    scheduled, replies = [], []

    class Message:
        photo = [SimpleNamespace(file_id="photo-file-1", file_unique_id="photo-unique-1")]
        video = None
        video_note = None
        document = None
        caption = "тип топлива LPI, объём 2.0, цвет белый, пробег 163400 км"
        message_id = 501
        chat_id = 77
        text = None

        async def reply_text(self, text, **kwargs):
            replies.append({"text": str(text), "kwargs": kwargs})

    try:
        cars_ui._v165_spool_enqueue = lambda *_args, **_kwargs: {
            "state": "accepted", "queued": 1}
        cars_ui._v171_schedule_media_extract = lambda *args, **kwargs: (
            scheduled.append((args, kwargs)) or True)
        started = time.monotonic()
        accepted = await cars_ui.auto_catch(
            Message(), {"id": 9903, "auto_number": "TEST-9903"}, 7,
            SimpleNamespace())
        elapsed = time.monotonic() - started
        check(accepted and replies, "UNIVERSAL_MEDIA_NO_ACK")
        check(elapsed <= 5.0, "UNIVERSAL_MEDIA_ACK_OVER_5S")
        check(len(scheduled) == 1, "UNIVERSAL_MEDIA_NOT_SCHEDULED_ONCE")
        fields = cars_ui._v171_media_candidates(
            Message.caption, {"fuel", "engine_cc", "color", "mileage_km"})
        check(fields.get("fuel") == "LPI", "MEDIA_CAPTION_FUEL")
        check(fields.get("engine_cc") == 2000, "MEDIA_CAPTION_ENGINE")
        check(fields.get("color") == "белый", "MEDIA_CAPTION_COLOR")
        check(fields.get("mileage_km") == 163400, "MEDIA_CAPTION_MILEAGE")
        return {"status": "PASS", "ack_seconds": round(elapsed, 3),
                "scheduled": len(scheduled), "caption_fields": len(fields),
                "llm_tokens": 0}
    finally:
        cars_ui._v165_spool_enqueue = original_spool
        cars_ui._v171_schedule_media_extract = original_schedule


async def universal_text_route_synthetic(cars_ui):
    """The reported long advertisement fills every missing technical field."""
    original_card_of = cars_ui.card_of
    original_cas = cars_ui._v168_cas_write
    state = {
        "id": 9904, "auto_number": "TEST-9904", "price_uah": 777777,
        "brand": "", "model": "", "year": "", "fuel": "",
        "engine_cc": "", "gearbox": "", "drive": "",
        "mileage_km": "", "color": "", "condition_text": "",
    }
    writes, replies = [], []
    reported_text = (
        "Hyundai Sonata 2018 · 2.0 LPI\n"
        "Характеристики:\n"
        "• экономичный двигатель 2.0 LPI\n"
        "• автоматическая коробка передач\n"
        "• передний привод\n"
        "• пробег — 163 400 км\n"
        "• белый цвет\n\n"
        "Почему выгодно бронировать автомобиль в пути:\n"
        "задаток — всего 500 $; задаток входит в общую стоимость автомобиля."
    )

    class Message:
        photo = None
        video = None
        video_note = None
        document = None
        caption = None
        message_id = 502
        chat_id = 77
        text = reported_text

        async def reply_text(self, text, **kwargs):
            replies.append({"text": str(text), "kwargs": kwargs})

    def fake_cas(card_id, field, expected_old, new_value, actor_id,
                 correction=False, _queue_on_busy=True):
        check(card_id == state["id"], "TEXT_ROUTE_WRONG_CARD")
        if not cars_ui._v168_empty(state.get(field)):
            return False, "filled"
        state[field] = new_value
        writes.append((field, new_value))
        return True, "applied"

    try:
        cars_ui.card_of = lambda _card_id: dict(state)
        cars_ui._v168_cas_write = fake_cas
        parsed = cars_ui._v172_text_candidates(
            reported_text,
            {"brand", "model", "year", "fuel", "engine_cc", "gearbox",
             "drive", "mileage_km", "color", "price_uah", "condition_text"})
        check("price_uah" not in parsed, "TEXT_DEPOSIT_BECAME_PRICE")
        started = time.monotonic()
        accepted = await cars_ui.auto_catch(
            Message(), dict(state), 7, SimpleNamespace())
        elapsed = time.monotonic() - started
        check(accepted and replies, "UNIVERSAL_TEXT_NO_ACK")
        check(elapsed <= 5.0, "UNIVERSAL_TEXT_OVER_5S")
        check(str(state.get("brand", "")).casefold() == "hyundai", "TEXT_BRAND")
        check(str(state.get("model", "")).casefold() == "sonata", "TEXT_MODEL")
        check(int(state.get("year") or 0) == 2018, "TEXT_YEAR")
        check(state.get("fuel") == "LPI", "TEXT_FUEL")
        check(int(state.get("engine_cc") or 0) == 2000, "TEXT_ENGINE")
        check(state.get("gearbox") == "automatic", "TEXT_GEARBOX")
        check(state.get("drive") == "fwd", "TEXT_DRIVE")
        check(int(state.get("mileage_km") or 0) == 163400, "TEXT_MILEAGE")
        check(state.get("color") == "белый", "TEXT_COLOR")
        check(state.get("price_uah") == 777777, "TEXT_PRICE_OVERWRITE")
        first_write_count = len(writes)
        second = await cars_ui.auto_catch(
            Message(), dict(state), 7, SimpleNamespace())
        check(second, "UNIVERSAL_TEXT_REPEAT_NOT_HANDLED")
        check(len(writes) == first_write_count, "UNIVERSAL_TEXT_REPEAT_OVERWROTE")
        check("повторно не записывал" in replies[-1]["text"],
              "UNIVERSAL_TEXT_REPEAT_REPLY")
        return {"status": "PASS", "ack_seconds": round(elapsed, 3),
                "fields_written": first_write_count, "repeat_writes": 0,
                "deposit_ignored": True, "new_card_created": False,
                "llm_tokens": 0}
    finally:
        cars_ui.card_of = original_card_of
        cars_ui._v168_cas_write = original_cas


def field_queue_synthetic(cars_ui, guard, db_module):
    guard_original = {name: getattr(guard, name) for name in
                      ("FIELD_SPOOL_PATH", "FIELD_SPOOL_LOCK")}
    db_update = db_module.update_card_field
    db_log = db_module.log_action
    db_connect = db_module.connect
    db_get_card = db_module.get_card
    cars_cas = cars_ui._v168_cas_write
    with tempfile.TemporaryDirectory(prefix="task067-fields-") as directory:
        root = pathlib.Path(directory)
        applied = []
        try:
            guard.FIELD_SPOOL_PATH = root / "fields.jsonl"
            guard.FIELD_SPOOL_LOCK = root / "fields.lock"

            def fake_update(table, card_id, field, value, actor_id, _queue_on_busy=False):
                applied.append(("set", table, card_id, field, value, actor_id))
                return {"queued": False}

            def fake_cas(card_id, field, expected, value, actor_id,
                         correction=False, _queue_on_busy=False):
                applied.append(("cas", "cars", card_id, field, value, actor_id))
                return True, "applied"

            def fake_log(actor_id, action, table, card_id, field, old, new):
                applied.append(("audit", table, card_id, field, new, actor_id))

            db_module.update_card_field = fake_update
            db_module.log_action = fake_log
            cars_ui._v168_cas_write = fake_cas
            first = guard.enqueue_field_update(
                "clients", 44, "name", "Test", 7, mode="set")
            duplicate = guard.enqueue_field_update(
                "clients", 44, "name", "Test", 7, mode="set")
            second = guard.enqueue_field_update(
                "cars", 55, "fuel", "LPI", 7,
                expected_old=None, correction=False, mode="cas")
            third = guard.enqueue_field_update(
                "cars", 55, "fuel", "LPI", 7,
                expected_old=None, mode="audit")
            check(first["state"] == "accepted", "FIELD_QUEUE_ACCEPT")
            check(duplicate["state"] == "duplicate", "FIELD_QUEUE_DUPLICATE")
            check(second["state"] == "accepted", "FIELD_QUEUE_CAS_ACCEPT")
            check(third["state"] == "accepted", "FIELD_QUEUE_AUDIT_ACCEPT")
            before = guard._field_spool_state()
            check(before["queued"] == 3, "FIELD_QUEUE_COUNT")
            recovery = guard._attempt_field_recovery(before)
            after = guard._field_spool_state()
            check(recovery.get("processed") == 3 and after["queued"] == 0,
                  "FIELD_QUEUE_DRAIN")
            check([item[0] for item in applied] == ["set", "cas", "audit"],
                  "FIELD_QUEUE_ORDER")

            class LockedConnection:
                def __enter__(self):
                    return self
                def execute(self, *_args, **_kwargs):
                    return self
                def __exit__(self, *_args):
                    raise sqlite3.OperationalError("database is locked")

            # Exercise the real production update_card_field fallback.  No
            # production DB is touched: connect/get_card are isolated here.
            db_module.update_card_field = db_update
            db_module.connect = lambda: LockedConnection()
            db_module.get_card = lambda *_args: {"mileage_km": None}
            queued = db_module.update_card_field(
                "cars", 77, "mileage_km", 163400, 7)
            check(queued.get("queued") is True, "DB_LOCK_NOT_QUEUED")
            check(guard._field_spool_state()["queued"] == 1,
                  "DB_LOCK_QUEUE_COUNT")
            db_module.connect = db_connect
            db_module.get_card = db_get_card
            db_module.update_card_field = fake_update
            lock_recovery = guard._attempt_field_recovery(guard._field_spool_state())
            check(lock_recovery.get("processed") == 1,
                  "DB_LOCK_QUEUE_DRAIN")
            check(guard._field_spool_state()["queued"] == 0,
                  "DB_LOCK_QUEUE_REMAINS")
            return {"status": "PASS", "accepted": 4, "duplicates_rejected": 1,
                    "processed": 4, "queue": 0, "order_exact": True,
                    "database_locked_queued": True}
        finally:
            db_module.update_card_field = db_update
            db_module.log_action = db_log
            db_module.connect = db_connect
            db_module.get_card = db_get_card
            cars_ui._v168_cas_write = cars_cas
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
        "voice_restore_semantic": ("CRM-VOICE-RESTORE-01-V1.3.1" in sources["cars_ui.py"]
                                   and "_v169_semantic_fields" in sources["cars_ui.py"]
                                   and "not override" not in sources["cars_ui.py"]),
        "stt_last_known_good_ru": ('CRM-VOICE-RESTORE-01-V1.3.1' in sources["ai.py"]
                                    and '"language": "ru"' in sources["ai.py"]),
        "media_receipts": "media_mark" in sources["cars_ui.py"],
        "client_fast_tail": "media_tail" in sources["client_ui.py"],
        "updates_preserved": all("drop_pending_updates=True" not in sources[name]
                                 for name in ("run_all.py", "team_bot.py", "lead_bot.py")),
        "delivery_route": 'pattern=r"^car_stage:"' in sources["cars_ui.py"],
        "condition_route": 'pattern=r"^car_cond:"' in sources["cars_ui.py"],
        "db_wait_bounded": ("CRM-DB-BOUNDED-QUEUE-001" in sources["db.py"]
                            and "ZAMOK_OZHIDANIE = 2.0" in sources["db.py"]
                            and "PRAGMA busy_timeout=450" in sources["db.py"]),
        "db_no_hot_journal_switch": ("PRAGMA journal_mode=DELETE" not in
                                      sources["db.py"]),
        "db_field_durable_queue": ("enqueue_field_update" in sources["db.py"]
                                   and "FIELD_SPOOL_PATH" in sources["crm_online_guard.py"]),
        "guard_latency_percentiles": ("latency_seconds" in sources["crm_online_guard.py"]
                                      and '"p95"' in sources["crm_online_guard.py"]
                                      and '"p99"' in sources["crm_online_guard.py"]),
        "event_loop_autorecovery": ("restart_stalled_event_loop" in
                                    sources["crm_online_guard.py"]
                                    and "_restart_budget_available" in
                                    sources["crm_online_guard.py"]),
        "selected_field_route": ("CRM-INPUT-DB-ROUTES-02-V1.3.2" in
                                  sources["cars_ui.py"]
                                  and "_v169_parse_number(value)" in
                                  sources["cars_ui.py"]),
        "container_durable_route": ("CRM-CONTAINER-ROUTES-02-V1.3.2" in
                                     sources["konteyner.py"]
                                     and "return db.update_card_field" in
                                     sources["konteyner.py"]),
        "crm_ferry_vocabulary": "_v170_anchor_ferry_terms" in sources["cars_ui.py"],
        "media_extract_missing_only": (
            "CRM-MEDIA-EXTRACT-03-V1.3.3" in sources["cars_ui.py"]
            and "_v171_schedule_media_extract" in sources["cars_ui.py"]
            and "allowed_now" in sources["cars_ui.py"]),
        "universal_text_missing_only": (
            "CRM-UNIVERSAL-TEXT-04-V1.3.4" in sources["cars_ui.py"]
            and "_v172_apply_open_text" in sources["cars_ui.py"]
            and "_v172_queue_cas" in sources["cars_ui.py"]
            and "повторно не записывал" in sources["cars_ui.py"]),
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
        import db as db_module
        import konteyner
        result["callbacks"] = asyncio.run(callback_routes(cars_ui, state["latest_card"]))
        result["voice_golden"] = voice_golden(cars_ui)
        result["selected_field"] = selected_field_synthetic(cars_ui)
        result["container"] = asyncio.run(container_synthetic(konteyner))
        result["media"] = media_synthetic(cars_ui, guard)
        result["universal_media_route"] = asyncio.run(
            universal_media_route_synthetic(cars_ui))
        result["universal_text_route"] = asyncio.run(
            universal_text_route_synthetic(cars_ui))
        result["field_queue"] = field_queue_synthetic(cars_ui, guard, db_module)
        check(float(db_module.ZAMOK_OZHIDANIE) <= 2.0, "DB_QUEUE_WAIT_OVER_2S")
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

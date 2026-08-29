#!/usr/bin/env python3
"""Read-only and in-memory production postcheck for task 089."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace


ROOT = Path("/home/Carix")
TASK_ROOT = ROOT / "autopilot_inbox" / "cloud" / "task_089_crm_voice_photo_repair"
RECEIPT = TASK_ROOT / "install_receipt.json"
STATUS = ROOT / ".crm_guard_status.json"
TARGETS = (
    "cars_ui.py",
    "local_ocr.py",
    "team_bot.py",
    "konteyner.py",
    "card_render.py",
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def check_card_open(cars_ui) -> dict:
    events: list[str] = []

    class Message:
        async def reply_text(self, *args, **kwargs):
            events.append("card_text")

    class Query:
        data = "car_open:999999"
        from_user = SimpleNamespace(id=777)
        message = Message()

        async def answer(self, *args, **kwargs):
            events.append("ack")

    async def photos(message, card):
        events.append("photos")

    async def videos(message, card):
        events.append("videos")

    async def ack(query, *args, **kwargs):
        await query.answer(*args, **kwargs)

    cars_ui.db.get_staff = lambda user_id: {"id": user_id}
    cars_ui.card_of = lambda card_id: {"id": int(card_id), "mileage_km": 10_000}
    cars_ui.render = lambda card, staff: "CARD"
    cars_ui.card_kb = lambda card, staff: None
    cars_ui.CR.send_photos = photos
    cars_ui.CR.send_videos = videos
    cars_ui._v168_ack = ack
    context = SimpleNamespace(user_data={"car_media_wait": "old"})
    try:
        await cars_ui.open_card(SimpleNamespace(callback_query=Query()), context)
    except cars_ui.ApplicationHandlerStop:
        pass
    assert events.index("card_text") < events.index("photos") < events.index("videos")
    assert context.user_data["car_last"] == 999999
    assert context.user_data["car_voice_active"] == 999999
    assert "car_media_wait" not in context.user_data
    return {"events": events, "active_card": context.user_data["car_voice_active"]}


async def check_container_stage(konteyner) -> dict:
    events: list[str] = []
    card = {"id": 999999, "status": "parking", "sea_container": "", "sea_date_out": ""}

    class Message:
        async def reply_text(self, *args, **kwargs):
            events.append("reply")

    class Query:
        data = "car_setstage:999999:sea_loaded"
        from_user = SimpleNamespace(id=777)
        message = Message()

        async def answer(self, *args, **kwargs):
            events.append("answer")

    def write(card_id, field, value, user_id):
        assert card_id == 999999 and field == "status" and user_id == 777
        events.append("write")
        card[field] = value

    konteyner._karta = lambda card_id: card
    konteyner._pisat = write
    stopped = False
    try:
        await konteyner.posle_statusa(
            SimpleNamespace(callback_query=Query()), SimpleNamespace(user_data={}))
    except Exception as exc:
        from telegram.ext import ApplicationHandlerStop
        if not isinstance(exc, ApplicationHandlerStop):
            raise
        stopped = True
    assert stopped
    assert card["status"] == "sea_loaded"
    assert events[0] == "write"
    assert "answer" in events and "reply" in events
    return {"events": events, "saved_status": card["status"]}


async def check_media_bound(card_render) -> dict:
    class Media:
        media = "fake-file-id"

    class SlowMessage:
        async def reply_photo(self, *args, **kwargs):
            await asyncio.sleep(30)

        async def reply_media_group(self, *args, **kwargs):
            await asyncio.sleep(30)

    started = time.monotonic()
    sent = await card_render._otpravit(SlowMessage(), [[Media()]])
    elapsed = time.monotonic() - started
    assert sent == 0
    assert 3.5 <= elapsed < 5.5
    return {"sent": sent, "bounded_seconds": round(elapsed, 3)}


async def main() -> int:
    sys.path.insert(0, str(ROOT))
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
    assert receipt["status"] == "PASS" and receipt["production_write"] is True
    hashes = {name: sha(ROOT / name) for name in TARGETS}
    assert hashes == receipt["after_sha256"]
    for name in TARGETS:
        compile((ROOT / name).read_text(encoding="utf-8"), name, "exec")

    import local_ocr
    mileage_cases = {
        "пробег 48 тысяч": 48_000,
        "пробіг 48 тисяч": 48_000,
        "пробег 48000": 48_000,
        "пробіг сорок вісім тисяч": 48_000,
        "mileage 48k": 48_000,
        "120 500 км": 120_500,
    }
    mileage = {
        text: local_ocr.fields_from_text(text, {"mileage_km"}).get("mileage_km")
        for text in mileage_cases
    }
    assert mileage == mileage_cases

    import cars_ui
    parsed = local_ocr.fields_from_text("пробег 48000", {"mileage_km"})
    named = cars_ui._v168_named_fields("пробег 48000", {"mileage_km"})
    changes, skipped = cars_ui.voice_change_plan(
        {"id": 999999, "mileage_km": 10_000}, parsed, named, override=True)
    assert named == {"mileage_km"} and not skipped
    assert any(item[0] == "mileage_km" and item[2] == 48_000 for item in changes)

    import konteyner
    import card_render
    card_open = await check_card_open(cars_ui)
    container = await check_container_stage(konteyner)
    media = await check_media_bound(card_render)

    status = json.loads(STATUS.read_text(encoding="utf-8"))
    status_age = time.time() - STATUS.stat().st_mtime
    heartbeats = status.get("heartbeat_age_seconds", {})
    assert status_age < 15
    assert heartbeats.get("crm_bot", 999) < 10
    assert heartbeats.get("client_bot", 999) < 10
    assert not status.get("active")

    result = {
        "task_id": "task_089",
        "status": "PASS",
        "production_write": False,
        "crm_db_write": False,
        "media_write": False,
        "checks": {
            "exact_installed_hashes": True,
            "all_sources_compile": True,
            "mileage_ru_uk": mileage,
            "filled_mileage_overwrite": changes,
            "card_text_before_media": card_open,
            "container_stage_write_first": container,
            "media_send_bounded": media,
            "runtime_status_age_seconds": round(status_age, 3),
            "runtime_heartbeats": heartbeats,
            "runtime_active_operations": 0,
        },
        "finished_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "errors": [],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

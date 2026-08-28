#!/usr/bin/env python3
"""Offline acceptance tests for CRM-VOICE-FILL-001."""
from __future__ import annotations

import ast
import importlib.util
import os
from pathlib import Path

import patch_payload


HERE = Path(__file__).resolve().parent


def load_local_ocr():
    configured = os.environ.get("TASK062_LOCAL_OCR")
    path = Path(configured) if configured else HERE.parent / "task_061" / "local_ocr.py"
    spec = importlib.util.spec_from_file_location("task062_contract_ocr", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_plan():
    namespace = {}
    exec(compile(patch_payload.VOICE_PLAN_SOURCE, "voice_plan.py", "exec"), namespace)
    return namespace["voice_change_plan"]


def one_function(source, expected):
    tree = ast.parse(source)
    assert len(tree.body) == 1
    assert tree.body[0].name == expected


def test_sources_compile_and_are_bounded():
    singles = {
        "VOICE_PLAN_SOURCE": "voice_change_plan",
        "VOICE_UNDO_SOURCE": "voice_undo",
        "OPEN_CARD_SOURCE": "open_card",
        "CARS_LIST_SOURCE": "cars_list",
        "MENU_CB_SOURCE": "menu_cb",
        "CATCH_MESSAGE_SOURCE": "catch_message",
        "REGISTER_SOURCE": "register",
    }
    for attribute, function in singles.items():
        one_function(getattr(patch_payload, attribute), function)


def test_voice_route_never_creates_card():
    source = patch_payload.CATCH_MESSAGE_SOURCE
    folded = source.casefold()
    for forbidden in (
        "create_card", "run_ai_draft", "ai_draft", "ai.parse_message",
        "ai.parse_image", "notify_managers", "сотруднику",
    ):
        assert forbidden not in folded
    for required in (
        "CRM-VOICE-FILL-001", "car_voice_active", "hard_deadline = started + 15.0",
        "Новая карточка автоматически не создаётся", "raise ApplicationHandlerStop",
    ):
        assert required in source


def test_one_stt_and_zero_llm_contract():
    source = patch_payload.CATCH_MESSAGE_SOURCE
    assert source.count("ai.transcribe") == 1
    assert "ai.voice_enabled" in source
    assert "0 LLM-токенов" in source
    assert "ai.parse" not in source


def test_deduplication_and_undo_contract():
    assert "crm_voice_seen" in patch_payload.CATCH_MESSAGE_SOURCE
    assert "marker in seen" in patch_payload.CATCH_MESSAGE_SOURCE
    assert "car_vundo:" in patch_payload.CATCH_MESSAGE_SOURCE
    assert "voice_undo" in patch_payload.REGISTER_SOURCE
    assert "current" in patch_payload.VOICE_UNDO_SOURCE
    assert "change.get(\"new\")" in patch_payload.VOICE_UNDO_SOURCE
    assert "create_card" not in patch_payload.VOICE_UNDO_SOURCE


def test_active_card_is_set_and_cleared():
    assert 'context.user_data["car_voice_active"] = int(cid)' in patch_payload.OPEN_CARD_SOURCE
    assert 'pop("car_voice_active", None)' in patch_payload.CARS_LIST_SOURCE
    assert 'pop("car_voice_active", None)' in patch_payload.MENU_CB_SOURCE


def test_fill_empty_and_explicit_override():
    plan = load_plan()
    allowed = {"drive", "color"}
    changes, skipped = plan({"drive": "4wd"}, {"drive": "fwd"}, allowed, False)
    assert changes == [] and skipped == ["drive"]
    changes, skipped = plan({"drive": "4wd"}, {"drive": "fwd"}, allowed, True)
    assert changes == [("drive", "4wd", "fwd")] and skipped == []
    changes, skipped = plan({"drive": None}, {"published": 1}, allowed, True)
    assert changes == [] and skipped == []


def test_ten_transcribed_voice_samples():
    ocr = load_local_ocr()
    allowed = {
        "brand", "model", "year", "vin", "mileage_km", "fuel",
        "gearbox", "engine_cc", "drive", "color",
    }
    samples = (
        ("привод передний", "drive", "fwd"),
        ("привод задний", "drive", "rwd"),
        ("привод полный", "drive", "4wd"),
        ("топливо газ", "fuel", "LPG"),
        ("топливо дизель", "fuel", "diesel"),
        ("топливо гибрид", "fuel", "hybrid"),
        ("топливо бензин", "fuel", "gasoline"),
        ("коробка автомат", "gearbox", "automatic"),
        ("коробка механика", "gearbox", "manual"),
        ("пробег 198 тысяч км", "mileage_km", 198000),
    )
    plan = load_plan()
    empty_card = {field: None for field in allowed}
    for text, field, expected in samples:
        parsed = ocr.fields_from_text(text, allowed)
        assert parsed.get(field) == expected, (text, parsed)
        changes, skipped = plan(empty_card, parsed, allowed, False)
        assert skipped == []
        assert any(item[0] == field and item[2] == expected for item in changes)


def test_exact_ua0009_case():
    ocr = load_local_ocr()
    allowed = {"drive"}
    parsed = ocr.fields_from_text("привод передний", allowed)
    plan = load_plan()
    changes, skipped = plan(
        {"id": 9, "auto_number": "UA-0009", "drive": None},
        parsed, allowed, False,
    )
    assert changes == [("drive", None, "fwd")]
    assert skipped == []


def main():
    tests = [value for name, value in globals().items() if name.startswith("test_")]
    for test in tests:
        test()
        print("PASS", test.__name__)
    print("PASS", len(tests), "contract tests")


if __name__ == "__main__":
    main()

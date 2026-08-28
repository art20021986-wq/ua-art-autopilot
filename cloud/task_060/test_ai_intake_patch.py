"""Offline unit tests for TASK 060 ai_intake_patch.py. Run with: python -m pytest
or plain: python cloud/task_060/test_ai_intake_patch.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from ai_intake_patch import normalize_ai_result, process_intake, has_any_readable_field


class FakeAiFilter:
    ALLOWED = {"brand", "model", "year", "price_usd", "price_uah", "mileage_km",
               "fuel", "engine", "transmission", "vin"}


def test_nested_value_shape():
    raw = {"fields": {"brand": {"value": "Kia"}, "model": {"value": "K5"},
                        "year": {"value": 2018}, "unknown_field": {"value": "x"}}}
    out = normalize_ai_result(raw, FakeAiFilter.ALLOWED)
    assert out == {"brand": "Kia", "model": "K5", "year": 2018}


def test_scalar_nested_shape():
    raw = {"fields": {"price_usd": 11400, "price_uah": 510720}}
    out = normalize_ai_result(raw, FakeAiFilter.ALLOWED)
    assert out == {"price_usd": 11400, "price_uah": 510720}


def test_flat_shape():
    raw = {"mileage_km": 198000, "vin": "KNAGU416BKA324445", "junk": "ignored"}
    out = normalize_ai_result(raw, FakeAiFilter.ALLOWED)
    assert out == {"mileage_km": 198000, "vin": "KNAGU416BKA324445"}


def test_kia_k5_full_case():
    raw = {
        "fields": {
            "brand": {"value": "Kia"},
            "model": {"value": "K5"},
            "year": {"value": 2018},
            "price_usd": {"value": 11400},
            "price_uah": {"value": 510720},
            "mileage_km": {"value": 198000},
            "fuel": {"value": "LPG"},
            "engine": {"value": "2.0"},
            "transmission": {"value": "automatic"},
            "vin": {"value": "KNAGU416BKA324445"},
        }
    }
    result = process_intake(raw, FakeAiFilter)
    assert result["ok"] is True
    assert result["route_to_staff"] is False
    assert len(result["fields"]) == 10
    assert "preview_text" in result


def test_partial_result_still_ok():
    raw = {"fields": {"brand": {"value": "Kia"}}}
    result = process_intake(raw, FakeAiFilter)
    assert result["ok"] is True
    assert result["fields"] == {"brand": "Kia"}


def test_no_readable_fields():
    raw = {"fields": {"unknown": {"value": "x"}}}
    result = process_intake(raw, FakeAiFilter)
    assert result["ok"] is False
    assert "preview_text" not in result
    assert result["route_to_staff"] is False


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    passed = 0
    for t in tests:
        t()
        passed += 1
        print(f"PASS: {t.__name__}")
    print(f"{passed}/{len(tests)} tests passed")

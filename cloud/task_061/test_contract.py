#!/usr/bin/env python3
"""Offline acceptance tests for CRM-AI-CARD-001."""
from __future__ import annotations

import ast
import os
import time
from pathlib import Path

import local_ocr
import patch_payload


ALLOWED = {
    "brand", "model", "year", "vin", "mileage_km", "fuel",
    "gearbox", "engine_cc", "drive", "color", "condition_text",
}
VIN = "KNAGU416BKA324445"


def test_ten_sequential_text_inputs():
    samples = [
        "Kia K5 2018 198 tuc. km LPG 2.0 l Astomat " + VIN,
        "Киа K5 2018, 198 тыс. км, газ 2 л, автомат, " + VIN,
        "Kia K5 2018 mileage 198000 km LPG 2.0 automatic " + VIN,
        "KIA K5 2018 198 тис. км газ 2,0 л автомат " + VIN,
        "Hyundai Sonata 2019 120000 km gasoline 2.0 automatic KMHE341DBKA123456",
        "Toyota Aqua 2020 88000 km hybrid automatic NHP10123456789012",
        "Nissan Note 2018 91000 km hybrid automatic HE121234567890123",
        "Mercedes B180 2010 150000 km gasoline automatic WDD2452321J123456",
        "BMW X3 2021 45000 km diesel 2.0 automatic AWD WBAXX11010A123456",
        "Audi A4 2022 33000 km gasoline 2.0 automatic WAUZZZF40NA123456",
    ]
    for sample in samples:
        fields = local_ocr.fields_from_text(sample, ALLOWED)
        assert fields, sample
        assert set(fields) <= ALLOWED
        assert "brand" in fields and "model" in fields and "year" in fields


def test_exact_kia_case():
    fields = local_ocr.fields_from_text(
        "Kia K5 2018 11 400 $ 510720 грн 198 Tuc. KM fas,2n Astomat " + VIN,
        ALLOWED,
    )
    assert fields == {
        "brand": "Kia", "model": "K5", "year": "2018", "vin": VIN,
        "mileage_km": 198000, "fuel": "LPG", "gearbox": "automatic",
        "engine_cc": 2000,
    }


def test_source_contract():
    source = patch_payload.RUN_AI_DRAFT_SOURCE
    tree = ast.parse(source)
    assert len(tree.body) == 1 and tree.body[0].name == "run_ai_draft"
    folded = source.casefold()
    for forbidden in (
        "notify_managers", "сотруднику", "передал менеджеру",
        "ai.parse_image", "ai.parse_message",
    ):
        assert forbidden not in folded
    for required in (
        "hard_deadline = started + 15.0",
        "Новая карточка открыта",
        "Сохранить карточку",
        "0 AI-токенов",
    ):
        assert required in source


def test_attached_image_when_supplied():
    path = os.environ.get("TASK061_TEST_IMAGE")
    if not path:
        return
    started = time.monotonic()
    fields = local_ocr.fields_from_image(Path(path).read_bytes(), ALLOWED, 13.5)
    elapsed = time.monotonic() - started
    assert elapsed <= 15.0, elapsed
    assert fields == {
        "brand": "Kia", "model": "K5", "year": "2018", "vin": VIN,
        "mileage_km": 198000, "fuel": "LPG", "gearbox": "automatic",
        "engine_cc": 2000,
    }, fields


def main():
    tests = [value for name, value in globals().items() if name.startswith("test_")]
    for test in tests:
        test()
        print("PASS", test.__name__)
    print("PASS", len(tests), "contract tests")


if __name__ == "__main__":
    main()

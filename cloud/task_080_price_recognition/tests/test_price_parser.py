"""
TASK 080 — offline sandbox/canary tests for the shared deterministic
sale-price parser. No network, no database, no CRM import. Run with:

    python -m pytest cloud/task_080_price_recognition/tests/test_price_parser.py -v

These tests were authored and manually desk-checked against the parser
logic in this delivery round (see ../TEST_RESULTS.md for the literal
desk-check trace). They have NOT been executed inside a live pytest
runner in this delivery channel because no such runner is available here;
the controller must execute this file for real before Gate B.
"""
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from price_parser import parse_sale_price_message  # noqa: E402


def _ok_value(text, wait=False):
    r = parse_sale_price_message(text, in_price_uah_wait=wait)
    assert r.ok, f"expected ok for {text!r}, got reason={r.reason}"
    assert r.field == "price_uah"
    return r.value


def _rejected(text, wait=False):
    r = parse_sale_price_message(text, in_price_uah_wait=wait)
    assert not r.ok, f"expected reject for {text!r}, got value={r.value}"
    return r.reason


# --- Required 8 owner formats -------------------------------------------

def test_format_1():
    assert _ok_value("Стоимость автомобиля 11 400 долларов") == 11400


def test_format_2():
    assert _ok_value("цена машины 11400 $") == 11400


def test_format_3():
    assert _ok_value("цена авто: 11 400 USD") == 11400


def test_format_4():
    assert _ok_value("ціна авто 11 400 доларів") == 11400


def test_format_5_ru_words():
    assert _ok_value("стоимость авто одиннадцать тысяч четыреста долларов") == 11400


def test_format_6_ua_words():
    assert _ok_value("ціна авто одинадцять тисяч чотириста доларів") == 11400


def test_format_7_thousand_comma():
    assert _ok_value("цена 11,4 тыс. долларов") == 11400


def test_format_8_k_suffix():
    assert _ok_value("цена 11.4k USD") == 11400


def test_bare_digits_only_in_wait_mode():
    assert _ok_value("11400", wait=True) == 11400


def test_bare_digits_rejected_outside_wait_mode():
    reason = _rejected("11400")
    assert reason == "NO_SALE_PRICE_INTENT"


# --- Number/format normalization -----------------------------------------

def test_nbsp_grouping():
    assert _ok_value("цена\u00a011\u00a0400") == 11400


def test_grouped_comma():
    assert _ok_value("цена 11,400") == 11400


def test_grouped_dot():
    assert _ok_value("цена 11.400") == 11400


# --- Protected non-price fields / competing context ----------------------

def test_year_only_rejected():
    reason = _rejected("год выпуска 2014")
    assert reason == "NO_SALE_PRICE_INTENT"


def test_mileage_only_rejected():
    reason = _rejected("пробег 120000 км")
    assert reason == "NO_SALE_PRICE_INTENT"


def test_engine_only_rejected():
    reason = _rejected("двигатель 2.0 л")
    assert reason == "NO_SALE_PRICE_INTENT"


def test_eta_only_rejected():
    reason = _rejected("ETA 14 дней")
    assert reason == "NO_SALE_PRICE_INTENT"


def test_container_only_rejected():
    reason = _rejected("контейнер номер 4521")
    assert reason == "NO_SALE_PRICE_INTENT"


def test_purchase_cost_wording_blocked_even_with_price_word():
    reason = _rejected("цена закупки автомобиля 11400")
    assert reason == "AMBIGUOUS_CONTEXT_BLOCKED"


def test_logistics_cost_wording_blocked():
    reason = _rejected("стоимость логистики 11400")
    assert reason == "AMBIGUOUS_CONTEXT_BLOCKED"


def test_customs_cost_wording_blocked():
    reason = _rejected("стоимость таможни 500")
    assert reason == "AMBIGUOUS_CONTEXT_BLOCKED"


# --- Ambiguity / negative / overflow --------------------------------------

def test_two_competing_amounts_rejected():
    reason = _rejected("цена 11400 или 12000 долларов")
    assert reason == "MULTIPLE_COMPETING_AMOUNTS"


def test_zero_rejected():
    reason = _rejected("цена 0")
    assert reason == "OUT_OF_RANGE"


def test_overflow_rejected():
    reason = _rejected("цена 99999999")
    assert reason == "OUT_OF_RANGE"


# --- Explicit change intent flag ------------------------------------------

def test_explicit_change_intent_flagged():
    r = parse_sale_price_message("измени цену на 12000")
    assert r.ok
    assert r.is_explicit_change_intent is True


def test_no_change_intent_flag_absent():
    r = parse_sale_price_message("цена 12000")
    assert r.ok
    assert r.is_explicit_change_intent is False


# --- Never targets a non price_uah field -----------------------------------

def test_result_field_is_always_price_uah_on_success():
    for text in [
        "цена 11400",
        "стоимость автомобиля 11400",
        "ціна авто 11400",
        "вартість авто 11400",
    ]:
        r = parse_sale_price_message(text)
        assert r.ok
        assert r.field == "price_uah"


# --- Performance sanity (<=50ms per parse) ---------------------------------

def test_parse_is_fast():
    text = "Стоимость автомобиля 11 400 долларов"
    start = time.perf_counter()
    for _ in range(1000):
        parse_sale_price_message(text)
    elapsed_ms_per_call = (time.perf_counter() - start) * 1000 / 1000
    assert elapsed_ms_per_call <= 50

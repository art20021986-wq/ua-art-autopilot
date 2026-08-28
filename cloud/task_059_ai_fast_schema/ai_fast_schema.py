#!/usr/bin/env python3
"""Fast, schema-closed helpers for UA ART CRM AI intake.

This module contains no Telegram or database writes.  The live bot passes its
existing ``ai_filter``/``db`` modules in, so the deployed CRM form remains the
single source of truth for allowed fields.
"""
from __future__ import annotations

import re


PHOTO_TARGET_SECONDS = 5.0
PHOTO_HARD_SECONDS = 7.0
TEXT_HARD_SECONDS = 2.0
VOICE_TRANSCRIBE_SECONDS = 7.0
VOICE_HARD_SECONDS = 10.0
PROMPT_MARKER = "UA_ART_SCHEMA_CLOSED_V1"


def _norm(value):
    return re.sub(r"[^a-zа-яіїєґ0-9]+", "_", str(value or "").strip().lower()).strip("_")


def car_fields(ai_filter):
    allowed = getattr(ai_filter, "ALLOWED", {})
    return frozenset(str(name) for name in allowed)


def allowed_for_type(parsed_type, ai_filter, db_module=None):
    if parsed_type == "car":
        return car_fields(ai_filter)
    if parsed_type == "client" and db_module is not None:
        return frozenset(getattr(db_module, "CLIENT_FIELDS", ()))
    return frozenset()


def sanitize_parsed(parsed, ai_filter, db_module=None):
    """Return only fields that have a real destination in the CRM form."""
    if not isinstance(parsed, dict):
        return None
    parsed_type = parsed.get("type")
    allowed = allowed_for_type(parsed_type, ai_filter, db_module)
    if not allowed:
        return None
    raw_fields = parsed.get("fields")
    if not isinstance(raw_fields, dict):
        raw_fields = {}
    fields = {name: value for name, value in raw_fields.items() if name in allowed}
    meta = parsed.get("_meta") if isinstance(parsed.get("_meta"), dict) else {}
    safe_meta = {
        key: meta[key]
        for key in ("model", "elapsed", "source")
        if key in meta and isinstance(meta[key], (str, int, float))
    }
    result = {
        "type": parsed_type,
        "fields": fields,
        "question": None,
        "summary": "Автомобиль" if parsed_type == "car" else "Клиент",
    }
    if safe_meta:
        result["_meta"] = safe_meta
    return result


def parsed_from_data(data, parsed_type="car"):
    return {
        "type": parsed_type,
        "fields": {name: {"value": value} for name, value in data.items()},
        "question": None,
        "summary": "Автомобиль" if parsed_type == "car" else "Клиент",
    }


def _choose(allowed, *names):
    return next((name for name in names if name in allowed), None)


def labeled_text_data(text, ai_filter):
    """Fast deterministic parser for ``Поле: значение`` owner messages."""
    allowed = car_fields(ai_filter)
    fixed_raw = {
        "марка": _choose(allowed, "brand"),
        "бренд": _choose(allowed, "brand"),
        "модель": _choose(allowed, "model"),
        "год": _choose(allowed, "year"),
        "рік": _choose(allowed, "year"),
        "поколение": _choose(allowed, "trim"),
        "покоління": _choose(allowed, "trim"),
        "комплектация": _choose(allowed, "trim"),
        "комплектація": _choose(allowed, "trim"),
        "vin": _choose(allowed, "vin"),
        "вин": _choose(allowed, "vin"),
        "топливо": _choose(allowed, "fuel"),
        "паливо": _choose(allowed, "fuel"),
        "двигатель": _choose(allowed, "engine_cc", "engine"),
        "двигун": _choose(allowed, "engine_cc", "engine"),
        "объем двигателя": _choose(allowed, "engine_cc", "engine"),
        "объём двигателя": _choose(allowed, "engine_cc", "engine"),
        "пробег": _choose(allowed, "mileage_km", "mileage"),
        "пробіг": _choose(allowed, "mileage_km", "mileage"),
        "кпп": _choose(allowed, "gearbox"),
        "коробка": _choose(allowed, "gearbox"),
        "коробка передач": _choose(allowed, "gearbox"),
        "привод": _choose(allowed, "drive"),
        "колір": _choose(allowed, "color"),
        "цвет": _choose(allowed, "color"),
        "цена": _choose(allowed, "price_total", "price_buy"),
        "ціна": _choose(allowed, "price_total", "price_buy"),
        "цена usd": _choose(allowed, "price_total", "price_buy"),
        "цена в гривнах": _choose(allowed, "price_uah"),
        "ціна у гривнях": _choose(allowed, "price_uah"),
        "этап": _choose(allowed, "stage"),
        "етап": _choose(allowed, "stage"),
    }
    fixed = {_norm(label): field for label, field in fixed_raw.items()}
    reverse = {}
    for field, aliases in getattr(ai_filter, "ALLOWED", {}).items():
        reverse[_norm(field)] = field
        for alias in aliases:
            reverse[_norm(alias)] = field
    result = {}
    for raw_line in str(text or "").splitlines():
        if ":" not in raw_line:
            continue
        label, value = raw_line.split(":", 1)
        canonical = fixed.get(_norm(label)) or reverse.get(_norm(label))
        if canonical in allowed and value.strip():
            result[canonical] = value.strip()
    if not result:
        return {}
    # Reuse the production normalizers but give them only whitelisted keys.
    return {
        key: value
        for key, value in ai_filter.clean(parsed_from_data(result), "").items()
        if key in allowed
    }


def clean_car(parsed, ai_filter, extra_text=""):
    safe = sanitize_parsed(parsed, ai_filter)
    if safe is None:
        safe = parsed_from_data({})
    data = ai_filter.clean(safe, extra_text or "")
    allowed = car_fields(ai_filter)
    return {key: value for key, value in data.items() if key in allowed}


def fast_text_data(text, ai_filter):
    labeled = labeled_text_data(text, ai_filter)
    fallback = clean_car(parsed_from_data({}), ai_filter, text or "")
    merged = dict(fallback)
    merged.update(labeled)
    return merged


def install_prompt(ai_module, ai_filter):
    """Constrain the existing model prompt without changing client parsing."""
    allowed = sorted(car_fields(ai_filter))
    rule = (
        "\n\n[" + PROMPT_MARKER + "] Для type=car разрешены ТОЛЬКО поля: "
        + ", ".join(allowed)
        + ". Не извлекай прочие сведения, не помещай их в summary/question. "
          "Верни только JSON; fields не должен содержать другие ключи."
    )
    for name in ("SYSTEM_PROMPT", "IMAGE_PROMPT"):
        current = str(getattr(ai_module, name, ""))
        if PROMPT_MARKER not in current:
            setattr(ai_module, name, current + rule)
    try:
        ai_module.MAX_TOKENS = min(int(ai_module.MAX_TOKENS), 700)
    except Exception:
        pass

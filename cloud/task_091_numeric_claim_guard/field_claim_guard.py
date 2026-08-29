#!/usr/bin/env python3
"""Deterministic one-source-number -> one-CRM-field guard.

The guard never invents a field.  It only removes numeric assignments that
cannot be tied to a distinct, compatible occurrence in the original message.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping


CONTRACT_ID = "CRM-NUMERIC-SINGLE-CLAIM-091-V1.0"

_NUMBER_RE = re.compile(
    r"(?<![\dA-Za-zА-Яа-яІіЇїЄєҐґ])"
    r"(\d{1,3}(?:[ ,.\u00a0]\d{3})+|\d+(?:[.,]\d+)?)"
    r"(?!\d)"
)
_YEAR_LABEL_RE = re.compile(r"(?:год|рік|year)\s*[:=\-]?\s*$", re.I)
_ENGINE_LABEL_RE = re.compile(
    r"(?:объ[её]м|обем|двигател\w*|двигун\w*|engine|displacement)"
    r"\s*[:=\-]?\s*$",
    re.I,
)
_MILEAGE_LABEL_RE = re.compile(
    r"(?:пробег|пробіг|mileage|odometer|километраж)\s*[:=\-]?\s*$",
    re.I,
)
_PRICE_LABEL_RE = re.compile(
    r"(?:цена|ціна|стоимость|вартість|price)\s*[:=\-]?\s*$",
    re.I,
)
_PRICE_PREFIX_UNIT_RE = re.compile(r"(?:\$|₴|€)\s*$")
_ENGINE_CC_UNIT_RE = re.compile(
    r"^\s*(?:cc|ccm|cm\s*\^?\s*3|см\s*\^?\s*[³3]|куб(?:\.|\w*)?)\b",
    re.I,
)
_ENGINE_L_UNIT_RE = re.compile(r"^\s*(?:l|л)\b", re.I)
_MILEAGE_UNIT_RE = re.compile(r"^\s*(?:km|км)\b", re.I)
_PRICE_UNIT_RE = re.compile(
    r"^\s*(?:\$|usd\b|долл\w*\b|грн\b|uah\b|₴|eur\b|€)", re.I
)


FIELD_GROUPS = {
    "year": "year",
    "engine": "engine",
    "engine_cc": "engine",
    "mileage": "mileage",
    "mileage_km": "mileage",
    "price": "price",
    "price_uah": "price",
    "price_total": "price",
    "price_buy": "price",
    "cost_total": "price",
    "cost_purchase": "price",
}
FIELD_PRIORITY = {
    "engine_cc": 0,
    "engine": 1,
    "mileage_km": 0,
    "mileage": 1,
    "price_uah": 0,
    "price_total": 1,
    "price_buy": 2,
    "cost_total": 3,
    "cost_purchase": 4,
    "price": 5,
    "year": 0,
}


@dataclass(frozen=True)
class Token:
    start: int
    end: int
    raw: str
    digits_value: int
    decimal_value: float | None
    owner: str | None
    owner_score: int


def _plain_integer(value: Any) -> int | None:
    if value in (None, "", "-", "—") or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    text = str(value).strip().replace("\u00a0", " ")
    digits = re.sub(r"\D", "", text)
    return int(digits) if digits else None


def _decimal(raw: str) -> float | None:
    text = raw.replace("\u00a0", "").replace(" ", "")
    if text.count(",") + text.count(".") != 1:
        return None
    separator = "," if "," in text else "."
    left, right = text.split(separator, 1)
    if not left.isdigit() or not right.isdigit():
        return None
    try:
        return float(left + "." + right)
    except ValueError:
        return None


def _context_owner(prefix: str, suffix: str) -> tuple[str | None, int]:
    # A physical unit is stronger than a textual label and reserves the token.
    if _ENGINE_CC_UNIT_RE.search(suffix):
        return "engine", 120
    if _MILEAGE_UNIT_RE.search(suffix):
        return "mileage", 120
    if _PRICE_UNIT_RE.search(suffix):
        return "price", 120
    if _PRICE_PREFIX_UNIT_RE.search(prefix):
        return "price", 120
    if _ENGINE_L_UNIT_RE.search(suffix):
        return "engine", 115
    if _ENGINE_LABEL_RE.search(prefix):
        return "engine", 90
    if _MILEAGE_LABEL_RE.search(prefix):
        return "mileage", 90
    if _PRICE_LABEL_RE.search(prefix):
        return "price", 90
    if _YEAR_LABEL_RE.search(prefix):
        return "year", 90
    return None, 0


def _tokens(source_text: str) -> list[Token]:
    source = str(source_text or "")
    result: list[Token] = []
    for match in _NUMBER_RE.finditer(source):
        raw = match.group(1)
        digits = re.sub(r"\D", "", raw)
        if not digits:
            continue
        prefix = source[max(0, match.start() - 40):match.start()].casefold()
        suffix = source[match.end():match.end() + 20].casefold()
        owner, score = _context_owner(prefix, suffix)
        result.append(Token(
            start=match.start(),
            end=match.end(),
            raw=raw,
            digits_value=int(digits),
            decimal_value=_decimal(raw),
            owner=owner,
            owner_score=score,
        ))
    return result


def _token_value(token: Token, group: str) -> int | None:
    if group == "engine" and token.owner == "engine":
        # 2.0 L -> 2000 cc; 1,999 cc -> 1999 cc.
        if token.decimal_value is not None and token.decimal_value <= 8.0:
            return int(round(token.decimal_value * 1000))
        return token.digits_value
    return token.digits_value


def _compatible_score(token: Token, group: str, value: int) -> int:
    candidate = _token_value(token, group)
    if candidate != value:
        return 0
    if token.owner is not None:
        return token.owner_score if token.owner == group else 0
    if group == "year" and 1900 <= value <= 2100 and re.fullmatch(r"\d{4}", token.raw):
        return 30
    # Unlabelled numeric tokens are not safe evidence for engine, mileage or price.
    return 0


def enforce(data: Mapping[str, Any] | None, source_text: str | None) -> dict[str, Any]:
    """Return a copy in which one numeric occurrence can claim only one field.

    Non-numeric fields are untouched. If no original source is available, the
    function preserves the data because token identity cannot be established.
    """
    result = dict(data or {})
    source = str(source_text or "")
    tokens = _tokens(source)
    if not tokens:
        return result

    fields: list[tuple[str, str, int]] = []
    for field, raw in result.items():
        group = FIELD_GROUPS.get(field)
        if group is None:
            continue
        value = _plain_integer(raw)
        if value is not None:
            fields.append((field, group, value))

    # Highest-confidence claims are allocated first. A token index can be used once.
    ranked: list[tuple[int, str, str, int, int]] = []
    for field, group, value in fields:
        for index, token in enumerate(tokens):
            score = _compatible_score(token, group, value)
            if score:
                ranked.append((score, field, group, value, index))
    ranked.sort(key=lambda item: (
        -item[0], item[4], FIELD_PRIORITY.get(item[1], 99), item[1]
    ))

    assigned_fields: set[str] = set()
    assigned_tokens: set[int] = set()
    for _score, field, _group, _value, index in ranked:
        if field in assigned_fields or index in assigned_tokens:
            continue
        assigned_fields.add(field)
        assigned_tokens.add(index)

    assigned_values = {
        value for field, _group, value in fields if field in assigned_fields
    }

    # A numeric field whose apparent source occurrences all belong to another
    # semantic field is an invented duplicate and must not be persisted.
    for field, group, value in fields:
        if field in assigned_fields:
            continue
        if value in assigned_values:
            result.pop(field, None)
            continue
        same_value = [
            token for token in tokens
            if token.digits_value == value
            or (group == "engine" and _token_value(token, group) == value)
        ]
        if same_value and any(token.owner is not None for token in same_value):
            result.pop(field, None)
            continue
        # Bare year is the only safe unlabelled numeric fallback.
        if group == "year" and any(
            token.owner is None
            and token.digits_value == value
            and re.fullmatch(r"\d{4}", token.raw)
            for token in same_value
        ):
            # It would have been assigned unless another stronger field already
            # consumed the very same occurrence.
            result.pop(field, None)

    return result


__all__ = ["CONTRACT_ID", "enforce"]

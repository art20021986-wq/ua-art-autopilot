"""
TASK 080 — shared deterministic sale-price parser.

One canonical function is used by typed text, voice transcript, photo
caption, and explicit price-field input paths so text/voice parity is
guaranteed. No network calls, no AI calls, no LLM tokens. Deterministic
regex + finite lexicon only. Target parse time is well under 50 ms for
typical CRM message lengths.

Canonical target field: cars.price_uah ("Цена продажи").
This module NEVER decides to write price_total, price_buy, cost_total,
cost_purchase, or any other internal cost field. It only ever proposes a
value for price_uah, or returns ok=False.

This module has no side effects: it does not touch the database, does not
import crm modules, and performs no I/O. Integration (reading the active
card id, writing price_uah + history + audit atomically, and building the
user-facing response) is out of scope for this file and must be done by a
separately hash-gated patch against the live, freshly-audited functions.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Lexicons
# ---------------------------------------------------------------------------

SALE_PRICE_INTENT_PATTERNS = [
    r"стоимость\s+автомобил\w*",
    r"стоимость\s+авто\b",
    r"стоимость\b",
    r"цена\s+машин\w*",
    r"цена\s+авто\b",
    r"цена\s+автомобил\w*",
    r"цена\b",
    r"ціна\s+авто\b",
    r"ціна\s+автомобіл\w*",
    r"ціна\b",
    r"вартість\s+авто\b",
    r"вартість\s+автомобіл\w*",
    r"вартість\b",
]

EXPLICIT_CHANGE_INTENT_PATTERNS = [
    r"измен\w*", r"исправ\w*", r"замен\w*", r"поменя\w*", r"скорректир\w*",
    r"зміни\w*", r"виправ\w*", r"заміни\w*", r"поміня\w*",
]

# Fields/wording that must NEVER be mistaken for sale price even if a number
# appears nearby, unless the message ALSO contains explicit sale-price intent
# with its own separate number.
BLOCKING_CONTEXT_PATTERNS = [
    r"\bгод\w*\b", r"\bрік\w*\b",              # year
    r"\bкм\b", r"\bпробег\w*\b", r"\bпробіг\w*\b",  # mileage
    r"\bдвигател\w*\b", r"\bдвигун\w*\b", r"\bкуб\w*\b", r"\bл\.?с\.?\b",  # engine
    r"\bvin\b",
    r"\beta\b", r"\bприб\w*\b",                 # ETA
    r"\bконтейнер\w*\b",
    r"\bзакуп\w*\b", r"\bзакупк\w*\b", r"\bзакупівл\w*\b",  # purchase cost
    r"\bлогистик\w*\b", r"\bлогістик\w*\b",     # logistics cost
    r"\bтаможен\w*\b", r"\bмитн\w*\b",           # customs cost
]

CURRENCY_WORDS = [
    r"\$", r"usd\b", r"долар\w*\b", r"доллар\w*\b", r"грн\b", r"гривен\w*\b",
    r"гривн\w*\b", r"uah\b",
]

NBSP = "\u00a0"


# ---------------------------------------------------------------------------
# Number-word lexicon (RU + UA), sufficient for used-car sale price ranges.
# ---------------------------------------------------------------------------

_UNITS = {
    "один": 1, "одна": 1, "одну": 1, "один": 1,
    "два": 2, "две": 2, "дві": 2,
    "три": 3, "чотири": 4, "четыре": 4,
    "пять": 5, "п'ять": 5, "пʼять": 5,
    "шесть": 6, "шість": 6,
    "семь": 7, "сім": 7,
    "восемь": 8, "вісім": 8,
    "девять": 9, "дев'ять": 9, "девʼять": 9,
}

_TEENS = {
    "десять": 10, "десять": 10,
    "одиннадцать": 11, "одинадцять": 11,
    "двенадцать": 12, "дванадцять": 12,
    "тринадцать": 13, "тринадцять": 13,
    "четырнадцать": 14, "чотирнадцять": 14,
    "пятнадцать": 15, "п'ятнадцять": 15, "пʼятнадцять": 15,
    "шестнадцать": 16, "шістнадцять": 16,
    "семнадцать": 17, "сімнадцять": 17,
    "восемнадцать": 18, "вісімнадцять": 18,
    "девятнадцать": 19, "дев'ятнадцять": 19, "девʼятнадцять": 19,
}

_TENS = {
    "двадцать": 20, "двадцять": 20,
    "тридцать": 30, "тридцять": 30,
    "сорок": 40, "сорок": 40,
    "пятьдесят": 50, "п'ятдесят": 50, "пʼятдесят": 50,
    "шестьдесят": 60, "шістдесят": 60,
    "семьдесят": 70, "сімдесят": 70,
    "восемьдесят": 80, "вісімдесят": 80,
    "девяносто": 90, "дев'яносто": 90, "девʼяносто": 90,
}

_HUNDREDS = {
    "сто": 100,
    "двести": 200, "двісті": 200,
    "триста": 300,
    "четыреста": 400, "чотириста": 400,
    "пятьсот": 500, "п'ятсот": 500, "пʼятсот": 500,
    "шестьсот": 600, "шістсот": 600,
    "семьсот": 700, "сімсот": 700,
    "восемьсот": 800, "вісімсот": 800,
    "девятьсот": 900, "дев'ятсот": 900, "девʼятсот": 900,
}

_SCALE = {
    "тысяча": 1000, "тысячи": 1000, "тысяч": 1000,
    "тисяча": 1000, "тисячі": 1000, "тисяч": 1000,
}

_ALL_WORD_VALUES = {}
_ALL_WORD_VALUES.update(_UNITS)
_ALL_WORD_VALUES.update(_TEENS)
_ALL_WORD_VALUES.update(_TENS)
_ALL_WORD_VALUES.update(_HUNDREDS)


def _words_to_number(tokens: list) -> Optional[int]:
    """Convert a contiguous run of RU/UA number words into an integer.
    Returns None if the tokens do not form a valid number expression.
    """
    total = 0
    group = 0
    consumed_any = False
    for tok in tokens:
        tok_l = tok.lower()
        if tok_l in _SCALE:
            scale = _SCALE[tok_l]
            if group == 0:
                group = 1
            total += group * scale
            group = 0
            consumed_any = True
        elif tok_l in _ALL_WORD_VALUES:
            group += _ALL_WORD_VALUES[tok_l]
            consumed_any = True
        else:
            # unknown token breaks the sequence
            break
    total += group
    if not consumed_any or total <= 0:
        return None
    return total


# ---------------------------------------------------------------------------
# Digit/decimal amount extraction
# ---------------------------------------------------------------------------

_GROUPED_DIGITS_RE = re.compile(r"^\d{1,3}(?:[ ,.]\d{3})+$")
_PLAIN_DIGITS_RE = re.compile(r"^\d+$")
_K_SUFFIX_RE = re.compile(r"^(\d+(?:[.,]\d+)?)\s*k$", re.IGNORECASE)
_THOUSAND_SUFFIX_RE = re.compile(
    r"^(\d+(?:[.,]\d+)?)\s*(?:тыс\.?|тис\.?|тысяч\w*|тисяч\w*)$", re.IGNORECASE
)


def _normalize_number_token(raw: str) -> Optional[int]:
    raw = raw.strip()
    m = _K_SUFFIX_RE.match(raw)
    if m:
        val = float(m.group(1).replace(",", "."))
        return int(round(val * 1000))
    m = _THOUSAND_SUFFIX_RE.match(raw)
    if m:
        val = float(m.group(1).replace(",", "."))
        return int(round(val * 1000))
    if _GROUPED_DIGITS_RE.match(raw):
        return int(re.sub(r"[ ,.]", "", raw))
    if _PLAIN_DIGITS_RE.match(raw):
        return int(raw)
    return None


_CANDIDATE_NUMERIC_RE = re.compile(
    r"(?:\d{1,3}(?:[ ,.]\d{3})+|\d+(?:[.,]\d+)?\s*k\b|"
    r"\d+(?:[.,]\d+)?\s*(?:тыс\.?|тис\.?|тысяч\w*|тисяч\w*)|\d+)",
    re.IGNORECASE,
)


def _find_numeric_candidates(segment: str):
    out = []
    for m in _CANDIDATE_NUMERIC_RE.finditer(segment):
        val = _normalize_number_token(m.group(0))
        if val is not None:
            out.append((val, m.start(), m.end()))
    return out


_NUMBER_WORD_RUN_RE = re.compile(
    r"(?:[а-яіїєґ']+(?:[\s-]+|$)){1,8}", re.IGNORECASE
)


def _find_word_number_candidates(segment: str):
    """Scan for maximal runs of RU/UA number words and convert them."""
    tokens = re.findall(r"[а-яіїєґ']+", segment, re.IGNORECASE)
    if not tokens:
        return []
    results = []
    i = 0
    n = len(tokens)
    while i < n:
        if tokens[i].lower() in _ALL_WORD_VALUES or tokens[i].lower() in _SCALE:
            j = i
            run = []
            while j < n and (tokens[j].lower() in _ALL_WORD_VALUES or tokens[j].lower() in _SCALE):
                run.append(tokens[j])
                j += 1
            val = _words_to_number(run)
            if val:
                results.append(val)
            i = j
        else:
            i += 1
    return results


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def _normalize_text(text: str) -> str:
    text = text.replace(NBSP, " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _has_any(patterns, text_lower: str) -> bool:
    return any(re.search(p, text_lower) for p in patterns)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@dataclass
class PriceParseResult:
    ok: bool
    value: Optional[int] = None
    field: str = "price_uah"
    reason: str = ""
    is_explicit_change_intent: bool = False


MIN_SANE_PRICE = 1
MAX_SANE_PRICE = 500_000  # sanity ceiling in the message's own units; no FX conversion performed


def parse_sale_price_message(text: str, in_price_uah_wait: bool = False) -> PriceParseResult:
    """Shared deterministic sale-price parser.

    Used identically by typed text, voice transcript text, photo caption
    text, and the explicit price_uah wait-field input. No network, no AI,
    no LLM tokens. Pure function of its inputs.

    Parameters
    ----------
    text: raw user-visible string (already transcribed if voice).
    in_price_uah_wait: True only when the UI has an explicit open
        price_uah edit/fill prompt active for the current card.

    Returns
    -------
    PriceParseResult with ok=True and an integer value only when a single,
    unambiguous sale-price amount was found (or bare digits were given
    while in_price_uah_wait is True). Never proposes a non price_uah field.
    """
    if text is None:
        return PriceParseResult(ok=False, reason="EMPTY_INPUT")

    norm = _normalize_text(text)
    if not norm:
        return PriceParseResult(ok=False, reason="EMPTY_INPUT")

    lower = norm.lower()

    is_change_intent = _has_any(EXPLICIT_CHANGE_INTENT_PATTERNS, lower)

    # Bare-digits fast path: only while an explicit price_uah wait is active.
    if in_price_uah_wait:
        bare = _normalize_number_token(norm)
        if bare is not None:
            if bare < MIN_SANE_PRICE or bare > MAX_SANE_PRICE:
                return PriceParseResult(ok=False, reason="OUT_OF_RANGE")
            return PriceParseResult(ok=True, value=bare, field="price_uah",
                                     is_explicit_change_intent=is_change_intent)

    has_intent = _has_any(SALE_PRICE_INTENT_PATTERNS, lower)
    if not has_intent:
        return PriceParseResult(ok=False, reason="NO_SALE_PRICE_INTENT")

    if _has_any(BLOCKING_CONTEXT_PATTERNS, lower):
        # Sale-price wording is present, but so is a competing internal /
        # non-price context (year, mileage, ETA, container, purchase cost,
        # logistics cost, customs cost, engine size, VIN). Fail closed
        # rather than risk writing the wrong number into price_uah.
        return PriceParseResult(ok=False, reason="AMBIGUOUS_CONTEXT_BLOCKED")

    numeric_candidates = _find_numeric_candidates(lower)
    word_candidates = _find_word_number_candidates(lower)

    distinct_values = set(v for v, _, _ in numeric_candidates) | set(word_candidates)

    if len(distinct_values) == 0:
        return PriceParseResult(ok=False, reason="NO_AMOUNT_FOUND")
    if len(distinct_values) > 1:
        return PriceParseResult(ok=False, reason="MULTIPLE_COMPETING_AMOUNTS")

    value = next(iter(distinct_values))

    if value < MIN_SANE_PRICE or value > MAX_SANE_PRICE:
        return PriceParseResult(ok=False, reason="OUT_OF_RANGE")

    return PriceParseResult(ok=True, value=value, field="price_uah",
                             is_explicit_change_intent=is_change_intent)

"""
TASK 061 — CRM-AI-CARD-001
Deterministic, zero-token local recognition for CRM card auto-open.

This module is a NEW, self-contained file. It does not modify or import
private CRM internals directly. The integration layer (see
team_bot_integration_patch.md) is responsible for:
  1. Calling `recognize(text, allowed_keys)` with OCR/caption/transcribed text
     and the CURRENT LIVE `ai_filter.ALLOWED` key set read at call time.
  2. Filtering the returned dict to only keys present in `allowed_keys`
     (this module already does that filtering internally, but the caller
     must pass the live ALLOWED set — never a hardcoded copy).
  3. Opening the draft card immediately if the filtered dict is non-empty.

No network calls, no model tokens, no database writes happen here.
"""
import re
from typing import Dict, Optional, Set

# ---------------------------------------------------------------------------
# Deterministic regex patterns (no ML, no external calls)
# ---------------------------------------------------------------------------

_VIN_RE = re.compile(r"\b([A-HJ-NPR-Z0-9]{17})\b", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(19[5-9]\d|20[0-4]\d)\b")
_MILEAGE_RE = re.compile(
    r"(\d{1,3}(?:[\s,.]?\d{3})*)\s*(?:km|км|km\.|км\.)",
    re.IGNORECASE,
)
_ENGINE_CC_RE = re.compile(
    r"(\d{3,5})\s*(?:cc|см3|куб|cm3)",
    re.IGNORECASE,
)

_FUEL_MAP = {
    "lpg": "LPG",
    "газ": "LPG",
    "gasoline": "Бензин",
    "petrol": "Бензин",
    "бензин": "Бензин",
    "diesel": "Дизель",
    "дизель": "Дизель",
    "hybrid": "Гибрид",
    "гибрид": "Гибрид",
    "electric": "Электро",
    "электро": "Электро",
    "cng": "CNG",
}

_TRANS_MAP = {
    "automatic": "Автомат",
    "auto": "Автомат",
    "акпп": "Автомат",
    "автомат": "Автомат",
    "manual": "Механика",
    "мкпп": "Механика",
    "механика": "Механика",
    "cvt": "Вариатор",
    "вариатор": "Вариатор",
}

# Small deterministic brand list used only to help split "Brand Model" text.
# This is NOT exhaustive; unmatched brand/model tokens are simply skipped
# (never invented), which satisfies "unknown values are ignored".
_KNOWN_BRANDS = [
    "kia", "hyundai", "toyota", "honda", "nissan", "mazda", "chevrolet",
    "ford", "volkswagen", "bmw", "mercedes", "audi", "lexus", "genesis",
    "ssangyong", "renault", "peugeot", "citroen", "skoda", "mitsubishi",
    "subaru", "suzuki", "volvo", "jeep", "chrysler", "dodge", "cadillac",
    "infiniti", "acura", "land rover", "jaguar", "porsche", "mini",
    "fiat", "opel", "seat", "daewoo",
]


def _extract_brand_model(text: str) -> Dict[str, str]:
    """Find a known brand token followed by an alphanumeric model token."""
    lower = text.lower()
    for brand in _KNOWN_BRANDS:
        idx = lower.find(brand)
        if idx == -1:
            continue
        after = text[idx + len(brand):].strip()
        m = re.match(r"^\s*([A-Za-zА-Яа-я0-9\-]{1,15})", after)
        result = {"brand": brand.capitalize() if brand != "bmw" else "BMW"}
        if m:
            candidate = m.group(1)
            # avoid capturing a bare year as "model"
            if not _YEAR_RE.fullmatch(candidate):
                result["model"] = candidate.upper() if len(candidate) <= 4 else candidate.title()
        return result
    return {}


def _extract_vin(text: str) -> Optional[str]:
    m = _VIN_RE.search(text)
    if not m:
        return None
    vin = m.group(1).upper()
    # Basic VIN sanity: reject strings that are all-digits (likely not VIN)
    if vin.isdigit():
        return None
    return vin


def _extract_year(text: str) -> Optional[str]:
    m = _YEAR_RE.search(text)
    return m.group(1) if m else None


def _extract_mileage(text: str) -> Optional[str]:
    m = _MILEAGE_RE.search(text)
    if not m:
        return None
    raw = re.sub(r"[\s,.]", "", m.group(1))
    return raw


def _extract_engine_cc(text: str) -> Optional[str]:
    m = _ENGINE_CC_RE.search(text)
    return m.group(1) if m else None


def _extract_keyword(text: str, table: Dict[str, str]) -> Optional[str]:
    lower = text.lower()
    for key, value in table.items():
        if re.search(r"\b" + re.escape(key) + r"\b", lower):
            return value
    return None


def recognize(text: str, allowed_keys: Optional[Set[str]] = None) -> Dict[str, str]:
    """
    Deterministically parse `text` (OCR result, caption, or transcription)
    into a flat dict of CRM field candidates.

    If `allowed_keys` is provided, the returned dict is filtered to contain
    only keys present in that set (the live ai_filter.ALLOWED schema).
    Nothing is invented: a key is only present if a matching pattern was
    found in the source text.
    """
    if not text:
        return {}

    found: Dict[str, str] = {}

    brand_model = _extract_brand_model(text)
    found.update(brand_model)

    vin = _extract_vin(text)
    if vin:
        found["vin"] = vin

    year = _extract_year(text)
    if year:
        found["year"] = year

    mileage = _extract_mileage(text)
    if mileage:
        found["mileage"] = mileage

    engine_cc = _extract_engine_cc(text)
    if engine_cc:
        found["engine_cc"] = engine_cc

    fuel = _extract_keyword(text, _FUEL_MAP)
    if fuel:
        found["fuel_type"] = fuel

    transmission = _extract_keyword(text, _TRANS_MAP)
    if transmission:
        found["transmission"] = transmission

    if allowed_keys is not None:
        found = {k: v for k, v in found.items() if k in allowed_keys}

    return found

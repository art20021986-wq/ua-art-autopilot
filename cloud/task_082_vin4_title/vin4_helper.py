"""Centralized VIN4 title/button rendering helper for UA ART CRM bot.

All render call sites (car list rows, inline keyboard buttons, CRM card
headers) must go through this module. Do NOT hardcode VIN4 values for any
specific UA-ID; always derive from `cars.vin` at render time so future cards
(UA-0014, UA-9999, ...) are covered automatically.

No runtime LLM calls. Pure deterministic string logic. tokens = 0.
"""
from __future__ import annotations

import re
from html import escape as _html_escape

__all__ = [
    "normalize_vin",
    "is_valid_vin",
    "get_vin4",
    "build_base_title",
    "render_title_html",
    "render_button_label",
    "strip_vin_suffix_html",
    "strip_vin_suffix_plain",
    "has_vin_suffix_html",
    "has_vin_suffix_plain",
]

_VALID_VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")

# Trailing " · VIN <b>XXXX</b>" or " · VIN НЕТ" (bold or not) at end of string.
_HTML_SUFFIX_RE = re.compile(
    r"\s*·\s*(?:VIN\s*<b>[A-Z0-9]{4}</b>|<b>VIN\s*НЕТ</b>)\s*$",
    re.IGNORECASE,
)
# Trailing " · VIN XXXX" or " · VIN НЕТ" plain text at end of string.
_PLAIN_SUFFIX_RE = re.compile(
    r"\s*·\s*VIN\s*(?:[A-Z0-9]{4}|НЕТ)\s*$",
    re.IGNORECASE,
)

BUTTON_MAX_LEN = 64  # conservative Telegram inline button label safety limit


def normalize_vin(raw) -> str:
    """Strip, remove spaces/dashes, uppercase. Never raises."""
    if raw is None:
        return ""
    v = str(raw).strip()
    v = v.replace(" ", "").replace("-", "")
    return v.upper()


def is_valid_vin(normalized: str) -> bool:
    return bool(_VALID_VIN_RE.match(normalized or ""))


def get_vin4(raw_vin) -> str | None:
    """Return last 4 chars of a valid normalized 17-char VIN, else None.

    Uses characters (not only digits) because VIN may end in letters.
    """
    v = normalize_vin(raw_vin)
    if is_valid_vin(v):
        return v[-4:]
    return None


def build_base_title(ua_id: str, brand: str, model: str, year) -> str:
    ua_id = (ua_id or "").strip()
    brand = (brand or "").strip()
    model = (model or "").strip()
    year_s = "" if year in (None, "") else str(year).strip()
    parts = [p for p in (brand, model, year_s) if p]
    right = " ".join(parts)
    if ua_id and right:
        return f"{ua_id} · {right}"
    return ua_id or right


def strip_vin_suffix_html(text: str) -> str:
    """Remove a previously-appended HTML VIN suffix, if present (idempotency)."""
    return _HTML_SUFFIX_RE.sub("", text or "")


def strip_vin_suffix_plain(text: str) -> str:
    """Remove a previously-appended plain-text VIN suffix, if present."""
    return _PLAIN_SUFFIX_RE.sub("", text or "")


def has_vin_suffix_html(text: str) -> bool:
    return bool(_HTML_SUFFIX_RE.search(text or ""))


def has_vin_suffix_plain(text: str) -> bool:
    return bool(_PLAIN_SUFFIX_RE.search(text or ""))


def render_title_html(ua_id: str, brand: str, model: str, year, vin,
                       existing_title: str | None = None) -> str:
    """Build the HTML title with exactly one bold VIN4 (or bold 'VIN НЕТ').

    Format (valid VIN):   "UA-0013 · Mercedes-Benz Б-КЛАССА 2015 · VIN <b>1234</b>"
    Format (missing VIN): "UA-0013 · Mercedes-Benz Б-КЛАССА 2015 · <b>VIN НЕТ</b>"

    If `existing_title` is passed (legacy call sites that already built a
    title string), any prior VIN suffix is stripped first to guarantee
    idempotency (never a double suffix).
    """
    if existing_title is not None:
        base = strip_vin_suffix_html(existing_title)
    else:
        base = _html_escape(build_base_title(ua_id, brand, model, year))
    vin4 = get_vin4(vin)
    if vin4:
        tail = f"VIN <b>{_html_escape(vin4)}</b>"
    else:
        tail = "<b>VIN НЕТ</b>"
    base = base.rstrip()
    return f"{base} · {tail}" if base else tail


def _truncate(label: str, max_len: int = BUTTON_MAX_LEN) -> str:
    if len(label) <= max_len:
        return label
    if max_len <= 1:
        return label[:max_len]
    return label[: max_len - 1] + "…"


def render_button_label(ua_id: str, brand: str, model: str, year, vin,
                         existing_label: str | None = None) -> str:
    """Build the plain-text button label with exactly one VIN4/`VIN НЕТ` suffix.

    No HTML markup is ever inserted here — Telegram button captions are
    literal text.
    """
    if existing_label is not None:
        base = strip_vin_suffix_plain(existing_label)
    else:
        base = build_base_title(ua_id, brand, model, year)
    vin4 = get_vin4(vin)
    tail = f"VIN {vin4}" if vin4 else "VIN НЕТ"
    base = base.rstrip()
    label = f"{base} · {tail}" if base else tail
    return _truncate(label)

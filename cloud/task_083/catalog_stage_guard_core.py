"""
TASK 083 — CATALOG-CARD-DEDUP-GUARD-083 v1.0

Deterministic, dependency-free stage-card dedup guard.

This module is a PREPARED DELIVERABLE under cloud/task_083/. It is NOT installed
on production by this worker. A separate authorized Gate B installer is
responsible for copying/activating this logic (or an equivalent module) as
/home/Carix/catalog_stage_guard_core.py and wiring it into the three generators
(stranica.py, yadro.py, master_card.py) exactly once each, per TASK 083.

Design constraints satisfied:
- No hardcoded card ID list. All rules operate on card structure/fields, not IDs.
- No LLM calls at runtime. Pure deterministic string/dict logic.
- Idempotent: running the guard twice on an already-clean card changes nothing.
- Never touches ETA, VIN, VIN-check, price, photos, links, stage label, route.

The expected card representation is a plain dict produced by the existing
generators, with (at minimum) the following optional keys used by this guard:

    card = {
        "id": "UA-0001",                     # matches UA-[0-9]{4,}
        "engine_shown_in_main_line": True,     # bool: main-line engine text present
        "engine_text": "2.0T",                 # engine text, unchanged
        "vin_block_lines": [...],              # list[str], lower VIN block lines
        "media_badge_video_count": 3,          # int or None
        "video_count": 3,                      # int, source of truth
        "is_fallback": False,                  # True only for UA-0011-style fallback
        "stage_key": "kyiv" | "georgia" | "korea" | other,
        "stage_text_ru": "...",
        "stage_text_ua": "...",
    }

All functions return a NEW dict (do not mutate the input), so callers can diff
before/after during shadow rendering.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Dict, List

PUBLIC_ID_PATTERN = re.compile(r"^UA-[0-9]{4,}$")

# --- Canonical short texts (owner-approved, RU + UA mandatory) ------------

GEORGIA_TEXT_RU = (
    "До Киева — до 15 календарных дней после бронирования за 500 $. "
    "Точную дату укажем после отправки."
)
GEORGIA_TEXT_UA = (
    "До Києва — до 15 календарних днів після бронювання за 500 $. "
    "Точну дату вкажемо після відправлення."
)

KOREA_TEXT_RU = (
    "Предоплата 500 $ фиксирует бронирование. Отправка — ближайшим рейсом; "
    "дату прибытия рассчитаем после погрузки."
)
KOREA_TEXT_UA = (
    "Передоплата 500 $ фіксує бронювання. Відправлення — найближчим рейсом; "
    "дату прибуття розрахуємо після завантаження."
)

# Duplicate lower-stage phrase for Kyiv cards that must be fully removed while
# the upper green stage label is left untouched.
KYIV_DUPLICATE_PHRASES = (
    "Автомобиль в Киеве и готов к осмотру",
    "Автомобіль у Києві і готовий до огляду",
    "Автомобіль в Києві і готовий до огляду",
)

# Technical zero-video line that carries no client value and must never be
# shown publicly.
ZERO_VIDEO_PATTERNS = (
    re.compile(r"^\s*Видео\s*:\s*0\s*$", re.IGNORECASE),
    re.compile(r"^\s*Відео\s*:\s*0\s*$", re.IGNORECASE),
)


def is_public_card_id(card_id: str) -> bool:
    return bool(PUBLIC_ID_PATTERN.match(card_id or ""))


def _is_zero_video_line(line: str) -> bool:
    return any(p.match(line or "") for p in ZERO_VIDEO_PATTERNS)


def dedup_engine_line(card: Dict[str, Any]) -> Dict[str, Any]:
    """Remove duplicate engine text from the lower VIN block when the engine
    is already shown in the main line. Fallback cards that do NOT show the
    engine in the main line keep the engine line in the VIN block.
    """
    out = copy.deepcopy(card)
    if not out.get("vin_block_lines"):
        return out

    engine_text = out.get("engine_text")
    engine_shown_in_main = out.get("engine_shown_in_main_line", False)

    if engine_shown_in_main and engine_text:
        out["vin_block_lines"] = [
            line for line in out["vin_block_lines"] if engine_text not in (line or "")
        ]
    return out


def dedup_video_count(card: Dict[str, Any]) -> Dict[str, Any]:
    """Bottom block shows video count only when > 0 and not already shown in
    the media badge. 'Видео: 0' / 'Відео: 0' is never shown publicly.
    """
    out = copy.deepcopy(card)
    if not out.get("vin_block_lines"):
        return out

    video_count = out.get("video_count")
    media_badge_count = out.get("media_badge_video_count")

    filtered: List[str] = []
    for line in out["vin_block_lines"]:
        if _is_zero_video_line(line):
            continue  # never show "Видео: 0" / "Відео: 0"
        is_video_line = bool(re.match(r"^\s*(Видео|Відео)\s*:\s*\d+\s*$", line or "", re.IGNORECASE))
        if is_video_line and video_count and media_badge_count == video_count:
            continue  # already shown in media badge, drop the duplicate
        filtered.append(line)
    out["vin_block_lines"] = filtered
    return out


def dedup_kyiv_stage_text(card: Dict[str, Any]) -> Dict[str, Any]:
    """Remove the duplicate lower Kyiv phrase, keep the upper green stage label."""
    out = copy.deepcopy(card)
    if out.get("stage_key") != "kyiv":
        return out

    def strip_phrase(text: Any) -> Any:
        if not isinstance(text, str):
            return text
        cleaned = text
        for phrase in KYIV_DUPLICATE_PHRASES:
            cleaned = cleaned.replace(phrase, "").strip()
        return cleaned

    if "stage_lower_text_ru" in out:
        out["stage_lower_text_ru"] = strip_phrase(out.get("stage_lower_text_ru"))
        if out["stage_lower_text_ru"] == "":
            out["stage_lower_text_ru"] = None
    if "stage_lower_text_ua" in out:
        out["stage_lower_text_ua"] = strip_phrase(out.get("stage_lower_text_ua"))
        if out["stage_lower_text_ua"] == "":
            out["stage_lower_text_ua"] = None
    return out


def shorten_stage_text(card: Dict[str, Any]) -> Dict[str, Any]:
    """Replace verbose duplicated Georgia/Korea stage texts with the owner
    approved canonical short versions, in both RU and UA.
    """
    out = copy.deepcopy(card)
    stage_key = out.get("stage_key")
    if stage_key == "georgia":
        out["stage_text_ru"] = GEORGIA_TEXT_RU
        out["stage_text_ua"] = GEORGIA_TEXT_UA
    elif stage_key == "korea":
        out["stage_text_ru"] = KOREA_TEXT_RU
        out["stage_text_ua"] = KOREA_TEXT_UA
    return out


def apply_stage_card_guard(card: Dict[str, Any]) -> Dict[str, Any]:
    """Single entry point to be called by all three generators and the
    stage-card renderer for any card whose public id matches UA-[0-9]{4,}.

    Untouched fields: eta, vin, vin_check, price, photos, links, stage label,
    route. This function never reads or writes those keys.
    """
    card_id = card.get("id", "")
    if not is_public_card_id(card_id):
        # Non-public or malformed id: return unchanged, do not guess.
        return copy.deepcopy(card)

    result = card
    result = dedup_engine_line(result)
    result = dedup_video_count(result)
    result = dedup_kyiv_stage_text(result)
    result = shorten_stage_text(result)
    return result


def apply_to_catalog(cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Apply the guard to a full catalog list, preserving order and count.
    Used by shadow-render step before atomic publish of /video and /site
    katalog.html copies.
    """
    return [apply_stage_card_guard(c) for c in cards]


def verify_catalog_invariants(before: List[Dict[str, Any]], after: List[Dict[str, Any]]) -> List[str]:
    """Return a list of violation strings (empty list = safe to publish).

    Checks performed here are structural sanity checks for the Gate B
    installer to run before atomic replace. They do not touch production.
    """
    violations: List[str] = []

    if len(before) != len(after):
        violations.append(f"card_count_mismatch before={len(before)} after={len(after)}")

    before_ids = [c.get("id") for c in before]
    after_ids = [c.get("id") for c in after]
    if before_ids != after_ids:
        violations.append("card_id_order_or_set_changed")

    if len(set(after_ids)) != len(after_ids):
        violations.append("duplicate_public_ids_detected")

    for b, a in zip(before, after):
        for immutable_key in ("eta", "vin", "vin_check", "price", "photos", "links", "stage", "route"):
            if b.get(immutable_key) != a.get(immutable_key):
                violations.append(f"immutable_field_changed:{immutable_key}:{b.get('id')}")

        for line in a.get("vin_block_lines") or []:
            if _is_zero_video_line(line):
                violations.append(f"zero_video_line_still_public:{a.get('id')}")

    return violations

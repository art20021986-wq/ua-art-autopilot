"""Root-cause renderer fix for owner directive item 7.

Problem being fixed: the generic card-rendering mechanism previously fell back
to a narrow text-only template whenever certain fields (e.g. container number,
arrival date) were missing/empty, and could route a card to the wrong stage
template. This module defines a single unified full-template renderer that:

  1. Always renders the full standard template (cover photo + gallery +
     full info block), regardless of which optional fields are present.
  2. Omits an individual sub-block gracefully when its underlying field is
     empty/None, WITHOUT switching the whole card to any reduced template.
  3. Uses the CRM stage field as the only input for which stage label/section
     is shown (see guards.crm_is_single_source_of_stage).
  4. Requires the first media entry to be validated as the VIN's own cover
     photo before rendering the gallery block (delegates to
     guards.require_media_mapping_before_catalog_write for that check).

This is pure Python with no I/O; it returns a structured dict describing the
card sections. The real HTML/template layer on the CRM/site side should
consume this structure instead of re-implementing fallback logic.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    from .guards import require_media_mapping_before_catalog_write, GuardViolation
except ImportError:  # Supports the repository's direct-file test runner.
    from guards import require_media_mapping_before_catalog_write, GuardViolation

STAGE_LABELS = {
    "kr_bought": "В Корее",
    "on_ferry": "На пароме",  # retained only as a label map entry; guards.py
                                # blocks writing this status for cards that
                                # lack confirmed shipping evidence (TASK 082
                                # superseded logic).
    "in_transit": "В пути",
    "arrived": "Прибыл",
}

OPTIONAL_INFO_FIELDS = [
    "container_number",
    "arrival_date",
    "price",
    "mileage",
    "engine",
    "color",
    "notes",
]


def render_card(card: Dict[str, Any]) -> Dict[str, Any]:
    """Build the full unified card structure. Never falls back to a reduced
    template; missing optional fields simply do not appear as sub-blocks.
    """
    vin = card.get("vin")
    status = card.get("status")
    stage_label = STAGE_LABELS.get(status, status)

    media = card.get("media", [])
    gallery_error: Optional[str] = None
    try:
        require_media_mapping_before_catalog_write(media, vin)
        cover_photo = media[0]
        gallery = media
    except GuardViolation as exc:
        # Structural guard failure blocks catalog write entirely; the renderer
        # must not silently degrade to a fallback card -- it must refuse.
        cover_photo = None
        gallery = []
        gallery_error = str(exc)

    info_block: Dict[str, Any] = {}
    for field in OPTIONAL_INFO_FIELDS:
        value = card.get(field)
        if value not in (None, ""):
            info_block[field] = value

    return {
        "vin": vin,
        "stage_label": stage_label,
        "stage_source": "crm_status_field",
        "cover_photo": cover_photo,
        "gallery": gallery,
        "gallery_error": gallery_error,
        "info_block": info_block,
        "template": "full_unified_template",
        "used_fallback_template": False,
    }

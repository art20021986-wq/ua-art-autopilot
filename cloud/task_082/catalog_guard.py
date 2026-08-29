"""UA ART Autopilot — TASK 082 unified catalog runtime guard.

This module is a self-contained, deterministic, zero-LLM-token guard that
rebuilds catalog cards from CRM status and already-published individual
pages. It performs NO filesystem writes to production paths by itself; it
returns rendered content that an external, bounded installer (see
install_procedure.md) must write atomically with backup/verify/rollback.

Design constraints enforced here (TASK 082):
- stage source is CRM `status` only;
- sea_loaded -> stage 2 -> category/key `more` -> "На пароме · маршрут — Киев";
- exactly one card per UA code in output;
- full 55/45 template only (no text-only fallback path exists in this module);
- main photo must be an absolute URL taken from the already-published
  individual page after media sync; missing photo => card excluded
  (fail-closed), not published as fallback;
- title gets " VIN {last4}" appended, where last4 = last 4 chars of VIN;
- URL filter aliases: f/etap/stage numeric 1-4 and sea/ferry/more all resolve
  to the same stage;
- runtime uses 0 LLM tokens: purely deterministic table lookups and string
  formatting.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Stage table — single source of truth. Extend this table only; never branch
# stage logic elsewhere in the codebase.
# ---------------------------------------------------------------------------

STAGE_TABLE: Dict[str, Dict[str, object]] = {
    "new": {"stage": 1, "category": "new", "label": "Оформление"},
    "sea_loaded": {
        "stage": 2,
        "category": "more",
        "label": "На пароме · маршрут — Киев",
    },
    "customs": {"stage": 3, "category": "customs", "label": "На таможне"},
    "delivered": {"stage": 4, "category": "delivered", "label": "Доставлен"},
}

# URL filter aliases -> canonical stage number.
FILTER_ALIASES: Dict[str, int] = {
    "1": 1,
    "2": 2,
    "3": 3,
    "4": 4,
    "new": 1,
    "sea": 2,
    "ferry": 2,
    "more": 2,
    "customs": 3,
    "delivered": 4,
}

FILTER_PARAM_NAMES = ("f", "etap", "stage")


class CatalogGuardError(Exception):
    """Raised when a card cannot be safely rendered (fail-closed)."""


@dataclass(frozen=True)
class CrmCarRecord:
    ua_code: str
    vin: str
    status: str
    title_base: str
    description_snippet: str


@dataclass(frozen=True)
class PublishedPageInfo:
    ua_code: str
    individual_page_url: str
    main_photo_absolute_url: Optional[str]
    photo_count: int


@dataclass(frozen=True)
class RenderedCard:
    ua_code: str
    stage: int
    category: str
    title: str
    label: str
    main_photo_url: str
    individual_page_url: str
    html: str


def resolve_stage(status: str) -> Dict[str, object]:
    entry = STAGE_TABLE.get(status)
    if entry is None:
        raise CatalogGuardError(f"Unknown CRM status '{status}' — no stage mapping")
    return entry


def resolve_filter_stage(param_name: str, raw_value: str) -> Optional[int]:
    """Resolve an incoming URL filter parameter/value pair to a stage number.

    Returns None if the parameter name is not one of the supported aliases
    or the value is not recognised.
    """
    if param_name not in FILTER_PARAM_NAMES:
        return None
    key = raw_value.strip().lower()
    return FILTER_ALIASES.get(key)


def vin_suffix(vin: str) -> str:
    clean = (vin or "").strip()
    if len(clean) < 4:
        raise CatalogGuardError(f"VIN too short to derive suffix: '{vin}'")
    return clean[-4:]


def build_title(title_base: str, vin: str) -> str:
    return f"{title_base} VIN {vin_suffix(vin)}"


def render_card(car: CrmCarRecord, page: PublishedPageInfo) -> RenderedCard:
    """Render exactly one full 55/45 template card. Fail-closed on any
    missing prerequisite (no individual page, no main photo).
    """
    if page.individual_page_url is None or not page.individual_page_url.strip():
        raise CatalogGuardError(
            f"{car.ua_code}: no published individual page — excluding from catalog"
        )
    if not page.main_photo_absolute_url:
        raise CatalogGuardError(
            f"{car.ua_code}: no main photo available after media sync — excluding"
        )
    if not page.main_photo_absolute_url.startswith(("http://", "https://")):
        raise CatalogGuardError(
            f"{car.ua_code}: main photo URL is not absolute — excluding"
        )

    stage_info = resolve_stage(car.status)
    title = build_title(car.title_base, car.vin)

    html = _render_full_template_html(
        ua_code=car.ua_code,
        title=title,
        label=str(stage_info["label"]),
        category=str(stage_info["category"]),
        description_snippet=car.description_snippet,
        main_photo_url=page.main_photo_absolute_url,
        individual_page_url=page.individual_page_url,
    )

    return RenderedCard(
        ua_code=car.ua_code,
        stage=int(stage_info["stage"]),
        category=str(stage_info["category"]),
        title=title,
        label=str(stage_info["label"]),
        main_photo_url=page.main_photo_absolute_url,
        individual_page_url=page.individual_page_url,
        html=html,
    )


def _render_full_template_html(
    *,
    ua_code: str,
    title: str,
    label: str,
    category: str,
    description_snippet: str,
    main_photo_url: str,
    individual_page_url: str,
) -> str:
    """Single unified 55/45 template. No text-only fallback branch exists."""
    return (
        f'<article class="catalog-card" data-ua="{ua_code}" data-category="{category}">'
        f'  <div class="catalog-card__info" style="flex:55">'
        f'    <h3 class="catalog-card__title">{title}</h3>'
        f'    <p class="catalog-card__stage">{label}</p>'
        f'    <p class="catalog-card__desc">{description_snippet}</p>'
        f'    <a class="catalog-card__link" href="{individual_page_url}">Подробнее</a>'
        f'  </div>'
        f'  <div class="catalog-card__media" style="flex:45">'
        f'    <img src="{main_photo_url}" alt="{title}" loading="lazy">'
        f'  </div>'
        f'</article>'
    )


def rebuild_all(
    cars: List[CrmCarRecord],
    pages_by_ua: Dict[str, PublishedPageInfo],
) -> Dict[str, object]:
    """Rebuild the full set of catalog cards from CRM + published pages.

    Returns a dict with:
      - 'cards': ordered list of RenderedCard, exactly one per UA code that
        successfully rendered;
      - 'excluded': list of (ua_code, reason) for cars that failed
        fail-closed checks (no page / no photo / unknown status);

    Deduplication: if the same UA code appears more than once in `cars`,
    only the first occurrence is rendered; the rest are recorded as
    excluded duplicates to guarantee exactly one card per UA code.
    """
    seen: set = set()
    cards: List[RenderedCard] = []
    excluded: List[Dict[str, str]] = []

    for car in cars:
        if car.ua_code in seen:
            excluded.append({"ua_code": car.ua_code, "reason": "duplicate_ua_code_skipped"})
            continue
        seen.add(car.ua_code)

        page = pages_by_ua.get(car.ua_code)
        if page is None:
            excluded.append(
                {"ua_code": car.ua_code, "reason": "no_published_page_info"}
            )
            continue
        try:
            card = render_card(car, page)
            cards.append(card)
        except CatalogGuardError as exc:
            excluded.append({"ua_code": car.ua_code, "reason": str(exc)})

    return {"cards": cards, "excluded": excluded}


def assemble_catalog_html(cards: List[RenderedCard]) -> str:
    """Assemble the final catalog document body from rendered cards.

    This is a pure function; the caller (bounded installer, outside this
    module) is responsible for atomic file writes with backup/verify/
    rollback per install_procedure.md.
    """
    body = "\n".join(card.html for card in cards)
    return (
        '<div class="catalog-grid" data-guard="task-082-unified">\n'
        f"{body}\n"
        "</div>"
    )

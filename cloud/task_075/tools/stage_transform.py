"""TASK 075 — stage normalization and single-template card transform.

Implements:
- normalize_stage(): single CRM `status` -> one of the 4 public stages, or
  None if the raw status must be hidden (транзит / предоплата внесена).
- stage_text(): canonical public text per stage.
- build_card(): refuses to emit a card without a resolved photo (fixes the
  "text fallback without photo" defect).
- dedupe_one_card_per_stage(): guarantees exactly one card per (stage,
  category) pair (UA-0011 gate).
- migrate_ferry_route_cards(): ROUND 2 requirement — rewrites the ferry-route
  text on ALL existing `more`-stage cards, not just one card.
- render_card_html(): ROUND 3 single template, absolute photo required,
  <base> emitted before any CSS <link>.
- days_since_transition(): ROUND 3 — stage 3 day count from the actual
  transition timestamp, never from a payment/prepayment flag.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Dict, List, Optional

HIDDEN_MARKERS = ("транзит", "предоплата внесена", "предоплата")

STAGE_TEXT: Dict[str, Optional[str]] = {
    "korea": None,
    "more": "На пароме · маршрут — Киев",
    "gruzia": "В Грузии · маршрут — Киев",
    "kiev": "В Киеве · можно посмотреть",
}

STAGE_ORDER = ["korea", "more", "gruzia", "kiev"]  # 1 -> 2 -> 3 -> 4


class SandboxFail(Exception):
    """Raised to halt the pipeline immediately; any gate violation must stop
    processing rather than emit a partial/incorrect card."""


@dataclass
class Card:
    id: str
    stage: str
    category: str
    text: Optional[str]
    photo_url: str
    crm_photo_count: int
    transition_at: datetime


def normalize_stage(raw_status: str) -> Optional[str]:
    s = (raw_status or "").strip().lower()
    for marker in HIDDEN_MARKERS:
        if marker in s:
            return None
    if "корея" in s:
        return "korea"
    if "паром" in s:
        return "more"
    if "грузия" in s:
        return "gruzia"
    if "киев" in s:
        return "kiev"
    return None


def stage_text(stage: Optional[str]) -> Optional[str]:
    if stage is None:
        return None
    return STAGE_TEXT.get(stage)


def resolve_absolute_photo_url(raw_photo: Optional[str], base_media_host: str) -> str:
    if not raw_photo:
        raise SandboxFail("missing photo: text-only fallback is not permitted")
    if raw_photo.startswith("http://") or raw_photo.startswith("https://"):
        return raw_photo
    return base_media_host.rstrip("/") + "/" + raw_photo.lstrip("/")


def build_card(
    item_id: str,
    raw_status: str,
    crm_photo_count: int,
    raw_photo: Optional[str],
    base_media_host: str,
    transition_at: datetime,
) -> Optional[Card]:
    stage = normalize_stage(raw_status)
    if stage is None:
        return None  # hidden publicly, not an error
    if crm_photo_count <= 0:
        raise SandboxFail(
            f"{item_id}: media sync incomplete (crm_photo_count={crm_photo_count}); "
            "card withheld rather than rendered as text fallback"
        )
    photo_url = resolve_absolute_photo_url(raw_photo, base_media_host)
    return Card(
        id=item_id,
        stage=stage,
        category=stage,
        text=stage_text(stage),
        photo_url=photo_url,
        crm_photo_count=crm_photo_count,
        transition_at=transition_at,
    )


def dedupe_one_card_per_stage(cards: List[Card]) -> List[Card]:
    """Guarantee card_count == 1 per (stage, category). Keeps the most recent
    transition_at when duplicates exist for the same stage/category."""
    latest: Dict[tuple, Card] = {}
    for c in cards:
        key = (c.stage, c.category)
        existing = latest.get(key)
        if existing is None or c.transition_at > existing.transition_at:
            latest[key] = c
    return list(latest.values())


def migrate_ferry_route_cards(cards: List[Card]) -> List[Card]:
    """ROUND 2: rewrite the public text of every existing `more`-stage card
    to the canonical ferry route text, not only a single card."""
    migrated = []
    for c in cards:
        if c.stage == "more":
            migrated.append(replace(c, text=STAGE_TEXT["more"]))
        else:
            migrated.append(c)
    return migrated


def days_since_transition(transition_at: datetime, now: datetime) -> int:
    """ROUND 3: stage 3 day count is derived strictly from the actual
    transition timestamp. This function takes no payment/prepayment flag
    argument at all, structurally preventing that source of truth."""
    delta = now - transition_at
    return delta.days


def stage3_expired(card: Card, now: datetime, threshold_days: int = 15) -> bool:
    if card.stage != "gruzia":
        return False
    return days_since_transition(card.transition_at, now) >= threshold_days


def render_card_html(card: Card, base_href: str, css_hrefs: List[str]) -> str:
    """ROUND 3: single template. <base> is emitted before any CSS <link>.
    No article/plitka classes, no text-only fallback branch exists."""
    if not card.photo_url:
        raise SandboxFail("render_card_html called without a resolved photo_url")
    css_links = "\n".join(
        f'    <link rel="stylesheet" href="{href}">' for href in css_hrefs
    )
    text_html = f'<p class="ua-card-text">{card.text}</p>' if card.text else ""
    return (
        "<!doctype html>\n"
        "<html>\n"
        "<head>\n"
        f'    <base href="{base_href}">\n'
        f"{css_links}\n"
        "</head>\n"
        "<body>\n"
        f'  <div class="ua-card ua-card--{card.stage}" data-id="{card.id}">\n'
        f'    <img class="ua-card-photo" src="{card.photo_url}" alt="{card.id}">\n'
        f"    {text_html}\n"
        "  </div>\n"
        "</body>\n"
        "</html>\n"
    )


def run_pipeline(raw_items: List[dict], base_media_host: str) -> dict:
    """Any exception anywhere halts the pipeline and returns FAIL — sandbox
    contract: no partial output is ever considered a pass."""
    try:
        cards: List[Card] = []
        for item in raw_items:
            card = build_card(
                item_id=item["id"],
                raw_status=item["status"],
                crm_photo_count=item["crm_photo_count"],
                raw_photo=item.get("photo"),
                base_media_host=base_media_host,
                transition_at=item["transition_at"],
            )
            if card is not None:
                cards.append(card)
        cards = dedupe_one_card_per_stage(cards)
        cards = migrate_ferry_route_cards(cards)
        return {"status": "PASS", "cards": cards}
    except SandboxFail as exc:
        return {"status": "FAIL", "error": str(exc), "cards": []}
    except Exception as exc:  # noqa: BLE001 - deliberate broad halt-on-error
        return {"status": "FAIL", "error": f"unexpected: {exc}", "cards": []}

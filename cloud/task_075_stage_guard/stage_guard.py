#!/usr/bin/env python3
"""Pure sandbox renderer and fail-closed catalog stage gate for UA ART."""
from __future__ import annotations

import html as _html
import json
import re
from dataclasses import dataclass
from typing import Iterable, Mapping
from urllib.parse import urljoin


CONTRACT_ID = "CRM-CATALOG-STAGE-GUARD-003-V1.0"
CARD_ID_RE = re.compile(r"UA-[0-9]{4,}", re.I)
RASTER_RE = re.compile(r"\.(?:avif|jpe?g|png|webp)(?:[?#].*)?$", re.I)
STAGE_KEYS = {1: "korea", 2: "more", 3: "gruzia", 4: "kiev"}
PUBLIC_LABELS = {
    1: ("В Корее · выкуплен и проверен", "У Кореї · викуплений і перевірений"),
    2: ("На пароме · маршрут — Киев", "На поромі · маршрут — Київ"),
    3: ("В Грузии · маршрут — Киев", "У Грузії · маршрут — Київ"),
    4: ("В Киеве · можно посмотреть", "У Києві · можна оглянути"),
}
FORBIDDEN_PUBLIC = (
    "предоплата внесена",
    "передоплату внесено",
    "состояние транзит",
    "стан транзит",
    "автомобиль на пароме:",
    "автомобіль на поромі:",
)


class StageGuardError(RuntimeError):
    """A fail-closed catalog contract violation."""


@dataclass(frozen=True)
class CardSpan:
    start: int
    end: int
    card_id: str
    block: str


def esc(value) -> str:
    return _html.escape(str(value or ""), quote=True)


def stage_number(row: Mapping) -> int:
    """Map one authoritative CRM status to the four public stages."""
    status = str(row.get("status") or "").strip().casefold()
    explicit = row.get("stage")
    if status.startswith(("kr_", "korea")):
        return 1
    if status.startswith(("sea_", "ferry", "more", "ocean")):
        return 2
    if status.startswith(("ge_", "georgia")):
        return 3
    if status.startswith(("ua_", "kyiv", "kiev")):
        return 4
    try:
        number = int(explicit)
    except (TypeError, ValueError):
        number = 0
    if number in STAGE_KEYS:
        return number
    raise StageGuardError("UNKNOWN_STAGE:%s" % (row.get("auto_number") or "?"))


def media_count(value) -> int:
    if not value:
        return 0
    if isinstance(value, (list, tuple)):
        return len(value)
    try:
        loaded = json.loads(value) if isinstance(value, str) else value
    except Exception:
        return 0
    return len(loaded) if isinstance(loaded, list) else 0


def title(row: Mapping) -> str:
    return " ".join(
        str(row.get(key) or "").strip() for key in ("brand", "model", "year")
        if str(row.get(key) or "").strip()
    )


def money(value) -> str:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        number = 0
    return ("{:,.0f} $".format(number).replace(",", " ")
            if number > 0 else "Цена по запросу")


def card_spans(source: str) -> list[CardSpan]:
    """Return non-overlapping top-level catalog cards, not links inside cards."""
    candidates: list[tuple[int, int, str, str, int]] = []
    article_re = re.compile(r"<article\b[^>]*>.*?</article\s*>", re.I | re.S)
    anchor_re = re.compile(
        r"<a\b(?=[^>]*href=[\"'][^\"']*UA-[0-9]{4,}\.html(?:\?[^\"']*)?[\"'])"
        r"[^>]*>.*?</a\s*>",
        re.I | re.S,
    )
    for priority, pattern in ((0, article_re), (1, anchor_re)):
        for match in pattern.finditer(source):
            found = CARD_ID_RE.search(match.group(0))
            if found:
                candidates.append((match.start(), match.end(), found.group(0).upper(),
                                   match.group(0), priority))
    candidates.sort(key=lambda item: (item[0], item[4], -(item[1] - item[0])))
    selected: list[CardSpan] = []
    for start, end, identifier, block, _priority in candidates:
        if any(start >= item.start and end <= item.end for item in selected):
            continue
        if any(not (end <= item.start or start >= item.end) for item in selected):
            continue
        selected.append(CardSpan(start, end, identifier, block))
    return sorted(selected, key=lambda item: item.start)


def _set_attribute(opening: str, name: str, value: str) -> str:
    pattern = re.compile(r"\s+" + re.escape(name) + r"\s*=\s*([\"']).*?\1", re.I | re.S)
    opening = pattern.sub("", opening)
    return opening[:-1] + ' %s="%s">' % (name, esc(value))


def _ensure_class(opening: str, class_name: str) -> str:
    match = re.search(r"\sclass\s*=\s*([\"'])(.*?)\1", opening, re.I | re.S)
    if match:
        values = match.group(2).split()
        if class_name not in values:
            values.append(class_name)
        replacement = ' class="%s"' % esc(" ".join(values))
        return opening[:match.start()] + replacement + opening[match.end():]
    return opening[:-1] + ' class="%s">' % esc(class_name)


def normalize_block(block: str, row: Mapping) -> str:
    stage = stage_number(row)
    key = STAGE_KEYS[stage]
    opening_match = re.match(r"<(?:a|article)\b[^>]*>", block, re.I | re.S)
    if not opening_match:
        raise StageGuardError("CARD_OPENING_MISSING:%s" % row.get("auto_number"))
    opening = opening_match.group(0)
    opening = _set_attribute(opening, "data-ua-card-stage", key)
    opening = _set_attribute(opening, "data-etap", key)
    opening = _set_attribute(opening, "data-ua-stage", str(stage))
    opening = _ensure_class(opening, "ua-stage-filterable")
    block = opening + block[opening_match.end():]

    replacements = (
        (r"На\s+пароме\s*[·:]\s*(?:Маршрут\s*:\s*)?Корея\s*[→-]\s*Грузия",
         PUBLIC_LABELS[2][0]),
        (r"На\s+поромі\s*[·:]\s*(?:Маршрут\s*:\s*)?Корея\s*[→-]\s*Грузія",
         PUBLIC_LABELS[2][1]),
        (r"В\s+Грузии\s*[·:]\s*15\s+дн(?:ей|я)?\s+до\s+Киева\s+после\s+предоплаты",
         PUBLIC_LABELS[3][0]),
        (r"У\s+Грузії\s*[·:]\s*15\s+дн(?:ів|і)?\s+до\s+Києва\s+після\s+передоплати",
         PUBLIC_LABELS[3][1]),
    )
    for pattern, replacement in replacements:
        block = re.sub(pattern, replacement, block, flags=re.I)
    for forbidden in FORBIDDEN_PUBLIC:
        block = re.sub(re.escape(forbidden) + r"[^<]*", "", block, flags=re.I)
    return block


def render_card(row: Mapping, photo_url: str) -> str:
    identifier = str(row.get("auto_number") or "").upper()
    if not CARD_ID_RE.fullmatch(identifier):
        raise StageGuardError("INVALID_CARD_ID")
    if not photo_url:
        raise StageGuardError("MAIN_PHOTO_MISSING:%s" % identifier)
    stage = stage_number(row)
    key = STAGE_KEYS[stage]
    label_ru, label_uk = PUBLIC_LABELS[stage]
    mileage = row.get("mileage_km") or row.get("mileage") or "—"
    engine = row.get("engine_cc") or row.get("engine") or "—"
    fuel = row.get("fuel") or "—"
    gearbox = row.get("gearbox") or "—"
    vin = str(row.get("vin") or "VIN НЕ УКАЗАН").upper()
    photos = media_count(row.get("photos"))
    videos = media_count(row.get("videos"))
    return (
        '<a class="kat ua-stage-card-v2 ua-stage-filterable" '
        'href="{id}.html" data-ua-card="{id}" data-ua-card-stage="{key}" '
        'data-etap="{key}" data-ua-stage="{stage}">'
        '<div class="ua-stage-card-v2-body">'
        '<span class="ua-stage-card-v2-kicker">{id} · ЭТАП {stage} ИЗ 4</span>'
        '<h3>{title}</h3>'
        '<div class="ua-stage-card-v2-status"><span class="ua075-ru">{ru}</span>'
        '<span class="ua075-uk">{uk}</span></div>'
        '<div class="ua-stage-card-v2-spec">{mileage} км · {engine} см³ · {fuel} · {gearbox}</div>'
        '<div class="ua-stage-card-v2-vin"><span>VIN <b>{vin}</b></span>'
        '<i>VIN ПРОВЕРЕН</i><small>Фото: {photos} · Видео: {videos}</small></div>'
        '<span class="ua-stage-card-v2-open"><span class="ua075-ru">Открыть карточку →</span>'
        '<span class="ua075-uk">Відкрити картку →</span></span></div>'
        '<figure class="ua-stage-card-v2-photo"><img src="{photo}" alt="{title}" '
        'loading="lazy" decoding="async"></figure></a>'
    ).format(
        id=esc(identifier), key=esc(key), stage=stage, title=esc(title(row) or identifier),
        ru=esc(label_ru), uk=esc(label_uk), mileage=esc(mileage), engine=esc(engine),
        fuel=esc(fuel), gearbox=esc(gearbox), vin=esc(vin), photos=photos,
        videos=videos, photo=esc(photo_url),
    )


STYLE = r'''<style id="ua-stage-card-v2-style">
.ua-stage-card-v2{display:grid!important;grid-template-columns:minmax(0,55%) minmax(0,45%);padding:0!important;overflow:hidden;border:1px solid rgba(240,166,60,.46)!important;border-radius:22px!important;background:linear-gradient(145deg,#172a40,#102033)!important;color:#edf3fb!important;text-decoration:none!important;box-shadow:0 12px 30px rgba(0,0,0,.2);min-height:290px}
.ua-stage-card-v2 *{box-sizing:border-box}.ua-stage-card-v2-body{padding:24px 20px;min-width:0}.ua-stage-card-v2-kicker{display:block;color:#f0a63c;font-size:11px;font-weight:900;letter-spacing:.11em}.ua-stage-card-v2 h3{margin:11px 0 7px;font-size:26px;line-height:1.16;color:#f3f6fa}.ua-stage-card-v2-status{color:#72dfa5;font-size:14px;line-height:1.4}.ua-stage-card-v2-spec{margin-top:15px;color:#aebed0;font-size:13px;line-height:1.5}.ua-stage-card-v2-vin{display:grid;grid-template-columns:1fr auto;gap:8px;margin-top:17px;padding:13px;border-top:1px solid rgba(240,166,60,.32);background:rgba(10,25,40,.25);font-size:12px;color:#b9c8d8}.ua-stage-card-v2-vin b{color:#f3f6fa;overflow-wrap:anywhere}.ua-stage-card-v2-vin i{font-style:normal;color:#72dfa5;font-size:9px;border:1px solid rgba(64,190,125,.42);border-radius:999px;padding:4px 6px}.ua-stage-card-v2-vin small{grid-column:1/-1;color:#9fb0c5}.ua-stage-card-v2-open{display:block;margin-top:16px;color:#f4b65c;font-weight:850}.ua-stage-card-v2-photo{margin:0;min-width:0;min-height:100%;background:#0a1725}.ua-stage-card-v2-photo img{display:block;width:100%;height:100%;min-height:290px;object-fit:cover;object-position:center}.ua075-uk{display:none}html:lang(uk) .ua075-ru{display:none}html:lang(uk) .ua075-uk{display:inline}
@media(max-width:620px){.ua-stage-card-v2{grid-template-columns:minmax(0,56%) minmax(0,44%);min-height:330px}.ua-stage-card-v2-body{padding:20px 14px}.ua-stage-card-v2 h3{font-size:22px}.ua-stage-card-v2-status{font-size:13px}.ua-stage-card-v2-spec{font-size:12px}.ua-stage-card-v2-vin{grid-template-columns:1fr;padding:10px}.ua-stage-card-v2-vin i{justify-self:start}.ua-stage-card-v2-photo img{min-height:330px}}
</style>'''


FILTER_SCRIPT = r'''<script id="ua-stage-card-v2-filter">(function(){
function apply(){var p=new URLSearchParams(location.search),f=p.get('f')||'all';
var cards=document.querySelectorAll('[data-ua-card-stage]');for(var i=0;i<cards.length;i++){
var s=cards[i].getAttribute('data-ua-card-stage');cards[i].style.display=(f==='all'||s===f)?'':'none';}}
if(document.readyState==='loading'){document.addEventListener('DOMContentLoaded',apply)}else{apply()}})();</script>'''


def _inject_once(source: str, marker_id: str, payload: str, before: str) -> str:
    source = re.sub(
        r"<(?P<tag>style|script)\b[^>]*id=[\"']" + re.escape(marker_id)
        + r"[\"'][^>]*>.*?</(?P=tag)\s*>",
        "", source, flags=re.I | re.S,
    )
    position = source.lower().find(before.lower())
    if position < 0:
        raise StageGuardError("INSERTION_POINT_MISSING:" + before)
    return source[:position] + payload + source[position:]


def enforce_catalog(source: str, rows: Iterable[Mapping], photos: Mapping[str, str]) -> str:
    rows_by_id = {
        str(row.get("auto_number") or "").upper(): dict(row)
        for row in rows if int(row.get("published") or 0) == 1
    }
    if not rows_by_id:
        raise StageGuardError("NO_PUBLISHED_ROWS")
    spans = card_spans(source)
    by_id: dict[str, list[CardSpan]] = {}
    for span in spans:
        by_id.setdefault(span.card_id, []).append(span)
    for identifier in rows_by_id:
        if len(by_id.get(identifier, [])) > 1:
            raise StageGuardError("DUPLICATE_CARD:%s" % identifier)

    replacements: list[tuple[int, int, str]] = []
    missing: list[str] = []
    for identifier, row in rows_by_id.items():
        current = by_id.get(identifier, [])
        photo = str(photos.get(identifier) or "")
        if not current:
            missing.append(identifier)
            continue
        span = current[0]
        has_photo = bool(re.search(r"<img\b[^>]*\bsrc\s*=", span.block, re.I))
        is_fallback = "ua-cat-fallback" in span.block
        candidate = (render_card(row, photo) if is_fallback or not has_photo
                     else normalize_block(span.block, row))
        replacements.append((span.start, span.end, candidate))

    for start, end, value in sorted(replacements, reverse=True):
        source = source[:start] + value + source[end:]

    if missing:
        rendered = "".join(render_card(rows_by_id[identifier], photos.get(identifier, ""))
                           for identifier in missing)
        markers = (
            r'<div\b[^>]*class=[\"\'][^\"\']*\bempty-assist\b',
            r'<a\b(?=[^>]*class=[\"\'][^\"\']*\bvtoraya\b)(?=[^>]*href=[\"\'][^\"\']*podbor\.html)',
            r'</main\s*>', r'</body\s*>',
        )
        position = -1
        for pattern in markers:
            match = re.search(pattern, source, re.I)
            if match:
                position = match.start()
                break
        if position < 0:
            raise StageGuardError("CATALOG_INSERTION_POINT_MISSING")
        source = source[:position] + rendered + source[position:]

    source = _inject_once(source, "ua-stage-card-v2-style", STYLE, "</head>")
    source = _inject_once(source, "ua-stage-card-v2-filter", FILTER_SCRIPT, "</body>")
    return source


def audit_catalog(source: str, rows: Iterable[Mapping]) -> dict:
    rows_by_id = {
        str(row.get("auto_number") or "").upper(): dict(row)
        for row in rows if int(row.get("published") or 0) == 1
    }
    spans = card_spans(source)
    by_id: dict[str, list[CardSpan]] = {}
    for span in spans:
        by_id.setdefault(span.card_id, []).append(span)
    errors: list[str] = []
    cards = {}
    for identifier, row in sorted(rows_by_id.items()):
        found = by_id.get(identifier, [])
        expected_stage = stage_number(row)
        expected_key = STAGE_KEYS[expected_stage]
        if len(found) != 1:
            errors.append("CARD_COUNT:%s:%d" % (identifier, len(found)))
            continue
        block = found[0].block
        photo = bool(re.search(r"<img\b[^>]*\bsrc\s*=\s*[\"'][^\"']+[\"']", block, re.I))
        stage_ok = ('data-ua-card-stage="%s"' % expected_key) in block
        if not photo:
            errors.append("PHOTO_MISSING:" + identifier)
        if not stage_ok:
            errors.append("STAGE_MISMATCH:%s:%s" % (identifier, expected_key))
        folded = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", block)).casefold()
        leaked = [value for value in FORBIDDEN_PUBLIC if value.casefold() in folded]
        if leaked:
            errors.append("INTERNAL_TEXT_LEAK:%s" % identifier)
        if expected_stage == 2 and re.search(r"корея\s*[→-]\s*грузи", folded, re.I):
            errors.append("FERRY_ROUTE_OLD:%s" % identifier)
        cards[identifier] = {"count": 1, "photo": photo, "stage": expected_stage,
                             "category": expected_key, "stage_ok": stage_ok}
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "published_rows": len(rows_by_id),
        "canonical_cards": len([key for key in rows_by_id if len(by_id.get(key, [])) == 1]),
        "cards": cards,
    }


def extract_main_photo(page: str, page_url: str, identifier: str) -> str:
    values = re.findall(r"<img\b[^>]*\bsrc\s*=\s*[\"']([^\"']+)[\"']", page, re.I)
    if not values:
        return ""
    identifier_folded = identifier.casefold().replace("-", "")
    scored = []
    for index, value in enumerate(values):
        folded = value.casefold()
        if any(token in folded for token in ("logo", "icon", "flag", "whatsapp", "avatar")):
            continue
        if not (RASTER_RE.search(value) or value.startswith("data:image/")):
            continue
        normalized = folded.replace("-", "")
        score = (100 if identifier_folded in normalized else 0) + (20 if "foto" in folded else 0) - index
        scored.append((score, value))
    if not scored:
        return ""
    value = max(scored, key=lambda item: item[0])[1]
    return value if value.startswith("data:") else urljoin(page_url, value)

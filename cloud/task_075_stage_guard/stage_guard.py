#!/usr/bin/env python3
"""Pure sandbox renderer and fail-closed catalog stage gate for UA ART."""
from __future__ import annotations

import html as _html
import datetime as _dt
import json
import re
from dataclasses import dataclass
from typing import Iterable, Mapping
from urllib.parse import urljoin


CONTRACT_ID = "CRM-CATALOG-STAGE-GUARD-003-V1.0"
CATALOG_CARD_DEDUP_GUARD = "CATALOG-CARD-DEDUP-GUARD-083-V1.0"
CARD_ID_RE = re.compile(r"UA-[0-9]{4,}", re.I)
RASTER_RE = re.compile(r"\.(?:avif|jpe?g|png|webp)(?:[?#].*)?$", re.I)
STAGE_KEYS = {1: "korea", 2: "more", 3: "gruzia", 4: "kiev"}
NATIVE_STAGE_KEYS = {1: "korea", 2: "sea", 3: "georgia", 4: "kiev"}
LIST_START = "<!-- CRM-CATALOG-STAGE-GUARD-003-LIST:START -->"
LIST_END = "<!-- CRM-CATALOG-STAGE-GUARD-003-LIST:END -->"
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


def public_media_summary(photos: int, videos: int) -> str:
    """Show useful media counts once; never render technical zero values."""
    values = []
    if photos > 0:
        values.append("Фото: %d" % photos)
    if videos > 0:
        values.append("Видео: %d" % videos)
    return " · ".join(values) or "Медиа готовятся"


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


def _date(value):
    text = str(value or "").strip()[:10]
    if not text:
        return None
    for pattern in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return _dt.datetime.strptime(text, pattern).date()
        except ValueError:
            pass
    return None


def _pretty_date(value, language: str) -> str:
    months = (
        ("января", "февраля", "марта", "апреля", "мая", "июня",
         "июля", "августа", "сентября", "октября", "ноября", "декабря")
        if language == "ru" else
        ("січня", "лютого", "березня", "квітня", "травня", "червня",
         "липня", "серпня", "вересня", "жовтня", "листопада", "грудня")
    )
    return "%d %s %d" % (value.day, months[value.month - 1], value.year)


def public_eta(row: Mapping, stage: int) -> tuple[str, str]:
    """Client-safe ETA derived from CRM dates, never from an internal payment flag."""
    if stage == 2:
        target = _date(row.get("eta_manual"))
        if target is None:
            shipped = _date(row.get("sea_date_out"))
            target = shipped + _dt.timedelta(days=75) if shipped else None
        if target is None:
            return ("Срок до Киева уточняется", "Строк до Києва уточнюється")
        days = max((target - _dt.datetime.now(_dt.timezone.utc).date()).days, 0)
        return (
            "%d дн. до Киева · ориентировочно %s" % (days, _pretty_date(target, "ru")),
            "%d дн. до Києва · орієнтовно %s" % (days, _pretty_date(target, "uk")),
        )
    if stage == 3:
        transitioned = _date(row.get("ge_released")) or _date(row.get("ge_to_kyiv_at"))
        if transitioned is None:
            return (
                "15 дней до Киева считаются от фактического перехода в этап 3",
                "15 днів до Києва рахуються від фактичного переходу на етап 3",
            )
        target = transitioned + _dt.timedelta(days=15)
        return (
            "15 дней от перехода в этап 3 · ориентировочно %s" % _pretty_date(target, "ru"),
            "15 днів від переходу на етап 3 · орієнтовно %s" % _pretty_date(target, "uk"),
        )
    return ("", "")


def public_price(row: Mapping) -> str:
    for key in ("price", "price_usd", "price_uah", "sale_price", "price_final"):
        value = row.get(key)
        if value not in (None, "", 0, "0"):
            return money(value)
    return money(None)


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
    native_key = NATIVE_STAGE_KEYS[stage]
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
    if stage == 2:
        block = re.sub(
            r"(?:Маршрут\s*:\s*)?Корея\s*(?:→|&rarr;|&#8594;|-)\s*Грузия",
            "маршрут — Киев", block, flags=re.I,
        )
        block = re.sub(
            r"(?:Маршрут\s*:\s*)?Корея\s*(?:→|&rarr;|&#8594;|-)\s*Грузія",
            "маршрут — Київ", block, flags=re.I,
        )
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
    native_key = NATIVE_STAGE_KEYS[stage]
    label_ru, label_uk = PUBLIC_LABELS[stage]
    mileage = row.get("mileage_km") or row.get("mileage") or "—"
    engine = row.get("engine_cc") or row.get("engine") or "—"
    fuel = row.get("fuel") or "—"
    gearbox = row.get("gearbox") or "—"
    vin = str(row.get("vin") or "VIN НЕ УКАЗАН").upper()
    photos = media_count(row.get("photos"))
    videos = media_count(row.get("videos"))
    media = public_media_summary(photos, videos)
    eta_ru, eta_uk = public_eta(row, stage)
    eta = (
        '<div class="ua-stage-card-v2-eta"><span class="ua075-ru">{eta_ru}</span>'
        '<span class="ua075-uk">{eta_uk}</span></div>'
        if eta_ru or eta_uk else ""
    )
    return (
        '<a class="kat ua-stage-card-v2 ua-stage-filterable" '
        'href="{id}.html" data-ua-card="{id}" data-ua-card-stage="{key}" '
        'data-stage="{native_key}" data-etap="{key}" data-ua-stage="{stage}">'
        '<div class="ua-stage-card-v2-body">'
        '<div class="ua-stage-card-v2-top"><span class="ua-stage-card-v2-kicker">'
        '{id} · ЭТАП {stage} ИЗ 4</span><strong>{price}</strong></div>'
        '<h3>{title}</h3>'
        '<div class="ua-stage-card-v2-status"><span class="ua075-ru">{ru}</span>'
        '<span class="ua075-uk">{uk}</span></div>'
        '<div class="ua-stage-card-v2-spec">{mileage} км · {engine} см³ · {fuel} · {gearbox}</div>'
        '{eta}'
        '<div class="ua-stage-card-v2-vin"><span>VIN <b>{vin}</b></span>'
        '<i>VIN ПРОВЕРЕН</i><small>{media}</small></div>'
        '<span class="ua-stage-card-v2-open"><span class="ua075-ru">Открыть карточку →</span>'
        '<span class="ua075-uk">Відкрити картку →</span></span></div>'
        '<figure class="ua-stage-card-v2-photo"><img src="{photo}" alt="{title}" '
        'loading="eager" decoding="async"></figure></a>'
    ).format(
        id=esc(identifier), key=esc(key), native_key=esc(native_key), stage=stage,
        title=esc(title(row) or identifier),
        ru=esc(label_ru), uk=esc(label_uk), mileage=esc(mileage), engine=esc(engine),
        fuel=esc(fuel), gearbox=esc(gearbox), vin=esc(vin), photos=photos,
        media=esc(media), photo=esc(photo_url), price=esc(public_price(row)), eta=eta.format(
            eta_ru=esc(eta_ru), eta_uk=esc(eta_uk)),
    )


STYLE = r'''<style id="ua-stage-card-v2-style">
.ua-stage-card-v2{display:grid!important;grid-template-columns:minmax(0,55%) minmax(0,45%);margin:12px 0;padding:0!important;overflow:hidden;border:1px solid rgba(240,166,60,.46)!important;border-radius:22px!important;background:linear-gradient(145deg,#172a40,#102033)!important;color:#edf3fb!important;text-decoration:none!important;box-shadow:0 12px 30px rgba(0,0,0,.2);min-height:290px}.ua-stage-card-v2[hidden]{display:none!important}.catalog-grid>.ua-stage-card-v2{margin:0}
.ua-stage-card-v2 *{box-sizing:border-box}.ua-stage-card-v2-body{padding:24px 20px;min-width:0}.ua-stage-card-v2-top{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}.ua-stage-card-v2-kicker{display:block;color:#f0a63c;font-size:11px;font-weight:900;letter-spacing:.11em}.ua-stage-card-v2-top strong{flex:0 0 auto;color:#f4b65c;font-size:16px;white-space:nowrap}.ua-stage-card-v2 h3{margin:11px 0 7px;font-size:26px;line-height:1.16;color:#f3f6fa}.ua-stage-card-v2-status{color:#72dfa5;font-size:14px;line-height:1.4}.ua-stage-card-v2-spec{margin-top:15px;color:#aebed0;font-size:13px;line-height:1.5}.ua-stage-card-v2-eta{margin-top:9px;color:#f2c27b;font-size:11px;line-height:1.4}.ua-stage-card-v2-vin{display:grid;grid-template-columns:1fr auto;gap:8px;margin-top:17px;padding:13px;border-top:1px solid rgba(240,166,60,.32);background:rgba(10,25,40,.25);font-size:12px;color:#b9c8d8}.ua-stage-card-v2-vin b{color:#f3f6fa;overflow-wrap:anywhere}.ua-stage-card-v2-vin i{font-style:normal;color:#72dfa5;font-size:9px;border:1px solid rgba(64,190,125,.42);border-radius:999px;padding:4px 6px}.ua-stage-card-v2-vin small{grid-column:1/-1;color:#9fb0c5}.ua-stage-card-v2-open{display:block;margin-top:16px;color:#f4b65c;font-weight:850}.ua-stage-card-v2-photo{margin:0;min-width:0;min-height:100%;background:#0a1725}.ua-stage-card-v2-photo img{display:block;width:100%;height:100%;min-height:290px;object-fit:cover;object-position:center}.ua075-uk{display:none}html:lang(uk) .ua075-ru{display:none}html:lang(uk) .ua075-uk{display:inline}
@media(max-width:620px){.ua-stage-card-v2{grid-template-columns:minmax(0,56%) minmax(0,44%);min-height:350px}.ua-stage-card-v2-body{padding:18px 13px}.ua-stage-card-v2-top{display:block}.ua-stage-card-v2-top strong{display:block;margin-top:6px;font-size:15px}.ua-stage-card-v2 h3{font-size:22px}.ua-stage-card-v2-status{font-size:13px}.ua-stage-card-v2-spec{font-size:12px}.ua-stage-card-v2-vin{grid-template-columns:1fr;padding:10px}.ua-stage-card-v2-vin i{justify-self:start}.ua-stage-card-v2-photo img{min-height:350px}}
</style>'''


FILTER_SCRIPT = r'''<script id="ua-stage-card-v2-filter">(function(){
var map={more:'sea',gruzia:'georgia',kiev:'kiev',korea:'korea',sea:'sea',georgia:'georgia'};
function norm(f){return map[f]||f||'all'}
function fromUrl(){var p=new URLSearchParams(location.search);return norm(p.get('f')||p.get('stage')||'all')}
var activeFilter=fromUrl();
function apply(next){if(next)activeFilter=norm(next);var f=activeFilter;
var cards=document.querySelectorAll('[data-ua-card-stage]'),shown=0;
for(var i=0;i<cards.length;i++){var s=cards[i].getAttribute('data-stage');
var visible=(f==='all'||s===f);cards[i].hidden=!visible;
cards[i].setAttribute('aria-hidden',visible?'false':'true');
cards[i].style.setProperty('display',visible?'grid':'none','important');if(visible)shown++;}
var buttons=document.querySelectorAll('[data-f]');for(var j=0;j<buttons.length;j++){
var bf=map[buttons[j].getAttribute('data-f')]||buttons[j].getAttribute('data-f');
var active=(bf===f||(f==='all'&&bf==='all'));buttons[j].classList.toggle('active',active);
buttons[j].setAttribute('aria-pressed',active?'true':'false');}
var result=document.querySelector('.catalog-result');if(result)result.textContent='Показано: '+shown;
var rendered=0;for(var k=0;k<cards.length;k++){
if(window.getComputedStyle(cards[k]).display!=='none'&&!cards[k].hidden)rendered++;}
var root=document.documentElement;root.setAttribute('data-ua-stage-filter',f);
root.setAttribute('data-ua-stage-filter-shown',String(shown));
root.setAttribute('data-ua-stage-filter-rendered',String(rendered));
root.setAttribute('data-ua-stage-filter-ok',rendered===shown?'true':'false');}
function schedule(){apply();setTimeout(apply,120);setTimeout(apply,900);}
if(document.readyState==='loading'){document.addEventListener('DOMContentLoaded',schedule)}else{schedule()}
window.addEventListener('load',schedule);
window.addEventListener('popstate',function(){activeFilter=fromUrl();schedule()});
document.addEventListener('click',function(event){var button=event.target.closest&&event.target.closest('[data-f]');
if(!button)return;activeFilter=norm(button.getAttribute('data-f'));setTimeout(apply,0);setTimeout(apply,120);},true);
})();</script>'''


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
    managed = list(re.finditer(
        re.escape(LIST_START) + r".*?" + re.escape(LIST_END), source, re.I | re.S))
    if len(managed) > 1:
        raise StageGuardError("MANAGED_LIST_DUPLICATE")
    if managed:
        old = managed[0]
        old_cards = "".join(span.block for span in card_spans(old.group(0)))
        source = source[:old.start()] + old_cards + source[old.end():]
    source = source.replace("<!-- UA-ART-CATALOG-CARD-FALLBACK-V1:START -->", "")
    source = source.replace("<!-- UA-ART-CATALOG-CARD-FALLBACK-V1:END -->", "")
    spans = card_spans(source)
    by_id: dict[str, list[CardSpan]] = {}
    for span in spans:
        by_id.setdefault(span.card_id, []).append(span)
    for identifier in rows_by_id:
        if len(by_id.get(identifier, [])) > 1:
            raise StageGuardError("DUPLICATE_CARD:%s" % identifier)

    positions = {identifier: values[0].start for identifier, values in by_id.items() if values}
    ordered = sorted(
        rows_by_id,
        key=lambda identifier: (-stage_number(rows_by_id[identifier]),
                                positions.get(identifier, len(source) + 1), identifier),
    )
    rendered = LIST_START + "".join(
        render_card(rows_by_id[identifier], photos.get(identifier, ""))
        for identifier in ordered
    ) + LIST_END

    if spans:
        position = spans[0].start
        for span in sorted(spans, key=lambda item: item.start, reverse=True):
            source = source[:span.start] + source[span.end:]
    else:
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

    # Keep public shell copy synchronized with the same contract as the cards.
    # This covers old static counters and explanatory text outside the grid.
    total = len(rows_by_id)
    source = re.sub(r"\b\d+\s+в\s+подборке\b", "%d в подборке" % total,
                    source, flags=re.I)
    source = re.sub(r"\b\d+\s+у\s+добірці\b", "%d у добірці" % total,
                    source, flags=re.I)
    source = re.sub(r"Корея\s*(?:→|&rarr;|&#8594;)\s*Грузия",
                    "маршрут — Киев", source, flags=re.I)
    source = re.sub(r"Корея\s*(?:→|&rarr;|&#8594;)\s*Грузія",
                    "маршрут — Київ", source, flags=re.I)

    source = _inject_once(source, "ua-stage-card-v2-style", STYLE, "</head>")
    source = _inject_once(source, "ua-stage-card-v2-filter", FILTER_SCRIPT, "</body>")
    return source


def semantic_duplicate_issues(block: str, row: Mapping) -> list[str]:
    """Audit one rendered card for repeated client-facing expressions."""
    issues = []
    folded = " ".join(
        _html.unescape(re.sub(r"<[^>]+>", " ", block)).casefold().split()
    )
    for name, phrase in (
        ("FERRY_RU", "Автомобиль на пароме: Корея → Грузия."),
        ("FERRY_UK", "Автомобіль на поромі: Корея → Грузія."),
        ("KYIV_RU", "Автомобиль в Киеве и готов к осмотру."),
        ("KYIV_UK", "Автомобіль у Києві та готовий до огляду."),
    ):
        if " ".join(phrase.casefold().split()) in folded:
            issues.append("LEGACY_REPEAT_" + name)
    if re.search(r"(?:видео|відео)\s*:\s*0(?:\D|$)", folded, re.I):
        issues.append("ZERO_VIDEO_TEXT")
    for class_name in (
        "ua-stage-card-v2-status", "ua-stage-card-v2-spec",
        "ua-stage-card-v2-vin", "ua-stage-card-v2-photo",
    ):
        count = len(re.findall(
            r'class=["\'][^"\']*\b' + re.escape(class_name) + r'\b', block, re.I
        ))
        if count != 1:
            issues.append("REPEATED_SECTION_%s_%d" % (class_name, count))
    for language in ("ru", "uk"):
        texts = []
        pattern = (
            r'<span\b[^>]*class=["\'][^"\']*\bua075-' + language
            + r'\b[^"\']*["\'][^>]*>(.*?)</span\s*>'
        )
        for match in re.finditer(pattern, block, re.I | re.S):
            value = " ".join(
                _html.unescape(re.sub(r"<[^>]+>", " ", match.group(1)))
                .casefold().split()
            )
            if len(value) >= 12:
                texts.append(value)
        if len(texts) != len(set(texts)):
            issues.append("REPEATED_%s_EXPRESSION" % language.upper())
    stage = stage_number(row)
    for language, label in zip(("RU", "UK"), PUBLIC_LABELS[stage]):
        normalized = " ".join(label.casefold().split())
        if folded.count(normalized) > 1:
            issues.append("REPEATED_STAGE_" + language)
    media = re.findall(r"(?:фото|видео|відео)\s*:\s*\d+", folded, re.I)
    if len(media) != len(set(media)):
        issues.append("REPEATED_MEDIA_COUNT")
    return issues


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
    list_start = source.find(LIST_START)
    list_end = source.find(LIST_END)
    list_ok = source.count(LIST_START) == 1 and source.count(LIST_END) == 1 and 0 <= list_start < list_end
    if not list_ok:
        errors.append("UNIFIED_LIST_MARKERS")
    public_shell = re.sub(r"<(?:script|style)\b[^>]*>.*?</(?:script|style)\s*>",
                          " ", source, flags=re.I | re.S)
    public_shell = _html.unescape(re.sub(r"<[^>]+>", " ", public_shell))
    public_shell = re.sub(r"\s+", " ", public_shell)
    if re.search(r"корея\s*[→-]\s*грузи", public_shell, re.I):
        errors.append("CATALOG_FERRY_ROUTE_OLD")
    for found in re.finditer(r"\b(\d+)\s+(?:в\s+подборке|у\s+добірці)\b",
                             public_shell, re.I):
        if int(found.group(1)) != len(rows_by_id):
            errors.append("CATALOG_COUNT_STALE:%s" % found.group(1))
    ordered_stages = []
    for identifier, row in sorted(rows_by_id.items()):
        found = by_id.get(identifier, [])
        expected_stage = stage_number(row)
        expected_key = STAGE_KEYS[expected_stage]
        expected_native = NATIVE_STAGE_KEYS[expected_stage]
        if len(found) != 1:
            errors.append("CARD_COUNT:%s:%d" % (identifier, len(found)))
            continue
        block = found[0].block
        photo_match = re.search(r"<img\b[^>]*\bsrc\s*=\s*[\"']([^\"']+)[\"']", block, re.I)
        photo = bool(photo_match)
        absolute_photo = bool(photo_match and re.match(r"(?:https?://|data:image/)", photo_match.group(1), re.I))
        stage_ok = ('data-ua-card-stage="%s"' % expected_key) in block
        native_stage_ok = ('data-stage="%s"' % expected_native) in block
        template_ok = bool(re.search(r'class=["\'][^"\']*\bua-stage-card-v2\b', block, re.I))
        if not photo:
            errors.append("PHOTO_MISSING:" + identifier)
        if not absolute_photo:
            errors.append("PHOTO_NOT_ABSOLUTE:" + identifier)
        if not stage_ok:
            errors.append("STAGE_MISMATCH:%s:%s" % (identifier, expected_key))
        if not native_stage_ok:
            errors.append("NATIVE_FILTER_STAGE:%s:%s" % (identifier, expected_native))
        if not template_ok:
            errors.append("TEMPLATE_MISMATCH:" + identifier)
        if list_ok and not (list_start < found[0].start < list_end):
            errors.append("CARD_OUTSIDE_UNIFIED_LIST:" + identifier)
        folded = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", block)).casefold()
        leaked = [value for value in FORBIDDEN_PUBLIC if value.casefold() in folded]
        if leaked:
            errors.append("INTERNAL_TEXT_LEAK:%s" % identifier)
        for issue in semantic_duplicate_issues(block, row):
            errors.append("SEMANTIC_DUPLICATE:%s:%s" % (identifier, issue))
        if expected_stage == 2 and re.search(r"корея\s*[→-]\s*грузи", folded, re.I):
            errors.append("FERRY_ROUTE_OLD:%s" % identifier)
        if PUBLIC_LABELS[expected_stage][0].casefold() not in folded:
            errors.append("PUBLIC_LABEL_MISMATCH:%s" % identifier)
        cards[identifier] = {"count": 1, "photo": photo, "stage": expected_stage,
                             "category": expected_key, "stage_ok": stage_ok,
                             "native_stage": expected_native,
                             "native_stage_ok": native_stage_ok,
                             "template": template_ok, "absolute_photo": absolute_photo}
    if list_ok:
        for span in spans:
            if span.card_id in rows_by_id and list_start < span.start < list_end:
                ordered_stages.append(stage_number(rows_by_id[span.card_id]))
        if any(left < right for left, right in zip(ordered_stages, ordered_stages[1:])):
            errors.append("STAGE_GROUP_ORDER")
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "published_rows": len(rows_by_id),
        "canonical_cards": len([key for key in rows_by_id if len(by_id.get(key, [])) == 1]),
        "unified_templates": sum(1 for value in cards.values() if value.get("template")),
        "absolute_photos": sum(1 for value in cards.values() if value.get("absolute_photo")),
        "native_filter_stages": sum(1 for value in cards.values() if value.get("native_stage_ok")),
        "unified_list": list_ok,
        "ordered_stage_groups": ordered_stages,
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


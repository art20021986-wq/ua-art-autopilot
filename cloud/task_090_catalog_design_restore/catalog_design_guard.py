#!/usr/bin/env python3
"""Fail-closed immutable-shell catalog renderer for UA ART (TASK 090).

Only catalog cards and numeric counters are mutable.  Navigation, filters,
language controls, footer, WhatsApp and all other shell markup are copied from
an approved production backup and protected by a normalized SHA-256.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import os
import pathlib
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping


CONTRACT_ID = "CATALOG-DESIGN-STAGE-RESTORE-090-V1.0"
ROOT = pathlib.Path(os.environ.get("UA_ART_ROOT", "/home/Carix")).resolve()
GOLDEN_PATH = ROOT / "catalog_design_golden.html"
CARD_ID_RE = re.compile(r"UA-[0-9]{4,}", re.I)
ARTICLE_RE = re.compile(
    r'<article\b(?=[^>]*\bclass\s*=\s*["\'][^"\']*\bcatalog-card\b)'
    r'[^>]*>.*?</article\s*>',
    re.I | re.S,
)
CAT_START = "<!-- UA-ART-CATALOG-VIN-V1:START -->"
CAT_END = "<!-- UA-ART-CATALOG-VIN-V1:END -->"
STAGE_KEYS = {1: "korea", 2: "sea", 3: "georgia", 4: "kiev"}
FILTER_ORDER = ("all", "kiev", "georgia", "sea", "korea")
PUBLIC_LABELS = {
    1: ("В Корее · выкуплен и проверен", "У Кореї · викуплений і перевірений"),
    2: ("На пароме · маршрут — Киев", "На поромі · маршрут — Київ"),
    3: ("В Грузии · маршрут — Киев", "У Грузії · маршрут — Київ"),
    4: ("В Киеве · можно посмотреть", "У Києві · можна оглянути"),
}
EXPECTED_IDS = tuple("UA-%04d" % number for number in range(1, 14))
EXPECTED_STAGE_COUNTS = {"all": 13, "kiev": 3, "georgia": 1, "sea": 7, "korea": 2}


class CatalogDesignError(RuntimeError):
    """The requested catalog cannot be produced without breaking the shell."""


@dataclass(frozen=True)
class CardSpan:
    start: int
    end: int
    identifier: str
    source: str


def _esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def _sha(value: str | bytes) -> str:
    data = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(data).hexdigest()


def stage_number(row: Mapping[str, Any]) -> int:
    status = str(row.get("status") or "").strip().casefold()
    if status.startswith(("kr_", "korea")):
        return 1
    if status.startswith(("sea_", "ferry", "more", "ocean", "sold_transit")):
        return 2
    if status == "ge_to_kyiv" or status.startswith(("ge_", "georgia")):
        return 3
    if status.startswith(("ua_", "kyiv", "kiev")) or status in {"sold", "archive"}:
        return 4
    try:
        explicit = int(row.get("stage") or 0)
    except (TypeError, ValueError):
        explicit = 0
    if explicit in STAGE_KEYS:
        return explicit
    raise CatalogDesignError(
        "UNKNOWN_STAGE:%s:%s" % (row.get("auto_number") or "?", status)
    )


def _media_count(value: Any) -> int:
    if isinstance(value, (list, tuple)):
        return len(value)
    if not value:
        return 0
    try:
        decoded = json.loads(value) if isinstance(value, str) else value
    except Exception:
        return 0
    return len(decoded) if isinstance(decoded, list) else 0


def _money(row: Mapping[str, Any]) -> str:
    for key in ("price", "price_usd", "price_uah", "sale_price", "price_final"):
        value = row.get(key)
        if value not in (None, "", 0, "0"):
            try:
                return ("{:,.0f} $".format(float(value))).replace(",", " ")
            except (TypeError, ValueError):
                continue
    return "Цена по запросу"


def _title(row: Mapping[str, Any]) -> str:
    result = " ".join(
        str(row.get(key) or "").strip()
        for key in ("brand", "model", "year")
        if str(row.get(key) or "").strip()
    )
    return result or str(row.get("auto_number") or "")


def _specs(row: Mapping[str, Any]) -> str:
    mileage = row.get("mileage_km") or row.get("mileage") or "—"
    engine = row.get("engine_cc") or row.get("engine") or "—"
    return "%s км · %s см³ · %s · %s" % (
        mileage,
        engine,
        row.get("fuel") or "—",
        row.get("gearbox") or "—",
    )


def _parse_date(value: Any) -> dt.date | None:
    text = str(value or "").strip()[:10]
    for pattern in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return dt.datetime.strptime(text, pattern).date()
        except ValueError:
            pass
    return None


def _eta(row: Mapping[str, Any], stage: int) -> tuple[str, str]:
    if stage == 2:
        target = _parse_date(row.get("eta_manual"))
        shipped = _parse_date(row.get("sea_date_out"))
        if target is None and shipped is not None:
            target = shipped + dt.timedelta(days=75)
        if target is None:
            return ("Срок до Киева уточняется", "Строк до Києва уточнюється")
        days = max((target - dt.datetime.now(dt.timezone.utc).date()).days, 0)
        return ("%d дней до Киева" % days, "%d днів до Києва" % days)
    if stage == 3:
        return (
            "15 дней до Киева считаются от фактического перехода в этап 3",
            "15 днів до Києва рахуються від фактичного переходу на етап 3",
        )
    return ("", "")


def _article_spans(source: str) -> list[CardSpan]:
    result: list[CardSpan] = []
    for match in ARTICLE_RE.finditer(source):
        identifiers = CARD_ID_RE.findall(match.group(0))
        if not identifiers:
            raise CatalogDesignError("CARD_IDENTIFIER_MISSING")
        result.append(
            CardSpan(match.start(), match.end(), identifiers[0].upper(), match.group(0))
        )
    return result


def _set_attribute(tag: str, name: str, value: str) -> str:
    pattern = re.compile(r"\s+" + re.escape(name) + r'\s*=\s*(["\']).*?\1', re.I | re.S)
    tag = pattern.sub("", tag)
    if not tag.endswith(">"):
        raise CatalogDesignError("HTML_TAG_INVALID:" + name)
    return tag[:-1] + ' %s="%s">' % (name, _esc(value))


def _patch_opening(block: str, stage: int) -> str:
    match = re.match(r"<article\b[^>]*>", block, re.I | re.S)
    if not match:
        raise CatalogDesignError("ARTICLE_OPENING_MISSING")
    opening = match.group(0)
    opening = _set_attribute(opening, "data-stage", STAGE_KEYS[stage])
    opening = _set_attribute(opening, "data-ua-stage", str(stage))
    return opening + block[match.end():]


def _replace_tag_text(
    source: str, pattern: str, text: str, error: str, flags: int = re.I | re.S
) -> str:
    compiled = re.compile(pattern, flags)
    if not compiled.search(source):
        raise CatalogDesignError(error)
    return compiled.sub(lambda m: m.group(1) + _esc(text) + m.group(3), source, count=1)


def _vin_block(row: Mapping[str, Any], stage: int) -> str:
    identifier = str(row.get("auto_number") or "").upper()
    vin = str(row.get("vin") or "VIN НЕ УКАЗАН").upper()
    photos = _media_count(row.get("photos"))
    videos = _media_count(row.get("videos"))
    media = []
    if photos:
        media.append("Фото: %d" % photos)
    if videos:
        media.append("Видео: %d" % videos)
    eta_ru, eta_uk = _eta(row, stage)
    eta = ""
    if eta_ru or eta_uk:
        eta = (
            '<div class="ua-cat-vin-v1-copy">'
            '<span class="ua068-ru">%s</span><span class="ua068-uk">%s</span></div>'
            % (_esc(eta_ru), _esc(eta_uk))
        )
    return (
        CAT_START
        + '<div class="ua-cat-vin-v1" data-ua-card="%s" '
        'data-ua-stage-tile="%d" data-category="%s">'
        '<div class="ua-cat-vin-v1-top"><span>VIN <b>%s</b></span>'
        '<i class="%s">%s</i></div>'
        '<div class="ua-cat-vin-v1-spec">%s</div>%s</div>'
        % (
            _esc(identifier),
            stage,
            _esc({1: "korea", 2: "more", 3: "gruzia", 4: "kiev"}[stage]),
            _esc(vin),
            "ok" if row.get("vin") else "warn",
            "VIN ПРОВЕРЕН" if row.get("vin") else "VIN УТОЧНЯЕТСЯ",
            _esc(" · ".join(media) or "Медиа готовятся"),
            eta,
        )
        + CAT_END
    )


def render_card(
    prototype: str, row: Mapping[str, Any], photo_url: str
) -> str:
    identifier = str(row.get("auto_number") or "").strip().upper()
    if not re.fullmatch(r"UA-[0-9]{4,}", identifier):
        raise CatalogDesignError("INVALID_IDENTIFIER:" + identifier)
    if not photo_url:
        raise CatalogDesignError("MAIN_PHOTO_MISSING:" + identifier)
    stage = stage_number(row)
    old_ids = set(value.upper() for value in CARD_ID_RE.findall(prototype))
    if not old_ids:
        raise CatalogDesignError("PROTOTYPE_IDENTIFIER_MISSING")
    block = prototype
    for old in sorted(old_ids, key=len, reverse=True):
        block = re.sub(re.escape(old), identifier, block, flags=re.I)
    block = _patch_opening(block, stage)

    # The approved article structure is retained; only its dynamic fields change.
    photo_anchor = re.compile(
        r'(<a\b(?=[^>]*\bclass\s*=\s*["\'][^"\']*\bcatalog-photo\b)[^>]*>)',
        re.I | re.S,
    )
    match = photo_anchor.search(block)
    if not match:
        raise CatalogDesignError("CATALOG_PHOTO_ANCHOR_MISSING:" + identifier)
    tag = _set_attribute(match.group(1), "href", identifier + ".html")
    block = block[:match.start(1)] + tag + block[match.end(1):]

    image = re.compile(
        r'(<img\b(?=[^>]*\bsrc\s*=)[^>]*>)', re.I | re.S
    )
    image_match = image.search(block, match.start())
    if not image_match:
        raise CatalogDesignError("CATALOG_IMAGE_MISSING:" + identifier)
    image_tag = _set_attribute(image_match.group(1), "src", photo_url)
    image_tag = _set_attribute(image_tag, "alt", _title(row))
    block = block[:image_match.start(1)] + image_tag + block[image_match.end(1):]

    block = _replace_tag_text(
        block,
        r'(<span\b[^>]*class=["\'][^"\']*\bphoto-count\b[^"\']*["\'][^>]*>)(.*?)(</span\s*>)',
        "%d фото" % _media_count(row.get("photos")),
        "PHOTO_COUNT_MISSING:" + identifier,
    )
    block = _replace_tag_text(
        block,
        r'(<div\b[^>]*class=["\'][^"\']*\bcatalog-top\b[^"\']*["\'][^>]*>\s*<span\b[^>]*>)(.*?)(</span\s*>)',
        identifier,
        "CATALOG_CODE_MISSING:" + identifier,
    )

    price = _money(row)
    price_re = re.compile(
        r'(<div\b[^>]*class=["\'][^"\']*\bcatalog-top\b[^"\']*["\'][^>]*>.*?<b\b[^>]*>)(.*?)(</b\s*>)',
        re.I | re.S,
    )
    price_match = price_re.search(block)
    if not price_match:
        raise CatalogDesignError("CATALOG_PRICE_MISSING:" + identifier)
    price_tag_match = re.search(r"<b\b[^>]*>", price_match.group(1), re.I | re.S)
    prefix = price_match.group(1)
    if price_tag_match:
        old_tag = price_tag_match.group(0)
        new_tag = _set_attribute(_set_attribute(old_tag, "data-ru", price), "data-uk", price)
        prefix = prefix[:price_tag_match.start()] + new_tag + prefix[price_tag_match.end():]
    block = (
        block[:price_match.start()]
        + prefix
        + _esc(price)
        + price_match.group(3)
        + block[price_match.end():]
    )

    block = _replace_tag_text(
        block, r"(<h2\b[^>]*>)(.*?)(</h2\s*>)", _title(row),
        "CATALOG_TITLE_MISSING:" + identifier,
    )

    label_ru, label_uk = PUBLIC_LABELS[stage]
    status_re = re.compile(
        r'(<div\b[^>]*class=["\'][^"\']*\bstatus-pill\b[^"\']*["\'][^>]*>)(.*?)(</div\s*>)',
        re.I | re.S,
    )
    status_match = status_re.search(block)
    if not status_match:
        raise CatalogDesignError("CATALOG_STATUS_MISSING:" + identifier)
    status_tag = status_match.group(1)
    status_tag = _set_attribute(status_tag, "data-ru", label_ru)
    status_tag = _set_attribute(status_tag, "data-uk", label_uk)
    block = (
        block[:status_match.start()]
        + status_tag
        + _esc(label_ru)
        + status_match.group(3)
        + block[status_match.end():]
    )

    # The first plain paragraph after the status is the approved specification line.
    status_end = status_match.start() + len(status_tag) + len(_esc(label_ru)) + len(status_match.group(3))
    spec_re = re.compile(r"(<p\b[^>]*>)(.*?)(</p\s*>)", re.I | re.S)
    spec_match = spec_re.search(block, status_end)
    if not spec_match:
        raise CatalogDesignError("CATALOG_SPECS_MISSING:" + identifier)
    block = (
        block[:spec_match.start()]
        + spec_match.group(1)
        + _esc(_specs(row))
        + spec_match.group(3)
        + block[spec_match.end():]
    )

    canonical = re.compile(re.escape(CAT_START) + r".*?" + re.escape(CAT_END), re.S)
    if canonical.search(block):
        block = canonical.sub(_vin_block(row, stage), block, count=1)
    else:
        arrow = re.search(
            r'<a\b(?=[^>]*\bclass\s*=\s*["\'][^"\']*\bcard-arrow\b)',
            block, re.I,
        )
        if not arrow:
            raise CatalogDesignError("CATALOG_VIN_INSERTION_MISSING:" + identifier)
        block = block[:arrow.start()] + _vin_block(row, stage) + block[arrow.start():]

    arrow_re = re.compile(
        r'(<a\b(?=[^>]*\bclass\s*=\s*["\'][^"\']*\bcard-arrow\b)[^>]*>)',
        re.I | re.S,
    )
    arrow_match = arrow_re.search(block)
    if not arrow_match:
        raise CatalogDesignError("CATALOG_ARROW_MISSING:" + identifier)
    arrow_tag = _set_attribute(arrow_match.group(1), "href", identifier + ".html")
    block = block[:arrow_match.start(1)] + arrow_tag + block[arrow_match.end(1):]
    return block


def _normalize_shell(source: str) -> str:
    spans = _article_spans(source)
    if spans:
        source = source[:spans[0].start] + "<!--UA090:CARD-REGION-->" + source[spans[-1].end:]
    replacements = (
        (r"(?i)(Все|Усі)\s*·\s*\d+", r"\1 · #"),
        (r"(?i)(В Киеве|У Києві)\s*·\s*\d+", r"\1 · #"),
        (r"(?i)(В Грузии|У Грузії)\s*·\s*\d+", r"\1 · #"),
        (r"(?i)(На пароме|На поромі)\s*·\s*\d+", r"\1 · #"),
        (r"(?i)(В Корее|У Кореї)\s*·\s*\d+", r"\1 · #"),
        (r"(?i)(Показано\s*:?\s*)\d+", r"\1#"),
        (r"(?i)(\d+)\s+в подборке", "# в подборке"),
        (r"(?i)(\d+)\s+у добірці", "# у добірці"),
        (r"([?&](?:v|ver|version|ts|t)=)\d+", r"\1#"),
    )
    for pattern, replacement in replacements:
        source = re.sub(pattern, replacement, source)
    return re.sub(r"\s+", " ", source).strip()


def shell_fingerprint(source: str) -> str:
    return _sha(_normalize_shell(source))


def shell_audit(source: str, require_cards: bool = True) -> dict[str, Any]:
    errors: list[str] = []
    if not re.search(r"<nav\b", source, re.I):
        errors.append("NAV_MISSING")
    filter_counts = {
        key: len(re.findall(r'data-f\s*=\s*["\']' + re.escape(key) + r'["\']', source, re.I))
        for key in FILTER_ORDER
    }
    if filter_counts != {key: 1 for key in FILTER_ORDER}:
        errors.append("FILTERS_INVALID")
    if not re.search(r"catalog-result", source, re.I):
        errors.append("CATALOG_RESULT_MISSING")
    if not re.search(r'(?:data-lang\s*=\s*["\']ru|setLang\s*\(\s*["\']ru)', source, re.I):
        errors.append("RU_CONTROL_MISSING")
    if not re.search(r'(?:data-lang\s*=\s*["\'](?:uk|ua)|setLang\s*\(\s*["\'](?:uk|ua))', source, re.I):
        errors.append("UK_CONTROL_MISSING")
    if not re.search(r"<footer\b", source, re.I):
        errors.append("FOOTER_MISSING")
    if not re.search(r"(?:wa\.me|whatsapp)", source, re.I):
        errors.append("WHATSAPP_MISSING")
    cards = _article_spans(source)
    if require_cards and not cards:
        errors.append("APPROVED_CARDS_MISSING")
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "filter_counts": filter_counts,
        "article_cards": len(cards),
        "fingerprint": shell_fingerprint(source) if cards else None,
    }


def _update_counters(source: str, counts: Mapping[str, int]) -> str:
    total = counts["all"]
    pairs = (
        (r"Все\s*·\s*\d+", "Все · %d" % total),
        (r"Усі\s*·\s*\d+", "Усі · %d" % total),
        (r"В Киеве\s*·\s*\d+", "В Киеве · %d" % counts["kiev"]),
        (r"У Києві\s*·\s*\d+", "У Києві · %d" % counts["kiev"]),
        (r"В Грузии\s*·\s*\d+", "В Грузии · %d" % counts["georgia"]),
        (r"У Грузії\s*·\s*\d+", "У Грузії · %d" % counts["georgia"]),
        (r"На пароме\s*·\s*\d+", "На пароме · %d" % counts["sea"]),
        (r"На поромі\s*·\s*\d+", "На поромі · %d" % counts["sea"]),
        (r"В Корее\s*·\s*\d+", "В Корее · %d" % counts["korea"]),
        (r"У Кореї\s*·\s*\d+", "У Кореї · %d" % counts["korea"]),
        (r"Показано\s*:?\s*\d+", "Показано: %d" % total),
        (r"\d+\s+в подборке", "%d в подборке" % total),
        (r"\d+\s+у добірці", "%d у добірці" % total),
    )
    for pattern, replacement in pairs:
        source = re.sub(pattern, replacement, source, flags=re.I)
    return source


def _rows_by_id(rows: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for original in rows:
        row = dict(original)
        try:
            published = int(row.get("published") or 0)
        except (TypeError, ValueError):
            published = 0
        if published != 1:
            continue
        identifier = str(row.get("auto_number") or "").strip().upper()
        if not re.fullmatch(r"UA-[0-9]{4,}", identifier):
            raise CatalogDesignError("INVALID_PUBLISHED_IDENTIFIER:" + identifier)
        if identifier in result:
            raise CatalogDesignError("DUPLICATE_PUBLISHED_IDENTIFIER:" + identifier)
        stage_number(row)
        result[identifier] = row
    if not result:
        raise CatalogDesignError("NO_PUBLISHED_ROWS")
    return result


def build_catalog(
    golden: str,
    rows: Iterable[Mapping[str, Any]],
    photos: Mapping[str, str],
) -> str:
    baseline_audit = shell_audit(golden)
    if baseline_audit["status"] != "PASS":
        raise CatalogDesignError("GOLDEN_SHELL_INVALID:" + ",".join(baseline_audit["errors"]))
    baseline_spans = _article_spans(golden)
    by_identifier = {span.identifier: span for span in baseline_spans}
    prototypes_by_stage: dict[int, str] = {}
    for span in baseline_spans:
        match = re.search(r'data-stage\s*=\s*["\'](korea|sea|georgia|kiev)["\']', span.source, re.I)
        if match:
            reverse = {value: key for key, value in STAGE_KEYS.items()}
            prototypes_by_stage.setdefault(reverse[match.group(1).casefold()], span.source)
    fallback = baseline_spans[0].source

    row_map = _rows_by_id(rows)
    baseline_order = {span.identifier: index for index, span in enumerate(baseline_spans)}
    ordered = sorted(
        row_map,
        key=lambda identifier: (
            -stage_number(row_map[identifier]),
            baseline_order.get(identifier, 100000),
            identifier,
        ),
    )
    cards: list[str] = []
    for identifier in ordered:
        row = row_map[identifier]
        stage = stage_number(row)
        prototype = by_identifier.get(identifier)
        prototype_source = prototype.source if prototype else prototypes_by_stage.get(stage, fallback)
        cards.append(render_card(prototype_source, row, str(photos.get(identifier) or "")))

    generated = (
        golden[:baseline_spans[0].start]
        + "\n".join(cards)
        + golden[baseline_spans[-1].end:]
    )
    counts = {"all": len(row_map), "kiev": 0, "georgia": 0, "sea": 0, "korea": 0}
    for row in row_map.values():
        counts[STAGE_KEYS[stage_number(row)]] += 1
    generated = _update_counters(generated, counts)

    if shell_fingerprint(generated) != shell_fingerprint(golden):
        raise CatalogDesignError("IMMUTABLE_SHELL_FINGERPRINT_CHANGED")
    audit = audit_catalog(generated, list(row_map.values()), golden)
    if audit["status"] != "PASS":
        raise CatalogDesignError("GENERATED_CATALOG_INVALID:" + ",".join(audit["errors"]))
    return generated


def audit_catalog(
    source: str,
    rows: Iterable[Mapping[str, Any]],
    golden: str | None = None,
) -> dict[str, Any]:
    row_map = _rows_by_id(rows)
    errors: list[str] = []
    shell = shell_audit(source)
    errors.extend(shell["errors"])
    spans = _article_spans(source)
    found = [span.identifier for span in spans]
    if len(found) != len(set(found)):
        errors.append("DUPLICATE_CARD")
    if set(found) != set(row_map):
        errors.append("CARD_SET_MISMATCH")
    counts = {"all": len(found), "kiev": 0, "georgia": 0, "sea": 0, "korea": 0}
    for span in spans:
        expected = STAGE_KEYS[stage_number(row_map[span.identifier])] if span.identifier in row_map else None
        match = re.search(r'data-stage\s*=\s*["\']([^"\']+)["\']', span.source, re.I)
        actual = match.group(1).casefold() if match else None
        if actual != expected:
            errors.append("CARD_STAGE_MISMATCH:" + span.identifier)
        if actual in counts:
            counts[actual] += 1
        if span.source.count(CAT_START) != 1 or span.source.count(CAT_END) != 1:
            errors.append("VIN_BLOCK_COUNT:" + span.identifier)
        hrefs = re.findall(
            r'href\s*=\s*["\'](?:[^"\']*/)?' + re.escape(span.identifier)
            + r'\.html(?:\?[^"\']*)?["\']',
            span.source, re.I,
        )
        if len(hrefs) != 2:  # photo link + approved arrow link
            errors.append("CARD_LINK_COUNT:" + span.identifier)
    if golden is not None and shell_fingerprint(source) != shell_fingerprint(golden):
        errors.append("SHELL_FINGERPRINT_MISMATCH")
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "ids": found,
        "counts": counts,
        "article_cards": len(spans),
        "filters": shell["filter_counts"],
        "shell_fingerprint": shell_fingerprint(source) if spans else None,
    }


def assert_live_acceptance(
    source: str, rows: Iterable[Mapping[str, Any]], golden: str
) -> dict[str, Any]:
    audit = audit_catalog(source, rows, golden)
    errors = list(audit["errors"])
    if tuple(sorted(audit["ids"])) != EXPECTED_IDS:
        errors.append("CURRENT_13_IDS_INVALID")
    if audit["counts"] != EXPECTED_STAGE_COUNTS:
        errors.append("CURRENT_STAGE_COUNTS_INVALID")
    audit["errors"] = errors
    audit["status"] = "PASS" if not errors else "FAIL"
    if errors:
        raise CatalogDesignError("LIVE_ACCEPTANCE_FAIL:" + ",".join(errors))
    return audit


def extract_main_photo(page: str, identifier: str) -> str:
    candidates = []
    patterns = (
        r'<img\b(?=[^>]*\bdata-mcf-foto\s*=\s*["\']1["\'])[^>]*\bsrc\s*=\s*["\']([^"\']+)["\']',
        r'<meta\b(?=[^>]*\bproperty\s*=\s*["\']og:image["\'])[^>]*\bcontent\s*=\s*["\']([^"\']+)["\']',
        r'<img\b[^>]*\bsrc\s*=\s*["\']([^"\']+)["\']',
    )
    for pattern in patterns:
        candidates.extend(re.findall(pattern, page, re.I | re.S))
        if candidates:
            break
    for value in candidates:
        cleaned = html.unescape(value).strip()
        if re.search(r"\.(?:avif|jpe?g|png|webp)(?:[?#].*)?$", cleaned, re.I):
            return cleaned
    # The approved stage image is deterministic and remains a safe final source.
    fallback = "/video/stage/%s.webp" % identifier
    return fallback


def build_from_golden_path(
    rows: Iterable[Mapping[str, Any]],
    photos: Mapping[str, str],
    golden_path: pathlib.Path | str = GOLDEN_PATH,
) -> str:
    path = pathlib.Path(golden_path)
    if not path.is_file():
        raise CatalogDesignError("GOLDEN_FILE_MISSING:" + str(path))
    return build_catalog(path.read_text(encoding="utf-8"), rows, photos)


__all__ = [
    "CONTRACT_ID",
    "CatalogDesignError",
    "EXPECTED_IDS",
    "EXPECTED_STAGE_COUNTS",
    "GOLDEN_PATH",
    "assert_live_acceptance",
    "audit_catalog",
    "build_catalog",
    "build_from_golden_path",
    "extract_main_photo",
    "shell_audit",
    "shell_fingerprint",
    "stage_number",
]

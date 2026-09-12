"""Deterministic, script-free additional specifications and guarded composition.

Pure functions only. Never writes files, imports CRM, or performs network I/O.
"""
from __future__ import annotations

import hashlib
import html
import json
import math
import re
from urllib.parse import urlsplit

from . import shell_guard

START, END = shell_guard.SPEC_MARKERS
PINNED_SHELL_ASSETS_SHA256 = "a6a0fe686687ca04c00e697a72ee4a07957ac0afa96d37d53a9ff0146b0868ed"
BAD_TEXT = re.compile(r"[<>]|https?://|www\.|javascript:|data:|carhistory|vindecoderz|affiliate", re.I)
PRICE = re.compile(r"price|cost|auction|advert|ц[еі]на|стоимость|вартість|реклам|₩|\$|€", re.I)
VERIFIED = {"VERIFIED", "VERIFIED_10SRC", "MANUAL_VERIFIED", "TRUSTED", "MANUAL", "CURATED_PASS",
            "MODEL_VERIFIED", "VEHICLE_VERIFIED"}
KEY_RE = re.compile(r"[A-Za-z0-9_.:-]{1,120}\Z")

GROUPS = {
    "engine": ("Двигун", "Двигатель"),
    "dynamics": ("Динаміка", "Динамика"),
    "consumption": ("Витрата пального", "Расход топлива"),
    "dimensions": ("Розміри", "Размеры"),
    "capacity": ("Місткість", "Вместимость"),
    "weight": ("Маса", "Масса"),
    "suspension": ("Підвіска", "Подвеска"),
    "brakes": ("Гальма", "Тормоза"),
    "steering": ("Кермове керування", "Рулевое управление"),
    "wheels": ("Колеса", "Колёса"),
    "ecology": ("Екологія", "Экология"),
    "transmission_detail": ("Трансмісія", "Трансмиссия"),
    "additional": ("Інші характеристики", "Другие характеристики"),
}

UK_LABELS = {
    "doors": "Кількість дверей", "seats": "Кількість місць",
    "urban_fuel_consumption": "Витрата в місті", "highway_fuel_consumption": "Витрата на трасі",
    "combined_fuel_consumption": "Змішана витрата", "urban_fuel_economy": "Економічність у місті",
    "highway_fuel_economy": "Економічність на трасі", "combined_fuel_economy": "Змішана економічність",
    "co2_emissions": "Викиди CO₂", "emission_standard": "Екологічний стандарт",
    "energy_efficiency_class": "Клас енергоефективності", "acceleration_0_100": "Розгін 0–100 км/год",
    "maximum_speed": "Максимальна швидкість", "maximum_power": "Максимальна потужність",
    "specific_power": "Питома потужність", "maximum_torque": "Максимальний крутний момент",
    "engine_layout": "Розташування двигуна", "engine_code": "Код двигуна",
    "cylinders": "Кількість циліндрів", "engine_configuration": "Конфігурація двигуна",
    "cylinder_bore": "Діаметр циліндра", "piston_stroke": "Хід поршня",
    "compression_ratio": "Ступінь стиснення", "valves_per_cylinder": "Клапанів на циліндр",
    "fuel_injection": "Система впорскування", "aspiration": "Тип наддуву",
    "valvetrain": "Газорозподільний механізм", "engine_oil_capacity": "Об’єм оливи",
    "coolant_capacity": "Об’єм охолоджувальної рідини", "kerb_weight": "Споряджена маса",
    "gross_weight": "Допустима повна маса", "payload": "Вантажопідйомність",
    "boot_capacity": "Об’єм багажника", "boot_capacity_maximum": "Максимальний об’єм багажника",
    "fuel_tank_capacity": "Об’єм паливного бака", "length": "Довжина", "width": "Ширина",
    "height": "Висота", "wheelbase": "Колісна база", "front_track": "Передня колія",
    "rear_track": "Задня колія", "ground_clearance": "Дорожній просвіт",
    "drag_coefficient": "Коефіцієнт аеродинамічного опору", "turning_circle": "Діаметр розвороту",
    "number_of_gears": "Кількість передач", "front_suspension": "Передня підвіска",
    "rear_suspension": "Задня підвіска", "front_brakes": "Передні гальма",
    "rear_brakes": "Задні гальма", "steering_type": "Кермове керування",
    "power_steering": "Підсилювач керма", "tyre_size": "Розмір шин", "wheel_size": "Розмір дисків",
}


class SpecError(RuntimeError):
    """Publication guard failure; retain the last published page."""


def _uid(value):
    if not isinstance(value, str) or not shell_guard.UID.fullmatch(value):
        raise SpecError("INVALID_CARD_UID")
    return value


def _language(lang):
    if lang == "ua":
        lang = "uk"
    if lang not in {"uk", "ru"}:
        raise SpecError("UNSUPPORTED_SPECIFICATION_LANGUAGE")
    return lang


def _text(value, maximum=500):
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        raise SpecError("INVALID_SPECIFICATION_TEXT_TYPE")
    if isinstance(value, float) and not math.isfinite(value):
        raise SpecError("INVALID_SPECIFICATION_NUMBER")
    value = re.sub(r"\s+", " ", str(value)).strip()
    if (not value or len(value) > maximum or BAD_TEXT.search(value)
            or PRICE.search(value) or shell_guard.VIN.search(value)
            or any(ord(c) < 32 for c in value)):
        raise SpecError("UNSAFE_SPECIFICATION_TEXT")
    return value


def _flag(value):
    if value not in (0, 1, "0", "1", False, True):
        raise SpecError("INVALID_SPECIFICATION_FLAG")
    return str(value).lower() not in {"0", "false"}


def _provenance(fact):
    """Render only approved links; legacy citations remain plain historic text.

    The registry owns host/source matching. A URL on an unapproved domain is
    never a link and never appears as raw text or in an HTML attribute.
    """
    source_id = fact.get("source_id")
    raw_url = fact.get("source_url")
    source = fact.get("source")
    if not source_id and not raw_url and not source:
        return None
    # Source metadata does not become an HTML escape hatch, even when historic.
    if source_id:
        source_id = _text(source_id, 100)
    if raw_url:
        if not isinstance(raw_url, str) or len(raw_url) > 2048 or any(c in raw_url for c in '<>"\'\r\n\t\\'):
            raise SpecError("UNSAFE_SOURCE_URL")
        try:
            parsed = urlsplit(raw_url)
            port = parsed.port
        except ValueError as exc:
            raise SpecError("UNSAFE_SOURCE_URL") from exc
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.fragment or port not in {None, 443}):
            raise SpecError("UNSAFE_SOURCE_URL")
        if any(x in raw_url.lower() for x in ("affiliate", "javascript:", "utm_", "clickid=", "ref=", "referrer=")):
            raise SpecError("SOURCE_TRACKING_FORBIDDEN")
    from .sources import SourceError, load_registry, validate_source_url
    registry = load_registry()
    record = registry.get(source_id) if source_id else None
    if record is None:
        # Original source names can themselves be URLs in legacy records.
        # Use a neutral historical label rather than importing that content.
        return {"kind": "historical", "url": "", "name": ""}
    if not raw_url:
        return {"kind": "approved", "url": "", "name": record.name}
    try:
        safe_url = validate_source_url(source_id, raw_url, registry=registry)
    except SourceError as exc:
        raise SpecError("SOURCE_URL_NOT_APPROVED") from exc
    return {"kind": "approved", "url": safe_url, "name": _text(record.name, 160)}


def normalize_facts(facts):
    """Support canonical and preserved legacy field records without HTML data."""
    result = {}
    for fact in facts:
        if not isinstance(fact, dict):
            raise SpecError("INVALID_SPECIFICATION_RECORD")
        if not _flag(fact.get("is_visible", 0 if fact.get("hidden") else 1)):
            continue
        if _flag(fact.get("is_price_field", 0)):
            raise SpecError("PRICE_FIELD_FORBIDDEN")
        state = fact.get("verification_status")
        if state is None:
            verification = fact.get("verification")
            if (fact.get("manual") is True or fact.get("is_manual") == 1) and verification == "manual":
                state = "MANUAL_VERIFIED"
            elif verification is True or verification in {"verified", "confirmed", "official"}:
                state = "VERIFIED"
            elif (isinstance(fact.get("legacy_import"), dict)
                    and fact["legacy_import"].get("receipt_id")
                    and fact["legacy_import"].get("fresh_verification") is False):
                state = "VERIFIED"
        state = str(state or "UNVERIFIED").upper()
        if state not in VERIFIED:
            continue
        key = fact.get("key", fact.get("field_key"))
        if (not isinstance(key, str) or not KEY_RE.fullmatch(key)
                or key.casefold() in {"vin", "vin_code", "chassis_number"}):
            raise SpecError("INVALID_SPECIFICATION_KEY")
        label_ru = _text(fact.get("label_ru", fact.get("label", key)), 160)
        label_uk = _text(fact.get("label_uk", fact.get("label_ua", UK_LABELS.get(key, label_ru))), 160)
        raw_value = fact.get("value", fact.get("field_value", fact.get("display_value")))
        is_boolean = isinstance(raw_value, bool)
        value = ("Так" if raw_value else "Ні") if is_boolean else _text(raw_value)
        unit = fact.get("unit") or ""
        if unit:
            if is_boolean:
                raise SpecError("BOOLEAN_SPECIFICATION_UNIT_FORBIDDEN")
            unit = _text(unit, 50)
            if not value.endswith(unit):
                value += " " + unit
        category = fact.get("category") or "additional"
        if category not in GROUPS:
            category = "additional"
        row = {"key": key, "label_ru": label_ru, "label_uk": label_uk,
               "value": value, "category": category, "provenance": _provenance(fact)}
        if is_boolean:
            row["value_ru"] = "Да" if raw_value else "Нет"
        if key in result and result[key] != row:
            raise SpecError("CONFLICTING_SPECIFICATION_KEY:" + key)
        result[key] = row
    rows = sorted(result.values(), key=lambda r: (list(GROUPS).index(r["category"]), r["key"]))
    if not rows:
        raise SpecError("NO_VERIFIED_VISIBLE_SPECIFICATION")
    return rows


def _digest(rows):
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


def facts_digest(facts):
    """Digest exactly the normalized visible render payload for a change manifest."""
    return _digest(normalize_facts(facts))


def _i18n(uk, ru, lang):
    return '<span data-ua="%s" data-uk="%s" data-ru="%s">%s</span>' % (
        html.escape(uk, quote=True), html.escape(uk, quote=True),
        html.escape(ru, quote=True), html.escape(ru if lang == "ru" else uk))


def _source_details(source, lang):
    if not source:
        return ""
    if source["kind"] == "historical":
        text = _i18n("Збережене джерело попередньої версії", "Сохранённый источник предыдущей версии", lang)
    else:
        text = html.escape(source["name"])
        if source["url"]:
            text = '<a href="%s" rel="noopener noreferrer">%s</a>' % (html.escape(source["url"], quote=True), text)
    return '<details class="ua-rb10-source"><summary>%s</summary><p>%s</p></details>' % (
        _i18n("Джерело характеристики", "Источник характеристики", lang), text)


STYLE = (
    '<style id="ua-spec-rebuild10-style">'
    '.ua-rb10-link{display:block!important;visibility:visible!important;min-height:44px;box-sizing:border-box;'
    'padding:14px 16px;margin:16px 0 10px;border:1px solid #c79848;border-radius:14px;'
    'color:#e6b864;font-weight:700;text-decoration:underline;text-underline-offset:3px}'
    '.ua-rb10{display:block!important;visibility:visible!important;border:1px solid #c79848;'
    'border-radius:14px;margin:0 0 18px;padding:16px;scroll-margin-top:20px;overflow-wrap:anywhere}'
    '.ua-rb10 h2{font-size:20px;margin:0 0 14px}.ua-rb10 h3{color:#e6b864;font-size:16px;margin:18px 0 8px}'
    '.ua-rb10 dl{margin:0}.ua-rb10-row{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);'
    'gap:10px;border-top:1px solid #ffffff20;padding:9px 0}.ua-rb10 dt,.ua-rb10 dd{margin:0}'
    '.ua-rb10 dd{text-align:right;font-weight:600}.ua-rb10-source{font-size:12px;font-weight:400;margin-top:6px}'
    '.ua-rb10-source summary{cursor:pointer;text-decoration:underline;list-style:revert}'
    '.ua-rb10-source p{margin:6px 0}.ua-rb10-source a{color:inherit;overflow-wrap:anywhere}'
    '.ua-rb10 a:focus-visible,.ua-rb10 summary:focus-visible,.ua-rb10-link:focus-visible'
    '{outline:2px solid #e6b864;outline-offset:3px}'
    '@media(max-width:560px){.ua-rb10-row{grid-template-columns:1fr;gap:4px}.ua-rb10 dd{text-align:left}}'
    '</style>'
)


def render_block(uid, facts, lang="uk"):
    """Return one owned block with a visible link and an always-expanded section."""
    uid, lang = _uid(uid), _language(lang)
    rows = normalize_facts(facts)
    groups = []
    for category, titles in GROUPS.items():
        items = [r for r in rows if r["category"] == category]
        if not items:
            continue
        body = "".join('<div class="ua-rb10-row" data-spec-key="%s"><dt>%s</dt><dd>%s%s</dd></div>' % (
            html.escape(r["key"], quote=True), _i18n(r["label_uk"], r["label_ru"], lang),
            _i18n(r["value"], r["value_ru"], lang) if "value_ru" in r else html.escape(r["value"]),
            _source_details(r["provenance"], lang)) for r in items)
        groups.append('<section class="ua-rb10-group"><h3>%s</h3><dl>%s</dl></section>' % (
            _i18n(*titles, lang), body))
    return (START + STYLE + '<a class="ua-rb10-link" href="#additional-specification">%s</a>'
            '<section id="additional-specification" class="blok ua-rb10" data-ua-additional-spec="1" '
            'data-spec-card="%s" data-spec-version="%s" aria-labelledby="additional-specification-title">'
            '<h2 id="additional-specification-title">%s</h2>%s</section>' + END) % (
                _i18n("Додаткова специфікація →", "Дополнительная спецификация →", lang), uid, _digest(rows),
                _i18n("Додаткова специфікація", "Дополнительная спецификация", lang), "".join(groups))


def _span(source):
    if not isinstance(source, str) or len(source.encode("utf-8")) > 4 * 1024 * 1024:
        raise SpecError("INVALID_HTML_INPUT")
    try:
        page = shell_guard._Page(source)
        span = shell_guard._marked_span(page, (START, END))
    except shell_guard.ShellError as exc:
        raise SpecError(str(exc)) from exc
    # Raw marker-looking strings in scripts/attributes are ambiguous as well.
    if source.count(START) != (1 if span else 0) or source.count(END) != (1 if span else 0):
        raise SpecError("AMBIGUOUS_SPECIFICATION_MARKERS")
    for node in page.nodes:
        own = (node.attrs.get("id") in {"additional-specification", "additional-specification-title"}
               or "data-ua-additional-spec" in node.attrs
               or "ua-additional-spec" in (node.attrs.get("class") or "").split())
        if own and (not span or node.start < span[2] or node.end > span[3]):
            raise SpecError("UNMARKED_SPECIFICATION_REQUIRES_REVIEW")
    if span:
        fragment = source[span[2]:span[3]]
        inner = shell_guard._Page(fragment)
        roots = shell_guard._children(inner.root)
        for node in roots:
            if not isinstance(node, shell_guard._Node):
                raise SpecError("UNKNOWN_SPECIFICATION_MARKUP")
            is_style = node.tag == "style" and node.attrs.get("id") in {"ua-spec-auto10-style", "ua-spec-rebuild10-style"}
            is_old = node.tag == "details" and "ua-additional-spec" in (node.attrs.get("class") or "").split()
            is_link = node.tag == "a" and node.attrs.get("class") == "ua-rb10-link"
            is_section = node.tag == "section" and node.attrs.get("id") == "additional-specification"
            if not node.closed or node.duplicate_attrs or not (is_style or is_old or is_link or is_section):
                raise SpecError("UNKNOWN_SPECIFICATION_MARKUP")
        if len(roots) not in {2, 3} or inner.comments:
            raise SpecError("UNKNOWN_SPECIFICATION_MARKUP")
    return None if span is None else (span[0], span[1])


def _without_block(source):
    span = _span(source)
    return source if span is None else source[:span[0]] + source[span[1]:]


def _insertion(source):
    marker = "<!-- UA-ART-DELIVERY-STAGES-PERMANENT-V1:START -->"
    page = shell_guard._Page(source)
    hits = [start for comment, start, _ in page.comments if comment == marker]
    if len(hits) != 1 or source.count(marker) != 1:
        raise SpecError("SPECIFICATION_INSERTION_ANCHOR_MISSING_OR_AMBIGUOUS")
    return hits[0]


def compose_page(original_html, uid, facts, lang="uk"):
    """Compose entirely in memory; caller must use its approved publication route."""
    uid, lang, facts = _uid(uid), _language(lang), list(facts)
    _span(original_html)
    try:
        normalized = shell_guard.normalize_html(original_html, uid)
        span = _span(normalized)
        block = render_block(uid, facts, lang)
        a, b = span if span else (_insertion(normalized),) * 2
        output = normalized[:a] + block + normalized[b:]
        validate_page(output, uid, facts, previous=original_html, lang=lang)
        return output
    except shell_guard.ShellError as exc:
        raise SpecError(str(exc)) from exc


def validate_page(source, uid, facts, previous=None, lang="uk"):
    """Prove exact fact rendering, one VIN, no lost keys, and unchanged shell."""
    uid, lang, facts = _uid(uid), _language(lang), list(facts)
    rows = normalize_facts(facts)
    span = _span(source)
    if span is None:
        raise SpecError("SPECIFICATION_BLOCK_MISSING")
    if source[span[0]:span[1]] != render_block(uid, facts, lang):
        raise SpecError("SPECIFICATION_DIFFERS_FROM_CONFIRMED_DATA")
    page = shell_guard._Page(source)
    links = [node for node in page.nodes if node.attrs.get("class") == "ua-rb10-link"]
    sections = [node for node in page.nodes if node.attrs.get("id") == "additional-specification"]
    if (len(links) != 1 or len(sections) != 1
            or not all(shell_guard._is_visible(node) for node in links + sections)):
        raise SpecError("SPECIFICATION_ANCHOR_OR_SECTION_NOT_VISIBLE")
    if re.search(r"carhistory(?:\.kr)?|vindecoderz(?:\.com)?|(?:Проверить|Перевірити)\s+VIN|2\s*200\s*KRW", source, re.I):
        raise SpecError("PUBLIC_VIN_ADVERTISEMENT_FORBIDDEN")
    if previous is not None:
        old_span = _span(previous)
        if old_span:
            old = previous[old_span[0]:old_span[1]]
            old_keys = {node.attrs["data-spec-key"] for node in shell_guard._Page(old).nodes
                        if "data-spec-key" in node.attrs}
            if old_keys - {row["key"] for row in rows}:
                raise SpecError("PREVIOUS_SPECIFICATION_KEYS_LOST")
            old_count = sum(bool({"ua-addspec-row", "ua-rb10-row"} & set((node.attrs.get("class") or "").split()))
                            for node in shell_guard._Page(old).nodes)
            if old_count > len(rows):
                raise SpecError("PREVIOUS_SPECIFICATION_ROWS_LOST")
    try:
        vin = shell_guard.validate_one_visible_vin(source, uid)
        assets = shell_guard.validate_shell_assets(previous if previous is not None else source, source)
        if previous is not None:
            delta = shell_guard.permitted_delta(previous, source, uid)
        elif assets["ordered_static_assets_sha256"] != PINNED_SHELL_ASSETS_SHA256:
            raise SpecError("UNREVIEWED_NEW_CARD_SHELL_ASSETS")
        else:
            delta = {"outside_permitted_regions_byte_changes": 0, "status": "PINNED_TEMPLATE"}
    except shell_guard.ShellError as exc:
        raise SpecError(str(exc)) from exc
    return {"status": "PASS", "rows": len(rows), "data_status": "READY", "language": lang,
            "version": _digest(rows), "visible_vin_count": vin["visible_vin_count"],
            "visible_anchor": "#additional-specification", "javascript_required": False,
            "shell_assets_sha256": assets["ordered_static_assets_sha256"], "shell_delta": delta}


def validate_authorized_card_change(before, after, uid, facts, manifest, current_row):
    """Validate one exact full-card image already authorized by the runtime.

    This does not authenticate the manifest. The runtime must verify it inside
    the active manual-operation ticket, independently bind the canonical store
    digest/revision, and retain the publication lock through commit/readback.
    There is deliberately no general "allow shell changes" switch.
    """
    uid, facts = _uid(uid), list(facts)
    if not isinstance(manifest, dict) or not isinstance(current_row, dict):
        raise SpecError("AUTHORIZED_CARD_CHANGE_MANIFEST_REQUIRED")
    required = {"uid", "plan_id", "action", "before_sha256", "after_sha256", "crm_row_sha256",
                "shell_assets_sha256", "revision", "facts_digest", "render_facts_sha256", "authorization"}
    if (set(manifest) != required or manifest["uid"] != uid or manifest["action"] != "publish"
            or manifest["authorization"] != "PASS" or not isinstance(manifest["plan_id"], str)
            or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,200}", manifest["plan_id"])
            or isinstance(manifest["revision"], bool) or not isinstance(manifest["revision"], int)
            or manifest["revision"] < 1):
        raise SpecError("AUTHORIZED_CARD_CHANGE_MANIFEST_INVALID")
    for key in required:
        if key.endswith("sha256") or key == "facts_digest":
            if not isinstance(manifest[key], str) or not re.fullmatch(r"[0-9a-f]{64}", manifest[key]):
                raise SpecError("AUTHORIZED_CARD_CHANGE_DIGEST_INVALID")
    try:
        row_hash = hashlib.sha256(json.dumps(current_row, ensure_ascii=False, sort_keys=True,
                                            separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
    except (TypeError, ValueError) as exc:
        raise SpecError("AUTHORIZED_CARD_CHANGE_ROW_INVALID") from exc
    actual = {"before_sha256": hashlib.sha256(before.encode("utf-8")).hexdigest(),
              "after_sha256": hashlib.sha256(after.encode("utf-8")).hexdigest(),
              "crm_row_sha256": row_hash, "render_facts_sha256": facts_digest(facts)}
    if any(manifest[key] != value for key, value in actual.items()):
        raise SpecError("AUTHORIZED_CARD_CHANGE_PREIMAGE_POSTIMAGE_ROW_OR_FACTS_MISMATCH")
    try:
        assets = shell_guard.validate_shell_assets(before, after)
        shell_guard.validate_one_visible_vin(before, uid)
    except shell_guard.ShellError as exc:
        raise SpecError(str(exc)) from exc
    if manifest["shell_assets_sha256"] != assets["ordered_static_assets_sha256"]:
        raise SpecError("AUTHORIZED_CARD_CHANGE_SHELL_FINGERPRINT_MISMATCH")
    # A reviewed existing preimage is the template baseline. The canonical block
    # must still validate; the exact full-card postimage is independently pinned.
    result = validate_page(after, uid, facts, previous=after)
    old_span = _span(before)
    if old_span:
        old = shell_guard._Page(before[old_span[0]:old_span[1]])
        old_keys = {node.attrs["data-spec-key"] for node in old.nodes if "data-spec-key" in node.attrs}
        if old_keys - {row["key"] for row in normalize_facts(facts)}:
            raise SpecError("PREVIOUS_SPECIFICATION_KEYS_LOST")
    return {**result, "shell_delta": {"status": "EXACT_AUTHORIZED_FULL_CARD_CHANGE",
            "before_sha256": actual["before_sha256"], "after_sha256": actual["after_sha256"],
            "crm_row_sha256": row_hash, "plan_id": manifest["plan_id"],
            "revision": manifest["revision"], "facts_digest": manifest["facts_digest"],
            "render_facts_sha256": actual["render_facts_sha256"]}}

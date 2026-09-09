"""Specification-only renderer and guarded page reconciliation.

No work happens at import. CRM data are never written. The normal publisher
and this reconciler must share the existing publication lock. Installation
and the current server paths remain subject to Gate B.
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import html
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import urllib.request
from typing import Any, Callable, Iterable

START = "<!--UA099_ADD_SPEC_START-->"
END = "<!--UA099_ADD_SPEC_END-->"
MAX_PAGE_BYTES = 4 * 1024 * 1024
UID_RE = re.compile(r"^UA-[0-9]{4,6}$")
BAD_TEXT = re.compile(r"<[^>]*>|https?://|www\.|javascript:|data:|carhistory|vindecoderz|affiliate", re.I)
PRICE = re.compile(r"price|cost|auction|advert|ц[еі]на|стоимость|вартість|реклам|₩|\$|€", re.I)
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
    pass


def uid(value: Any) -> str:
    value = str(value or "").strip().upper()
    if not UID_RE.fullmatch(value):
        raise SpecError("INVALID_CARD_ID")
    return value


def _text(value: Any, maximum: int = 500) -> str:
    value = re.sub(r"\s+", " ", str(value if value is not None else "")).strip()
    if not value or len(value) > maximum or BAD_TEXT.search(value) or PRICE.search(value):
        raise SpecError("UNSAFE_SPECIFICATION_TEXT")
    return value


def normalize_facts(facts: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    result = {}
    for fact in facts:
        if not int(fact.get("is_visible", 1)):
            continue
        if int(fact.get("is_price_field", 0)):
            raise SpecError("PRICE_FIELD_FORBIDDEN")
        state = str(fact.get("verification_status", "VERIFIED")).upper()
        if state not in {"VERIFIED", "VERIFIED_10SRC", "MANUAL_VERIFIED", "TRUSTED", "MANUAL", "CURATED_PASS"}:
            continue
        key = _text(fact.get("field_key", fact.get("key")), 120)
        if not re.fullmatch(r"[a-zA-Z0-9_.:-]+", key) or key.casefold() in {"vin", "vin_code", "chassis_number"}:
            raise SpecError("INVALID_SPECIFICATION_KEY")
        label = _text(fact.get("label_ru", fact.get("label", key)), 160)
        value = _text(fact.get("field_value", fact.get("display_value", fact.get("value"))))
        unit = str(fact.get("unit") or "").strip()
        if unit:
            unit = _text(unit, 50)
            if not value.endswith(unit):
                value += " " + unit
        category = str(fact.get("category") or "additional")
        if category not in GROUPS:
            category = "additional"
        row = {"key": key, "label_ru": label, "label_uk": UK_LABELS.get(key, label),
               "value": value, "category": category}
        if key in result and result[key] != row:
            raise SpecError("CONFLICTING_SPECIFICATION_KEY:" + key)
        result[key] = row
    return sorted(result.values(), key=lambda row: (list(GROUPS).index(row["category"]), row["key"]))


def _digest(rows: list[dict[str, str]]) -> str:
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _i18n(uk: str, ru: str) -> str:
    return '<span data-ua="%s" data-uk="%s" data-ru="%s">%s</span>' % (
        html.escape(uk, quote=True), html.escape(uk, quote=True),
        html.escape(ru, quote=True), html.escape(uk))


def render_block(card_uid: str, facts: Iterable[dict[str, Any]]) -> str:
    card_uid = uid(card_uid)
    rows = normalize_facts(facts)
    groups = []
    for category, titles in GROUPS.items():
        items = [row for row in rows if row["category"] == category]
        if not items:
            continue
        body = "".join('<div class="ua-addspec-row" data-spec-key="%s"><dt>%s</dt><dd>%s</dd></div>' % (
            html.escape(row["key"], quote=True), _i18n(row["label_uk"], row["label_ru"]),
            html.escape(row["value"])) for row in items)
        groups.append('<section class="ua-addspec-group"><h3>%s</h3><dl>%s</dl></section>' % (_i18n(*titles), body))
    body = "".join(groups) or '<p class="ua-addspec-empty">%s</p>' % _i18n(
        "Підтверджені характеристики ще готуються.", "Подтверждённые характеристики ещё готовятся.")
    style = ('<style id="ua-spec-auto10-style">'
             '.ua-additional-spec{display:block!important;visibility:visible!important;border:1px solid #c79848;border-radius:12px;margin:18px 0;padding:0;overflow:hidden}'
             '.ua-additional-spec summary{display:flex!important;align-items:center;justify-content:space-between;gap:12px;box-sizing:border-box;min-height:44px;padding:18px;cursor:pointer;font-weight:700;list-style:none}'
             '.ua-additional-spec summary::-webkit-details-marker{display:none}.ua-additional-spec summary:focus-visible{outline:2px solid #c79848;outline-offset:-4px}'
             '.ua-addspec-summary-text{display:grid;gap:6px;min-width:0;overflow-wrap:anywhere}.ua-addspec-summary-hint{color:#e6b864;font-size:14px;line-height:1.4;font-weight:600;text-decoration:underline;text-underline-offset:3px}'
             '.ua-additional-spec summary:after{content:"＋";color:#c79848;flex-shrink:0}.ua-additional-spec[open] summary:after{content:"−"}'
             '.ua-addspec-body{padding:0 18px 18px}.ua-addspec-group h3{color:#c79848;font-size:15px;margin:18px 0 8px}'
             '.ua-addspec-group dl{margin:0}.ua-addspec-row{display:grid;grid-template-columns:1fr 1fr;gap:16px;border-top:1px solid #ffffff20;padding:9px 0}'
             '.ua-addspec-row dt,.ua-addspec-row dd{margin:0;overflow-wrap:anywhere}.ua-addspec-row dd{text-align:right;font-weight:600}'
             '@media(max-width:560px){.ua-addspec-row{grid-template-columns:1fr;gap:4px}.ua-addspec-row dd{text-align:left}}'
             '</style>')
    return (START + style + '<details class="blok ua-additional-spec" data-ua-additional-spec="1" '
            'data-spec-card="%s" data-spec-version="%s"><summary><span class="ua-addspec-summary-text">%s'
            '<span class="ua-addspec-summary-hint">%s</span></span></summary>'
            '<div class="ua-addspec-body">%s</div></details>' + END) % (
                card_uid, _digest(rows), _i18n("Додаткова специфікація", "Дополнительная спецификация"),
                _i18n("Переглянути характеристики", "Посмотреть характеристики"), body)


def _span(source: str) -> tuple[int, int] | None:
    a, b = source.count(START), source.count(END)
    if a == b == 0:
        if re.search(r'data-ua-additional-spec\s*=|class=[\"\'][^\"\']*ua-additional-spec', source, re.I):
            raise SpecError("UNMARKED_SPECIFICATION_REQUIRES_REVIEW")
        return None
    if a != 1 or b != 1 or source.index(START) >= source.index(END):
        raise SpecError("MALFORMED_OR_DUPLICATE_SPECIFICATION")
    return source.index(START), source.index(END) + len(END)


def strip_block(source: str) -> str:
    span = _span(source)
    return source[:span[0]] + source[span[1]:] if span else source


def _insert_at(source: str) -> int:
    for marker in ("<!--UA099_CLEAN_VIN_START-->", "<!-- UA-ART-DELIVERY-STAGES-PERMANENT-V1:START -->"):
        if marker in source:
            return source.index(marker)
    match = re.search(r'<(?:div|section)\b[^>]*class=[\"\'][^\"\']*\bua-clean-vin\b', source, re.I)
    if match:
        return match.start()
    raise SpecError("SPECIFICATION_INSERTION_ANCHOR_MISSING")


def inject(source: str, card_uid: str, facts: Iterable[dict[str, Any]]) -> str:
    facts = list(facts)
    span = _span(source)
    block = render_block(card_uid, facts)
    if span:
        output = source[:span[0]] + block + source[span[1]:]
    else:
        at = _insert_at(source)
        output = source[:at] + block + source[at:]
    if strip_block(output) != strip_block(source):
        raise SpecError("NON_SPECIFICATION_CHANGE")
    validate_page(output, card_uid, facts, previous=source)
    return output


def validate_page(source: str, card_uid: str, facts: Iterable[dict[str, Any]], *, previous: str | None = None) -> dict[str, Any]:
    card_uid = uid(card_uid)
    facts = list(facts)
    rows = normalize_facts(facts)
    if re.search(r"carhistory(?:\.kr)?|vindecoderz(?:\.com)?|(?:Проверить|Перевірити)\s+VIN|2\s*200\s*KRW", source, re.I):
        raise SpecError("PUBLIC_VIN_ADVERTISEMENT_FORBIDDEN")
    span = _span(source)
    if span is None:
        raise SpecError("SPECIFICATION_BLOCK_MISSING")
    if source[span[0]:span[1]] != render_block(card_uid, facts):
        raise SpecError("SPECIFICATION_DIFFERS_FROM_CONFIRMED_DATA")
    if len(re.findall(r'data-ua-additional-spec=[\"\']1[\"\']', source)) != 1:
        raise SpecError("SPECIFICATION_BLOCK_COUNT")
    if previous:
        old_span = _span(previous)
        if old_span:
            old = previous[old_span[0]:old_span[1]]
            old_keys = set(re.findall(r'data-spec-key="([^"]+)"', old))
            if old_keys - {row["key"] for row in rows}:
                raise SpecError("PREVIOUS_SPECIFICATION_KEYS_LOST")
            old_count = len(re.findall(r'class=[\"\'][^\"\']*\bua-addspec-row\b', old))
            if old_count > len(rows):
                raise SpecError("PREVIOUS_SPECIFICATION_ROWS_LOST")
    return {"status": "PASS", "rows": len(rows), "data_status": "READY" if rows else "NEEDS_REVIEW", "version": _digest(rows)}


def load_facts(card_uid: str) -> list[dict[str, Any]]:
    card_uid = uid(card_uid)
    # Legacy callbacks and common writers also pass here. Read the current
    # identity independently of queue status so READY/old manual facts cannot
    # bypass a newly discovered context conflict. This import starts no worker.
    import vin_spec_service
    card = next((row for row in vin_spec_service.read_cards() if row["car_uid"] == card_uid), None)
    if card is None:
        raise SpecError("CURRENT_CARD_IDENTITY_MISSING")
    _assert_identity_context(card)
    path = Path(os.environ.get("UA_ART_SPEC_DB", "/home/Carix/vin_specs_task111_v3.db"))
    if not path.is_file():
        raise SpecError("CANONICAL_SPEC_DATABASE_MISSING")
    with contextlib.closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=15)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        return [dict(row) for row in conn.execute('''
            SELECT a.*, m.label_ru, m.category, m.unit, m.verification_status,
                   m.is_manual, m.is_visible
            FROM additional_specification a JOIN additional_specification_meta m
              ON a.car_uid=m.car_uid AND a.field_key=m.field_key
            WHERE a.car_uid=? AND a.is_price_field=0 AND m.is_visible=1
        ''', (card_uid,))]


def guard_write(path: Path, data: bytes) -> None:
    """Call before every atomic primary-page replacement in the shared writer."""
    if re.fullmatch(r"UA-[0-9]{4,6}\.html", path.name):
        previous = path.read_text(encoding="utf-8") if path.is_file() else None
        validate_page(data.decode("utf-8"), path.stem, load_facts(path.stem), previous=previous)


def _read_page(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise SpecError("PUBLIC_PAGE_MISSING_OR_SYMLINK")
    with path.open("rb") as handle:
        data = handle.read(MAX_PAGE_BYTES + 1)
    if len(data) > MAX_PAGE_BYTES:
        raise SpecError("PUBLIC_PAGE_TOO_LARGE")
    return data


def _atomic(path: Path, data: bytes) -> None:
    fd, name = tempfile.mkstemp(prefix=".ua-spec-", dir=path.parent)
    temp = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp, path.stat().st_mode & 0o777)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _public_read(card_uid: str) -> str:
    url = "https://www.uaart.com.ua/video/%s.html" % uid(card_uid)
    request = urllib.request.Request(url, headers={"Cache-Control": "no-cache", "User-Agent": "UA-ART-Spec-Verify/1"})
    with urllib.request.urlopen(request, timeout=15) as response:
        if response.status != 200 or response.geturl().split("?")[0] != url:
            raise SpecError("PUBLIC_RESPONSE_MISMATCH")
        body = response.read(MAX_PAGE_BYTES + 1)
    if len(body) > MAX_PAGE_BYTES:
        raise SpecError("PUBLIC_RESPONSE_TOO_LARGE")
    return body.decode("utf-8")


def _current_state(card_uid: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    # Importing the module does not start its worker. read_cards is strictly RO.
    import vin_spec_service
    card = next((row for row in vin_spec_service.read_cards() if row["car_uid"] == card_uid), None)
    if card is None:
        raise SpecError("CURRENT_CARD_IDENTITY_MISSING")
    return card, load_facts(card_uid)


def _assert_identity_context(card: dict[str, Any]) -> None:
    import source_policy
    issues = source_policy.identity_context_issues(card)
    if issues:
        raise SpecError("IDENTITY_CONTEXT_REQUIRES_REVIEW:" + ",".join(issues))


def _assert_current(card: dict[str, Any], facts: list[dict[str, Any]], reader: Callable) -> None:
    current, current_facts = reader(uid(card.get("car_uid", card.get("auto_number"))))
    _assert_identity_context(current)
    keys = ("car_uid", "vin", "brand", "model", "year", "fuel", "engine_cc", "transmission", "published")
    if any(str(current.get(key) or "").strip().casefold() != str(card.get(key) or "").strip().casefold() for key in keys):
        raise SpecError("CARD_CHANGED_DURING_SPECIFICATION_SYNC")
    if normalize_facts(current_facts) != normalize_facts(facts):
        raise SpecError("SPECIFICATION_CHANGED_DURING_SYNC")


def reconcile_published(card: dict[str, Any], facts: Iterable[dict[str, Any]], *,
                        root: Path | None = None, public_reader: Callable[[str], str] | None = None,
                        state_reader: Callable | None = None) -> dict[str, Any]:
    """Reconcile one already-published card under the existing shared lock.

    A failed public read leaves valid local updates intact for bounded retry;
    a failed local transaction restores only our own unchanged postimages.
    """
    if card.get("published") not in (True, 1, "1"):
        return {"status": "NOT_REQUIRED", "detail": "DRAFT_NOT_PUBLISHED"}
    facts = list(facts)
    code = uid(card.get("car_uid", card.get("auto_number")))
    root = (root or Path(os.environ.get("UA_ART_ROOT", "/home/Carix"))).resolve()
    if not root.is_dir():
        return {"status": "FAIL", "detail": "RUNTIME_ROOT_MISSING"}
    reader = public_reader or _public_read
    state_reader = state_reader or _current_state
    lock_path = root / ".ua_art_publish_transaction.lock"
    try:
        if lock_path.is_symlink():
            raise SpecError("PUBLICATION_LOCK_SYMLINK")
        with lock_path.open("a+b") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return {"status": "FAIL", "detail": "PUBLICATION_LOCK_BUSY"}
            paths = [root / "video" / (code + ".html")]
            if (root / "site").is_dir():
                paths.append(root / "site" / (code + ".html"))
            if any(path.parent.is_symlink() or path.resolve().parent != path.parent for path in paths):
                raise SpecError("PUBLIC_ROOT_SYMLINK")
            before = {path: _read_page(path) for path in paths}
            _assert_current(card, facts, state_reader)
            after = {path: inject(data.decode("utf-8"), code, facts).encode() for path, data in before.items()}
            changed = []
            try:
                for path in paths:
                    _assert_current(card, facts, state_reader)
                    if _read_page(path) != before[path]:
                        raise SpecError("CONCURRENT_PUBLIC_PAGE_CHANGE")
                    if after[path] != before[path]:
                        _atomic(path, after[path])
                        changed.append(path)
                for path in paths:
                    if _read_page(path) != after[path]:
                        raise SpecError("LOCAL_READBACK_MISMATCH")
                    validate_page(after[path].decode(), code, facts, previous=before[path].decode())
                _assert_current(card, facts, state_reader)
            except Exception:
                for path in reversed(changed):
                    if _read_page(path) == after[path]:
                        _atomic(path, before[path])
                raise
            live = reader(code)
            result = validate_page(live, code, facts)
            return {"status": "PASS" if changed else "UNCHANGED", "detail": "PUBLIC_SPEC_VERIFIED",
                    "rows": result["rows"], "version": result["version"], "data_status": result["data_status"]}
    except Exception as exc:
        return {"status": "FAIL", "detail": type(exc).__name__ + ":" + str(exc)[:180]}

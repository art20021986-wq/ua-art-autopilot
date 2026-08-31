#!/usr/bin/env python3
"""Shared CRM/public renderer for the operator-separated additional specification."""
from __future__ import annotations

import html
import json
import os
import pathlib
import re
import sqlite3
from typing import Any


DB_PATH = pathlib.Path(os.environ.get("UA_ART_CRM_DB", "/home/Carix/crm.db"))
CARD_RE = re.compile(r"^UA[-‑–—]?0*(\d{1,4})$", re.I)
PRICE_RE = re.compile(
    r"(?:[$€£₴₽₩¥]|\b(?:price|cost|purchase|auction|wholesale|dealer|margin|markup|"
    r"закуп|себесто|цена|вартість|낙찰|경매|금액|만원)\b)", re.I,
)
CATEGORIES = (
    "engine", "dynamics", "consumption", "dimensions", "capacity", "weight",
    "suspension", "brakes", "steering", "wheels", "ecology", "additional",
)
CATEGORY_TITLES = {
    "engine": "Двигатель",
    "dynamics": "Динамика",
    "consumption": "Расход",
    "dimensions": "Размеры",
    "capacity": "Вместимость",
    "weight": "Масса",
    "suspension": "Подвеска",
    "brakes": "Тормоза",
    "steering": "Рулевое управление",
    "wheels": "Колёса",
    "ecology": "Экология",
    "additional": "Дополнительно",
}
UNIT_ALIASES = {
    "mm": ("mm", "мм"),
    "мм": ("mm", "мм"),
    "cm": ("cm", "см"),
    "см": ("cm", "см"),
    "km": ("km", "км"),
    "км": ("km", "км"),
    "kg": ("kg", "кг"),
    "кг": ("kg", "кг"),
    "kw": ("kw", "квт"),
    "квт": ("kw", "квт"),
    "hp": ("hp", "лс", "л.с"),
    "лс": ("hp", "лс", "л.с"),
    "л.с.": ("hp", "лс", "л.с"),
    "l": ("l", "л"),
    "л": ("l", "л"),
}
START = "<!--UA099_ADD_SPEC_START-->"
END = "<!--UA099_ADD_SPEC_END-->"
VIN_START = "<!--UA099_CLEAN_VIN_START-->"
VIN_END = "<!--UA099_CLEAN_VIN_END-->"
PRIMARY_ACTION_RE = re.compile(
    r"(?P<open><(?P<tag>a|button|div)\b"
    r"(?=[^>]*(?:class=['\"][^'\"]*\bkn_kupit\b|data-ua-primary-action(?:=['\"][^'\"]*['\"])?))"
    r"[^>]*>)(?P<inner>[\s\S]*?)(?P<close></(?P=tag)>)",
    re.I,
)


def canonical_uid(value: Any) -> str | None:
    match = CARD_RE.fullmatch(str(value or "").strip())
    return "UA-%04d" % int(match.group(1)) if match else None


def connect(readonly: bool = True) -> sqlite3.Connection:
    resolved = DB_PATH.resolve()
    if readonly:
        conn = sqlite3.connect("file:" + str(resolved) + "?mode=ro", uri=True, timeout=20)
        conn.execute("PRAGMA query_only=ON")
    else:
        conn = sqlite3.connect(str(resolved), timeout=30)
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def fetch_specs(value: Any, include_hidden: bool = False) -> list[dict[str, Any]]:
    uid = canonical_uid(value)
    if not uid or not DB_PATH.is_file():
        return []
    with connect(True) as conn:
        if not _table_exists(conn, "additional_specification"):
            return []
        rows = conn.execute(
            """
            SELECT a.id,a.car_uid,a.field_key,a.field_value,a.confidence,
                   COALESCE(m.label_ru,a.field_key) AS label_ru,
                   COALESCE(m.category,'additional') AS category,
                   COALESCE(m.unit,'') AS unit,
                   COALESCE(m.verification_status,'VERIFIED') AS verification_status,
                   COALESCE(m.evidence_count,0) AS evidence_count,
                   COALESCE(m.source_domains_json,'[]') AS source_domains_json,
                   COALESCE(m.is_manual,0) AS is_manual,
                   COALESCE(m.is_visible,1) AS is_visible
              FROM additional_specification a
              LEFT JOIN additional_specification_meta m
                ON m.car_uid=a.car_uid AND m.field_key=a.field_key
             WHERE a.car_uid=?
               AND a.is_price_field=0
               AND (?=1 OR COALESCE(m.is_visible,1)=1)
             ORDER BY CASE COALESCE(m.category,'additional')
               WHEN 'engine' THEN 1 WHEN 'dynamics' THEN 2 WHEN 'consumption' THEN 3
               WHEN 'dimensions' THEN 4 WHEN 'capacity' THEN 5 WHEN 'weight' THEN 6
               WHEN 'suspension' THEN 7 WHEN 'brakes' THEN 8 WHEN 'steering' THEN 9
               WHEN 'wheels' THEN 10 WHEN 'ecology' THEN 11 ELSE 12 END,
               COALESCE(m.label_ru,a.field_key),a.id
            """,
            (uid, 1 if include_hidden else 0),
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        if PRICE_RE.search(str(item.get("field_key") or "")):
            continue
        if PRICE_RE.search(str(item.get("label_ru") or "")):
            continue
        if PRICE_RE.search(str(item.get("field_value") or "")):
            continue
        result.append(item)
    return result


def get_spec(spec_id: int, car_uid: Any | None = None) -> dict[str, Any] | None:
    uid = canonical_uid(car_uid) if car_uid is not None else None
    with connect(True) as conn:
        row = conn.execute(
            """
            SELECT a.id,a.car_uid,a.field_key,a.field_value,a.confidence,
                   COALESCE(m.label_ru,a.field_key) AS label_ru,
                   COALESCE(m.category,'additional') AS category,
                   COALESCE(m.unit,'') AS unit,COALESCE(m.is_manual,0) AS is_manual,
                   COALESCE(m.is_visible,1) AS is_visible,
                   COALESCE(m.evidence_count,0) AS evidence_count,
                   COALESCE(m.source_domains_json,'[]') AS source_domains_json,
                   COALESCE(m.verification_status,'VERIFIED') AS verification_status
              FROM additional_specification a
              LEFT JOIN additional_specification_meta m
                ON m.car_uid=a.car_uid AND m.field_key=a.field_key
             WHERE a.id=?
            """,
            (int(spec_id),),
        ).fetchone()
    item = dict(row) if row else None
    return item if item and (uid is None or item["car_uid"] == uid) else None


def _ensure_safe_value(value: Any) -> str:
    text = str(value or "").strip()
    if not text or len(text) > 500:
        raise ValueError("INVALID_ADDITIONAL_SPEC_VALUE")
    if PRICE_RE.search(text):
        raise ValueError("PRICE_VALUE_FORBIDDEN")
    return text


def _value_with_unit(value: Any, unit: Any) -> str:
    raw_value = str(value or "").strip()
    raw_unit = str(unit or "").strip()
    if not raw_unit:
        return raw_value
    aliases = UNIT_ALIASES.get(raw_unit.casefold(), (raw_unit.casefold(),))
    normalized = raw_value.casefold().replace("\u00a0", " ")
    for alias in aliases:
        token = re.escape(alias).replace(r"\.", r"\.?\s*")
        if re.search(r"(?<![a-zа-яёіїєґ])" + token + r"(?![a-zа-яёіїєґ])", normalized, re.I):
            return raw_value
    return raw_value + " " + raw_unit


def set_visible(spec_id: int, car_uid: Any, visible: bool, actor_id: int | None = None) -> dict[str, Any]:
    item = get_spec(spec_id, car_uid)
    if not item:
        raise ValueError("ADDITIONAL_SPEC_NOT_FOUND")
    with connect(False) as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "UPDATE additional_specification_meta SET is_visible=?,updated_at=datetime('now') "
            "WHERE car_uid=? AND field_key=?",
            (1 if visible else 0, item["car_uid"], item["field_key"]),
        )
        conn.execute(
            "INSERT INTO additional_specification_audit"
            "(car_uid,field_key,action,new_value,actor_id) VALUES(?,?,?,?,?)",
            (item["car_uid"], item["field_key"], "VISIBILITY", str(int(bool(visible))), actor_id),
        )
        conn.commit()
    return get_spec(spec_id, car_uid) or item


def set_category(spec_id: int, car_uid: Any, category: str, actor_id: int | None = None) -> dict[str, Any]:
    item = get_spec(spec_id, car_uid)
    if not item or category not in CATEGORIES:
        raise ValueError("INVALID_ADDITIONAL_SPEC_CATEGORY")
    with connect(False) as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "UPDATE additional_specification_meta SET category=?,is_manual=1,"
            "verification_status='MANUAL_VERIFIED',updated_at=datetime('now') "
            "WHERE car_uid=? AND field_key=?",
            (category, item["car_uid"], item["field_key"]),
        )
        conn.execute(
            "INSERT INTO additional_specification_audit"
            "(car_uid,field_key,action,old_value,new_value,actor_id) VALUES(?,?,?,?,?,?)",
            (item["car_uid"], item["field_key"], "CATEGORY", item["category"], category, actor_id),
        )
        conn.commit()
    return get_spec(spec_id, car_uid) or item


def set_manual_value(spec_id: int, car_uid: Any, value: Any, actor_id: int | None = None) -> dict[str, Any]:
    item = get_spec(spec_id, car_uid)
    if not item:
        raise ValueError("ADDITIONAL_SPEC_NOT_FOUND")
    clean = _ensure_safe_value(value)
    with connect(False) as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "UPDATE additional_specification SET field_value=?,normalized_value=?,source='AI' "
            "WHERE id=? AND car_uid=?",
            (clean, re.sub(r"\s+", " ", clean.casefold()).strip(), int(spec_id), item["car_uid"]),
        )
        conn.execute(
            "UPDATE additional_specification_meta SET is_manual=1,is_visible=1,"
            "verification_status='MANUAL_VERIFIED',updated_at=datetime('now') "
            "WHERE car_uid=? AND field_key=?",
            (item["car_uid"], item["field_key"]),
        )
        conn.execute(
            "INSERT INTO additional_specification_audit"
            "(car_uid,field_key,action,old_value,new_value,actor_id) VALUES(?,?,?,?,?,?)",
            (item["car_uid"], item["field_key"], "VALUE", item["field_value"], clean, actor_id),
        )
        conn.commit()
    return get_spec(spec_id, car_uid) or item


def _car_vin(uid: str) -> str:
    if not DB_PATH.is_file():
        return ""
    with connect(True) as conn:
        row = conn.execute("SELECT vin FROM cars WHERE auto_number=?", (uid,)).fetchone()
    return str(row[0] or "").strip().upper() if row else ""


def _car_status(uid: str) -> str:
    if not DB_PATH.is_file():
        return ""
    with connect(True) as conn:
        row = conn.execute("SELECT status FROM cars WHERE auto_number=?", (uid,)).fetchone()
    return str(row[0] or "").strip() if row else ""


def crm_summary(value: Any) -> str:
    rows = fetch_specs(value, include_hidden=True)
    visible = sum(1 for row in rows if int(row.get("is_visible") or 0) == 1)
    manual = sum(1 for row in rows if int(row.get("is_manual") or 0) == 1)
    if not rows:
        return "Подтверждённые дополнительные характеристики пока не найдены."
    return "Подтверждено: %d · видно клиентам: %d · ручных правок: %d" % (
        len(rows), visible, manual,
    )


def render_public_block(value: Any) -> str:
    uid = canonical_uid(value)
    rows = fetch_specs(uid) if uid else []
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        category = row["category"] if row["category"] in CATEGORIES else "additional"
        grouped.setdefault(category, []).append(row)
    body = []
    for category in CATEGORIES:
        items = grouped.get(category) or []
        if not items:
            continue
        rendered = []
        for row in items:
            shown_value = _value_with_unit(row["field_value"], row.get("unit"))
            rendered.append(
                "<div class='ua-addspec-row'><dt>%s</dt><dd>%s</dd></div>" % (
                    html.escape(str(row["label_ru"])), html.escape(shown_value),
                )
            )
        body.append(
            "<section class='ua-addspec-group'><h3>%s</h3><dl>%s</dl></section>" % (
                html.escape(CATEGORY_TITLES[category]), "".join(rendered),
            )
        )
    if not body:
        body.append(
            "<p class='ua-addspec-empty'>Подтверждённые дополнительные характеристики "
            "пока не найдены.</p>"
        )
    count = len(rows)
    noun = "параметров" if count == 0 or count >= 5 else ("параметр" if count == 1 else "параметра")
    return (
        START
        + "<details class='blok ua-additional-spec' data-ua-additional-spec='1'>"
          "<summary><span>Дополнительная спецификация</span>"
          "<small>%d %s</small></summary><div class='ua-addspec-body'>%s</div></details>"
        % (count, noun, "".join(body))
        + END
    )


def _contract_marker_span(source: str, kind: str) -> tuple[int, int] | None:
    comments = list(re.finditer(r"<!--[\s\S]{0,500}?-->", source))
    candidates = [m for m in comments if kind.casefold() in m.group(0).casefold()]
    starts = [m for m in candidates if re.search(r"(?:START|BEGIN)", m.group(0), re.I)]
    ends = [m for m in candidates if re.search(r"(?:END|FINISH)", m.group(0), re.I)]
    if starts and ends:
        start = starts[0]
        end = next((m for m in ends if m.start() > start.end()), None)
        if end:
            return start.start(), end.end()
    return None


def _remove_original_vin(source: str) -> str:
    span = _contract_marker_span(source, "VIN")
    if span:
        source = source[:span[0]] + source[span[1]:]
    source = re.sub(
        r"<tr>\s*<td\s+class=['\"]k['\"]>\s*VIN\s*</td>\s*<td>[^<]*</td>\s*</tr>",
        "", source, flags=re.I,
    )
    source = re.sub(
        r"<a\b[^>]*href=['\"][^'\"]*carhistory\.kr[^'\"]*['\"][^>]*>[\s\S]*?</a>",
        "", source, flags=re.I,
    )
    return source


def _stage_number(uid: str) -> int:
    status = _car_status(uid)
    if status == "ua_arrived":
        return 4
    if status == "ge_waiting":
        return 3
    if status in ("sea_loaded", "sea_transit"):
        return 2
    return 1


def _expected_action(uid: str) -> str:
    return "Купить" if _stage_number(uid) == 4 else "Задаток 500 $"


def _set_primary_action(source: str, expected: str) -> str:
    return PRIMARY_ACTION_RE.sub(
        lambda match: match.group("open") + html.escape(expected) + match.group("close"),
        source,
    )


def _primary_action_texts(source: str) -> list[str]:
    return [
        re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", match.group("inner")))).strip()
        for match in PRIMARY_ACTION_RE.finditer(source)
    ]


def _ensure_diagnostics_action(source: str, uid: str) -> str:
    expected = _expected_action(uid)
    source = _set_primary_action(source, expected)
    if not _primary_action_texts(source):
        stage = _stage_number(uid)
        block = (
            "<div class='blok ua-diagnostics-primary-action'>"
            "<a class='dejstvie kn_kupit ua-primary-action-v1' "
            "data-ua-primary-action='1' data-ua-stage-action='%d' "
            "href='https://t.me/UA_artcompany_LLC_bot?start=kupit_%s'>%s</a></div>"
            % (stage, html.escape(uid), html.escape(expected))
        )
        for anchor in ("</main>", "</body>"):
            if anchor in source.lower():
                position = source.lower().rfind(anchor)
                source = source[:position] + block + source[position:]
                break
        else:
            source += block
    actions = _primary_action_texts(source)
    if actions != [expected]:
        raise RuntimeError("UA099_DIAGNOSTICS_ACTION:%s:%r" % (uid, actions))
    return source


def _clean_vin_block(uid: str, stage: int | None = None, videos: int | None = None) -> str:
    vin = _car_vin(uid)
    if not vin:
        return ""
    stage = int(stage) if stage is not None else _stage_number(uid)
    videos = max(0, int(videos or 0))
    return (
        VIN_START
        + "<div class='blok ua-clean-vin' data-ua-clean-vin='1' data-ua-card='%s' "
          "data-ua-stage='%d' data-ua-video-count='%d'><div class='zag'>VIN</div>"
          "<div class='ua-vin-value'>%s</div><div class='ua-vin-note'>"
          "VIN внесён оператором CRM. Проверка истории выполняется менеджером по запросу."
          "</div></div>" % (html.escape(uid), stage, videos, html.escape(vin))
        + VIN_END
    )


def _insert_before_stage(source: str, block: str) -> str:
    span = _contract_marker_span(source, "STAGE")
    if span:
        return source[:span[0]] + block + source[span[0]:]
    marker = re.search(r"<[^>]+data-ua-stage=['\"]\d+['\"][^>]*>", source, re.I)
    if marker:
        nearest = max(source.rfind("<section", 0, marker.start()), source.rfind("<div", 0, marker.start()))
        if nearest >= 0:
            return source[:nearest] + block + source[nearest:]
    table = re.search(
        r"<div\s+class=['\"]blok['\"]>\s*<div\s+class=['\"]zag['\"]>\s*Коротко\s*</div>"
        r"[\s\S]*?</table>\s*</div>", source, re.I,
    )
    if table:
        return source[:table.end()] + block + source[table.end():]
    raise RuntimeError("UA099_STAGE_INSERTION_ANCHOR_MISSING:" + block[:30])


def _remove_duplicate_description_label(source: str) -> str:
    pattern = re.compile(
        r"(<div\s+class=['\"]zag['\"]>\s*Описание\s*</div>)\s*"
        r"<div\s+class=['\"]tehstr['\"]>\s*<div\s+class=['\"]m['\"]>\s*•\s*</div>\s*"
        r"<div>\s*Описание\s*</div>\s*</div>", re.I,
    )
    return pattern.sub(r"\1", source, count=1)


def _css() -> str:
    return """
<style id="ua099-additional-spec-style">
.ua-additional-spec{padding:0;overflow:hidden}.ua-additional-spec summary{list-style:none;cursor:pointer;padding:18px 20px;display:flex;align-items:center;justify-content:space-between;gap:12px;font-weight:800;font-size:18px}.ua-additional-spec summary::-webkit-details-marker{display:none}.ua-additional-spec summary:after{content:'＋';font-size:22px;color:#eda63a}.ua-additional-spec[open] summary:after{content:'−'}.ua-additional-spec summary small{margin-left:auto;color:var(--seryj,#9aa8ba);font-size:12px;font-weight:600;white-space:nowrap}.ua-addspec-body{padding:0 20px 18px}.ua-addspec-group{padding:14px 0;border-top:1px solid rgba(120,150,185,.18)}.ua-addspec-group h3{margin:0 0 8px;color:#eda63a;font-size:14px;letter-spacing:.06em;text-transform:uppercase}.ua-addspec-group dl{margin:0}.ua-addspec-row{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px;padding:8px 0}.ua-addspec-row dt{color:var(--seryj,#9aa8ba);min-width:0;overflow-wrap:anywhere}.ua-addspec-row dd{margin:0;text-align:right;font-weight:700;min-width:0;overflow-wrap:anywhere}.ua-addspec-empty{margin:0;padding:14px 0;color:var(--seryj,#9aa8ba)}.ua-clean-vin .ua-vin-value{font-size:18px;font-weight:800;letter-spacing:.04em;overflow-wrap:anywhere}.ua-clean-vin .ua-vin-note{margin-top:8px;color:var(--seryj,#9aa8ba);font-size:13px}@media(max-width:560px){.ua-additional-spec summary{padding:16px}.ua-addspec-body{padding:0 16px 16px}.ua-addspec-row{grid-template-columns:1fr;gap:3px}.ua-addspec-row dd{text-align:left}.ua-additional-spec summary small{display:none}}
</style>
""".strip()


def inject_public_spec(source: str, value: Any) -> str:
    uid = canonical_uid(value)
    if not source or not uid:
        return source
    # The operator CRM status is authoritative.  Generated legacy HTML may
    # contain more than one stale data-ua-stage attribute while wrappers are
    # being normalized, so it must not decide the public CTA.
    stage = _stage_number(uid)
    # Count what the browser will actually render.  Legacy metadata can be
    # stale and was the source of a false publication block on UA-0001.
    videos = len(re.findall(r"<video\b", source, re.I))
    source = re.sub(re.escape(START) + r"[\s\S]*?" + re.escape(END), "", source)
    source = re.sub(re.escape(VIN_START) + r"[\s\S]*?" + re.escape(VIN_END), "", source)
    source = _remove_original_vin(source)
    source = _remove_duplicate_description_label(source)
    source = re.sub(r"\bВ море\b", "На пароме", source, flags=re.I)
    source = source.replace(">Забронировать авто за 500 $<", ">Задаток 500 $<")
    source = source.replace(">Купить авто<", ">Купить<")
    source = _set_primary_action(source, _expected_action(uid))
    block = render_public_block(uid) + _clean_vin_block(uid, stage, videos)
    source = _insert_before_stage(source, block)
    if "ua099-additional-spec-style" not in source:
        source = re.sub(r"</head>", _css() + "</head>", source, count=1, flags=re.I)
    errors = public_contract_errors(source, uid)
    if errors:
        raise RuntimeError("UA099_PUBLIC_CONTRACT:%s:%s" % (uid, ";".join(errors)))
    return source


def normalize_diagnostics(source: str, value: Any) -> str:
    uid = canonical_uid(value)
    if not source or not uid:
        return source
    source = re.sub(r"\bВ море\b", "На пароме", source, flags=re.I)
    expected_action = _expected_action(uid)
    source = source.replace(">Забронировать авто за 500 $<", ">" + expected_action + "<")
    source = source.replace(">Задаток 500 $<", ">" + expected_action + "<")
    source = source.replace(">Купить авто<", ">" + expected_action + "<")
    source = _set_primary_action(source, expected_action)
    if re.search(r"carhistory\.kr", source, re.I):
        source = re.sub(
            r"<a\b[^>]*href=['\"][^'\"]*carhistory\.kr[^'\"]*['\"][^>]*>[\s\S]*?</a>",
            "", source, flags=re.I,
        )
    source = _ensure_diagnostics_action(source, uid)
    errors = diagnostics_contract_errors(source, uid)
    if errors:
        raise RuntimeError("UA099_DIAGNOSTICS_CONTRACT:%s:%s" % (uid, ";".join(errors)))
    return source


def diagnostics_contract_errors(source: str, value: Any) -> list[str]:
    uid = canonical_uid(value) or str(value)
    errors = []
    if _primary_action_texts(source) != [_expected_action(uid)]:
        errors.append("diagnostics primary action")
    if re.search(r"carhistory\.kr|Проверить VIN", source, re.I):
        errors.append("diagnostics external VIN CTA")
    if re.search(r"\bВ море\b", source, re.I):
        errors.append("diagnostics old sea wording")
    if uid not in source or "</html>" not in source.lower():
        errors.append("diagnostics identity or incomplete HTML")
    return errors


def public_contract_errors(source: str, value: Any) -> list[str]:
    uid = canonical_uid(value) or str(value)
    errors = []
    if source.count(START) != 1 or source.count(END) != 1:
        errors.append("additional spec blocks != 1")
    if source.count(VIN_START) != 1 or source.count(VIN_END) != 1:
        errors.append("clean VIN blocks != 1")
    if len(re.findall(r"data-ua-additional-spec=['\"]1['\"]", source, re.I)) != 1:
        errors.append("additional spec element != 1")
    if re.search(r"carhistory\.kr|Korea\s+CarHistory|Проверить VIN", source, re.I):
        errors.append("external VIN CTA remains")
    if re.search(r"\bВ море\b", source, re.I):
        errors.append("old sea wording remains")
    expected_action = _expected_action(uid)
    actions = _primary_action_texts(source)
    if actions != [expected_action]:
        errors.append("primary action != 1 exact %s" % expected_action)
    if source.find(START) > source.find(VIN_START) or source.find(VIN_START) < 0:
        errors.append("additional spec/VIN order")
    stage = _contract_marker_span(source, "STAGE")
    if stage and source.find(VIN_END) > stage[0]:
        errors.append("VIN/stage order")
    diag = re.findall(
        r"href=['\"](?:[^'\"]*/)?" + re.escape(uid) + r"-diag\.html(?:\?[^'\"]*)?['\"]",
        source, re.I,
    )
    if len(diag) != 1:
        errors.append("diagnostics links != 1")
    if re.search(
        r"<div\s+class=['\"]zag['\"]>\s*Описание\s*</div>\s*"
        r"<div\s+class=['\"]tehstr['\"][\s\S]{0,180}?<div>\s*Описание\s*</div>",
        source, re.I,
    ):
        errors.append("duplicate description label")
    labels = [
        html.unescape(re.sub(r"<[^>]+>", "", label)).strip()
        for label in re.findall(
            r"<div\s+class=['\"]ua-addspec-row['\"]>\s*<dt>([\s\S]*?)</dt>",
            source, re.I,
        )
    ]
    signatures = [
        " ".join(sorted(re.findall(r"[a-zа-яёіїєґ0-9]+", label.casefold().replace("ё", "е"))))
        for label in labels
    ]
    if len(signatures) != len(set(signatures)):
        errors.append("semantic duplicate additional labels")
    if "</html>" not in source.lower():
        errors.append("html incomplete")
    return errors


if __name__ == "__main__":
    assert canonical_uid("UA-9") == "UA-0009"
    assert canonical_uid("UA-0016") == "UA-0016"
    assert PRICE_RE.search("purchase price")
    print("UA099_ADDITIONAL_SPEC_SELFTEST_PASS")

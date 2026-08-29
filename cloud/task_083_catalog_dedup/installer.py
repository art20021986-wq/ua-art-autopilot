#!/usr/bin/env python3
"""Atomic TASK 083 installer for the permanent catalog de-duplication guard.

Runs on PythonAnywhere.  It supports both catalog renderers that can exist in
production: the legacy TASK 074 cards and the unified stage-card renderer.
CRM rows, media and individual vehicle pages are read-only invariants.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import html as html_lib
import json
import os
import pathlib
import re
import shutil
import sqlite3
import tempfile
from typing import Any


CONTRACT = "CATALOG-CARD-DEDUP-GUARD-083-V1.0"
SOURCE_MARKER = "# CATALOG-CARD-DEDUP-GUARD-083-V1.0-PERMANENT"
CORE_MARKER = "CATALOG_CARD_DEDUP_GUARD = \"CATALOG-CARD-DEDUP-GUARD-083-V1.0\""
PREVIOUS_SOURCE_MARKER = "# CATALOG-CARD-UNIFY-002-V1.0-PERMANENT"
STYLE_MARKER = "UA-CATALOG-CARD-UNIFY-002-V1.0"
STAGE_STYLE_MARKER = "ua-stage-card-v2-style"
ROOT = pathlib.Path("/home/Carix")
REMOTE_ROOT = ROOT / "autopilot_inbox/cloud/task_083_catalog_dedup"
BACKUP_PARENT = REMOTE_ROOT / "backups"
RECEIPTS = {
    "shadow": REMOTE_ROOT / "shadow_receipt.json",
    "install": REMOTE_ROOT / "install_receipt.json",
    "rollback": REMOTE_ROOT / "rollback_receipt.json",
}
LOCK_PATH = ROOT / ".task083_catalog_dedup.lock"
DB_PATH = ROOT / "crm.db"
SOURCE_PATHS = [ROOT / name for name in ("stranica.py", "yadro.py", "master_card.py")]
CORE_PATH = ROOT / "catalog_stage_guard_core.py"
RUNTIME_PATH = ROOT / "catalog_stage_guard_runtime.py"
PUBLISHER_PATH = ROOT / "publikaciya.py"
CATALOG_PATHS = [ROOT / "video/katalog.html", ROOT / "site/katalog.html"]
CARD_PAGE_GLOBS = [ROOT / "video/UA-*.html", ROOT / "site/UA-*.html"]

# Exact source layer produced by successful TASK 074 production run.
EXPECTED_BASE_SHA256 = {
    str(ROOT / "stranica.py"): "84a56024e185932c3f2af289db87d1b98558acdf9c4788256dfd36d544ec28b3",
    str(ROOT / "yadro.py"): "a0976afb93a4d2fdcab392601d25253700977618a02b04bc31903a18e95ee81a",
    str(ROOT / "master_card.py"): "df2001cd808e5fbb2201e2dbc5e06ab3d529be3cdb65dbaca691a15a2bad2174",
}

# Git object id of cloud/task_075_stage_guard/stage_guard.py before TASK 083.
# Production TASK 082 copies that file byte-for-byte to CORE_PATH.
EXPECTED_CORE_BASE_BLOB = "0ba2385f59fb8cc34f65b609af973c76a5196e81"

RU_DUPLICATE = "Автомобиль на пароме: Корея → Грузия."
UK_DUPLICATE = "Автомобіль на поромі: Корея → Грузія."
RU_UNKNOWN_OLD = "Автомобиль на пароме · количество дней до Киева уточняется."
UK_UNKNOWN_OLD = "Автомобіль на поромі · кількість днів до Києва уточнюється."
RU_UNKNOWN_NEW = "Количество дней до Киева уточняется."
UK_UNKNOWN_NEW = "Кількість днів до Києва уточнюється."
RU_KYIV_DUPLICATE = "Автомобиль в Киеве и готов к осмотру."
UK_KYIV_DUPLICATE = "Автомобіль у Києві та готовий до огляду."
RU_GEORGIA_OLD = (
    "После внесения предоплаты 500 $ автомобиль прибудет в Киев в течение "
    "15 календарных дней. Точная дата появится после внесения предоплаты."
)
UK_GEORGIA_OLD = (
    "Після внесення передоплати 500 $ автомобіль прибуде до Києва протягом "
    "15 календарних днів. Точна дата з’явиться після внесення передоплати."
)
RU_GEORGIA_NEW = (
    "До Киева — до 15 календарных дней после бронирования за 500 $. "
    "Точную дату укажем после отправки."
)
UK_GEORGIA_NEW = (
    "До Києва — до 15 календарних днів після бронювання за 500 $. "
    "Точну дату вкажемо після відправлення."
)
RU_KOREA_OLD = (
    "После внесения предоплаты 500 $ автомобиль будет отправлен ближайшим "
    "паромом. Дата прибытия будет рассчитана после погрузки на паром."
)
UK_KOREA_OLD = (
    "Після внесення передоплати 500 $ автомобіль буде відправлено найближчим "
    "поромом. Дату прибуття буде розраховано після завантаження на пором."
)
RU_KOREA_NEW = (
    "Предоплата 500 $ фиксирует бронирование. Отправка — ближайшим рейсом; "
    "дату прибытия рассчитаем после погрузки."
)
UK_KOREA_NEW = (
    "Передоплата 500 $ фіксує бронювання. Відправлення — найближчим рейсом; "
    "дату прибуття розрахуємо після завантаження."
)
CAT_START = "<!-- UA-ART-CATALOG-VIN-V1:START -->"
CAT_END = "<!-- UA-ART-CATALOG-VIN-V1:END -->"


class Blocked(RuntimeError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_bytes(path: pathlib.Path) -> bytes:
    data = path.read_bytes()
    if len(data) > 24 * 1024 * 1024:
        raise Blocked("FILE_TOO_LARGE:" + str(path))
    return data


def atomic_write(path: pathlib.Path, data: bytes, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(dir=path.parent, prefix="." + path.name + ".", delete=False)
    temp = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(temp, mode)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def atomic_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    atomic_write(path, (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode())


def db_snapshot() -> dict[str, Any]:
    data = read_bytes(DB_PATH)
    handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    temp = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(data)
        connection = sqlite3.connect("file:%s?mode=ro" % temp, uri=True)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA query_only=ON")
            quick = connection.execute("PRAGMA quick_check").fetchone()[0]
            rows = [dict(row) for row in connection.execute(
                "SELECT * FROM cars WHERE published=1 ORDER BY id"
            )]
        finally:
            connection.close()
    finally:
        temp.unlink(missing_ok=True)
    normalized = json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str).encode()
    identifiers = [str(row.get("auto_number") or "").upper() for row in rows]
    ua0009_row = next((row for row in rows if row.get("auto_number") == "UA-0009"), None)
    return {
        "file_sha256": sha256(data),
        "rows_sha256": sha256(normalized),
        "quick_check": str(quick),
        "count": len(rows),
        "identifiers": identifiers,
        "ua0009": bool(ua0009_row),
        "ua0009_status": (ua0009_row or {}).get("status"),
    }


def protected_pages_snapshot() -> dict[str, str]:
    result: dict[str, str] = {}
    for pattern in CARD_PAGE_GLOBS:
        for path in sorted(pattern.parent.glob(pattern.name)):
            # Catalog is the only public HTML write target.
            if path.name == "katalog.html":
                continue
            result[str(path)] = sha256(read_bytes(path))
    return result


def source_helper_code() -> str:
    """Return the zero-token runtime guard embedded in every active generator."""
    return r'''# CATALOG-CARD-DEDUP-GUARD-083 runtime helper
import re as _ua083_re
_UA083_CAT_START = "<!-- UA-ART-CATALOG-VIN-V1:START -->"
_UA083_CAT_END = "<!-- UA-ART-CATALOG-VIN-V1:END -->"

def _ua083_visible(fragment):
    value = _ua083_re.sub(r"<[^>]+>", " ", fragment)
    for old, new in (
        ("&nbsp;", " "), ("&#10;", " "), ("&#x0a;", " "),
        ("&amp;", "&"), ("&rarr;", "→"), ("&gt;", ">"), ("&lt;", "<"),
    ):
        value = value.replace(old, new).replace(old.upper(), new)
    return " ".join(value.casefold().replace("\u00a0", " ").split())

def _ua083_dedup_block(block, upper):
    replacements = (
        ("Автомобиль на пароме: Корея → Грузия.", ""),
        ("Автомобіль на поромі: Корея → Грузія.", ""),
        ("Автомобиль на пароме · количество дней до Киева уточняется.",
         "Количество дней до Киева уточняется."),
        ("Автомобіль на поромі · кількість днів до Києва уточнюється.",
         "Кількість днів до Києва уточнюється."),
        ("Автомобиль в Киеве и готов к осмотру.", ""),
        ("Автомобіль у Києві та готовий до огляду.", ""),
        ("После внесения предоплаты 500 $ автомобиль прибудет в Киев в течение "
         "15 календарных дней. Точная дата появится после внесения предоплаты.",
         "До Киева — до 15 календарных дней после бронирования за 500 $. "
         "Точную дату укажем после отправки."),
        ("Після внесення передоплати 500 $ автомобіль прибуде до Києва протягом "
         "15 календарних днів. Точна дата з’явиться після внесення передоплати.",
         "До Києва — до 15 календарних днів після бронювання за 500 $. "
         "Точну дату вкажемо після відправлення."),
        ("После внесения предоплаты 500 $ автомобиль будет отправлен ближайшим "
         "паромом. Дата прибытия будет рассчитана после погрузки на паром.",
         "Предоплата 500 $ фиксирует бронирование. Отправка — ближайшим рейсом; "
         "дату прибытия рассчитаем после погрузки."),
        ("Після внесення передоплати 500 $ автомобіль буде відправлено найближчим "
         "поромом. Дату прибуття буде розраховано після завантаження на пором.",
         "Передоплата 500 $ фіксує бронювання. Відправлення — найближчим рейсом; "
         "дату прибуття розрахуємо після завантаження."),
    )
    for old, new in replacements:
        block = block.replace(old, new)

    spec = _ua083_re.search(
        r'<div class=["\']ua-cat-vin-v1-spec["\']>\s*'
        r'Двигатель:\s*<b>(.*?)</b>\s*·\s*Видео:\s*<b>(\d+)</b>\s*</div>',
        block, _ua083_re.I | _ua083_re.S,
    )
    if spec:
        engine_html, video_text = spec.group(1), spec.group(2)
        engine_text = _ua083_visible(engine_html)
        upper_text = _ua083_visible(upper)
        video_duplicate = bool(_ua083_re.search(
            r'(^|\D)' + _ua083_re.escape(video_text) +
            r'\s*(?:видео|відео)(?:\D|$)', upper_text,
        ))
        pieces = []
        if engine_text and engine_text not in upper_text:
            pieces.append("Двигатель: <b>" + engine_html + "</b>")
        if int(video_text) > 0 and not video_duplicate:
            pieces.append("Видео: <b>" + video_text + "</b>")
        replacement = (
            '<div class="ua-cat-vin-v1-spec">' + " · ".join(pieces) + "</div>"
            if pieces else ""
        )
        block = block[:spec.start()] + replacement + block[spec.end():]

    copy = _ua083_re.search(
        r'<div class=["\']ua-cat-vin-v1-copy["\']>(.*?)</div>',
        block, _ua083_re.I | _ua083_re.S,
    )
    if copy and not _ua083_visible(copy.group(1)):
        block = block[:copy.start()] + block[copy.end():]
    block = _ua083_re.sub(r"([.!?])\s{2,}", r"\1 ", block)
    return block

def _ua083_dedup_catalog(source):
    pattern = _ua083_re.compile(
        _ua083_re.escape(_UA083_CAT_START) + r".*?" +
        _ua083_re.escape(_UA083_CAT_END), _ua083_re.S,
    )
    matches = list(pattern.finditer(source))
    if not matches:
        return source
    output = []
    cursor = 0
    previous_end = 0
    for match in matches:
        output.append(source[cursor:match.start()])
        upper = source[previous_end:match.start()]
        output.append(_ua083_dedup_block(match.group(0), upper))
        cursor = match.end()
        previous_end = match.end()
    output.append(source[cursor:])
    return "".join(output)
'''


def patch_generator_source(source: str) -> str:
    if SOURCE_MARKER in source:
        validate_source(source)
        return source
    if source.count(PREVIOUS_SOURCE_MARKER) != 1 or source.count(STYLE_MARKER) != 1:
        raise Blocked("SOURCE_TASK074_BASE_MISSING")
    definition = "def _ua068_ensure_catalog("
    if source.count(definition) != 1:
        raise Blocked("SOURCE_CATALOG_DEFINITION_COUNT")
    start = source.find(definition)
    end = source.find("def _ua068_card_errors", start)
    if start < 0 or end < 0:
        raise Blocked("SOURCE_CATALOG_FUNCTION_BOUNDARY")
    base = source[start:end].replace(
        definition, "def _ua068_ensure_catalog_base(", 1
    )
    wrapper = (
        "\ndef _ua068_ensure_catalog(*args, **kwargs):\n"
        "    return _ua083_dedup_catalog("
        "_ua068_ensure_catalog_base(*args, **kwargs))\n\n"
    )
    source = (
        source[:start] + source_helper_code() + "\n" + base + wrapper + source[end:]
    )
    marker_at = source.find("\n", source.find(PREVIOUS_SOURCE_MARKER))
    if marker_at < 0:
        raise Blocked("SOURCE_MARKER_INSERT_POINT")
    source = source[: marker_at + 1] + SOURCE_MARKER + "\n" + source[marker_at + 1 :]
    validate_source(source)
    return source


def validate_source(source: str) -> None:
    checks = {
        "source_marker": source.count(SOURCE_MARKER) == 1,
        "previous_marker": source.count(PREVIOUS_SOURCE_MARKER) == 1,
        "style_marker": source.count(STYLE_MARKER) == 1,
        "helper": source.count("def _ua083_dedup_catalog(") == 1,
        "base": source.count("def _ua068_ensure_catalog_base(") == 1,
        "wrapper": source.count("def _ua068_ensure_catalog(*args, **kwargs):") == 1,
    }
    if not all(checks.values()):
        raise Blocked("SOURCE_GUARD_INVALID:" + json.dumps(checks, sort_keys=True))
    compile(source, "production-generator.py", "exec")


def git_blob_id(data: bytes) -> str:
    header = ("blob %d\0" % len(data)).encode()
    return hashlib.sha1(header + data).hexdigest()


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise Blocked("CORE_PATCH_POINT_%s:%d" % (label, count))
    return source.replace(old, new, 1)


def core_guard_code() -> str:
    return r'''

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
'''


def patch_core_source(source: str) -> str:
    if CORE_MARKER in source:
        validate_core_source(source)
        return source
    if git_blob_id(source.encode()) != EXPECTED_CORE_BASE_BLOB:
        raise Blocked("CORE_BASE_BLOB_MISMATCH")
    source = replace_once(
        source,
        'CONTRACT_ID = "CRM-CATALOG-STAGE-GUARD-003-V1.0"\n',
        'CONTRACT_ID = "CRM-CATALOG-STAGE-GUARD-003-V1.0"\n' + CORE_MARKER + "\n",
        "MARKER",
    )
    source = replace_once(
        source,
        "\n\ndef title(row: Mapping) -> str:\n",
        '''

def public_media_summary(photos: int, videos: int) -> str:
    """Show useful media counts once; never render technical zero values."""
    values = []
    if photos > 0:
        values.append("Фото: %d" % photos)
    if videos > 0:
        values.append("Видео: %d" % videos)
    return " · ".join(values) or "Медиа готовятся"


def title(row: Mapping) -> str:
''',
        "MEDIA_HELPER",
    )
    source = replace_once(
        source,
        '    videos = media_count(row.get("videos"))\n    eta_ru, eta_uk = public_eta(row, stage)\n',
        '    videos = media_count(row.get("videos"))\n'
        '    media = public_media_summary(photos, videos)\n'
        '    eta_ru, eta_uk = public_eta(row, stage)\n',
        "MEDIA_VALUE",
    )
    source = replace_once(
        source,
        "'<i>VIN ПРОВЕРЕН</i><small>Фото: {photos} · Видео: {videos}</small></div>'",
        "'<i>VIN ПРОВЕРЕН</i><small>{media}</small></div>'",
        "MEDIA_RENDER",
    )
    source = replace_once(
        source,
        "videos=videos, photo=esc(photo_url), price=esc(public_price(row)), eta=eta.format(",
        "media=esc(media), photo=esc(photo_url), price=esc(public_price(row)), eta=eta.format(",
        "MEDIA_FORMAT",
    )
    source = replace_once(
        source,
        "\n\ndef audit_catalog(source: str, rows: Iterable[Mapping]) -> dict:\n",
        core_guard_code() + "\n\ndef audit_catalog(source: str, rows: Iterable[Mapping]) -> dict:\n",
        "AUDIT_HELPER",
    )
    source = replace_once(
        source,
        '        if leaked:\n            errors.append("INTERNAL_TEXT_LEAK:%s" % identifier)\n'
        '        if expected_stage == 2 and re.search(r"корея\\s*[→-]\\s*грузи", folded, re.I):\n',
        '        if leaked:\n            errors.append("INTERNAL_TEXT_LEAK:%s" % identifier)\n'
        '        for issue in semantic_duplicate_issues(block, row):\n'
        '            errors.append("SEMANTIC_DUPLICATE:%s:%s" % (identifier, issue))\n'
        '        if expected_stage == 2 and re.search(r"корея\\s*[→-]\\s*грузи", folded, re.I):\n',
        "AUDIT_CALL",
    )
    validate_core_source(source)
    return source


def validate_core_source(source: str) -> None:
    checks = {
        "marker": source.count(CORE_MARKER) == 1,
        "media_helper": source.count("def public_media_summary(") == 1,
        "semantic_helper": source.count("def semantic_duplicate_issues(") == 1,
        "audit_call": source.count("semantic_duplicate_issues(block, row)") == 1,
        "zero_template_removed": "Фото: {photos} · Видео: {videos}" not in source,
    }
    if not all(checks.values()):
        raise Blocked("CORE_GUARD_INVALID:" + json.dumps(checks, sort_keys=True))
    compile(source, "catalog_stage_guard_core.py", "exec")


def visible(fragment: str) -> str:
    value = re.sub(r"<[^>]+>", " ", fragment)
    return " ".join(
        html_lib.unescape(value).casefold().replace("\u00a0", " ").split()
    )


def patch_catalog_block(block: str, upper: str = "") -> str:
    replacements = (
        (RU_DUPLICATE, ""),
        (UK_DUPLICATE, ""),
        (RU_UNKNOWN_OLD, RU_UNKNOWN_NEW),
        (UK_UNKNOWN_OLD, UK_UNKNOWN_NEW),
        (RU_KYIV_DUPLICATE, ""),
        (UK_KYIV_DUPLICATE, ""),
        (RU_GEORGIA_OLD, RU_GEORGIA_NEW),
        (UK_GEORGIA_OLD, UK_GEORGIA_NEW),
        (RU_KOREA_OLD, RU_KOREA_NEW),
        (UK_KOREA_OLD, UK_KOREA_NEW),
    )
    for old, new in replacements:
        block = block.replace(old, new)
    spec = re.search(
        r'<div class=["\']ua-cat-vin-v1-spec["\']>\s*'
        r'Двигатель:\s*<b>(.*?)</b>\s*·\s*Видео:\s*<b>(\d+)</b>\s*</div>',
        block, re.I | re.S,
    )
    if spec:
        engine_html, video_text = spec.group(1), spec.group(2)
        engine_text = visible(engine_html)
        upper_text = visible(upper)
        video_duplicate = bool(re.search(
            r"(^|\D)" + re.escape(video_text) +
            r"\s*(?:видео|відео)(?:\D|$)", upper_text,
        ))
        pieces = []
        if engine_text and engine_text not in upper_text:
            pieces.append("Двигатель: <b>" + engine_html + "</b>")
        if int(video_text) > 0 and not video_duplicate:
            pieces.append("Видео: <b>" + video_text + "</b>")
        replacement = (
            '<div class="ua-cat-vin-v1-spec">' + " · ".join(pieces) + "</div>"
            if pieces else ""
        )
        block = block[:spec.start()] + replacement + block[spec.end():]
    copy = re.search(
        r'<div class=["\']ua-cat-vin-v1-copy["\']>(.*?)</div>',
        block, re.I | re.S,
    )
    if copy and not visible(copy.group(1)):
        block = block[:copy.start()] + block[copy.end():]
    return re.sub(r"([.!?])\s{2,}", r"\1 ", block)


def catalog_pairs(source: str) -> list[tuple[str, str]]:
    pattern = re.compile(re.escape(CAT_START) + r".*?" + re.escape(CAT_END), re.S)
    result = []
    previous_end = 0
    for match in pattern.finditer(source):
        result.append((source[previous_end:match.start()], match.group(0)))
        previous_end = match.end()
    return result


def catalog_blocks(source: str) -> list[str]:
    return [block for _, block in catalog_pairs(source)]


def stage_pairs(source: str) -> list[tuple[str, str]]:
    pattern = re.compile(
        r'<a\b(?=[^>]*\bdata-ua-card=["\']UA-[0-9]{4,}["\'])'
        r'(?=[^>]*\bclass=["\'][^"\']*\bua-stage-card-v2\b)[^>]*>.*?</a\s*>',
        re.I | re.S,
    )
    result = []
    previous_end = 0
    for match in pattern.finditer(source):
        result.append((source[previous_end:match.start()], match.group(0)))
        previous_end = match.end()
    return result


def catalog_mode(source: str) -> str:
    legacy = len(catalog_pairs(source))
    stage = len(stage_pairs(source))
    if legacy and stage:
        raise Blocked("CATALOG_MIXED_RENDERERS")
    if legacy:
        return "legacy_v1"
    if stage:
        return "stage_v2"
    raise Blocked("CATALOG_CARD_RENDERER_MISSING")


def patch_catalog(source: str) -> str:
    pattern = re.compile(re.escape(CAT_START) + r".*?" + re.escape(CAT_END), re.S)
    matches = list(pattern.finditer(source))
    if not matches:
        raise Blocked("CATALOG_CANONICAL_BLOCKS_MISSING")
    output = []
    cursor = 0
    previous_end = 0
    for match in matches:
        output.append(source[cursor:match.start()])
        upper = source[previous_end:match.start()]
        output.append(patch_catalog_block(match.group(0), upper))
        cursor = match.end()
        previous_end = match.end()
    output.append(source[cursor:])
    candidate = "".join(output)
    validate_catalog(candidate, require_dedup=True)
    return candidate


def patch_stage_catalog(source: str) -> str:
    if catalog_mode(source) != "stage_v2":
        raise Blocked("STAGE_CATALOG_EXPECTED")
    candidate = re.sub(
        r'\s*·\s*(?:Видео|Відео)\s*:\s*0(?=\s*</small\s*>)',
        "",
        source,
        flags=re.I,
    )
    candidate = re.sub(
        r'(<small\b[^>]*>)\s*(?:Видео|Відео)\s*:\s*0\s*(</small\s*>)',
        r'\1Медиа готовятся\2',
        candidate,
        flags=re.I,
    )
    for old, new in (
        (RU_DUPLICATE, ""), (UK_DUPLICATE, ""),
        (RU_KYIV_DUPLICATE, ""), (UK_KYIV_DUPLICATE, ""),
        (RU_UNKNOWN_OLD, RU_UNKNOWN_NEW), (UK_UNKNOWN_OLD, UK_UNKNOWN_NEW),
        (RU_GEORGIA_OLD, RU_GEORGIA_NEW), (UK_GEORGIA_OLD, UK_GEORGIA_NEW),
        (RU_KOREA_OLD, RU_KOREA_NEW), (UK_KOREA_OLD, UK_KOREA_NEW),
    ):
        candidate = candidate.replace(old, new)
    validate_catalog(candidate, require_dedup=True)
    return candidate


def patch_any_catalog(source: str) -> str:
    return patch_catalog(source) if catalog_mode(source) == "legacy_v1" else patch_stage_catalog(source)


def ferry_status_present(source: str) -> bool:
    pairs = catalog_pairs(source) if catalog_mode(source) == "legacy_v1" else stage_pairs(source)
    for upper, block in pairs:
        text = visible((upper if CAT_START in block else "") + block)
        if "на пароме" in text or "на поромі" in text:
            return True
    return False


def block_duplicate_issues(block: str, upper: str) -> list[str]:
    issues: list[str] = []
    upper_text = visible(upper)
    spec = re.search(
        r'<div class=["\']ua-cat-vin-v1-spec["\']>(.*?)</div>',
        block, re.I | re.S,
    )
    if spec:
        spec_text = visible(spec.group(1))
        engine = re.search(r"Двигатель:\s*<b>(.*?)</b>", spec.group(1), re.I | re.S)
        video = re.search(r"Видео:\s*<b>(\d+)</b>", spec.group(1), re.I | re.S)
        if engine and visible(engine.group(1)) in upper_text:
            issues.append("ENGINE_REPEATED")
        if video:
            count = video.group(1)
            if int(count) == 0:
                issues.append("ZERO_VIDEO_TECHNICAL_TEXT")
            elif re.search(
                r"(^|\D)" + re.escape(count) +
                r"\s*(?:видео|відео)(?:\D|$)", upper_text,
            ):
                issues.append("VIDEO_REPEATED")
        if not spec_text:
            issues.append("EMPTY_SPEC")
    lower_text = visible(block)
    for label, phrase in (
        ("FERRY_RU_REPEATED", RU_DUPLICATE),
        ("FERRY_UK_REPEATED", UK_DUPLICATE),
        ("KYIV_RU_REPEATED", RU_KYIV_DUPLICATE),
        ("KYIV_UK_REPEATED", UK_KYIV_DUPLICATE),
        ("GEORGIA_RU_WORDING_REPEATED", RU_GEORGIA_OLD),
        ("GEORGIA_UK_WORDING_REPEATED", UK_GEORGIA_OLD),
        ("KOREA_RU_WORDING_REPEATED", RU_KOREA_OLD),
        ("KOREA_UK_WORDING_REPEATED", UK_KOREA_OLD),
    ):
        if visible(phrase) in lower_text:
            issues.append(label)
    copy = re.search(
        r'<div class=["\']ua-cat-vin-v1-copy["\']>(.*?)</div>',
        block, re.I | re.S,
    )
    if copy and not visible(copy.group(1)):
        issues.append("EMPTY_COPY")
    return issues


def stage_duplicate_issues(block: str) -> list[str]:
    issues: list[str] = []
    folded = visible(block)
    if re.search(r"(?:видео|відео)\s*:\s*0(?:\D|$)", folded, re.I):
        issues.append("ZERO_VIDEO_TECHNICAL_TEXT")
    for label, phrase in (
        ("FERRY_RU_REPEATED", RU_DUPLICATE),
        ("FERRY_UK_REPEATED", UK_DUPLICATE),
        ("KYIV_RU_REPEATED", RU_KYIV_DUPLICATE),
        ("KYIV_UK_REPEATED", UK_KYIV_DUPLICATE),
        ("GEORGIA_RU_WORDING_REPEATED", RU_GEORGIA_OLD),
        ("GEORGIA_UK_WORDING_REPEATED", UK_GEORGIA_OLD),
        ("KOREA_RU_WORDING_REPEATED", RU_KOREA_OLD),
        ("KOREA_UK_WORDING_REPEATED", UK_KOREA_OLD),
    ):
        if visible(phrase) in folded:
            issues.append(label)
    for class_name in (
        "ua-stage-card-v2-status", "ua-stage-card-v2-spec",
        "ua-stage-card-v2-vin", "ua-stage-card-v2-photo",
    ):
        count = len(re.findall(
            r'class=["\'][^"\']*\b' + re.escape(class_name) + r'\b', block, re.I
        ))
        if count != 1:
            issues.append("SECTION_COUNT_%s_%d" % (class_name, count))
    for language in ("ru", "uk"):
        values = []
        pattern = (
            r'<span\b[^>]*class=["\'][^"\']*\bua075-' + language
            + r'\b[^"\']*["\'][^>]*>(.*?)</span\s*>'
        )
        for match in re.finditer(pattern, block, re.I | re.S):
            value = visible(match.group(1))
            if len(value) >= 12:
                values.append(value)
        if len(values) != len(set(values)):
            issues.append("REPEATED_%s_EXPRESSION" % language.upper())
    media = re.findall(r"(?:фото|видео|відео)\s*:\s*\d+", folded, re.I)
    if len(media) != len(set(media)):
        issues.append("REPEATED_MEDIA_COUNT")
    return issues


def validate_catalog(source: str, require_dedup: bool = True) -> dict[str, Any]:
    mode = catalog_mode(source)
    style_marker = STYLE_MARKER if mode == "legacy_v1" else STAGE_STYLE_MARKER
    if source.count(style_marker) != 1:
        raise Blocked("CATALOG_STYLE_MARKER_COUNT:" + mode)
    identifiers = []
    issue_map: dict[str, list[str]] = {}
    pairs = catalog_pairs(source) if mode == "legacy_v1" else stage_pairs(source)
    for upper, block in pairs:
        found = re.search(r'data-ua-card=["\'](UA-[0-9]{4,})["\']', block, re.I)
        if not found:
            raise Blocked("CATALOG_BLOCK_IDENTIFIER_MISSING")
        identifier = found.group(1).upper()
        identifiers.append(identifier)
        if not re.search(r"VIN\s*<b>[A-Z0-9]{11,20}</b>", block, re.I):
            raise Blocked("CATALOG_VIN_MISSING:" + identifier)
        issues = (
            block_duplicate_issues(block, upper)
            if mode == "legacy_v1" else stage_duplicate_issues(block)
        )
        if issues:
            issue_map[identifier] = issues
    if len(identifiers) != len(set(identifiers)):
        raise Blocked("CATALOG_DUPLICATE_CARD_BLOCK")
    if "UA-0009" not in identifiers:
        raise Blocked("CATALOG_UA0009_MISSING")
    if not ferry_status_present(source):
        raise Blocked("CATALOG_UPPER_FERRY_STATUS_MISSING")
    if require_dedup and issue_map:
        raise Blocked("CATALOG_SEMANTIC_DUPLICATES:" + json.dumps(issue_map, ensure_ascii=False, sort_keys=True))
    return {
        "mode": mode,
        "card_count": len(identifiers),
        "identifiers": identifiers,
        "duplicate_issues": issue_map,
    }


def catalog_shell(source: str) -> str:
    if catalog_mode(source) == "legacy_v1":
        pattern = re.compile(re.escape(CAT_START) + r".*?" + re.escape(CAT_END), re.S)
    else:
        pattern = re.compile(
            r'<a\b(?=[^>]*\bdata-ua-card=["\']UA-[0-9]{4,}["\'])'
            r'(?=[^>]*\bclass=["\'][^"\']*\bua-stage-card-v2\b)[^>]*>.*?</a\s*>',
            re.I | re.S,
        )
    return pattern.sub(
        lambda match: "<!-- CARD-SHELL:" + (
            re.search(r'data-ua-card=["\'](UA-[0-9]{4,})["\']', match.group(0), re.I).group(1)
            if re.search(r'data-ua-card=["\'](UA-[0-9]{4,})["\']', match.group(0), re.I)
            else "MISSING"
        ) + " -->",
        source,
    )


def source_snapshot() -> dict[str, dict[str, Any]]:
    result = {}
    for path in SOURCE_PATHS:
        data = read_bytes(path)
        source = data.decode("utf-8")
        result[str(path)] = {
            "sha256": sha256(data),
            "bytes": len(data),
            "marker": SOURCE_MARKER in source,
            "task074_marker": PREVIOUS_SOURCE_MARKER in source,
            "style_marker": source.count(STYLE_MARKER),
        }
    return result


def optional_stage_guard_snapshot() -> dict[str, Any]:
    exists = {path.name: path.is_file() for path in (CORE_PATH, RUNTIME_PATH)}
    if any(exists.values()) and not all(exists.values()):
        raise Blocked("STAGE_GUARD_PARTIAL_INSTALL:" + json.dumps(exists, sort_keys=True))
    result: dict[str, Any] = {"installed": all(exists.values()), "files": {}}
    for path in (CORE_PATH, RUNTIME_PATH, PUBLISHER_PATH):
        if not path.is_file():
            continue
        data = read_bytes(path)
        source = data.decode("utf-8")
        result["files"][str(path)] = {
            "sha256": sha256(data),
            "bytes": len(data),
            "dedup_marker": CORE_MARKER in source if path == CORE_PATH else None,
        }
    if result["installed"]:
        core = CORE_PATH.read_text(encoding="utf-8")
        if CORE_MARKER in core:
            validate_core_source(core)
        elif git_blob_id(core.encode()) != EXPECTED_CORE_BASE_BLOB:
            raise Blocked("CORE_STAGE_GUARD_UNKNOWN_BASE")
        runtime = RUNTIME_PATH.read_text(encoding="utf-8")
        if "UA-0011-CATALOG-FERRY-REPAIR-001-V1.0" not in runtime:
            raise Blocked("STAGE_RUNTIME_CONTRACT_MISSING")
    return result


def catalog_snapshot() -> dict[str, dict[str, Any]]:
    result = {}
    for path in CATALOG_PATHS:
        data = read_bytes(path)
        source = data.decode("utf-8")
        analysis = validate_catalog(source, require_dedup=False)
        style_marker = STYLE_MARKER if analysis["mode"] == "legacy_v1" else STAGE_STYLE_MARKER
        result[str(path)] = {
            "sha256": sha256(data),
            "bytes": len(data),
            "mode": analysis["mode"],
            "style_marker": source.count(style_marker),
            "canonical_blocks": analysis["card_count"],
            "canonical_identifiers": analysis["identifiers"],
            "duplicate_issues": analysis["duplicate_issues"],
            "ua0009": "UA-0009" in analysis["identifiers"],
            "ferry_status": ferry_status_present(source),
        }
    return result


def backup(paths: list[pathlib.Path]) -> pathlib.Path:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = BACKUP_PARENT / (stamp + "-" + hashlib.sha256(os.urandom(32)).hexdigest()[:12])
    for path in paths:
        target = root / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    return root


def restore(root: pathlib.Path, paths: list[pathlib.Path]) -> list[str]:
    changed = []
    for path in paths:
        saved = root / path.relative_to(ROOT)
        if not saved.is_file():
            raise Blocked("ROLLBACK_BACKUP_MISSING:" + str(saved))
        old = read_bytes(saved)
        if not path.exists() or read_bytes(path) != old:
            atomic_write(path, old, saved.stat().st_mode & 0o777)
            changed.append(str(path))
    return changed


def inspect_base() -> dict[str, Any]:
    db = db_snapshot()
    if (
        db["quick_check"] != "ok"
        or db["count"] < 11
        or not db["ua0009"]
        or len(db["identifiers"]) != len(set(db["identifiers"]))
    ):
        raise Blocked("DATABASE_INVARIANT")
    sources = source_snapshot()
    for path, item in sources.items():
        if not item["marker"] and item["sha256"] != EXPECTED_BASE_SHA256[path]:
            raise Blocked("SOURCE_BASE_SHA_MISMATCH:" + pathlib.Path(path).name)
        if not item["task074_marker"] or item["style_marker"] != 1:
            raise Blocked("SOURCE_TASK074_INVARIANT:" + pathlib.Path(path).name)
        if item["marker"]:
            validate_source(pathlib.Path(path).read_text(encoding="utf-8"))
    catalogs = catalog_snapshot()
    catalog_sets = [set(item["canonical_identifiers"]) for item in catalogs.values()]
    catalog_modes = {item["mode"] for item in catalogs.values()}
    if len(catalog_sets) != 2 or catalog_sets[0] != catalog_sets[1]:
        raise Blocked("CATALOG_VARIANT_ID_MISMATCH")
    if len(catalog_modes) != 1:
        raise Blocked("CATALOG_VARIANT_RENDERER_MISMATCH")
    public_ids = catalog_sets[0]
    database_ids = set(db["identifiers"])
    for path, item in catalogs.items():
        if (
            item["canonical_blocks"] < 11
            or not set(item["canonical_identifiers"]).issubset(database_ids)
            or not item["ua0009"]
            or not item["ferry_status"]
        ):
            raise Blocked(
                "CATALOG_BASE_INVARIANT:" + pathlib.Path(path).name + ":"
                + json.dumps(item, ensure_ascii=False, sort_keys=True)
            )
    if "UA-0011" not in public_ids:
        raise Blocked("CATALOG_UA0011_MISSING")
    stage_guard = optional_stage_guard_snapshot()
    mode = next(iter(catalog_modes))
    if mode == "stage_v2" and not stage_guard["installed"]:
        raise Blocked("STAGE_CATALOG_WITHOUT_RUNTIME_GUARD")
    return {
        "database": db,
        "sources": sources,
        "stage_guard": stage_guard,
        "catalogs": catalogs,
        "protected_pages": protected_pages_snapshot(),
    }


def run_shadow() -> dict[str, Any]:
    before = inspect_base()
    candidate_sources = {}
    for path in SOURCE_PATHS:
        source = path.read_text(encoding="utf-8")
        candidate = patch_generator_source(source)
        candidate_sources[str(path)] = {"sha256": sha256(candidate.encode()), "changed": candidate != source}
    candidate_core = None
    if before["stage_guard"]["installed"]:
        source = CORE_PATH.read_text(encoding="utf-8")
        candidate = patch_core_source(source)
        candidate_core = {
            "sha256": sha256(candidate.encode()),
            "changed": candidate != source,
            "marker": CORE_MARKER in candidate,
        }
    candidate_catalogs = {}
    for path in CATALOG_PATHS:
        source = path.read_text(encoding="utf-8")
        candidate = patch_any_catalog(source)
        if catalog_shell(candidate) != catalog_shell(source):
            raise Blocked("CATALOG_OUTSIDE_CARD_BLOCKS_CHANGED:" + path.name)
        candidate_catalogs[str(path)] = {
            "sha256": sha256(candidate.encode()),
            **validate_catalog(candidate, require_dedup=True),
        }
    after = inspect_base()
    if before != after:
        raise Blocked("SHADOW_PRODUCTION_CHANGED")
    return {
        "contract_id": CONTRACT, "status": "PASS", "mode": "SHADOW",
        "production_write": False, "crm_db_write": False,
        "before": before, "candidate_sources": candidate_sources,
        "candidate_core": candidate_core, "candidate_catalogs": candidate_catalogs,
    }


def run_install() -> dict[str, Any]:
    before = inspect_base()
    paths = SOURCE_PATHS + CATALOG_PATHS
    if before["stage_guard"]["installed"]:
        paths = paths + [CORE_PATH]
    backup_root = backup(paths)
    changed: list[str] = []
    try:
        for path in SOURCE_PATHS:
            data = read_bytes(path)
            candidate = patch_generator_source(data.decode("utf-8")).encode()
            if candidate != data:
                atomic_write(path, candidate, path.stat().st_mode & 0o777)
                changed.append(str(path))
        if before["stage_guard"]["installed"]:
            data = read_bytes(CORE_PATH)
            candidate = patch_core_source(data.decode("utf-8")).encode()
            if candidate != data:
                atomic_write(CORE_PATH, candidate, CORE_PATH.stat().st_mode & 0o777)
                changed.append(str(CORE_PATH))
        for path in CATALOG_PATHS:
            data = read_bytes(path)
            old_source = data.decode("utf-8")
            candidate_source = patch_any_catalog(old_source)
            if catalog_shell(candidate_source) != catalog_shell(old_source):
                raise Blocked("CATALOG_OUTSIDE_CARD_BLOCKS_CHANGED:" + path.name)
            candidate = candidate_source.encode()
            if candidate != data:
                atomic_write(path, candidate, path.stat().st_mode & 0o777)
                changed.append(str(path))
        after = inspect_base()
        if before["database"] != after["database"]:
            raise Blocked("DATABASE_CHANGED")
        if before["protected_pages"] != after["protected_pages"]:
            raise Blocked("PROTECTED_CARD_PAGES_CHANGED")
        before_ids = {
            path: item["canonical_identifiers"] for path, item in before["catalogs"].items()
        }
        after_ids = {
            path: item["canonical_identifiers"] for path, item in after["catalogs"].items()
        }
        if before_ids != after_ids:
            raise Blocked("CATALOG_CARD_SET_CHANGED")
        for item in after["catalogs"].values():
            if item["duplicate_issues"]:
                raise Blocked("CATALOG_DUPLICATE_TEXT_AFTER")
            if item["style_marker"] != 1:
                raise Blocked("CATALOG_STYLE_AFTER")
        if before["stage_guard"]["installed"]:
            validate_core_source(CORE_PATH.read_text(encoding="utf-8"))
        return {
            "contract_id": CONTRACT, "status": "PASS", "mode": "INSTALL",
            "production_write": True, "crm_db_write": False,
            "backup_root": str(backup_root), "changed_paths": changed,
            "managed_paths": [str(path) for path in paths],
            "before": before, "after": after,
        }
    except Exception:
        restore(backup_root, paths)
        raise


def run_rollback() -> dict[str, Any]:
    receipt = json.loads(RECEIPTS["install"].read_text(encoding="utf-8"))
    backup_root = pathlib.Path(str(receipt.get("backup_root") or ""))
    if BACKUP_PARENT not in backup_root.parents:
        raise Blocked("ROLLBACK_SCOPE_INVALID")
    allowed = set(SOURCE_PATHS + CATALOG_PATHS + [CORE_PATH])
    paths = [pathlib.Path(value) for value in receipt.get("managed_paths") or []]
    if not paths or any(path not in allowed for path in paths):
        raise Blocked("ROLLBACK_MANAGED_PATHS_INVALID")
    changed = restore(backup_root, paths)
    return {
        "contract_id": CONTRACT, "status": "PASS", "mode": "ROLLBACK",
        "production_write": True, "crm_db_write": False,
        "backup_root": str(backup_root), "restored": changed,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("shadow", "install", "rollback"))
    args = parser.parse_args()
    REMOTE_ROOT.mkdir(parents=True, exist_ok=True)
    LOCK_PATH.touch(exist_ok=True)
    receipt = RECEIPTS[args.mode]
    value: dict[str, Any]
    with LOCK_PATH.open("r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            value = {"shadow": run_shadow, "install": run_install, "rollback": run_rollback}[args.mode]()
        except Exception as exc:
            value = {
                "contract_id": CONTRACT, "status": "FAIL", "mode": args.mode.upper(),
                "production_write": args.mode != "shadow", "crm_db_write": False,
                "errors": [type(exc).__name__ + ":" + str(exc)],
            }
        atomic_json(receipt, value)
    print(json.dumps({"status": value["status"], "mode": value["mode"], "errors": value.get("errors", [])}, ensure_ascii=False))
    return 0 if value["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

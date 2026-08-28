#!/usr/bin/env python3
"""TASK 064: permanently restore diagnostics on every UA ART card.

The production entry point is intentionally self-contained and stdlib-only.
It discovers published cards from the read-only CRM, prepares every candidate
before the first write, creates a complete backup, installs atomically, and
rolls every changed file back if any invariant fails.
"""
from __future__ import annotations

import datetime as dt
import fcntl
import glob
import hashlib
import html
import io
import json
import os
import pathlib
import re
import sqlite3
import stat
import sys
import tempfile
import urllib.parse
from typing import Any


MODE = "TASK_064_DIAGNOSTICS_PERMANENT_ATOMIC_REPAIR"
ROOT = "/home/Carix"
VIDEO_ROOT = ROOT + "/video"
SITE_ROOT = ROOT + "/site"
CRM_PATH = ROOT + "/crm.db"
GENERATOR_PATH = ROOT + "/stranica.py"
YADRO_PATH = ROOT + "/yadro.py"
ETALON_ROOT = ROOT + "/etalon"
BACKUP_PARENT = ROOT + "/autopilot_inbox/cloud/task_064_diagnostics/backups"
LOCK_PATH = ROOT + "/.task064_diagnostics.lock"
POLICY_MARKER = "UA-DIAG-PERMANENT-V1"
CARD_MARKER = "<!--ua-art-diagnostics-permanent-v1-->"
EMPTY_RU = "Материалы пока не добавлены"
EMPTY_UK = "Матеріали поки не додані"
MAX_FILE_BYTES = 20 * 1024 * 1024
CARD_ID = re.compile(r"^UA-[0-9]{4,}$")


class RepairBlocked(RuntimeError):
    pass


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read(path: str, *, required: bool = True) -> bytes | None:
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        if required:
            raise RepairBlocked("missing_file:" + path)
        return None
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise RepairBlocked("unsafe_file:" + path)
    if info.st_size <= 0 or info.st_size > MAX_FILE_BYTES:
        raise RepairBlocked("invalid_file_size:" + path)
    with open(path, "rb") as handle:
        data = handle.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise RepairBlocked("file_too_large:" + path)
    return data


def _safe_parent(path: str) -> str:
    root = os.path.realpath(ROOT)
    parent = os.path.realpath(os.path.dirname(path))
    if os.path.commonpath((root, parent)) != root:
        raise RepairBlocked("path_escape:" + path)
    os.makedirs(parent, mode=0o755, exist_ok=True)
    return parent


def _fsync_dir(path: str) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write(path: str, data: bytes, mode: int = 0o644) -> None:
    parent = _safe_parent(path)
    if os.path.lexists(path) and os.path.islink(path):
        raise RepairBlocked("symlink_target:" + path)
    descriptor, temporary = tempfile.mkstemp(prefix=".task064-", dir=parent)
    try:
        os.fchmod(descriptor, stat.S_IMODE(mode))
        offset = 0
        while offset < len(data):
            offset += os.write(descriptor, data[offset:])
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, path)
        _fsync_dir(parent)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if os.path.exists(temporary):
            os.unlink(temporary)


def _published_rows() -> tuple[list[dict[str, Any]], str]:
    crm_before = _read(CRM_PATH)
    assert crm_before is not None
    connection = sqlite3.connect("file:" + CRM_PATH + "?mode=ro", uri=True, timeout=20)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        check = connection.execute("PRAGMA quick_check").fetchone()
        if not check or str(check[0]).lower() != "ok":
            raise RepairBlocked("crm_quick_check_failed")
        columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(cars)")}
        if not {"auto_number", "published"}.issubset(columns):
            raise RepairBlocked("crm_schema_missing_required_columns")
        order = "id" if "id" in columns else "auto_number"
        rows = [dict(row) for row in connection.execute(
            "SELECT * FROM cars WHERE published=1 ORDER BY " + order
        )]
    finally:
        connection.close()
    if not rows or len(rows) > 100:
        raise RepairBlocked("published_card_count_invalid")
    identifiers = []
    for row in rows:
        identifier = str(row.get("auto_number") or "").strip().upper()
        if not CARD_ID.fullmatch(identifier):
            raise RepairBlocked("invalid_card_id:" + identifier)
        row["auto_number"] = identifier
        identifiers.append(identifier)
    if len(set(identifiers)) != len(identifiers):
        raise RepairBlocked("duplicate_card_id")
    return rows, _sha(crm_before)


def _patch_generator(source: str) -> str:
    """Make the canonical generator unconditional and isolate diag filenames."""
    if POLICY_MARKER in source:
        _validate_generator(source)
        return source

    old_base = '''def est_diagnostika(m):
    """Есть ли хоть что-то для отдельной страницы диагностики."""
    if (m.get("diag_text") or "").strip():
        return True
    if (m.get("diag_link") or "").strip():
        return True
    foto, video = kadry_diagnostiki(m)
    return bool(foto or video)
'''
    new_base = '''def est_diagnostika(m=None, *argumenty, **imenovannye):
    """Диагностика является обязательным разделом каждой карточки."""
    return True
'''
    if source.count(old_base) != 1:
        raise RepairBlocked("generator_base_diagnostics_pattern_changed")
    source = source.replace(old_base, new_base, 1)

    old_variants = '        celi += glob.glob(os.path.join(papka, imya_bez + "-*.html"))'
    new_variants = '''        for _variant in glob.glob(os.path.join(papka, imya_bez + "-*.html")):
            # UA-DIAG-FILENAME-GUARD-V1: запись карточки не имеет права
            # перезаписывать её отдельную страницу диагностики.
            _base = os.path.basename(_variant)
            if (str(imya_bez).startswith("UA-")
                    and not str(imya_bez).endswith("-diag")
                    and _base.startswith(str(imya_bez) + "-diag")):
                continue
            celi.append(_variant)'''
    if source.count(old_variants) != 1:
        raise RepairBlocked("generator_variant_glob_pattern_changed")
    source = source.replace(old_variants, new_variants, 1)

    old_etalon = '''    for put in glob.glob(os.path.join(papka, "**", imya_bez + "*.html"), recursive=True):
        if "otklonennye" in put:
            continue'''
    new_etalon = '''    for put in glob.glob(os.path.join(papka, "**", imya_bez + "*.html"), recursive=True):
        # UA-DIAG-ETALON-GUARD-V1: эталон карточки и эталон диагностики
        # независимы; карточка не может затереть *-diag.html.
        _base = os.path.basename(put)
        if (str(imya_bez).startswith("UA-")
                and not str(imya_bez).endswith("-diag")
                and _base.startswith(str(imya_bez) + "-diag")):
            continue
        if "otklonennye" in put:
            continue'''
    if source.count(old_etalon) != 1:
        raise RepairBlocked("generator_etalon_glob_pattern_changed")
    source = source.replace(old_etalon, new_etalon, 1)

    final_pattern = re.compile(
        r"\n# ---------------------------------------------------------------------------\n"
        r"# UA-FIX947: строгое условие показа диагностики\.[\s\S]*\Z"
    )
    replacement = '''
# ---------------------------------------------------------------------------
# UA-DIAG-PERMANENT-V1: обязательная диагностика для всех старых и новых карт.
# Наличие материалов меняет только содержимое страницы: пустое состояние
# является нормальным. Этот финальный override запрещено делать условным.
# ---------------------------------------------------------------------------
DIAGNOSTICS_ALWAYS_VISIBLE = True


def est_diagnostika(m=None, *argumenty, **imenovannye):
    """Всегда создаём кнопку и companion-page; пустые данные не скрывают UI."""
    return True
'''
    source, count = final_pattern.subn(replacement, source, count=1)
    if count != 1:
        raise RepairBlocked("generator_final_override_pattern_changed")
    _validate_generator(source)
    return source


def _validate_generator(source: str) -> None:
    try:
        compile(source, GENERATOR_PATH, "exec")
    except SyntaxError as exc:
        raise RepairBlocked("generator_compile_failed") from exc
    required = (
        POLICY_MARKER,
        "DIAGNOSTICS_ALWAYS_VISIBLE = True",
        "UA-DIAG-FILENAME-GUARD-V1",
        "UA-DIAG-ETALON-GUARD-V1",
        "def est_diagnostika(m=None, *argumenty, **imenovannye):",
    )
    for marker in required:
        if marker not in source:
            raise RepairBlocked("generator_policy_missing:" + marker)
    if 'celi += glob.glob(os.path.join(papka, imya_bez + "-*.html"))' in source:
        raise RepairBlocked("generator_unsafe_variant_glob_remains")
    if "UA-FIX947: строгое условие показа диагностики" in source:
        raise RepairBlocked("generator_legacy_override_remains")


def _diag_anchor(identifier: str) -> str:
    return (
        CARD_MARKER
        + '<a class="mcf-diag-cta" href="%s-diag.html" '
          'style="display:flex;align-items:center;gap:12px;margin:14px 0;'
          'padding:15px 16px;border-radius:14px;text-decoration:none;'
          'background:linear-gradient(180deg,rgba(212,175,55,.20),'
          'rgba(212,175,55,.08));border:1px solid rgba(212,175,55,.55);'
          'color:#f4e3ae"><span style="font-size:22px;line-height:1">🔧</span>'
          '<span style="flex:1"><span style="display:block;font-weight:800;'
          'font-size:16px">Открыть комплексную диагностику →</span>'
          '<span style="display:block;font-size:13px;opacity:.85;margin-top:3px">'
          'ЛКП · OBD · ходовая · фото · видео</span></span>'
          '<span style="font-size:20px;opacity:.8">›</span></a>' % identifier
    )


def _diagnostic_link_count(source: str, identifier: str) -> int:
    return len(re.findall(
        r'href=["\']' + re.escape(identifier) + r'-diag\.html(?:\?[^"\']*)?["\']',
        source,
        flags=re.IGNORECASE,
    ))


def _ensure_diag_anchor(source: str, identifier: str) -> str:
    if "</html>" not in source.lower() or identifier not in source:
        raise RepairBlocked("invalid_card_html:" + identifier)
    pattern = re.compile(
        r'<a\b(?=[^>]*(?:\bclass=["\'][^"\']*\bmcf-diag-cta\b[^"\']*["\']'
        r'|\bhref=["\']' + re.escape(identifier)
        + r'-diag\.html(?:\?[^"\']*)?["\']))[^>]*>.*?</a>',
        flags=re.IGNORECASE | re.DOTALL,
    )
    cleaned = pattern.sub("", source).replace(CARD_MARKER, "")
    purchase = re.search(
        r'<a\b(?=[^>]*\bclass=["\'][^"\']*(?:kn_kupit|dejstvie|knp\s+zol)'
        r'[^"\']*["\'])[^>]*>',
        cleaned,
        flags=re.IGNORECASE,
    )
    if purchase is None:
        purchase = re.search(
            r'<a\b[^>]*href=["\']katalog\.html(?:\?[^"\']*)?["\'][^>]*>',
            cleaned,
            flags=re.IGNORECASE,
        )
    if purchase is None:
        raise RepairBlocked("diagnostics_anchor_not_found:" + identifier)
    candidate = cleaned[:purchase.start()] + _diag_anchor(identifier) + cleaned[purchase.start():]
    if _diagnostic_link_count(candidate, identifier) != 1:
        raise RepairBlocked("diagnostics_link_count_invalid:" + identifier)
    if candidate.count(CARD_MARKER) != 1 or candidate.count('class="mcf-diag-cta"') != 1:
        raise RepairBlocked("diagnostics_marker_count_invalid:" + identifier)
    return candidate


def _first_value(row: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _regular_media(identifier: str) -> tuple[list[str], list[str], str]:
    media_root = os.path.join(VIDEO_ROOT, "diag", identifier)
    photos: list[str] = []
    videos: list[str] = []
    if os.path.isdir(media_root) and not os.path.islink(media_root):
        for name in sorted(os.listdir(media_root)):
            path = os.path.join(media_root, name)
            try:
                info = os.lstat(path)
            except OSError:
                continue
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_size <= 0:
                continue
            suffix = pathlib.Path(name).suffix.lower()
            url = "/video/diag/%s/%s" % (
                urllib.parse.quote(identifier, safe=""), urllib.parse.quote(name, safe="")
            )
            if suffix in {".jpg", ".jpeg", ".png", ".webp"} and len(photos) < 50:
                photos.append(url)
            elif suffix in {".mp4", ".webm", ".mov"} and len(videos) < 10:
                videos.append(url)
    poster = photos[0] if photos else ""
    if not poster:
        photo_root = os.path.join(VIDEO_ROOT, "foto", identifier)
        if os.path.isdir(photo_root) and not os.path.islink(photo_root):
            for name in sorted(os.listdir(photo_root)):
                path = os.path.join(photo_root, name)
                try:
                    info = os.lstat(path)
                except OSError:
                    continue
                if (stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode)
                        and info.st_size > 0
                        and pathlib.Path(name).suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}):
                    poster = "/video/foto/%s/%s" % (
                        urllib.parse.quote(identifier, safe=""), urllib.parse.quote(name, safe="")
                    )
                    break
    if not poster:
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720">'
            '<rect width="100%%" height="100%%" fill="#0b1a2b"/>'
            '<text x="50%%" y="46%%" text-anchor="middle" fill="#d4af37" '
            'font-family="Arial" font-size="54">UA ART COMPANY</text>'
            '<text x="50%%" y="57%%" text-anchor="middle" fill="#e8eef6" '
            'font-family="Arial" font-size="34">%s · диагностика</text></svg>'
            % html.escape(identifier)
        )
        poster = "data:image/svg+xml," + urllib.parse.quote(svg, safe="")
    return photos, videos, poster


def _valid_diag_page(source: str, identifier: str) -> bool:
    lowered = source.lower()
    if "</html>" not in lowered or identifier.lower() not in lowered:
        return False
    if "диагност" not in lowered and "diagnostic" not in lowered:
        return False
    if "mcf-diag-cta" in lowered:
        return False
    return bool(re.search(
        r'href=["\']' + re.escape(identifier) + r'\.html(?:\?[^"\']*)?["\']',
        source,
        flags=re.IGNORECASE,
    ))


def _text_or_empty(value: str) -> str:
    if not value:
        return '<div class="empty">%s</div>' % EMPTY_RU
    lines = [line.strip() for line in value.replace("\r", "").split("\n") if line.strip()]
    return '<div class="copy">%s</div>' % "<br>".join(html.escape(line) for line in lines)


def _build_diag_page(row: dict[str, Any]) -> str:
    identifier = str(row["auto_number"])
    title = " ".join(
        str(row.get(key) or "").strip() for key in ("brand", "model", "year")
        if str(row.get(key) or "").strip()
    ) or identifier
    body = _first_value(row, ("diag_kuzov", "diag_lkp", "lkp_text", "diag_text"))
    technical = _first_value(row, ("diag_teh", "diag_tehsostoyanie", "diag_technical"))
    obd_text = _first_value(row, ("diag_obd", "diag_electronics"))
    obd_url = _first_value(row, ("diag_link",))
    photos, videos, poster = _regular_media(identifier)
    has_materials = bool(body or technical or obd_text or obd_url or photos or videos)
    if obd_url and not re.match(r"^https?://", obd_url, flags=re.IGNORECASE):
        obd_url = ""

    media_parts: list[str] = []
    if photos:
        media_parts.append('<div class="photos">')
        for index, url in enumerate(photos, 1):
            media_parts.append(
                '<img src="%s" loading="lazy" alt="%s · фото диагностики %d">'
                % (html.escape(url, quote=True), html.escape(identifier), index)
            )
        media_parts.append("</div>")
    if videos:
        for url in videos:
            media_parts.append(
                '<video controls playsinline preload="metadata" poster="%s">'
                '<source src="%s"></video>'
                % (html.escape(poster, quote=True), html.escape(url, quote=True))
            )
    media_html = "".join(media_parts) if media_parts else '<div class="empty">%s</div>' % EMPTY_RU
    obd_html = _text_or_empty(obd_text)
    if obd_url:
        obd_html += (
            '<a class="button" href="%s" target="_blank" rel="noopener">Открыть OBD-отчёт</a>'
            % html.escape(obd_url, quote=True)
        )
    status_text = "Проверка выполнена" if has_materials else EMPTY_RU
    status_class = "status ready" if has_materials else "status"

    return '''<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Комплексная диагностика %(id)s — UA ART COMPANY</title>
<style>
:root{--bg:#081421;--card:#102238;--line:rgba(212,175,55,.42);--gold:#d4af37;--text:#edf3fa;--muted:#aab7c7}
*{box-sizing:border-box}body{margin:0;background:linear-gradient(180deg,#07111d,#0b1b2d);color:var(--text);font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.wrap{width:min(760px,calc(100%% - 28px));margin:0 auto;padding:18px 0 44px}.brand{display:flex;align-items:center;gap:11px;padding:14px 0 20px;color:var(--gold);font-weight:900;letter-spacing:.7px}.logo{display:grid;place-items:center;width:45px;height:45px;border:1px solid var(--gold);border-radius:50%%}.hero,.section{border:1px solid var(--line);background:rgba(16,34,56,.92);border-radius:16px;padding:18px;margin-bottom:13px;box-shadow:0 14px 35px rgba(0,0,0,.18)}.id{color:var(--gold);font-size:13px;font-weight:800}.hero h1{margin:6px 0 2px;font-size:clamp(25px,6vw,38px)}.model{color:var(--muted)}.status{display:inline-flex;margin-top:14px;padding:8px 11px;border-radius:999px;background:rgba(170,183,199,.1);color:var(--muted);font-size:13px;font-weight:750}.ready{color:#77d59d;background:rgba(65,170,110,.12)}.section h2{display:flex;align-items:center;gap:10px;margin:0 0 12px;font-size:18px}.num{display:grid;place-items:center;width:29px;height:29px;border:1px solid var(--gold);border-radius:50%%;color:var(--gold);font-size:13px}.empty{padding:13px;border-radius:11px;background:rgba(170,183,199,.07);color:var(--muted)}.copy{white-space:normal}.button,.back{display:block;margin-top:13px;padding:14px;border:1px solid var(--gold);border-radius:12px;color:#f5df98;text-align:center;text-decoration:none;font-weight:800}.photos{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}.photos img{width:100%%;aspect-ratio:4/3;object-fit:cover;border-radius:10px;background:#07111d}video{display:block;width:100%%;max-height:70vh;margin-top:10px;border-radius:12px;background:#07111d}.note{margin:17px 0;color:var(--muted);text-align:center;font-size:13px}@media(max-width:520px){.wrap{width:min(100%% - 20px,760px)}.hero,.section{padding:15px}.photos{grid-template-columns:1fr}}
</style></head><body><main class="wrap">%(marker)s
<div class="brand"><span class="logo">UA</span><span>UA ART COMPANY</span></div>
<section class="hero"><div class="id">%(id)s</div><h1>Комплексная диагностика</h1><div class="model">%(title)s</div><div class="%(status_class)s">%(status)s</div></section>
<section class="section"><h2><span class="num">1</span>Кузов и безопасность</h2>%(body)s</section>
<section class="section"><h2><span class="num">2</span>Техническое состояние</h2>%(technical)s</section>
<section class="section"><h2><span class="num">3</span>Электроника и OBD</h2>%(obd)s</section>
<section class="section"><h2><span class="num">4</span>Фото и видео проверки</h2>%(media)s</section>
<div class="note">Все материалы относятся только к автомобилю %(id)s</div>
<a class="back" href="%(id)s.html">← Вернуться к автомобилю</a>
</main></body></html>''' % {
        "id": html.escape(identifier),
        "title": html.escape(title),
        "marker": CARD_MARKER,
        "status_class": status_class,
        "status": status_text,
        "body": _text_or_empty(body),
        "technical": _text_or_empty(technical),
        "obd": obd_html,
        "media": media_html,
    }


def _mode_for(path: str) -> int:
    try:
        return stat.S_IMODE(os.lstat(path).st_mode)
    except FileNotFoundError:
        return 0o644


def _collect_candidates(rows: list[dict[str, Any]], patched_generator: bytes) -> dict[str, bytes]:
    candidates: dict[str, bytes] = {GENERATOR_PATH: patched_generator}
    by_id = {str(row["auto_number"]): row for row in rows}
    cards: dict[tuple[str, str], str] = {}
    diagnostics: dict[tuple[str, str], str] = {}

    for identifier, row in by_id.items():
        video_card_path = os.path.join(VIDEO_ROOT, identifier + ".html")
        video_source_bytes = _read(video_card_path)
        assert video_source_bytes is not None
        try:
            video_source = video_source_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RepairBlocked("card_not_utf8:" + identifier) from exc

        for root in (VIDEO_ROOT, SITE_ROOT):
            path = os.path.join(root, identifier + ".html")
            source_bytes = _read(path, required=False)
            source = video_source if source_bytes is None else source_bytes.decode("utf-8")
            cards[(root, identifier)] = _ensure_diag_anchor(source, identifier)

        valid_pages: dict[str, str] = {}
        for root in (VIDEO_ROOT, SITE_ROOT):
            path = os.path.join(root, identifier + "-diag.html")
            source_bytes = _read(path, required=False)
            if source_bytes is not None:
                try:
                    source = source_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    source = ""
                if _valid_diag_page(source, identifier):
                    valid_pages[root] = source
        generated = _build_diag_page(row)
        for root in (VIDEO_ROOT, SITE_ROOT):
            other = SITE_ROOT if root == VIDEO_ROOT else VIDEO_ROOT
            diagnostics[(root, identifier)] = valid_pages.get(root) or valid_pages.get(other) or generated

        for root in (VIDEO_ROOT, SITE_ROOT):
            card = cards[(root, identifier)]
            diag = diagnostics[(root, identifier)]
            candidates[os.path.join(root, identifier + ".html")] = card.encode("utf-8")
            candidates[os.path.join(root, identifier + "-diag.html")] = diag.encode("utf-8")
            for variant in glob.glob(os.path.join(root, identifier + "-*.html")):
                if os.path.islink(variant):
                    raise RepairBlocked("symlink_variant:" + variant)
                name = os.path.basename(variant)
                candidates[variant] = (diag if name.startswith(identifier + "-diag") else card).encode("utf-8")

        if os.path.isdir(ETALON_ROOT) and not os.path.islink(ETALON_ROOT):
            for path in glob.glob(os.path.join(ETALON_ROOT, "**", identifier + "*.html"), recursive=True):
                if os.path.islink(path):
                    raise RepairBlocked("symlink_etalon:" + path)
                name = os.path.basename(path)
                candidates[path] = (
                    diagnostics[(VIDEO_ROOT, identifier)]
                    if name.startswith(identifier + "-diag")
                    else cards[(VIDEO_ROOT, identifier)]
                ).encode("utf-8")
    return candidates


def _validate_installed(rows: list[dict[str, Any]], generator_sha: str) -> list[dict[str, Any]]:
    generator = _read(GENERATOR_PATH)
    assert generator is not None
    if _sha(generator) != generator_sha:
        raise RepairBlocked("generator_readback_mismatch")
    _validate_generator(generator.decode("utf-8"))
    results = []
    for row in rows:
        identifier = str(row["auto_number"])
        item = {"id": identifier, "roots": {}, "empty_state": None}
        for root in (VIDEO_ROOT, SITE_ROOT):
            card_path = os.path.join(root, identifier + ".html")
            diag_path = os.path.join(root, identifier + "-diag.html")
            card_bytes = _read(card_path)
            diag_bytes = _read(diag_path)
            assert card_bytes is not None and diag_bytes is not None
            card = card_bytes.decode("utf-8")
            diag = diag_bytes.decode("utf-8")
            if _diagnostic_link_count(card, identifier) != 1:
                raise RepairBlocked("installed_card_link_count:" + card_path)
            if card.count(CARD_MARKER) != 1:
                raise RepairBlocked("installed_card_marker_count:" + card_path)
            if not _valid_diag_page(diag, identifier):
                raise RepairBlocked("installed_diag_invalid:" + diag_path)
            item["roots"][os.path.basename(root)] = {
                "card_sha256": _sha(card_bytes),
                "diag_sha256": _sha(diag_bytes),
                "diag_links": 1,
            }
            if root == VIDEO_ROOT:
                item["empty_state"] = EMPTY_RU in diag or EMPTY_UK in diag
        results.append(item)
    return results


def run_repair() -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "mode": MODE,
        "status": "BLOCKED",
        "generated_at_utc": _utc_now(),
        "production_write": False,
        "production_files_changed": 0,
        "crm_write": False,
        "db_write": False,
        "service_reload": False,
        "rollback_attempted": False,
        "rollback_completed": False,
        "backup_root": "",
        "crm_sha256_before": "",
        "crm_sha256_after": "",
        "generator_sha256_before": "",
        "generator_sha256_after": "",
        "yadro_sha256": "",
        "card_ids": [],
        "cards": [],
        "changed_paths": [],
        "errors": [],
    }
    before: dict[str, bytes | None] = {}
    changed: list[str] = []
    backup_root = ""
    try:
        rows, crm_sha = _published_rows()
        identifiers = [str(row["auto_number"]) for row in rows]
        receipt["card_ids"] = identifiers
        receipt["crm_sha256_before"] = crm_sha

        generator_bytes = _read(GENERATOR_PATH)
        yadro_bytes = _read(YADRO_PATH)
        assert generator_bytes is not None and yadro_bytes is not None
        receipt["generator_sha256_before"] = _sha(generator_bytes)
        receipt["yadro_sha256"] = _sha(yadro_bytes)
        yadro_text = yadro_bytes.decode("utf-8")
        if ('href=\\"%s-diag.html\\"' not in yadro_text
                or "Комплексная диагностика авто" not in yadro_text):
            raise RepairBlocked("yadro_future_card_contract_missing")

        patched_text = _patch_generator(generator_bytes.decode("utf-8"))
        patched_bytes = patched_text.encode("utf-8")
        candidates = _collect_candidates(rows, patched_bytes)

        # Prepare and validate the entire candidate set before the first write.
        for path, data in candidates.items():
            if not data or len(data) > MAX_FILE_BYTES:
                raise RepairBlocked("candidate_size_invalid:" + path)
            if path.endswith(".py"):
                compile(data.decode("utf-8"), path, "exec")
            elif "</html>" not in data[-800:].decode("utf-8", errors="ignore").lower():
                raise RepairBlocked("candidate_html_truncated:" + path)
            before[path] = _read(path, required=False)

        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_root = os.path.join(BACKUP_PARENT, stamp + "-" + _sha(patched_bytes)[:10])
        os.makedirs(backup_root, mode=0o700, exist_ok=False)
        receipt["backup_root"] = backup_root
        manifest = []
        for path in sorted(candidates):
            old = before[path]
            rel = os.path.relpath(path, ROOT)
            if old is not None:
                backup_path = os.path.join(backup_root, rel)
                _atomic_write(backup_path, old, _mode_for(path))
            manifest.append({
                "path": rel,
                "before_sha256": _sha(old) if old is not None else None,
                "candidate_sha256": _sha(candidates[path]),
                "existed": old is not None,
            })
        _atomic_write(
            os.path.join(backup_root, "manifest.json"),
            (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        )

        # Revalidate source bytes immediately before the first replacement.
        crm_check = _read(CRM_PATH)
        assert crm_check is not None
        if _sha(crm_check) != crm_sha:
            raise RepairBlocked("crm_changed_before_install")
        for path in sorted(candidates):
            current = _read(path, required=False)
            if current != before[path]:
                raise RepairBlocked("concurrent_change:" + path)

        for path in sorted(candidates):
            old = before[path]
            candidate = candidates[path]
            if old == candidate:
                continue
            _atomic_write(path, candidate, _mode_for(path))
            changed.append(path)
            receipt["production_write"] = True
            receipt["production_files_changed"] = len(changed)
            readback = _read(path)
            if readback != candidate:
                raise RepairBlocked("readback_mismatch:" + path)

        receipt["generator_sha256_after"] = _sha(patched_bytes)
        receipt["cards"] = _validate_installed(rows, _sha(patched_bytes))
        crm_after = _read(CRM_PATH)
        assert crm_after is not None
        receipt["crm_sha256_after"] = _sha(crm_after)
        if receipt["crm_sha256_after"] != crm_sha:
            raise RepairBlocked("crm_changed_during_install")
        receipt["changed_paths"] = [os.path.relpath(path, ROOT) for path in changed]
        receipt["status"] = "PASS"
    except Exception as exc:
        receipt["errors"].append(str(exc) if isinstance(exc, RepairBlocked) else "unexpected_failure")
        if changed:
            receipt["rollback_attempted"] = True
            rollback_errors = []
            for path in reversed(changed):
                try:
                    old = before[path]
                    if old is None:
                        if os.path.exists(path):
                            os.unlink(path)
                            _fsync_dir(os.path.dirname(path))
                    else:
                        _atomic_write(path, old, _mode_for(path))
                    if _read(path, required=False) != old:
                        raise RepairBlocked("rollback_readback_mismatch")
                except Exception:
                    rollback_errors.append("rollback_failed:" + path)
            receipt["rollback_completed"] = not rollback_errors
            receipt["errors"].extend(rollback_errors)
            receipt["status"] = "ROLLED_BACK" if not rollback_errors else "BLOCKED"
        try:
            crm_after = _read(CRM_PATH)
            if crm_after is not None:
                receipt["crm_sha256_after"] = _sha(crm_after)
        except Exception:
            receipt["errors"].append("crm_post_failure_check_failed")
    return receipt


def self_test() -> int:
    card = (
        "<!doctype html><html><body><div>UA-9999</div>"
        "<a class='old' href='UA-9999-diag.html'>old</a>"
        "<a class='dejstvie kn_kupit' href='#'>Купить</a></body></html>"
    )
    fixed = _ensure_diag_anchor(card, "UA-9999")
    fixed_twice = _ensure_diag_anchor(fixed, "UA-9999")
    if _diagnostic_link_count(fixed, "UA-9999") != 1 or fixed != fixed_twice:
        raise SystemExit("SELF_TEST_CARD_IDEMPOTENCY_FAIL")
    page = _build_diag_page({"auto_number": "UA-9999", "brand": "Test", "model": "Empty"})
    for required in (
        "Кузов и безопасность", "Техническое состояние", "Электроника и OBD",
        "Фото и видео проверки", EMPTY_RU, 'href="UA-9999.html"',
    ):
        if required not in page:
            raise SystemExit("SELF_TEST_DIAG_TEMPLATE_FAIL:" + required)
    print("TASK064_SELF_TEST_PASS")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    descriptor = os.open(LOCK_PATH, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            receipt = {
                "mode": MODE, "status": "BLOCKED", "generated_at_utc": _utc_now(),
                "production_write": False, "production_files_changed": 0,
                "crm_write": False, "db_write": False, "service_reload": False,
                "rollback_attempted": False, "rollback_completed": False,
                "backup_root": "", "crm_sha256_before": "", "crm_sha256_after": "",
                "generator_sha256_before": "", "generator_sha256_after": "",
                "yadro_sha256": "", "card_ids": [], "cards": [],
                "changed_paths": [], "errors": ["concurrent_repair_run"],
            }
        else:
            receipt = run_repair()
    finally:
        os.close(descriptor)
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    # The controller consumes the explicit status; always emit the receipt.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

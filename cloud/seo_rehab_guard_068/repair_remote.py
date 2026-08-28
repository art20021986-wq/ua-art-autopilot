#!/usr/bin/env python3
"""Atomic SEO rehabilitation installer for UA ART production.

Scope: generator guards, published HTML, robots.txt and sitemap.xml only.
Every changed path is backed up first. Any failed invariant restores the full
write set automatically.
"""
from __future__ import annotations

import argparse
import ast
import datetime as dt
import fcntl
import hashlib
import json
import os
import pathlib
import re
import stat
import tempfile
import time
import urllib.parse
import urllib.request


CONTRACT = "SEO-REHAB-GUARD-068"
MARKER = "# SEO-REHAB-GUARD-068-PRODUCTION-V1"
ROOT = "/home/Carix"
VIDEO_ROOT = ROOT + "/video"
SITE_ROOT = ROOT + "/site"
WSGI_PATH = "/var/www/www_uaart_com_ua_wsgi.py"
GENERATOR_PATHS = (ROOT + "/stranica.py", ROOT + "/yadro.py", ROOT + "/master_card.py")
SOURCE_PATHS = GENERATOR_PATHS + (WSGI_PATH,)
SAFE_ROOT = ROOT + "/autopilot_inbox/cloud/seo_rehab_guard_068"
BACKUP_PARENT = SAFE_ROOT + "/backups"
RECEIPT_PATH = SAFE_ROOT + "/install_receipt.json"
SOURCE_RECEIPT_PATH = SAFE_ROOT + "/source_install_receipt.json"
DRY_RUN_RECEIPT_PATH = SAFE_ROOT + "/dry_run_receipt.json"
ROLLBACK_RECEIPT_PATH = SAFE_ROOT + "/rollback_receipt.json"
SOURCE_ROLLBACK_RECEIPT_PATH = SAFE_ROOT + "/source_rollback_receipt.json"
LOCK_PATH = ROOT + "/.seo_rehab_guard_068.lock"
MAX_BYTES = 24 * 1024 * 1024
ORIGIN = "https://www.uaart.com.ua"
REQUIRED_CTA = "Задаток 500 $"
CORE_FILES = ("index.html", "katalog.html", "info.html", "podbor.html")
EXPECTED_SOURCE_SHA = {
    ROOT + "/stranica.py": "001620f8f582c3ecbd638d0a1a557de085d019ea85fe17f5e4948f74c114931a",
    ROOT + "/yadro.py": "c95b0ef03d1d52423e48b127aefb75d22f00d17f531c0402daf178523707bb79",
    ROOT + "/master_card.py": "438559b3caf31ee66a4774e865ee52796c7e06a3f3e0785b54f96d4064e5b270",
    WSGI_PATH: "5cd015061758cb105832ed17d3934b6570d7e18d58de366273bdfbb5cf7818c8",
}

CANONICAL_RE = re.compile(
    r'<link\b(?=[^>]*\brel\s*=\s*["\'][^"\']*\bcanonical\b[^"\']*["\'])[^>]*>\s*',
    re.I,
)
ROBOTS_RE = re.compile(
    r'<meta\b(?=[^>]*\bname\s*=\s*["\'](?:robots|googlebot)["\'])[^>]*>\s*',
    re.I,
)
ACTION_RE = re.compile(r'(<(?P<tag>a|button)\b[^>]*>)(?P<inner>.*?)(</(?P=tag)\s*>)', re.I | re.S)
DIAG_ANCHOR_RE = re.compile(
    r'<a\b(?=[^>]*(?:\bclass\s*=\s*["\'][^"\']*\bmcf-diag-cta\b[^"\']*["\']'
    r'|\bhref\s*=\s*["\'][^"\']*UA-[0-9]{4,}-diag\.html[^"\']*["\']))[^>]*>.*?</a\s*>\s*',
    re.I | re.S,
)
CTA_RE = re.compile(
    r'(?:Купить авто|Купити авто|Задаток\s*\$?\s*500\s*\$?'
    r'|Депозит\s*\$?\s*500\s*\$?|Забронировать авто за\s*\$?\s*500\s*\$?)',
    re.I,
)
CARD_RE = re.compile(r'^UA-[0-9]{4,}\.html$', re.I)
SOURCE_TARGETS = {
    ROOT + "/stranica.py": {"sobrat_kartochku", "sobrat_katalog"},
    ROOT + "/yadro.py": {"karta_html", "katalog_html"},
    ROOT + "/master_card.py": {"obrabotat_kartochku", "obrabotat_obshuyu", "proverit"},
    WSGI_PATH: set(),
}


class RepairBlocked(RuntimeError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_file(path: str, *, required: bool = True) -> bytes | None:
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        if required:
            raise RepairBlocked("missing_file:" + path)
        return None
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise RepairBlocked("unsafe_file:" + path)
    if info.st_size <= 0 or info.st_size > MAX_BYTES:
        raise RepairBlocked("invalid_file_size:" + path)
    with open(path, "rb") as handle:
        payload = handle.read(MAX_BYTES + 1)
    if len(payload) > MAX_BYTES:
        raise RepairBlocked("file_too_large:" + path)
    return payload


def mode_for(path: str) -> int:
    try:
        return stat.S_IMODE(os.lstat(path).st_mode)
    except FileNotFoundError:
        return 0o644


def fsync_dir(path: str) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write(path: str, payload: bytes, mode: int = 0o644) -> None:
    parent = os.path.realpath(os.path.dirname(path))
    root = os.path.realpath(ROOT)
    if os.path.commonpath((root, parent)) != root and os.path.realpath(path) != WSGI_PATH:
        raise RepairBlocked("path_escape:" + path)
    os.makedirs(parent, mode=0o755, exist_ok=True)
    if os.path.lexists(path) and os.path.islink(path):
        raise RepairBlocked("symlink_target:" + path)
    descriptor, temporary = tempfile.mkstemp(prefix=".seo068-", dir=parent)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        fsync_dir(parent)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_json(path: str, value: dict) -> None:
    atomic_write(path, (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def backup_key(path: str) -> str:
    if path == WSGI_PATH:
        return "__external__/var/www/www_uaart_com_ua_wsgi.py"
    relative = os.path.relpath(path, ROOT)
    if relative == ".." or relative.startswith("../"):
        raise RepairBlocked("backup_path_escape:" + path)
    return relative


def display_path(path: str) -> str:
    return path if path == WSGI_PATH else os.path.relpath(path, ROOT)


def allowed_restore_path(path: str) -> bool:
    real = os.path.realpath(path)
    root = os.path.realpath(ROOT)
    return real == WSGI_PATH or os.path.commonpath((root, real)) == root


def attr(tag: str, name: str) -> str:
    match = re.search(r'\b' + re.escape(name) + r'\s*=\s*(["\'])(.*?)\1', tag, re.I | re.S)
    return match.group(2) if match else ""


def strip_tags(value: str) -> str:
    value = re.sub(r'<(?:script|style)\b.*?</(?:script|style)>', ' ', value, flags=re.I | re.S)
    value = re.sub(r'<[^>]+>', ' ', value)
    value = re.sub(r'&nbsp;|&#160;', ' ', value, flags=re.I)
    return re.sub(r'\s+', ' ', value).strip()


def insert_head(source: str, addition: str) -> str:
    if re.search(r'</head\s*>', source, re.I):
        return re.sub(r'</head\s*>', addition + "\n</head>", source, count=1, flags=re.I)
    match = re.search(r'<html\b[^>]*>', source, re.I)
    if match:
        return source[:match.end()] + "\n<head>" + addition + "\n</head>" + source[match.end():]
    return "<head>" + addition + "\n</head>\n" + source


def canonical_for(file_name: str) -> str:
    return ORIGIN + "/video/" + file_name


def diag_anchor(identifier: str) -> str:
    return (
        '<!--seo-rehab-guard-068-diagnostics-->'
        '<a class="mcf-diag-cta" href="%s-diag.html" '
        'style="display:flex;align-items:center;gap:12px;margin:14px 0;padding:15px 16px;'
        'border-radius:14px;text-decoration:none;background:linear-gradient(180deg,rgba(212,175,55,.20),'
        'rgba(212,175,55,.08));border:1px solid rgba(212,175,55,.55);color:#f4e3ae">'
        '<span style="font-size:22px;line-height:1">🔧</span><span style="flex:1">'
        '<span style="display:block;font-weight:800;font-size:16px">Открыть комплексную диагностику →</span>'
        '<span style="display:block;font-size:13px;opacity:.85;margin-top:3px">'
        'ЛКП · OBD · ходовая · фото · видео</span></span><span style="font-size:20px;opacity:.8">›</span></a>'
    ) % identifier


def normalize_cta(source: str) -> str:
    def replace(match: re.Match) -> str:
        opening, inner, closing = match.group(1), match.group('inner'), match.group(4)
        classes = attr(opening, "class").split()
        visible = strip_tags(inner)
        if "kn_kupit" not in classes and not CTA_RE.search(visible):
            return match.group(0)
        new_opening = re.sub(
            r'\b(aria-label|title)\s*=\s*(["\'])(.*?)\2',
            lambda item: '%s=%s%s%s' % (
                item.group(1), item.group(2), CTA_RE.sub(REQUIRED_CTA, item.group(3)), item.group(2)
            ),
            opening,
            flags=re.I | re.S,
        )
        new_inner = CTA_RE.sub(REQUIRED_CTA, inner)
        return new_opening + new_inner + closing

    return ACTION_RE.sub(replace, source)


def diagnostic_hrefs(source: str) -> list[str]:
    values = []
    for match in re.finditer(r'<a\b[^>]*>', source, re.I):
        href = attr(match.group(0), "href")
        if re.search(r'UA-[0-9]{4,}-diag\.html(?:[?#]|$)', href, re.I):
            values.append(href.split('?', 1)[0].split('#', 1)[0].rsplit('/', 1)[-1].upper())
    return values


def ensure_diag_target(identifier: str) -> None:
    target = identifier + "-diag.html"
    matches = []
    for root in (VIDEO_ROOT, SITE_ROOT):
        payload = read_file(root + "/" + target, required=False)
        if payload and b"</html" in payload.lower():
            matches.append(root)
    if not matches:
        raise RepairBlocked("diagnostic_target_missing:" + identifier)


def normalize_card(source: str, identifier: str) -> str:
    identifier = identifier.upper()
    ensure_diag_target(identifier)
    hrefs = diagnostic_hrefs(source)
    expected = identifier + "-DIAG.HTML"
    wrong = [value for value in hrefs if value != expected]
    if wrong:
        raise RepairBlocked("wrong_diagnostic_target:%s:%s" % (identifier, ",".join(wrong)))
    source = DIAG_ANCHOR_RE.sub("", source).replace("<!--seo-rehab-guard-068-diagnostics-->", "")
    source = normalize_cta(source)
    addition = diag_anchor(identifier) + "\n"
    purchase = re.search(
        r'<a\b(?=[^>]*\bclass\s*=\s*["\'][^"\']*\bkn_kupit\b[^"\']*["\'])',
        source,
        re.I,
    )
    position = purchase.start() if purchase else source.lower().rfind("</body>")
    if position < 0:
        raise RepairBlocked("diagnostic_insertion_point_missing:" + identifier)
    return source[:position] + addition + source[position:]


def normalize_html(source: str, file_name: str) -> str:
    source = CANONICAL_RE.sub("", source)
    source = ROBOTS_RE.sub("", source)
    source = insert_head(source, '<link rel="canonical" href="%s">' % canonical_for(file_name))
    if CARD_RE.fullmatch(file_name):
        source = normalize_card(source, pathlib.PurePosixPath(file_name).stem)
    return source


def facts(source: str, file_name: str) -> dict:
    canonical = re.findall(
        r'<link\b(?=[^>]*\brel\s*=\s*["\'][^"\']*canonical[^"\']*["\'])'
        r'(?=[^>]*\bhref\s*=\s*["\']([^"\']+)["\'])[^>]*>', source, re.I,
    )
    robots = re.findall(
        r'<meta\b(?=[^>]*\bname\s*=\s*["\'](?:robots|googlebot)["\'])'
        r'(?=[^>]*\bcontent\s*=\s*["\']([^"\']*)["\'])[^>]*>', source, re.I,
    )
    primary = []
    for match in ACTION_RE.finditer(source):
        opening = match.group(1)
        visible = strip_tags(match.group('inner'))
        if "kn_kupit" in attr(opening, "class").split() or CTA_RE.search(visible):
            primary.append(visible)
    result = {"canonical": canonical, "robots": robots, "primary_cta": primary, "diagnostics": []}
    if CARD_RE.fullmatch(file_name):
        result["diagnostics"] = diagnostic_hrefs(source)
    return result


def validate_html(source: str, file_name: str) -> None:
    value = facts(source, file_name)
    expected = canonical_for(file_name)
    errors = []
    if value["canonical"] != [expected]:
        errors.append("canonical=" + repr(value["canonical"]))
    if any(re.search(r'(?:^|[,\s])(noindex|nofollow)(?:$|[,\s])', item, re.I) for item in value["robots"]):
        errors.append("robots=" + repr(value["robots"]))
    if CARD_RE.fullmatch(file_name):
        identifier = pathlib.PurePosixPath(file_name).stem.upper()
        if value["primary_cta"] != [REQUIRED_CTA]:
            errors.append("cta=" + repr(value["primary_cta"]))
        if value["diagnostics"] != [identifier + "-DIAG.HTML"]:
            errors.append("diagnostics=" + repr(value["diagnostics"]))
    if errors:
        raise RepairBlocked("html_contract:%s:%s" % (file_name, ";".join(errors)))


def normalize_allowed(source: str) -> str:
    source = CANONICAL_RE.sub("", source)
    source = ROBOTS_RE.sub("", source)
    source = DIAG_ANCHOR_RE.sub("", source).replace("<!--seo-rehab-guard-068-diagnostics-->", "")
    source = CTA_RE.sub("__SEO068_CTA__", source)
    return re.sub(r'\s+', ' ', source).strip()


COMMON_SOURCE = r'''
# SEO-REHAB-GUARD-068-PRODUCTION-V1
import os as _ua_seo068_os
import pathlib as _ua_seo068_pathlib
import re as _ua_seo068_re

_UA_SEO068_ORIGIN = "https://www.uaart.com.ua"
_UA_SEO068_CTA = "Задаток 500 $"
_UA_SEO068_CANONICAL = _ua_seo068_re.compile(r'<link\b(?=[^>]*\brel\s*=\s*["\'][^"\']*\bcanonical\b[^"\']*["\'])[^>]*>\s*', _ua_seo068_re.I)
_UA_SEO068_ROBOTS = _ua_seo068_re.compile(r'<meta\b(?=[^>]*\bname\s*=\s*["\'](?:robots|googlebot)["\'])[^>]*>\s*', _ua_seo068_re.I)
_UA_SEO068_ACTION = _ua_seo068_re.compile(r'(<(?P<tag>a|button)\b[^>]*>)(?P<inner>.*?)(</(?P=tag)\s*>)', _ua_seo068_re.I | _ua_seo068_re.S)
_UA_SEO068_DIAG = _ua_seo068_re.compile(r'<a\b(?=[^>]*(?:\bclass\s*=\s*["\'][^"\']*\bmcf-diag-cta\b[^"\']*["\']|\bhref\s*=\s*["\'][^"\']*UA-[0-9]{4,}-diag\.html[^"\']*["\']))[^>]*>.*?</a\s*>\s*', _ua_seo068_re.I | _ua_seo068_re.S)
_UA_SEO068_CTA_RE = _ua_seo068_re.compile(r'(?:Купить авто|Купити авто|Задаток\s*\$?\s*500\s*\$?|Депозит\s*\$?\s*500\s*\$?|Забронировать авто за\s*\$?\s*500\s*\$?)', _ua_seo068_re.I)

def _ua_seo068_attr(tag, name):
    found = _ua_seo068_re.search(r'\b' + _ua_seo068_re.escape(name) + r'\s*=\s*(["\'])(.*?)\1', tag, _ua_seo068_re.I | _ua_seo068_re.S)
    return found.group(2) if found else ""

def _ua_seo068_strip(value):
    value = _ua_seo068_re.sub(r'<(?:script|style)\b.*?</(?:script|style)>', ' ', value, flags=_ua_seo068_re.I | _ua_seo068_re.S)
    value = _ua_seo068_re.sub(r'<[^>]+>', ' ', value)
    return _ua_seo068_re.sub(r'\s+', ' ', value).strip()

def _ua_seo068_head(source, addition):
    if _ua_seo068_re.search(r'</head\s*>', source, _ua_seo068_re.I):
        return _ua_seo068_re.sub(r'</head\s*>', addition + '\n</head>', source, count=1, flags=_ua_seo068_re.I)
    found = _ua_seo068_re.search(r'<html\b[^>]*>', source, _ua_seo068_re.I)
    if found:
        return source[:found.end()] + '\n<head>' + addition + '\n</head>' + source[found.end():]
    return '<head>' + addition + '\n</head>\n' + source

def _ua_seo068_diag_anchor(identifier):
    return ('<!--seo-rehab-guard-068-diagnostics--><a class="mcf-diag-cta" href="%s-diag.html" style="display:flex;align-items:center;gap:12px;margin:14px 0;padding:15px 16px;border-radius:14px;text-decoration:none;background:linear-gradient(180deg,rgba(212,175,55,.20),rgba(212,175,55,.08));border:1px solid rgba(212,175,55,.55);color:#f4e3ae"><span style="font-size:22px;line-height:1">🔧</span><span style="flex:1"><span style="display:block;font-weight:800;font-size:16px">Открыть комплексную диагностику →</span><span style="display:block;font-size:13px;opacity:.85;margin-top:3px">ЛКП · OBD · ходовая · фото · видео</span></span><span style="font-size:20px;opacity:.8">›</span></a>' % identifier)

def _ua_seo068_cta(source):
    def replace(found):
        opening, inner, closing = found.group(1), found.group('inner'), found.group(4)
        classes = _ua_seo068_attr(opening, 'class').split()
        if 'kn_kupit' not in classes and not _UA_SEO068_CTA_RE.search(_ua_seo068_strip(inner)):
            return found.group(0)
        inner = _UA_SEO068_CTA_RE.sub(_UA_SEO068_CTA, inner)
        return opening + inner + closing
    return _UA_SEO068_ACTION.sub(replace, source)

def _ua_seo068_normalize(source, file_name, identifier=''):
    if not source:
        return source
    source = _UA_SEO068_CANONICAL.sub('', str(source))
    source = _UA_SEO068_ROBOTS.sub('', source)
    source = _ua_seo068_head(source, '<link rel="canonical" href="%s/video/%s">' % (_UA_SEO068_ORIGIN, file_name))
    if identifier:
        identifier = str(identifier).upper()
        target = identifier + '-diag.html'
        if not any(_ua_seo068_os.path.isfile(_ua_seo068_os.path.join(root, target)) for root in ('/home/Carix/video', '/home/Carix/site')):
            raise RuntimeError('SEO068_DIAGNOSTIC_TARGET_MISSING:' + identifier)
        hrefs = []
        for tag in _ua_seo068_re.findall(r'<a\b[^>]*>', source, _ua_seo068_re.I):
            href = _ua_seo068_attr(tag, 'href')
            match = _ua_seo068_re.search(r'(UA-[0-9]{4,}-diag\.html)(?:[?#]|$)', href, _ua_seo068_re.I)
            if match:
                hrefs.append(match.group(1).upper())
        if any(value != target.upper() for value in hrefs):
            raise RuntimeError('SEO068_WRONG_DIAGNOSTIC:' + identifier)
        source = _UA_SEO068_DIAG.sub('', source).replace('<!--seo-rehab-guard-068-diagnostics-->', '')
        source = _ua_seo068_cta(source)
        purchase = _ua_seo068_re.search(r'<a\b(?=[^>]*\bclass\s*=\s*["\'][^"\']*\bkn_kupit\b[^"\']*["\'])', source, _ua_seo068_re.I)
        position = purchase.start() if purchase else source.lower().rfind('</body>')
        if position < 0:
            raise RuntimeError('SEO068_INSERTION_POINT_MISSING:' + identifier)
        source = source[:position] + _ua_seo068_diag_anchor(identifier) + '\n' + source[position:]
    return source

def _ua_seo068_identifier(mapping):
    try:
        return str(mapping.get('auto_number') or mapping.get('id') or mapping.get('kod') or '').upper()
    except Exception:
        return ''

def _ua_seo068_core_path(source):
    title = ''
    match = _ua_seo068_re.search(r'<title\b[^>]*>(.*?)</title>', str(source), _ua_seo068_re.I | _ua_seo068_re.S)
    if match:
        title = _ua_seo068_strip(match.group(1)).lower()
    if 'каталог' in title:
        return 'katalog.html'
    if 'подбор' in title:
        return 'podbor.html'
    if 'услов' in title or 'информац' in title:
        return 'info.html'
    if 'ua art company' in title:
        return 'index.html'
    canonical = _ua_seo068_re.search(
        r'<link\b(?=[^>]*\brel\s*=\s*["\'][^"\']*canonical[^"\']*["\'])'
        r'(?=[^>]*\bhref\s*=\s*["\']([^"\']+)["\'])[^>]*>',
        str(source), _ua_seo068_re.I,
    )
    if canonical:
        file_name = canonical.group(1).split('?', 1)[0].split('#', 1)[0].rsplit('/', 1)[-1]
        if file_name in ('index.html', 'katalog.html', 'info.html', 'podbor.html'):
            return file_name
    return ''
'''.strip()

STRANICA_WRAPPERS = r'''
_ua_seo068_original_sobrat_kartochku = sobrat_kartochku
def sobrat_kartochku(m, kadry, sredn=None):
    result = _ua_seo068_original_sobrat_kartochku(m, kadry, sredn)
    identifier = _ua_seo068_identifier(m)
    if not _ua_seo068_re.fullmatch(r'UA-[0-9]{4,}', identifier):
        raise RuntimeError('SEO068_CARD_ID_INVALID:' + identifier)
    return _ua_seo068_normalize(result, identifier + '.html', identifier)

_ua_seo068_original_sobrat_katalog = sobrat_katalog
def sobrat_katalog(spisok, kadry_po_nomeru, legkie_po_nomeru):
    return _ua_seo068_normalize(_ua_seo068_original_sobrat_katalog(spisok, kadry_po_nomeru, legkie_po_nomeru), 'katalog.html')
'''.strip()

YADRO_WRAPPERS = r'''
_ua_seo068_original_karta_html = karta_html
def karta_html(m, foto, bron=False):
    result = _ua_seo068_original_karta_html(m, foto, bron)
    identifier = _ua_seo068_identifier(m)
    if not _ua_seo068_re.fullmatch(r'UA-[0-9]{4,}', identifier):
        raise RuntimeError('SEO068_CARD_ID_INVALID:' + identifier)
    return _ua_seo068_normalize(result, identifier + '.html', identifier)

_ua_seo068_original_katalog_html = katalog_html
def katalog_html(spisok, foto_po_nomeru, video_po_nomeru):
    return _ua_seo068_normalize(_ua_seo068_original_katalog_html(spisok, foto_po_nomeru, video_po_nomeru), 'katalog.html')
'''.strip()

MASTER_WRAPPERS = r'''
_ua_seo068_original_obrabotat_kartochku = obrabotat_kartochku
def obrabotat_kartochku(html, kod):
    result = _ua_seo068_original_obrabotat_kartochku(html, kod)
    identifier = str(kod).upper()
    if not _ua_seo068_re.fullmatch(r'UA-[0-9]{4,}', identifier):
        raise RuntimeError('SEO068_CARD_ID_INVALID:' + identifier)
    return _ua_seo068_normalize(result, identifier + '.html', identifier)

_ua_seo068_original_obrabotat_obshuyu = obrabotat_obshuyu
def obrabotat_obshuyu(html):
    result = _ua_seo068_original_obrabotat_obshuyu(html)
    file_name = _ua_seo068_core_path(result)
    return _ua_seo068_normalize(result, file_name) if file_name else result

_ua_seo068_original_proverit = proverit
def proverit(html, kod=''):
    errors = list(_ua_seo068_original_proverit(html, kod) or [])
    file_name = (str(kod).upper() + '.html') if kod else _ua_seo068_core_path(html)
    if file_name:
        expected = _UA_SEO068_ORIGIN + '/video/' + file_name
        canonicals = _ua_seo068_re.findall(r'<link\b(?=[^>]*\brel\s*=\s*["\'][^"\']*canonical[^"\']*["\'])(?=[^>]*\bhref\s*=\s*["\']([^"\']+)["\'])[^>]*>', str(html), _ua_seo068_re.I)
        if canonicals != [expected]:
            errors.append('SEO068 canonical')
        if _ua_seo068_re.search(r'<meta\b(?=[^>]*\bname\s*=\s*["\'](?:robots|googlebot)["\'])[^>]*\bcontent\s*=\s*["\'][^"\']*(?:noindex|nofollow)', str(html), _ua_seo068_re.I):
            errors.append('SEO068 robots')
        if kod:
            identifier = str(kod).upper()
            primary = []
            for found in _UA_SEO068_ACTION.finditer(str(html)):
                opening = found.group(1)
                visible = _ua_seo068_strip(found.group('inner'))
                if 'kn_kupit' in _ua_seo068_attr(opening, 'class').split() or _UA_SEO068_CTA_RE.search(visible):
                    primary.append(visible)
            if primary != [_UA_SEO068_CTA]:
                errors.append('SEO068 CTA')
            diagnostics = []
            for tag in _ua_seo068_re.findall(r'<a\b[^>]*>', str(html), _ua_seo068_re.I):
                href = _ua_seo068_attr(tag, 'href')
                match = _ua_seo068_re.search(r'(UA-[0-9]{4,}-diag\.html)(?:[?#]|$)', href, _ua_seo068_re.I)
                if match:
                    diagnostics.append(match.group(1).upper())
            if diagnostics != [identifier + '-DIAG.HTML']:
                errors.append('SEO068 diagnostics')
    result = []
    for error in errors:
        if error not in result:
            result.append(error)
    return result
'''.strip()


WSGI_WRAPPER = r'''
# SEO-REHAB-GUARD-068-PRODUCTION-V1
import os as _ua_seo068_wsgi_os
import re as _ua_seo068_wsgi_re

_ua_seo068_wsgi_previous = application
_ua_seo068_wsgi_core = ('index.html', 'katalog.html', 'info.html', 'podbor.html')

def _ua_seo068_wsgi_payload(path):
    if path == '/robots.txt':
        return (
            b'User-agent: *\nAllow: /\nDisallow: /video/preview/\n'
            b'Sitemap: https://www.uaart.com.ua/sitemap.xml\n',
            'text/plain; charset=utf-8',
        )
    if path == '/sitemap.xml':
        root = '/home/Carix/video'
        cards = sorted(
            name for name in _ua_seo068_wsgi_os.listdir(root)
            if _ua_seo068_wsgi_re.fullmatch(r'UA-[0-9]{4,}\.html', name, _ua_seo068_wsgi_re.I)
        )
        names = [name for name in _ua_seo068_wsgi_core if _ua_seo068_wsgi_os.path.isfile(_ua_seo068_wsgi_os.path.join(root, name))]
        names.extend(cards)
        body = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
        body.extend('  <url><loc>https://www.uaart.com.ua/video/%s</loc></url>' % name for name in names)
        body.append('</urlset>')
        return ('\n'.join(body) + '\n').encode('utf-8'), 'application/xml; charset=utf-8'
    return None

def application(environ, start_response):
    method = str(environ.get('REQUEST_METHOD', 'GET')).upper()
    path = str(environ.get('PATH_INFO', ''))
    value = _ua_seo068_wsgi_payload(path) if method in ('GET', 'HEAD') else None
    if value is None:
        return _ua_seo068_wsgi_previous(environ, start_response)
    payload, content_type = value
    start_response('200 OK', [
        ('Content-Type', content_type),
        ('Content-Length', str(len(payload))),
        ('Cache-Control', 'no-store'),
        ('X-Content-Type-Options', 'nosniff'),
    ])
    return [] if method == 'HEAD' else [payload]
'''.strip()


def patch_source(path: str, payload: bytes) -> bytes:
    source = payload.decode("utf-8")
    if MARKER in source:
        if source.count(MARKER) != 1:
            raise RepairBlocked("source_marker_count:" + path)
        compile(source, path, "exec")
        return payload
    if sha(payload) != EXPECTED_SOURCE_SHA[path]:
        raise RepairBlocked("source_sha_changed:" + path)
    if path == WSGI_PATH:
        if not re.search(r'(?m)^\s*application\s*=', source):
            raise RepairBlocked("wsgi_application_missing")
        candidate = (source.rstrip() + "\n\n" + WSGI_WRAPPER + "\n").encode("utf-8")
    else:
        wrappers = STRANICA_WRAPPERS if path.endswith("stranica.py") else YADRO_WRAPPERS if path.endswith("yadro.py") else MASTER_WRAPPERS
        candidate = (source.rstrip() + "\n\n" + COMMON_SOURCE + "\n\n" + wrappers + "\n").encode("utf-8")
    compile(candidate.decode("utf-8"), path, "exec")
    if candidate.decode("utf-8").count(MARKER) != 1:
        raise RepairBlocked("candidate_source_marker_count:" + path)
    return candidate


def source_inventory() -> list[dict]:
    records = []
    for path in SOURCE_PATHS:
        payload = read_file(path)
        source = payload.decode("utf-8")
        tree = ast.parse(source, filename=path)
        targets = SOURCE_TARGETS[path]
        counts: dict[str, int] = {}
        functions = []
        for node in ast.iter_child_nodes(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or node.name not in targets:
                continue
            counts[node.name] = counts.get(node.name, 0) + 1
            args = [item.arg for item in node.args.posonlyargs + node.args.args]
            if node.args.vararg:
                args.append("*" + node.args.vararg.arg)
            args.extend(item.arg for item in node.args.kwonlyargs)
            if node.args.kwarg:
                args.append("**" + node.args.kwarg.arg)
            lines = source.splitlines()
            segment = "\n".join(lines[node.lineno - 1:node.end_lineno])
            functions.append({
                "name": node.name,
                "ordinal": counts[node.name],
                "args": args,
                "async": isinstance(node, ast.AsyncFunctionDef),
                "line_start": node.lineno,
                "line_end": node.end_lineno,
                "sha256": sha(segment.encode("utf-8")),
            })
        records.append({
            "path": path,
            "bytes": len(payload),
            "sha256": sha(payload),
            "seo068_marker_count": source.count(MARKER),
            "functions": functions,
            "wsgi_application_assignment": bool(re.search(r'(?m)^\s*application\s*=', source)) if path == WSGI_PATH else None,
        })
    return records


def card_ids() -> list[str]:
    result = sorted({
        pathlib.PurePosixPath(path).stem.upper()
        for root in (VIDEO_ROOT, SITE_ROOT)
        for path in pathlib.Path(root).glob("UA-*.html")
        if CARD_RE.fullmatch(path.name)
    })
    if not result or "UA-0009" not in result or "UA-0010" not in result:
        raise RepairBlocked("card_set_invalid:" + repr(result))
    return result


def robots_text() -> bytes:
    return (
        "User-agent: *\nAllow: /\nDisallow: /video/preview/\n"
        "Sitemap: https://www.uaart.com.ua/sitemap.xml\n"
    ).encode("utf-8")


def sitemap_text(identifiers: list[str]) -> bytes:
    paths = ["/video/" + name for name in CORE_FILES]
    paths.extend("/video/" + identifier + ".html" for identifier in identifiers)
    body = "\n".join("  <url><loc>%s%s</loc></url>" % (ORIGIN, path) for path in paths)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + body + "\n</urlset>\n"
    ).encode("utf-8")


def build_candidates(*, include_sources: bool = True, include_content: bool = True) -> tuple[dict[str, bytes], list[str]]:
    identifiers = card_ids() if include_content else []
    candidates: dict[str, bytes] = {}
    if include_sources:
        for path in SOURCE_PATHS:
            candidates[path] = patch_source(path, read_file(path))
    if include_content:
        for root in (VIDEO_ROOT, SITE_ROOT):
            for file_name in CORE_FILES + tuple(identifier + ".html" for identifier in identifiers):
                path = root + "/" + file_name
                payload = read_file(path, required=True)
                source = payload.decode("utf-8")
                candidate = normalize_html(source, file_name)
                validate_html(candidate, file_name)
                if normalize_allowed(source) != normalize_allowed(candidate):
                    raise RepairBlocked("protected_html_changed:" + path)
                candidates[path] = candidate.encode("utf-8")
            candidates[root + "/robots.txt"] = robots_text()
            candidates[root + "/sitemap.xml"] = sitemap_text(identifiers)
    if not candidates:
        raise RepairBlocked("candidate_set_empty")
    return candidates, identifiers


def tree_hash(candidates: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    for path in sorted(candidates):
        digest.update(path.encode())
        digest.update(b"\0")
        digest.update(candidates[path])
        digest.update(b"\0")
    return digest.hexdigest()


def validate_candidates(candidates: dict[str, bytes], identifiers: list[str]) -> None:
    for path, payload in candidates.items():
        if not payload or len(payload) > MAX_BYTES:
            raise RepairBlocked("candidate_size:" + path)
        if path.endswith(".py"):
            compile(payload.decode("utf-8"), path, "exec")
        elif path.endswith(".html"):
            validate_html(payload.decode("utf-8"), pathlib.PurePosixPath(path).name)
        elif path.endswith("robots.txt") and payload != robots_text():
            raise RepairBlocked("robots_candidate_invalid")
        elif path.endswith("sitemap.xml") and payload != sitemap_text(identifiers):
            raise RepairBlocked("sitemap_candidate_invalid")


def backup_candidates(candidates: dict[str, bytes]) -> tuple[str, list[dict]]:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_root = BACKUP_PARENT + "/" + stamp + "-" + tree_hash(candidates)[:12]
    os.makedirs(backup_root, mode=0o700, exist_ok=False)
    manifest = []
    for path in sorted(candidates):
        before = read_file(path, required=False)
        relative = backup_key(path)
        entry = {
            "path": path,
            "backup_key": relative,
            "existed": before is not None,
            "mode": mode_for(path),
            "before_sha256": sha(before) if before is not None else None,
            "candidate_sha256": sha(candidates[path]),
        }
        if before is not None:
            atomic_write(backup_root + "/" + relative, before, entry["mode"])
        manifest.append(entry)
    atomic_json(backup_root + "/manifest.json", {"contract": CONTRACT, "files": manifest})
    return backup_root, manifest


def restore(backup_root: str, manifest: list[dict]) -> dict:
    errors = []
    restored = []
    for entry in reversed(manifest):
        path = str(entry["path"])
        try:
            if not allowed_restore_path(path):
                raise RepairBlocked("restore_path_invalid:" + path)
            if entry["existed"]:
                payload = read_file(backup_root + "/" + entry["backup_key"])
                if sha(payload) != entry["before_sha256"]:
                    raise RepairBlocked("backup_hash:" + path)
                atomic_write(path, payload, int(entry["mode"]))
            elif os.path.exists(path):
                os.unlink(path)
                fsync_dir(os.path.dirname(path))
            restored.append(path)
        except Exception as exc:
            errors.append(type(exc).__name__ + ":" + str(exc))
    return {"status": "PASS" if not errors else "FAIL", "restored": restored, "errors": errors}


def public_canary(identifier: str) -> dict:
    url = ORIGIN + "/video/" + identifier + ".html?seo068_canary=" + urllib.parse.quote(str(time.time_ns()))
    last = ""
    for attempt in range(1, 6):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "ua-art-seo068-canary/1"})
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = response.read(MAX_BYTES + 1)
                final_url = response.geturl()
                status = response.status
            if len(payload) > MAX_BYTES:
                raise RepairBlocked("canary_too_large")
            source = payload.decode("utf-8", errors="replace")
            validate_html(source, identifier + ".html")
            if status != 200 or not final_url.startswith(ORIGIN + "/video/" + identifier + ".html"):
                raise RepairBlocked("canary_http")
            return {"status": status, "final_url": final_url, "sha256": sha(payload), "attempt": attempt}
        except Exception as exc:
            last = type(exc).__name__ + ":" + str(exc)
            time.sleep(attempt * 2)
    raise RepairBlocked("public_canary_failed:" + last)


def dry_run() -> dict:
    inventory = source_inventory()
    hashes = []
    identifiers = []
    count = 0
    for _ in range(10):
        candidates, identifiers = build_candidates()
        validate_candidates(candidates, identifiers)
        hashes.append(tree_hash(candidates))
        count = len(candidates)
    if len(set(hashes)) != 1:
        raise RepairBlocked("nondeterministic_candidates")
    return {
        "contract": CONTRACT,
        "mode": "dry-run",
        "status": "PASS",
        "production_write": False,
        "candidate_files": count,
        "card_ids": identifiers,
        "source_inventory": inventory,
        "repeatability": {"runs": 10, "unique_sha256": 1, "tree_sha256": hashes[0]},
        "generated_at_utc": utc_now(),
    }


def install(phase: str) -> dict:
    if phase not in ("sources", "content"):
        raise RepairBlocked("install_phase_invalid:" + phase)
    include_sources = phase == "sources"
    include_content = phase == "content"
    receipt = {
        "contract": CONTRACT,
        "mode": "install",
        "phase": phase,
        "status": "FAIL",
        "production_write": False,
        "backup_root": "",
        "changed_paths": [],
        "canary": None,
        "rollback": None,
        "errors": [],
        "generated_at_utc": utc_now(),
    }
    changed: list[str] = []
    manifest: list[dict] = []
    try:
        candidates, identifiers = build_candidates(
            include_sources=include_sources,
            include_content=include_content,
        )
        validate_candidates(candidates, identifiers)
        before = {path: read_file(path, required=False) for path in candidates}
        backup_root, manifest = backup_candidates(candidates)
        receipt["backup_root"] = backup_root
        for path in sorted(candidates):
            if read_file(path, required=False) != before[path]:
                raise RepairBlocked("concurrent_file_change:" + path)

        canary_paths: list[str] = []
        if include_content:
            canary_id = identifiers[-1]
            canary_paths = [root + "/" + canary_id + ".html" for root in (VIDEO_ROOT, SITE_ROOT)]
            for path in canary_paths:
                if before[path] != candidates[path]:
                    atomic_write(path, candidates[path], mode_for(path))
                    changed.append(path)
            receipt["production_write"] = bool(changed)
            receipt["changed_paths"] = [display_path(path) for path in changed]
            receipt["canary"] = {"id": canary_id, "local_paths": [display_path(path) for path in canary_paths]}
            receipt["canary"]["public"] = public_canary(canary_id)

        for path in sorted(candidates):
            if path in canary_paths or before[path] == candidates[path]:
                continue
            atomic_write(path, candidates[path], mode_for(path))
            changed.append(path)
            if read_file(path) != candidates[path]:
                raise RepairBlocked("readback_mismatch:" + path)
        for path in SOURCE_PATHS:
            if path in candidates:
                compile(read_file(path).decode("utf-8"), path, "exec")
                if read_file(path).decode("utf-8").count(MARKER) != 1:
                    raise RepairBlocked("installed_source_marker:" + path)
        validate_candidates({path: read_file(path) for path in candidates}, identifiers)
        receipt["production_write"] = bool(changed)
        receipt["changed_paths"] = [display_path(path) for path in changed]
        receipt["card_ids"] = identifiers
        receipt["candidate_files"] = len(candidates)
        receipt["candidate_tree_sha256"] = tree_hash(candidates)
        receipt["status"] = "PASS"
    except Exception as exc:
        receipt["errors"].append(type(exc).__name__ + ":" + str(exc))
        if changed and receipt["backup_root"]:
            receipt["rollback"] = restore(receipt["backup_root"], manifest)
            if receipt["rollback"]["status"] != "PASS":
                receipt["errors"].append("AUTOROLLBACK_FAILED")
    atomic_json(SOURCE_RECEIPT_PATH if phase == "sources" else RECEIPT_PATH, receipt)
    return receipt


def rollback_receipt(receipt_path: str, output_path: str, expected_phase: str) -> dict:
    installed = json.loads(read_file(receipt_path).decode("utf-8"))
    if installed.get("contract") != CONTRACT or installed.get("phase") != expected_phase:
        raise RepairBlocked("rollback_receipt_invalid:" + expected_phase)
    backup_root = installed.get("backup_root") or ""
    if not backup_root.startswith(BACKUP_PARENT + "/"):
        raise RepairBlocked("rollback_backup_invalid")
    bundle = json.loads(read_file(backup_root + "/manifest.json").decode("utf-8"))
    result = restore(backup_root, bundle["files"])
    receipt = {
        "contract": CONTRACT,
        "mode": "rollback",
        "phase": expected_phase,
        "backup_root": backup_root,
        "generated_at_utc": utc_now(),
        **result,
    }
    atomic_json(output_path, receipt)
    return receipt


def self_test() -> None:
    fixture = '''<!doctype html><html><head><meta name="robots" content="noindex,nofollow"><link rel="canonical" href="https://www.uaart.com.ua/video/preview/v4/UA-9999.html"><title>Fixture</title></head><body><div>VIN ABC123 · 24 500 $ · На пароме</div><a class="kn_kupit" href="https://t.me/bot?start=UA-9999">Купить авто</a></body></html>'''
    original = ensure_diag_target
    globals()["ensure_diag_target"] = lambda identifier: None
    try:
        candidate = normalize_html(fixture, "UA-9999.html")
        validate_html(candidate, "UA-9999.html")
        if normalize_allowed(fixture) != normalize_allowed(candidate):
            raise RepairBlocked("self_test_protected_diff")
        if normalize_html(candidate, "UA-9999.html") != candidate:
            raise RepairBlocked("self_test_not_idempotent")
        hashes = {sha(normalize_html(fixture, "UA-9999.html").encode()) for _ in range(10)}
        if len(hashes) != 1:
            raise RepairBlocked("self_test_nondeterministic")
    finally:
        globals()["ensure_diag_target"] = original
    compile("application = lambda environ, start_response: []\n\n" + WSGI_WRAPPER, "wsgi-fixture.py", "exec")
    for wrappers in (STRANICA_WRAPPERS, YADRO_WRAPPERS, MASTER_WRAPPERS):
        compile(COMMON_SOURCE + "\n\n" + wrappers, "generator-fixture.py", "exec")
    digest = tree_hash({"/home/Carix/a": b"a", "/home/Carix/b": b"b"})
    if len(digest) != 64 or digest != tree_hash({"/home/Carix/b": b"b", "/home/Carix/a": b"a"}):
        raise RepairBlocked("self_test_tree_hash")
    print("SEO_REHAB_068_SELF_TEST_PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--sources-only", action="store_true")
    parser.add_argument("--content-only", action="store_true")
    parser.add_argument("--rollback-content", action="store_true")
    parser.add_argument("--rollback-sources", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    modes = (
        args.dry_run, args.sources_only, args.content_only,
        args.rollback_content, args.rollback_sources, args.self_test,
    )
    if sum(modes) != 1:
        raise SystemExit("ONE_MODE_ONLY")
    if args.self_test:
        self_test()
        return 0
    os.makedirs(SAFE_ROOT, mode=0o700, exist_ok=True)
    with open(LOCK_PATH, "a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if args.dry_run:
            try:
                value = dry_run()
            except Exception as exc:
                value = {
                    "contract": CONTRACT,
                    "mode": "dry-run",
                    "status": "FAIL",
                    "production_write": False,
                    "errors": [type(exc).__name__ + ":" + str(exc)],
                    "generated_at_utc": utc_now(),
                }
                try:
                    value["source_inventory"] = source_inventory()
                except Exception as inventory_exc:
                    value["inventory_error"] = type(inventory_exc).__name__ + ":" + str(inventory_exc)
            atomic_json(DRY_RUN_RECEIPT_PATH, value)
        elif args.sources_only:
            value = install("sources")
        elif args.content_only:
            value = install("content")
        elif args.rollback_content:
            try:
                value = rollback_receipt(RECEIPT_PATH, ROLLBACK_RECEIPT_PATH, "content")
            except Exception as exc:
                value = {
                    "contract": CONTRACT, "mode": "rollback", "phase": "content",
                    "status": "FAIL", "errors": [type(exc).__name__ + ":" + str(exc)],
                    "generated_at_utc": utc_now(),
                }
                atomic_json(ROLLBACK_RECEIPT_PATH, value)
        elif args.rollback_sources:
            try:
                value = rollback_receipt(
                    SOURCE_RECEIPT_PATH, SOURCE_ROLLBACK_RECEIPT_PATH, "sources"
                )
            except Exception as exc:
                value = {
                    "contract": CONTRACT, "mode": "rollback", "phase": "sources",
                    "status": "FAIL", "errors": [type(exc).__name__ + ":" + str(exc)],
                    "generated_at_utc": utc_now(),
                }
                atomic_json(SOURCE_ROLLBACK_RECEIPT_PATH, value)
        else:
            raise SystemExit("MODE_REQUIRED")
    print(json.dumps({"contract": value["contract"], "mode": value["mode"], "status": value["status"]}))
    return 0 if value["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

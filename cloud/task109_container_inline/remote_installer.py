#!/usr/bin/env python3
"""Fail-closed TASK109 installer for the inline container tracking control.

Runs on PythonAnywhere.  It changes only the permanent delivery-stage helper
inside the three card generators and the same marked region in existing
published vehicle cards.  CRM data, media, catalogue, prices, VINs and every
byte outside the delivery-stage marker are protected.
"""
from __future__ import annotations

import datetime as dt
import fcntl
import glob
import hashlib
import html
import json
import os
import pathlib
import re
import shutil
import stat
import sys
import tempfile
from typing import Any


TASK_ID = "TASK109-CONTAINER-TRACK-INLINE"
CONTRACT = "UA-CARDS-CONTAINER-TRACK-INLINE-001-V1.0"
ROOT = "/home/Carix"
VIDEO_ROOT = ROOT + "/video"
SITE_ROOT = ROOT + "/site"
SOURCE_PATHS = (
    ROOT + "/stranica.py",
    ROOT + "/yadro.py",
    ROOT + "/master_card.py",
)
PROTECTED_PATHS = (
    ROOT + "/crm.db",
    ROOT + "/cars_ui.py",
    ROOT + "/db.py",
    ROOT + "/team_bot.py",
    ROOT + "/start_safe.py",
    VIDEO_ROOT + "/index.html",
    VIDEO_ROOT + "/katalog.html",
)
SAFE_ROOT = ROOT + "/autopilot_inbox/cloud/task_068_ferry_vin"
SOURCE_RECEIPT = SAFE_ROOT + "/task109_source_receipt.json"
CARDS_RECEIPT = SAFE_ROOT + "/task109_cards_receipt.json"
VERIFY_RECEIPT = SAFE_ROOT + "/task109_verify_receipt.json"
ROLLBACK_RECEIPT = SAFE_ROOT + "/task109_rollback_receipt.json"
BACKUP_PARENT = SAFE_ROOT + "/task109_backups"
LOCK_PATH = ROOT + "/.task109_container_inline.lock"
MAX_FILE_BYTES = 32 * 1024 * 1024
START_MARKER = "<!-- UA-ART-DELIVERY-STAGES-PERMANENT-V1:START -->"
END_MARKER = "<!-- UA-ART-DELIVERY-STAGES-PERMANENT-V1:END -->"
CARD_RE = re.compile(r"^UA-[0-9]{4,}\.html$")


OLD_META_CSS = (
    ".ua-stage-v1-meta{display:flex;flex-wrap:wrap;gap:7px;margin-top:13px}"
    ".ua-stage-v1-badge{padding:7px 9px;border:1px solid rgba(142,160,183,.18);"
    "border-radius:10px;background:rgba(255,255,255,.035);color:#b9c5d4;"
    "font-size:11px}.ua-stage-v1-badge b{color:#eef3f8}"
)
NEW_META_CSS = (
    ".ua-stage-v1-meta{display:flex;flex-wrap:wrap;align-items:center;gap:7px;"
    "margin-top:13px}"
    ".ua-stage-v1-container-row{display:inline-flex;align-items:center;flex-wrap:nowrap;"
    "flex:0 0 auto;gap:10px;max-width:100%;min-width:0;white-space:nowrap}"
    ".ua-stage-v1-badge{padding:7px 9px;border:1px solid rgba(142,160,183,.18);"
    "border-radius:10px;background:rgba(255,255,255,.035);color:#b9c5d4;"
    "font-size:11px}.ua-stage-v1-badge b{color:#eef3f8}"
    ".ua-stage-v1-container-row .ua-stage-v1-badge{flex:0 0 auto;"
    "white-space:nowrap}"
)
OLD_LINK_CSS = (
    ".ua-stage-v1-track-link{display:inline-flex;margin-top:9px;color:#f2ba69;"
    "font-size:11px;font-weight:800;text-decoration:none}"
)
NEW_LINK_CSS = (
    ".ua-stage-v1-track-link{position:relative;display:inline-flex;"
    "align-items:center;flex:0 0 auto;min-height:32px;padding:6px 2px;"
    "color:#f2ba69;font-size:11px;font-weight:850;line-height:1;"
    "white-space:nowrap;text-decoration:underline;text-decoration-thickness:1px;"
    "text-underline-offset:3px}.ua-stage-v1-track-link:hover{color:#ffd18c}"
    ".ua-stage-v1-track-link:focus-visible{outline:2px solid #ffc05a;"
    "outline-offset:3px;border-radius:4px}"
)
OLD_MEDIA_CSS = (
    "@media(max-width:380px){.ua-delivery-v1{padding:16px 11px 14px}"
    ".ua-stage-v1-name{font-size:10.5px}.ua-stage-v1-node{width:36px;height:36px}"
    ".ua-stage-v1-track{top:17px}.ua-stage-v1-title{font-size:17px}"
    ".ua-stage-v1-count{font-size:9px}}"
)
NEW_MEDIA_CSS = (
    "@media(max-width:380px){.ua-delivery-v1{padding:16px 11px 14px}"
    ".ua-stage-v1-name{font-size:10.5px}.ua-stage-v1-node{width:36px;height:36px}"
    ".ua-stage-v1-track{top:17px}.ua-stage-v1-title{font-size:17px}"
    ".ua-stage-v1-count{font-size:9px}.ua-stage-v1-container-row{gap:7px}"
    ".ua-stage-v1-container-row .ua-stage-v1-badge{padding-left:7px;"
    "padding-right:7px;font-size:10px}.ua-stage-v1-track-link{font-size:10px}}"
    "@media(max-width:340px){.ua-stage-v1-container-row{gap:5px}"
    ".ua-stage-v1-container-row .ua-stage-v1-badge{padding-left:6px;"
    "padding-right:6px;font-size:9.2px}.ua-stage-v1-track-link{font-size:9.5px}}"
)

OLD_SOURCE_META = '''    container = str(m.get("sea_container") or "").strip()
    shipped = _ua_stage_date(m.get("sea_date_out"))
    if container or shipped is not None:
        out.append('<div class="ua-stage-v1-meta">')
        if container:
            out.append('<span class="ua-stage-v1-badge">Контейнер: <b>%s</b></span>' % _ua_stage_escape(container))
        if shipped is not None:
            out.append('<span class="ua-stage-v1-badge">Отправлен: <b>%s</b></span>' % _ua_stage_pretty(shipped))
        out.append('</div>')
'''

NEW_SOURCE_META = '''    container = str(m.get("sea_container") or "").strip()
    shipped = _ua_stage_date(m.get("sea_date_out"))
    tracking_href = ""
    if container.upper().startswith("ONEY") and len(container) > 4:
        tracking_href = "https://ecomm.one-line.com/one-ecom/manage-shipment/cargo-tracking?trakNoParam=%s" % _ua_stage_escape(container[4:])
    if container or shipped is not None:
        out.append('<div class="ua-stage-v1-meta">')
        if container:
            escaped_container = _ua_stage_escape(container)
            badge = '<span class="ua-stage-v1-badge">Контейнер: <b>%s</b></span>' % escaped_container
            if tracking_href:
                out.append('<span class="ua-stage-v1-container-row" data-ua-container-tracking-inline="1">%s<a class="ua-stage-v1-track-link" href="%s" target="_blank" rel="noopener noreferrer" data-ru="Отследить ↗" data-uk="Відстежити ↗" aria-label="Отследить контейнер %s — откроется в новой вкладке" data-ru-aria="Отследить контейнер %s — откроется в новой вкладке" data-uk-aria="Відстежити контейнер %s — відкриється в новій вкладці">Отследить ↗</a></span>' % (badge, tracking_href, escaped_container, escaped_container, escaped_container))
            else:
                out.append(badge)
        if shipped is not None:
            out.append('<span class="ua-stage-v1-badge">Отправлен: <b>%s</b></span>' % _ua_stage_pretty(shipped))
        out.append('</div>')
'''

OLD_SOURCE_LINK = '''    if container.upper().startswith("ONEY") and len(container) > 4:
        tracking = _ua_stage_escape(container[4:])
        out.append('<a class="ua-stage-v1-track-link" href="https://ecomm.one-line.com/one-ecom/manage-shipment/cargo-tracking?trakNoParam=%s" target="_blank" rel="noopener">Отследить контейнер онлайн →</a>' % tracking)
'''

NEW_SIGNATURE = 'data-ua-container-tracking-inline="1"'


class InstallError(RuntimeError):
    pass


def utc_now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_read(path: str, *, required: bool = True) -> bytes | None:
    try:
        before = os.lstat(path)
    except FileNotFoundError:
        if required:
            raise InstallError("MISSING:" + path)
        return None
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise InstallError("UNSAFE_FILE:" + path)
    if before.st_size <= 0 or before.st_size > MAX_FILE_BYTES:
        raise InstallError("FILE_SIZE:" + path)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise InstallError("FILE_IDENTITY_CHANGED:" + path)
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, MAX_FILE_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_FILE_BYTES:
                raise InstallError("FILE_TOO_LARGE:" + path)
        after = os.fstat(descriptor)
        if (opened.st_size, opened.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise InstallError("CONCURRENT_READ:" + path)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def fsync_dir(path: str) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write(path: str, value: bytes, mode: int) -> None:
    parent = os.path.dirname(path)
    handle = tempfile.NamedTemporaryFile(
        mode="wb", dir=parent, prefix="." + os.path.basename(path) + ".",
        suffix=".task109.tmp", delete=False,
    )
    temporary = handle.name
    try:
        with handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, stat.S_IMODE(mode))
        os.replace(temporary, path)
        fsync_dir(parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_json(path: str, value: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    current = safe_read(path, required=False)
    mode = os.lstat(path).st_mode if current is not None else 0o600
    atomic_write(path, payload, mode)


def stage_span(source: str) -> tuple[int, int]:
    if source.count(START_MARKER) != 1 or source.count(END_MARKER) != 1:
        raise InstallError("STAGE_MARKER_COUNT")
    start = source.index(START_MARKER)
    end = source.index(END_MARKER, start) + len(END_MARKER)
    return start, end


def transform_source(source: str) -> str:
    if NEW_SIGNATURE in source:
        validate_source(source)
        return source
    expected = {
        "meta_css": source.count(OLD_META_CSS),
        "link_css": source.count(OLD_LINK_CSS),
        "media_css": source.count(OLD_MEDIA_CSS),
        "meta_source": source.count(OLD_SOURCE_META),
        "link_source": source.count(OLD_SOURCE_LINK),
    }
    if set(expected.values()) != {1}:
        raise InstallError("SOURCE_ANCHOR_COUNTS:" + json.dumps(expected, sort_keys=True))
    candidate = source.replace(OLD_META_CSS, NEW_META_CSS, 1)
    candidate = candidate.replace(OLD_LINK_CSS, NEW_LINK_CSS, 1)
    candidate = candidate.replace(OLD_MEDIA_CSS, NEW_MEDIA_CSS, 1)
    candidate = candidate.replace(OLD_SOURCE_META, NEW_SOURCE_META, 1)
    candidate = candidate.replace(OLD_SOURCE_LINK, "", 1)
    compile(candidate, "task109-generator-candidate", "exec")
    validate_source(candidate)
    return candidate


def validate_source(source: str) -> None:
    compile(source, "task109-generator", "exec")
    checks = {
        "new_signature": source.count(NEW_SIGNATURE) == 1,
        "new_meta_css": source.count(NEW_META_CSS) == 1,
        "new_link_css": source.count(NEW_LINK_CSS) == 1,
        "new_media_css": source.count(NEW_MEDIA_CSS) == 1,
        "old_meta_css_absent": OLD_META_CSS not in source,
        "old_link_css_absent": OLD_LINK_CSS not in source,
        "old_source_link_absent": OLD_SOURCE_LINK not in source,
        "short_action": 'data-ru="Отследить ↗"' in source,
        "uk_action": 'data-uk="Відстежити ↗"' in source,
        "underline": "text-decoration:underline" in source,
        "nowrap": "white-space:nowrap" in source,
        "external_rel": 'rel="noopener noreferrer"' in source,
    }
    failed = sorted(key for key, ok in checks.items() if not ok)
    if failed:
        raise InstallError("SOURCE_CONTRACT:" + ",".join(failed))


TRACK_LINK_RE = re.compile(
    r'<a\s+class="ua-stage-v1-track-link"\s+href="([^"]+)"[^>]*>.*?</a>',
    re.IGNORECASE | re.DOTALL,
)
CONTAINER_BADGE_RE = re.compile(
    r'<span\s+class="ua-stage-v1-badge">Контейнер:\s*<b>([^<]+)</b></span>',
    re.IGNORECASE,
)


def canonical_link(href: str, container: str) -> str:
    number = html.escape(html.unescape(container).strip(), quote=True)
    url = html.escape(html.unescape(href).strip(), quote=True)
    return (
        '<a class="ua-stage-v1-track-link" href="%s" target="_blank" '
        'rel="noopener noreferrer" data-ru="Отследить ↗" '
        'data-uk="Відстежити ↗" '
        'aria-label="Отследить контейнер %s — откроется в новой вкладке" '
        'data-ru-aria="Отследить контейнер %s — откроется в новой вкладке" '
        'data-uk-aria="Відстежити контейнер %s — відкриється в новій вкладці">'
        'Отследить ↗</a>' % (url, number, number, number)
    )


def one_tracking_url(container: str) -> str:
    plain = html.unescape(container).strip().upper()
    if plain.startswith("ONEY") and len(plain) > 4 and plain.isalnum():
        return (
            "https://ecomm.one-line.com/one-ecom/manage-shipment/"
            "cargo-tracking?trakNoParam=" + plain[4:]
        )
    return ""


def transform_card(source: str) -> tuple[str, dict[str, Any]]:
    start, end = stage_span(source)
    prefix = source[:start]
    region = source[start:end]
    suffix = source[end:]
    before_outside = sha_bytes((prefix + suffix).encode("utf-8"))

    if OLD_META_CSS in region:
        if region.count(OLD_META_CSS) != 1:
            raise InstallError("CARD_META_CSS_COUNT")
        region = region.replace(OLD_META_CSS, NEW_META_CSS, 1)
    if OLD_LINK_CSS in region:
        if region.count(OLD_LINK_CSS) != 1:
            raise InstallError("CARD_LINK_CSS_COUNT")
        region = region.replace(OLD_LINK_CSS, NEW_LINK_CSS, 1)
    if OLD_MEDIA_CSS in region:
        if region.count(OLD_MEDIA_CSS) != 1:
            raise InstallError("CARD_MEDIA_CSS_COUNT")
        region = region.replace(OLD_MEDIA_CSS, NEW_MEDIA_CSS, 1)

    badges = list(CONTAINER_BADGE_RE.finditer(region))
    links = list(TRACK_LINK_RE.finditer(region))
    if len(badges) > 1 or len(links) > 1:
        raise InstallError("CARD_CONTAINER_CONTROL_DUPLICATE")

    container = html.unescape(badges[0].group(1)).strip() if badges else ""
    trackable = bool(one_tracking_url(container))
    if container:
        if NEW_SIGNATURE in region:
            pass
        else:
            href = links[0].group(1) if links else one_tracking_url(container)
            if href:
                region = TRACK_LINK_RE.sub("", region, count=1)
                badge_match = CONTAINER_BADGE_RE.search(region)
                if badge_match is None:
                    raise InstallError("CARD_BADGE_LOST")
                row = (
                    '<span class="ua-stage-v1-container-row" '
                    'data-ua-container-tracking-inline="1">%s%s</span>'
                    % (badge_match.group(0), canonical_link(href, container))
                )
                region = region[:badge_match.start()] + row + region[badge_match.end():]
    elif links:
        raise InstallError("CARD_TRACK_LINK_WITHOUT_CONTAINER")

    candidate = prefix + region + suffix
    after_outside = sha_bytes((candidate[:start] + candidate[start + len(region):]).encode("utf-8"))
    if before_outside != after_outside:
        raise InstallError("CARD_OUTSIDE_STAGE_CHANGED")
    details = validate_card(candidate)
    details["outside_stage_sha256"] = before_outside
    details["trackable"] = trackable
    return candidate, details


def validate_card(source: str) -> dict[str, Any]:
    start, end = stage_span(source)
    region = source[start:end]
    badges = list(CONTAINER_BADGE_RE.finditer(region))
    links = list(TRACK_LINK_RE.finditer(region))
    container = html.unescape(badges[0].group(1)).strip() if badges else ""
    trackable = bool(one_tracking_url(container))
    checks = {
        "new_meta_css": region.count(NEW_META_CSS) == 1,
        "new_link_css": region.count(NEW_LINK_CSS) == 1,
        "new_media_css": region.count(NEW_MEDIA_CSS) == 1,
        "old_css_absent": OLD_META_CSS not in region and OLD_LINK_CSS not in region,
        "old_label_absent": "Отследить контейнер онлайн" not in region,
        "nowrap": "flex-wrap:nowrap" in region and "white-space:nowrap" in region,
        "underline": "text-decoration:underline" in region,
    }
    if trackable:
        checks.update({
            "one_badge": len(badges) == 1,
            "one_link": len(links) == 1,
            "one_row": region.count(NEW_SIGNATURE) == 1,
            "short_label": 'data-ru="Отследить ↗"' in region,
            "uk_label": 'data-uk="Відстежити ↗"' in region,
            "external_rel": 'rel="noopener noreferrer"' in region,
        })
        if len(links) == 1:
            row_start = region.find(NEW_SIGNATURE)
            row_open = region.rfind("<span", 0, row_start)
            row_end = region.find("</span>", links[0].end())
            checks["same_row"] = row_open >= 0 and row_open < badges[0].start() < links[0].start() < row_end
            checks["correct_suffix"] = (
                "trakNoParam=" + html.unescape(container).strip().upper()[4:]
                in html.unescape(links[0].group(1))
            )
    else:
        checks["no_orphan_link"] = len(links) == 0
        checks["no_fake_row"] = region.count(NEW_SIGNATURE) == 0
    failed = sorted(key for key, ok in checks.items() if not ok)
    if failed:
        raise InstallError("CARD_CONTRACT:" + ",".join(failed))
    return {
        "container": container,
        "trackable": trackable,
        "row_count": region.count(NEW_SIGNATURE),
        "link_count": len(links),
        "stage_sha256": sha_bytes(region.encode("utf-8")),
    }


def card_paths() -> list[str]:
    found: list[str] = []
    roots: dict[str, set[str]] = {}
    for root in (VIDEO_ROOT, SITE_ROOT):
        names: set[str] = set()
        for path in glob.glob(root + "/UA-*.html"):
            name = os.path.basename(path)
            if CARD_RE.fullmatch(name):
                names.add(name)
                found.append(path)
        roots[root] = names
    if roots[VIDEO_ROOT] != roots[SITE_ROOT]:
        raise InstallError("CARD_ROOT_SET_MISMATCH")
    if len(roots[VIDEO_ROOT]) < 16:
        raise InstallError("CARD_COUNT_BELOW_BASELINE:%d" % len(roots[VIDEO_ROOT]))
    return sorted(found)


def inventory_media() -> str:
    root = VIDEO_ROOT + "/foto"
    digest = hashlib.sha256()
    if not os.path.isdir(root):
        return digest.hexdigest()
    for base, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(name for name in dirs if not os.path.islink(os.path.join(base, name)))
        for name in sorted(files):
            path = os.path.join(base, name)
            info = os.lstat(path)
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                continue
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            digest.update(("%s\0%d\0%d\n" % (rel, info.st_size, info.st_mtime_ns)).encode())
    return digest.hexdigest()


def protected_snapshot() -> dict[str, str]:
    return {os.path.relpath(path, ROOT): sha_file(path) for path in PROTECTED_PATHS}


def make_backup(paths: list[str], phase: str) -> tuple[str, list[dict[str, Any]]]:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = os.path.join(BACKUP_PARENT, stamp + "-" + phase)
    os.makedirs(target, mode=0o700, exist_ok=False)
    manifest: list[dict[str, Any]] = []
    for path in paths:
        data = safe_read(path)
        assert data is not None
        rel = os.path.relpath(path, ROOT)
        destination = os.path.join(target, rel)
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        with open(destination, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        manifest.append({
            "path": rel,
            "sha256": sha_bytes(data),
            "mode": stat.S_IMODE(os.lstat(path).st_mode),
        })
    atomic_json(os.path.join(target, "manifest.json"), {"phase": phase, "files": manifest})
    return target, manifest


def restore_backup(receipt_path: str) -> dict[str, Any]:
    result = {"task_id": TASK_ID, "contract_id": CONTRACT, "status": "FAIL", "restored": [], "errors": []}
    try:
        receipt_raw = safe_read(receipt_path)
        assert receipt_raw is not None
        receipt = json.loads(receipt_raw.decode("utf-8"))
        backup_root = os.path.realpath(str(receipt.get("backup", "")))
        parent = os.path.realpath(BACKUP_PARENT)
        if os.path.commonpath((parent, backup_root)) != parent:
            raise InstallError("BACKUP_SCOPE")
        manifest_raw = safe_read(os.path.join(backup_root, "manifest.json"))
        assert manifest_raw is not None
        manifest = json.loads(manifest_raw.decode("utf-8"))
        for item in reversed(manifest.get("files") or []):
            rel = str(item["path"])
            target = os.path.join(ROOT, rel)
            backup = os.path.join(backup_root, rel)
            data = safe_read(backup)
            assert data is not None
            if sha_bytes(data) != item["sha256"]:
                raise InstallError("BACKUP_HASH:" + rel)
            atomic_write(target, data, int(item["mode"]))
            if sha_file(target) != item["sha256"]:
                raise InstallError("RESTORE_READBACK:" + rel)
            result["restored"].append(rel)
        result["status"] = "PASS"
    except Exception as exc:
        result["errors"].append(type(exc).__name__ + ":" + str(exc))
    atomic_json(ROLLBACK_RECEIPT, result)
    return result


def install_sources() -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "task_id": TASK_ID, "contract_id": CONTRACT, "phase": "sources",
        "status": "FAIL", "started_at": utc_now(), "crm_write": False,
        "media_write": False, "changed": [], "errors": [],
    }
    before_protected = protected_snapshot()
    before_media = inventory_media()
    changed: list[str] = []
    backup = ""
    try:
        backup, _ = make_backup(list(SOURCE_PATHS), "sources")
        receipt["backup"] = backup
        before = {path: safe_read(path) for path in SOURCE_PATHS}
        candidates: dict[str, bytes] = {}
        for path, raw in before.items():
            assert raw is not None
            source = raw.decode("utf-8")
            candidate = transform_source(source).encode("utf-8")
            candidates[path] = candidate
        for path in SOURCE_PATHS:
            original = before[path]
            candidate = candidates[path]
            assert original is not None
            if candidate == original:
                continue
            if safe_read(path) != original:
                raise InstallError("CONCURRENT_SOURCE_CHANGE:" + path)
            atomic_write(path, candidate, os.lstat(path).st_mode)
            if safe_read(path) != candidate:
                raise InstallError("SOURCE_READBACK:" + path)
            changed.append(path)
        for path in SOURCE_PATHS:
            raw = safe_read(path)
            assert raw is not None
            validate_source(raw.decode("utf-8"))
        if protected_snapshot() != before_protected:
            raise InstallError("PROTECTED_CHANGED")
        if inventory_media() != before_media:
            raise InstallError("MEDIA_CHANGED")
        receipt.update({
            "status": "PASS",
            "changed": [os.path.relpath(path, ROOT) for path in changed],
            "source_sha256": {os.path.basename(path): sha_file(path) for path in SOURCE_PATHS},
            "protected_sha256": before_protected,
            "media_inventory_sha256": before_media,
            "finished_at": utc_now(),
        })
    except Exception as exc:
        receipt["errors"].append(type(exc).__name__ + ":" + str(exc))
        if backup:
            receipt["backup"] = backup
            atomic_json(SOURCE_RECEIPT, receipt)
            rollback = restore_backup(SOURCE_RECEIPT)
            receipt["rollback"] = rollback
            receipt["status"] = "ROLLED_BACK" if rollback.get("status") == "PASS" else "BLOCKED"
    atomic_json(SOURCE_RECEIPT, receipt)
    return receipt


def install_cards() -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "task_id": TASK_ID, "contract_id": CONTRACT, "phase": "cards",
        "status": "FAIL", "started_at": utc_now(), "crm_write": False,
        "media_write": False, "changed": [], "errors": [],
    }
    before_protected = protected_snapshot()
    before_media = inventory_media()
    changed: list[str] = []
    backup = ""
    try:
        paths = card_paths()
        backup, _ = make_backup(paths, "cards")
        receipt["backup"] = backup
        before = {path: safe_read(path) for path in paths}
        candidates: dict[str, bytes] = {}
        details: dict[str, Any] = {}
        for path, raw in before.items():
            assert raw is not None
            source = raw.decode("utf-8")
            candidate, item = transform_card(source)
            candidates[path] = candidate.encode("utf-8")
            details[os.path.relpath(path, ROOT)] = item
        for path in paths:
            original = before[path]
            candidate = candidates[path]
            assert original is not None
            if candidate == original:
                continue
            if safe_read(path) != original:
                raise InstallError("CONCURRENT_CARD_CHANGE:" + path)
            atomic_write(path, candidate, os.lstat(path).st_mode)
            if safe_read(path) != candidate:
                raise InstallError("CARD_READBACK:" + path)
            changed.append(path)
        verified = {}
        for path in paths:
            raw = safe_read(path)
            assert raw is not None
            verified[os.path.relpath(path, ROOT)] = validate_card(raw.decode("utf-8"))
        if protected_snapshot() != before_protected:
            raise InstallError("PROTECTED_CHANGED")
        if inventory_media() != before_media:
            raise InstallError("MEDIA_CHANGED")
        ids = sorted({os.path.basename(path)[:-5] for path in paths})
        trackable = sum(1 for key, item in verified.items() if key.startswith("video/") and item["trackable"])
        if trackable < 1:
            raise InstallError("NO_TRACKABLE_CARDS")
        receipt.update({
            "status": "PASS", "card_ids": ids, "card_count": len(ids),
            "page_count": len(paths), "tracking_card_count": trackable,
            "changed": [os.path.relpath(path, ROOT) for path in changed],
            "card_contracts": verified, "protected_sha256": before_protected,
            "media_inventory_sha256": before_media, "finished_at": utc_now(),
        })
    except Exception as exc:
        receipt["errors"].append(type(exc).__name__ + ":" + str(exc))
        if backup:
            receipt["backup"] = backup
            atomic_json(CARDS_RECEIPT, receipt)
            rollback = restore_backup(CARDS_RECEIPT)
            receipt["rollback"] = rollback
            receipt["status"] = "ROLLED_BACK" if rollback.get("status") == "PASS" else "BLOCKED"
    atomic_json(CARDS_RECEIPT, receipt)
    return receipt


def verify_installation() -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "task_id": TASK_ID, "contract_id": CONTRACT, "phase": "verify",
        "status": "FAIL", "read_only": True, "crm_write": False,
        "media_write": False, "errors": [],
    }
    try:
        for path in SOURCE_PATHS:
            raw = safe_read(path)
            assert raw is not None
            validate_source(raw.decode("utf-8"))
        paths = card_paths()
        values = {}
        for path in paths:
            raw = safe_read(path)
            assert raw is not None
            values[os.path.relpath(path, ROOT)] = validate_card(raw.decode("utf-8"))
        ids = sorted({os.path.basename(path)[:-5] for path in paths})
        trackable = sum(1 for key, item in values.items() if key.startswith("video/") and item["trackable"])
        receipt.update({
            "status": "PASS", "card_ids": ids, "card_count": len(ids),
            "page_count": len(paths), "tracking_card_count": trackable,
            "source_sha256": {os.path.basename(path): sha_file(path) for path in SOURCE_PATHS},
            "protected_sha256": protected_snapshot(),
            "media_inventory_sha256": inventory_media(), "finished_at": utc_now(),
        })
    except Exception as exc:
        receipt["errors"].append(type(exc).__name__ + ":" + str(exc))
    atomic_json(VERIFY_RECEIPT, receipt)
    return receipt


def source_fixture() -> str:
    return (
        "def ekran(v):\n    return str(v)\n\n"
        "def fixture(m):\n"
        "    css = r'''" + OLD_META_CSS + OLD_LINK_CSS + OLD_MEDIA_CSS + "'''\n"
        "    out = []\n"
        "    _ua_stage_date = lambda value: None\n"
        "    _ua_stage_escape = lambda value: str(value)\n"
        "    _ua_stage_pretty = lambda value: str(value)\n"
        + OLD_SOURCE_META
        + "    kind = 'due'\n"
        + OLD_SOURCE_LINK
        + "    return ''.join(out)\n"
    )


def card_fixture(container: str = "ONEYSELGF1046602") -> str:
    suffix = container[4:] if container.startswith("ONEY") else container
    return (
        "<!doctype html><html><head></head><body><h1>UNCHANGED</h1>"
        + START_MARKER + "<style>" + OLD_META_CSS + OLD_LINK_CSS + OLD_MEDIA_CSS + "</style>"
        + '<section class="ua-delivery-v1"><div class="ua-stage-v1-meta">'
        + '<span class="ua-stage-v1-badge">Контейнер: <b>' + container + "</b></span></div>"
        + '<div class="ua-stage-v1-eta"><div>103 дня</div>'
        + '<a class="ua-stage-v1-track-link" href="https://ecomm.one-line.com/one-ecom/manage-shipment/cargo-tracking?trakNoParam='
        + suffix + '" target="_blank" rel="noopener">Отследить контейнер онлайн →</a></div></section>'
        + END_MARKER + "<footer>UNCHANGED</footer></body></html>"
    )


def self_test() -> int:
    upgraded_source = transform_source(source_fixture())
    assert transform_source(upgraded_source) == upgraded_source
    validate_source(upgraded_source)

    original = card_fixture()
    start, end = stage_span(original)
    outside = original[:start] + original[end:]
    upgraded, details = transform_card(original)
    assert details["trackable"] is True
    assert transform_card(upgraded)[0] == upgraded
    new_start, new_end = stage_span(upgraded)
    assert upgraded[:new_start] + upgraded[new_end:] == outside
    validate_card(upgraded)
    assert "103 дня" in upgraded
    assert "ONEYSELGF1046602" in upgraded
    assert upgraded.index("ONEYSELGF1046602") < upgraded.index("Отследить ↗")
    assert "Отследить контейнер онлайн" not in upgraded
    assert "text-decoration:underline" in upgraded
    assert "flex-wrap:nowrap" in upgraded

    no_container = card_fixture("")
    no_container = TRACK_LINK_RE.sub("", no_container)
    no_container = no_container.replace(
        '<span class="ua-stage-v1-badge">Контейнер: <b></b></span>', ""
    )
    upgraded_empty, empty_details = transform_card(no_container)
    assert empty_details["trackable"] is False
    assert NEW_SIGNATURE not in upgraded_empty
    print("TASK109_REMOTE_SELF_TEST_PASS")
    return 0


def main() -> int:
    if len(sys.argv) == 1 or "--self-test" in sys.argv:
        return self_test()
    descriptor = os.open(LOCK_PATH, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        if "--sources-only" in sys.argv:
            result = install_sources()
        elif "--cards-only" in sys.argv:
            result = install_cards()
        elif "--verify" in sys.argv:
            result = verify_installation()
        elif "--rollback-sources" in sys.argv:
            result = restore_backup(SOURCE_RECEIPT)
        elif "--rollback-cards" in sys.argv:
            result = restore_backup(CARDS_RECEIPT)
        else:
            raise SystemExit("TASK109_MODE_REQUIRED")
    finally:
        os.close(descriptor)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

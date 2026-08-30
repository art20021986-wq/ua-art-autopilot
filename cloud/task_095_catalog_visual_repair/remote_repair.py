#!/usr/bin/env python3
"""Atomic production repair for TASK 095 rendered catalog visibility.

The repair is deliberately bounded to the two catalog HTML targets and the
approved catalog golden shell. CRM, SQLite, card pages and media bytes are
read-only. The installer removes the accidental inline display:none from the
catalog section, resolves every main image to an existing local media file,
and uses atomic replace with a complete rollback manifest.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import html
import json
import os
import pathlib
import re
import shutil
import tempfile
import time
import urllib.parse
from typing import Any, Iterable

CONTRACT_ID = "CATALOG-VISUAL-ACCEPTANCE-REPAIR-095-V1.0"
ROOT = pathlib.Path(os.environ.get("UA_ART_ROOT", "/home/Carix")).resolve()
REMOTE = ROOT / "autopilot_inbox/cloud/task_095_catalog_visual_repair"
VIDEO = ROOT / "video"
SITE = ROOT / "site"
VIDEO_CATALOG = VIDEO / "katalog.html"
SITE_CATALOG = SITE / "katalog.html"
GOLDEN = ROOT / "catalog_design_golden.html"
DB = ROOT / "crm.db"
LOCK = ROOT / ".ua_art_publish_transaction.lock"
BACKUPS = ROOT / "rezerv_publikacii/TASK095"
LAST_SUCCESS = REMOTE / "last_successful_install.json"
RECEIPTS = {
    "install": REMOTE / "install_receipt.json",
    "postcheck": REMOTE / "postcheck_receipt.json",
    "rollback": REMOTE / "rollback_receipt.json",
}
MAX_FILE = 64 * 1024 * 1024
EXPECTED_IDS = tuple("UA-%04d" % value for value in range(1, 14))
EXPECTED_COUNTS = {"all": 13, "kiev": 3, "georgia": 1, "sea": 7, "korea": 2}
STAGES = {"kiev", "georgia", "sea", "korea"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".avif"}


class RepairError(RuntimeError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha(value: bytes | str) -> str:
    data = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(data).hexdigest()


def read(path: pathlib.Path) -> bytes:
    value = path.read_bytes()
    if len(value) > MAX_FILE:
        raise RepairError("FILE_TOO_LARGE:" + str(path))
    return value


def atomic(path: pathlib.Path, value: bytes, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        dir=path.parent,
        prefix="." + path.name + ".",
        suffix=".task095.tmp",
        delete=False,
    )
    temporary = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(temporary, mode)
        os.replace(temporary, path)
        descriptor = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    atomic(
        path,
        (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        0o644,
    )


@contextlib.contextmanager
def production_lock(timeout_seconds: int = 180):
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    handle = open(LOCK, "a+", encoding="utf-8")
    deadline = time.monotonic() + timeout_seconds
    try:
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise RepairError("PRODUCTION_LOCK_TIMEOUT")
                time.sleep(0.25)
        yield
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def _set_attr(tag: str, name: str, value: str) -> str:
    pattern = re.compile(r"\s+" + re.escape(name) + r"\s*=\s*([\"']).*?\1", re.I | re.S)
    tag = pattern.sub("", tag)
    if not tag.endswith(">"):
        raise RepairError("INVALID_TAG:" + name)
    return tag[:-1] + ' %s="%s">' % (name, html.escape(value, quote=True))


def _remove_attr(tag: str, name: str) -> str:
    return re.sub(
        r"\s+" + re.escape(name) + r"(?:\s*=\s*([\"']).*?\1)?",
        "",
        tag,
        flags=re.I | re.S,
    )


def force_catalog_section_visible(source: str) -> str:
    pattern = re.compile(
        r'<section\b(?=[^>]*\bclass\s*=\s*["\'][^"\']*\bcontent-page\b[^"\']*\bcatalog-page\b[^"\']*["\'])[^>]*>',
        re.I | re.S,
    )
    matches = list(pattern.finditer(source))
    if len(matches) != 1:
        raise RepairError("CATALOG_SECTION_COUNT:%d" % len(matches))
    match = matches[0]
    tag = match.group(0)
    style_match = re.search(r'\s+style\s*=\s*(["\'])(.*?)\1', tag, re.I | re.S)
    if style_match:
        declarations = []
        for declaration in style_match.group(2).split(";"):
            text = declaration.strip()
            if not text:
                continue
            name, separator, value = text.partition(":")
            if separator and name.strip().casefold() == "display" and re.match(
                r"\s*none(?:\s*!important)?\s*$", value, re.I
            ):
                continue
            declarations.append(text)
        tag = tag[: style_match.start()] + tag[style_match.end() :]
        if declarations:
            tag = _set_attr(tag, "style", "; ".join(declarations) + ";")
    tag = _remove_attr(tag, "hidden")
    aria = re.search(r'\s+aria-hidden\s*=\s*(["\'])true\1', tag, re.I)
    if aria:
        tag = tag[: aria.start()] + tag[aria.end() :]
    tag = _set_attr(tag, "data-ua095-visible", "1")
    if re.search(r"display\s*:\s*none", tag, re.I):
        raise RepairError("CATALOG_SECTION_STILL_HIDDEN")
    return source[: match.start()] + tag + source[match.end() :]


def url_to_local(value: str, base: pathlib.Path = VIDEO) -> list[pathlib.Path]:
    cleaned = html.unescape(str(value or "")).strip()
    if not cleaned or cleaned.startswith(("data:", "javascript:")):
        return []
    parsed = urllib.parse.urlsplit(cleaned)
    path_text = urllib.parse.unquote(parsed.path or cleaned.split("?", 1)[0].split("#", 1)[0])
    candidates: list[pathlib.Path] = []
    if path_text.startswith("/video/"):
        candidates.append(VIDEO / path_text[len("/video/") :])
    elif path_text.startswith("/site/"):
        candidates.append(SITE / path_text[len("/site/") :])
    elif path_text.startswith("video/"):
        candidates.append(ROOT / path_text)
    elif path_text.startswith("site/"):
        candidates.append(ROOT / path_text)
    else:
        relative = path_text.lstrip("./")
        candidates.extend((base / relative, VIDEO / relative, SITE / relative))
    unique: list[pathlib.Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if ROOT != resolved and ROOT not in resolved.parents:
            continue
        key = str(resolved)
        if key not in seen:
            seen.add(key)
            unique.append(resolved)
    return unique


def usable_image(path: pathlib.Path) -> bool:
    try:
        return (
            path.is_file()
            and path.suffix.casefold() in IMAGE_EXTENSIONS
            and path.stat().st_size > 512
        )
    except OSError:
        return False


def image_score(path: pathlib.Path, identifier: str) -> tuple[int, int, int, str]:
    text = str(path).casefold()
    name = path.stem.casefold()
    bad = any(word in text for word in ("logo", "icon", "favicon", "whatsapp", "qr", "poster"))
    preferred = 0 if name in {"1", "01", "001", "0001"} or name.startswith("001") else 1
    primary_tree = 0 if str(VIDEO / "foto" / identifier).casefold() in text else 1
    return (1 if bad else 0, primary_tree, preferred, text)


def candidate_sources(identifier: str, current_src: str) -> Iterable[str]:
    if current_src:
        yield current_src
    for root in (VIDEO, SITE):
        page = root / (identifier + ".html")
        if not page.is_file():
            continue
        source = read(page).decode("utf-8", "replace")
        patterns = (
            r'<img\b(?=[^>]*\bdata-mcf-foto\s*=\s*["\']1["\'])[^>]*\bsrc\s*=\s*["\']([^"\']+)["\']',
            r'<meta\b(?=[^>]*\bproperty\s*=\s*["\']og:image["\'])[^>]*\bcontent\s*=\s*["\']([^"\']+)["\']',
            r'<img\b[^>]*\bsrc\s*=\s*["\']([^"\']+)["\']',
        )
        for pattern in patterns:
            values = re.findall(pattern, source, re.I | re.S)
            for value in values:
                yield value
            if values:
                break


def select_main_photo(identifier: str, current_src: str) -> tuple[pathlib.Path, str]:
    for source in candidate_sources(identifier, current_src):
        for candidate in url_to_local(source):
            if usable_image(candidate):
                return candidate, public_url(candidate)

    found: list[pathlib.Path] = []
    scan_roots = (
        VIDEO / "foto" / identifier,
        SITE / "foto" / identifier,
        ROOT / "foto" / identifier,
        VIDEO / "stage",
        SITE / "stage",
    )
    for base in scan_roots:
        if not base.is_dir():
            continue
        iterator = base.rglob("*") if identifier in str(base) else base.glob(identifier + ".*")
        for candidate in iterator:
            if usable_image(candidate):
                found.append(candidate.resolve())
    if not found:
        raise RepairError("NO_EXISTING_MAIN_PHOTO:" + identifier)
    found.sort(key=lambda path: image_score(path, identifier))
    selected = found[0]
    return selected, public_url(selected)


def public_url(path: pathlib.Path) -> str:
    resolved = path.resolve()
    if VIDEO == resolved or VIDEO in resolved.parents:
        return "/video/" + resolved.relative_to(VIDEO).as_posix()
    if SITE == resolved or SITE in resolved.parents:
        return "/site/" + resolved.relative_to(SITE).as_posix()
    raise RepairError("IMAGE_OUTSIDE_PUBLIC_ROOT:" + str(path))


def article_pattern() -> re.Pattern[str]:
    return re.compile(
        r'<article\b(?=[^>]*\bclass\s*=\s*["\'][^"\']*\bcatalog-card\b)[^>]*>.*?</article\s*>',
        re.I | re.S,
    )


def identifier_of(block: str) -> str:
    for pattern in (
        r'\bdata-ua-card\s*=\s*["\'](UA-[0-9]{4,})["\']',
        r'\bdata-ua-kod\s*=\s*["\'](UA-[0-9]{4,})["\']',
        r'\bdata-ua-card\s*=\s*["\'](UA-[0-9]{4,})["\']',
        r'\b(UA-[0-9]{4,})\b',
    ):
        match = re.search(pattern, block, re.I)
        if match:
            return match.group(1).upper()
    raise RepairError("CARD_IDENTIFIER_MISSING")


def current_image_src(block: str) -> str:
    image = re.search(r'<img\b(?=[^>]*\bsrc\s*=)[^>]*>', block, re.I | re.S)
    if not image:
        raise RepairError("CARD_IMAGE_TAG_MISSING")
    source = re.search(r'\bsrc\s*=\s*(["\'])(.*?)\1', image.group(0), re.I | re.S)
    if not source:
        raise RepairError("CARD_IMAGE_SRC_MISSING")
    return source.group(2)


def patch_image(block: str, source: str) -> str:
    image = re.search(r'<img\b(?=[^>]*\bsrc\s*=)[^>]*>', block, re.I | re.S)
    if not image:
        raise RepairError("CARD_IMAGE_TAG_MISSING")
    tag = image.group(0)
    tag = _set_attr(tag, "src", source)
    tag = _set_attr(tag, "loading", "eager")
    tag = _set_attr(tag, "fetchpriority", "auto")
    tag = _remove_attr(tag, "srcset")
    tag = _remove_attr(tag, "data-src")
    tag = _remove_attr(tag, "data-srcset")
    return block[: image.start()] + tag + block[image.end() :]


def patch_catalog(source: str, photo_map: dict[str, str] | None = None) -> tuple[str, dict[str, str]]:
    source = force_catalog_section_visible(source)
    pattern = article_pattern()
    blocks = list(pattern.finditer(source))
    if len(blocks) != 13:
        raise RepairError("ARTICLE_COUNT:%d" % len(blocks))
    resolved_map = dict(photo_map or {})

    output: list[str] = []
    cursor = 0
    for match in blocks:
        block = match.group(0)
        identifier = identifier_of(block)
        current = current_image_src(block)
        if identifier not in resolved_map:
            _path, public = select_main_photo(identifier, current)
            resolved_map[identifier] = public
        block = patch_image(block, resolved_map[identifier])
        output.append(source[cursor : match.start()])
        output.append(block)
        cursor = match.end()
    output.append(source[cursor:])
    candidate = "".join(output)
    audit_catalog(candidate, resolved_map)
    return candidate, resolved_map


def audit_catalog(source: str, photo_map: dict[str, str] | None = None) -> dict[str, Any]:
    errors: list[str] = []
    section = re.search(
        r'<section\b(?=[^>]*\bclass\s*=\s*["\'][^"\']*\bcontent-page\b[^"\']*\bcatalog-page\b[^"\']*["\'])[^>]*>',
        source,
        re.I | re.S,
    )
    if not section:
        errors.append("CATALOG_SECTION_MISSING")
    else:
        tag = section.group(0)
        if re.search(r"display\s*:\s*none", tag, re.I):
            errors.append("CATALOG_SECTION_DISPLAY_NONE")
        if not re.search(r'\bdata-ua095-visible\s*=\s*["\']1["\']', tag, re.I):
            errors.append("VISIBILITY_MARKER_MISSING")

    identifiers: list[str] = []
    counts = {"all": 0, "kiev": 0, "georgia": 0, "sea": 0, "korea": 0}
    resolved: dict[str, str] = {}
    for match in article_pattern().finditer(source):
        block = match.group(0)
        try:
            identifier = identifier_of(block)
            identifiers.append(identifier)
            stage_match = re.search(r'\bdata-stage\s*=\s*["\']([^"\']+)["\']', block, re.I)
            stage = stage_match.group(1).casefold() if stage_match else ""
            if stage not in STAGES:
                errors.append("CARD_STAGE:" + identifier)
            else:
                counts[stage] += 1
            image_src = current_image_src(block)
            resolved[identifier] = image_src
            if not any(usable_image(path) for path in url_to_local(image_src)):
                errors.append("IMAGE_FILE_MISSING:" + identifier + ":" + image_src)
            image_tag = re.search(r'<img\b(?=[^>]*\bsrc\s*=)[^>]*>', block, re.I | re.S)
            if not image_tag or not re.search(r'\bloading\s*=\s*["\']eager["\']', image_tag.group(0), re.I):
                errors.append("IMAGE_NOT_EAGER:" + identifier)
        except Exception as exc:
            errors.append(type(exc).__name__ + ":" + str(exc))
    counts["all"] = len(identifiers)
    if tuple(sorted(identifiers)) != EXPECTED_IDS:
        errors.append("IDENTIFIER_SET")
    if counts != EXPECTED_COUNTS:
        errors.append("STAGE_COUNTS:" + json.dumps(counts, sort_keys=True))
    if photo_map is not None and set(photo_map) != set(EXPECTED_IDS):
        errors.append("PHOTO_MAP_SET")
    result = {
        "contract_id": CONTRACT_ID,
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "article_cards": len(identifiers),
        "identifiers": identifiers,
        "counts": counts,
        "photos": resolved,
        "visible_marker": bool(section and "data-ua095-visible" in section.group(0)),
    }
    if errors:
        raise RepairError("CATALOG_AUDIT:" + ";".join(errors))
    return result


def db_hash() -> str:
    return sha(read(DB))


def create_backup(paths: Iterable[pathlib.Path]) -> tuple[pathlib.Path, dict[str, Any]]:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_root = BACKUPS / (stamp + "-" + sha(read(VIDEO_CATALOG))[:12])
    backup_root.mkdir(parents=True, exist_ok=False)
    manifest: dict[str, Any] = {}
    for path in paths:
        if not path.is_file():
            raise RepairError("TARGET_MISSING:" + str(path))
        relative = path.relative_to(ROOT)
        destination = backup_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        manifest[str(path)] = {
            "backup": str(destination),
            "sha256": sha(read(path)),
            "mode": path.stat().st_mode & 0o777,
        }
    return backup_root, manifest


def restore_manifest(manifest: dict[str, Any]) -> list[str]:
    restored: list[str] = []
    for path_text, metadata in manifest.items():
        path = pathlib.Path(path_text)
        backup = pathlib.Path(metadata["backup"])
        if BACKUPS != backup and BACKUPS not in backup.parents:
            raise RepairError("ROLLBACK_BACKUP_SCOPE:" + str(backup))
        data = read(backup)
        if sha(data) != metadata["sha256"]:
            raise RepairError("ROLLBACK_BACKUP_HASH:" + path_text)
        atomic(path, data, int(metadata["mode"]))
        if sha(read(path)) != metadata["sha256"]:
            raise RepairError("ROLLBACK_READBACK:" + path_text)
        restored.append(path_text)
    return restored


def run_install() -> dict[str, Any]:
    started = utc_now()
    targets = (VIDEO_CATALOG, SITE_CATALOG, GOLDEN)
    with production_lock():
        database_before = db_hash()
        backup_root, manifest = create_backup(targets)
        photo_map: dict[str, str] = {}
        candidates: dict[pathlib.Path, bytes] = {}
        try:
            for path in targets:
                source = read(path).decode("utf-8", "replace")
                candidate, photo_map = patch_catalog(source, photo_map)
                candidates[path] = candidate.encode("utf-8")
            for path, data in candidates.items():
                atomic(path, data, int(manifest[str(path)]["mode"]))
            audits = {
                str(path): audit_catalog(read(path).decode("utf-8", "replace"), photo_map)
                for path in targets
            }
            database_after = db_hash()
            if database_after != database_before:
                raise RepairError("CRM_DATABASE_CHANGED")
        except Exception:
            restore_manifest(manifest)
            raise
        success = {
            "contract_id": CONTRACT_ID,
            "backup_root": str(backup_root),
            "manifest": manifest,
            "photo_map": photo_map,
            "database_sha256": database_before,
            "installed_at_utc": utc_now(),
        }
        atomic_json(LAST_SUCCESS, success)
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "mode": "INSTALL",
        "production_write": True,
        "crm_write": False,
        "media_write": False,
        "backup_root": str(backup_root),
        "changed_files": [str(path) for path in targets],
        "photo_map": photo_map,
        "audits": audits,
        "database_before": database_before,
        "database_after": database_after,
        "started_at_utc": started,
        "finished_at_utc": utc_now(),
        "errors": [],
    }


def run_postcheck() -> dict[str, Any]:
    with production_lock():
        if not LAST_SUCCESS.is_file():
            raise RepairError("LAST_SUCCESS_MISSING")
        success = json.loads(LAST_SUCCESS.read_text(encoding="utf-8"))
        database = db_hash()
        if database != success["database_sha256"]:
            raise RepairError("POSTCHECK_DATABASE_CHANGED")
        photo_map = dict(success["photo_map"])
        audits = {
            str(path): audit_catalog(read(path).decode("utf-8", "replace"), photo_map)
            for path in (VIDEO_CATALOG, SITE_CATALOG, GOLDEN)
        }
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "mode": "POSTCHECK",
        "production_write": False,
        "crm_write": False,
        "media_write": False,
        "audits": audits,
        "database_sha256": database,
        "finished_at_utc": utc_now(),
        "errors": [],
    }


def run_rollback() -> dict[str, Any]:
    with production_lock():
        if not LAST_SUCCESS.is_file():
            raise RepairError("LAST_SUCCESS_MISSING")
        success = json.loads(LAST_SUCCESS.read_text(encoding="utf-8"))
        restored = restore_manifest(dict(success["manifest"]))
        database = db_hash()
        if database != success["database_sha256"]:
            raise RepairError("ROLLBACK_DATABASE_CHANGED")
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "mode": "ROLLBACK",
        "production_write": True,
        "crm_write": False,
        "media_write": False,
        "restored": restored,
        "database_sha256": database,
        "finished_at_utc": utc_now(),
        "errors": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=tuple(RECEIPTS))
    args = parser.parse_args()
    try:
        value = {
            "install": run_install,
            "postcheck": run_postcheck,
            "rollback": run_rollback,
        }[args.mode]()
    except Exception as exc:
        value = {
            "contract_id": CONTRACT_ID,
            "status": "FAIL",
            "mode": args.mode.upper(),
            "production_write": False,
            "crm_write": False,
            "media_write": False,
            "errors": [type(exc).__name__ + ":" + str(exc)],
            "finished_at_utc": utc_now(),
        }
    atomic_json(RECEIPTS[args.mode], value)
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0 if value["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

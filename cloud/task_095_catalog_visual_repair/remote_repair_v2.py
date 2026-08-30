#!/usr/bin/env python3
"""Corrected atomic production repair for TASK 095.

Scope: /home/Carix/video/katalog.html and /home/Carix/site/katalog.html only.
CRM, SQLite, card pages and media files are read-only.
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
VIDEO = ROOT / "video"
SITE = ROOT / "site"
TARGETS = (VIDEO / "katalog.html", SITE / "katalog.html")
DB = ROOT / "crm.db"
LOCK = ROOT / ".ua_art_publish_transaction.lock"
REMOTE = ROOT / "autopilot_inbox/cloud/task_095_catalog_visual_repair"
BACKUPS = ROOT / "rezerv_publikacii/TASK095"
LAST_SUCCESS = REMOTE / "last_successful_install_v2.json"
RECEIPTS = {mode: REMOTE / (mode + "_v2_receipt.json") for mode in ("install", "postcheck", "rollback")}
EXPECTED_IDS = tuple("UA-%04d" % value for value in range(1, 14))
EXPECTED_COUNTS = {"all": 13, "kiev": 3, "georgia": 1, "sea": 7, "korea": 2}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".avif"}
MAX_FILE = 64 * 1024 * 1024


class RepairError(RuntimeError):
    pass


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha(value: bytes | str) -> str:
    data = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(data).hexdigest()


def read(path: pathlib.Path) -> bytes:
    data = path.read_bytes()
    if len(data) > MAX_FILE:
        raise RepairError("FILE_TOO_LARGE:" + str(path))
    return data


def atomic(path: pathlib.Path, data: bytes, mode: int | None = None) -> None:
    handle = tempfile.NamedTemporaryFile(
        dir=path.parent,
        prefix="." + path.name + ".",
        suffix=".task095v2.tmp",
        delete=False,
    )
    temporary = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(data)
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
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic(path, (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(), 0o644)


@contextlib.contextmanager
def lock(timeout: int = 180):
    handle = open(LOCK, "a+", encoding="utf-8")
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise RepairError("LOCK_TIMEOUT")
                time.sleep(0.25)
        yield
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def set_attr(tag: str, name: str, value: str) -> str:
    pattern = re.compile(r"\s+" + re.escape(name) + r"\s*=\s*([\"']).*?\1", re.I | re.S)
    tag = pattern.sub("", tag)
    return tag[:-1] + ' %s="%s">' % (name, html.escape(value, quote=True))


def remove_attr(tag: str, name: str) -> str:
    pattern = re.compile(r"\s+" + re.escape(name) + r"(?:\s*=\s*([\"']).*?\1)?", re.I | re.S)
    return pattern.sub("", tag)


def visible_section(source: str) -> str:
    pattern = re.compile(
        r'<section\b(?=[^>]*\bclass\s*=\s*["\'][^"\']*\bcontent-page\b[^"\']*\bcatalog-page\b[^"\']*["\'])[^>]*>',
        re.I | re.S,
    )
    matches = list(pattern.finditer(source))
    if len(matches) != 1:
        raise RepairError("CATALOG_SECTION_COUNT:%d" % len(matches))
    match = matches[0]
    tag = match.group(0)
    style = re.search(r'\s+style\s*=\s*(["\'])(.*?)\1', tag, re.I | re.S)
    if style:
        keep = []
        for item in style.group(2).split(";"):
            declaration = item.strip()
            if not declaration:
                continue
            name, separator, value = declaration.partition(":")
            if separator and name.strip().casefold() == "display" and re.fullmatch(
                r"\s*none(?:\s*!important)?\s*", value, re.I
            ):
                continue
            keep.append(declaration)
        tag = tag[: style.start()] + tag[style.end() :]
        if keep:
            tag = set_attr(tag, "style", "; ".join(keep) + ";")
    tag = remove_attr(tag, "hidden")
    tag = re.sub(r'\s+aria-hidden\s*=\s*(["\'])true\1', "", tag, flags=re.I)
    tag = set_attr(tag, "data-ua095-visible", "1")
    if re.search(r"display\s*:\s*none", tag, re.I):
        raise RepairError("SECTION_REMAINS_HIDDEN")
    return source[: match.start()] + tag + source[match.end() :]


def local_paths(value: str, base: pathlib.Path = VIDEO) -> list[pathlib.Path]:
    text = html.unescape(str(value or "")).strip()
    if not text or text.startswith(("data:", "javascript:")):
        return []
    parsed = urllib.parse.urlsplit(text)
    path = urllib.parse.unquote(parsed.path or text.split("?", 1)[0].split("#", 1)[0])
    candidates: list[pathlib.Path] = []
    if path.startswith("/video/"):
        candidates.append(VIDEO / path[len("/video/") :])
    elif path.startswith("/site/"):
        candidates.append(SITE / path[len("/site/") :])
    else:
        relative = path.lstrip("./")
        candidates.extend((base / relative, VIDEO / relative, SITE / relative))
    result = []
    seen = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if ROOT != resolved and ROOT not in resolved.parents:
            continue
        if str(resolved) not in seen:
            seen.add(str(resolved))
            result.append(resolved)
    return result


def usable(path: pathlib.Path) -> bool:
    try:
        return path.is_file() and path.suffix.casefold() in IMAGE_EXTENSIONS and path.stat().st_size > 512
    except OSError:
        return False


def public_url(path: pathlib.Path) -> str:
    path = path.resolve()
    if VIDEO == path or VIDEO in path.parents:
        return "/video/" + path.relative_to(VIDEO).as_posix()
    if SITE == path or SITE in path.parents:
        return "/site/" + path.relative_to(SITE).as_posix()
    raise RepairError("NON_PUBLIC_MEDIA:" + str(path))


def scan_photo(identifier: str) -> pathlib.Path:
    found: list[pathlib.Path] = []
    for base in (VIDEO / "foto" / identifier, SITE / "foto" / identifier, ROOT / "foto" / identifier):
        if base.is_dir():
            found.extend(path.resolve() for path in base.rglob("*") if usable(path))
    for base in (VIDEO / "stage", SITE / "stage"):
        if base.is_dir():
            found.extend(path.resolve() for path in base.glob(identifier + ".*") if usable(path))
    if not found:
        raise RepairError("NO_MAIN_PHOTO:" + identifier)

    def score(path: pathlib.Path):
        text = str(path).casefold()
        stem = path.stem.casefold()
        bad = any(word in text for word in ("logo", "icon", "favicon", "whatsapp", "qr", "poster"))
        first = 0 if stem in {"1", "01", "001", "0001"} or stem.startswith("001") else 1
        video = 0 if VIDEO in path.parents else 1
        return (1 if bad else 0, video, first, text)

    found.sort(key=score)
    return found[0]


def card_page_sources(identifier: str) -> Iterable[str]:
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


def resolve_photo(identifier: str, current: str) -> str:
    for value in (current, *tuple(card_page_sources(identifier))):
        for path in local_paths(value):
            if usable(path):
                return public_url(path)
    return public_url(scan_photo(identifier))


def article_re() -> re.Pattern[str]:
    return re.compile(
        r'<article\b(?=[^>]*\bclass\s*=\s*["\'][^"\']*\bcatalog-card\b)[^>]*>.*?</article\s*>',
        re.I | re.S,
    )


def card_id(block: str) -> str:
    for pattern in (
        r'\bdata-ua-kod\s*=\s*["\'](UA-[0-9]{4,})["\']',
        r'\bdata-ua-card\s*=\s*["\'](UA-[0-9]{4,})["\']',
        r'\b(UA-[0-9]{4,})\b',
    ):
        match = re.search(pattern, block, re.I)
        if match:
            return match.group(1).upper()
    raise RepairError("CARD_ID_MISSING")


def patch_card(block: str, photo_map: dict[str, str]) -> str:
    identifier = card_id(block)
    image = re.search(r'<img\b(?=[^>]*\bsrc\s*=)[^>]*>', block, re.I | re.S)
    if not image:
        raise RepairError("IMAGE_TAG_MISSING:" + identifier)
    source = re.search(r'\bsrc\s*=\s*(["\'])(.*?)\1', image.group(0), re.I | re.S)
    if not source:
        raise RepairError("IMAGE_SRC_MISSING:" + identifier)
    if identifier not in photo_map:
        photo_map[identifier] = resolve_photo(identifier, source.group(2))
    tag = set_attr(image.group(0), "src", photo_map[identifier])
    tag = set_attr(tag, "loading", "eager")
    tag = remove_attr(tag, "srcset")
    tag = remove_attr(tag, "data-src")
    tag = remove_attr(tag, "data-srcset")
    return block[: image.start()] + tag + block[image.end() :]


def patch_catalog(source: str, photo_map: dict[str, str]) -> str:
    source = visible_section(source)
    matches = list(article_re().finditer(source))
    if len(matches) != 13:
        raise RepairError("ARTICLE_COUNT:%d" % len(matches))
    output = []
    cursor = 0
    for match in matches:
        output.append(source[cursor : match.start()])
        output.append(patch_card(match.group(0), photo_map))
        cursor = match.end()
    output.append(source[cursor:])
    candidate = "".join(output)
    audit(candidate, photo_map)
    return candidate


def audit(source: str, photo_map: dict[str, str]) -> dict[str, Any]:
    errors = []
    section = re.search(
        r'<section\b(?=[^>]*\bclass\s*=\s*["\'][^"\']*\bcontent-page\b[^"\']*\bcatalog-page\b[^"\']*["\'])[^>]*>',
        source,
        re.I | re.S,
    )
    if not section or re.search(r"display\s*:\s*none", section.group(0), re.I):
        errors.append("CATALOG_HIDDEN")
    ids = []
    counts = {"all": 0, "kiev": 0, "georgia": 0, "sea": 0, "korea": 0}
    for match in article_re().finditer(source):
        block = match.group(0)
        identifier = card_id(block)
        ids.append(identifier)
        stage = re.search(r'\bdata-stage\s*=\s*["\'](kiev|georgia|sea|korea)["\']', block, re.I)
        if not stage:
            errors.append("STAGE_MISSING:" + identifier)
        else:
            counts[stage.group(1).casefold()] += 1
        image = re.search(r'<img\b(?=[^>]*\bsrc\s*=)[^>]*>', block, re.I | re.S)
        src = re.search(r'\bsrc\s*=\s*(["\'])(.*?)\1', image.group(0), re.I | re.S) if image else None
        if not image or not src:
            errors.append("IMAGE_MISSING:" + identifier)
        else:
            if not any(usable(path) for path in local_paths(src.group(2))):
                errors.append("IMAGE_FILE_MISSING:" + identifier)
            if not re.search(r'\bloading\s*=\s*["\']eager["\']', image.group(0), re.I):
                errors.append("IMAGE_NOT_EAGER:" + identifier)
    counts["all"] = len(ids)
    if tuple(sorted(ids)) != EXPECTED_IDS:
        errors.append("ID_SET")
    if counts != EXPECTED_COUNTS:
        errors.append("COUNTS:" + json.dumps(counts, sort_keys=True))
    if set(photo_map) != set(EXPECTED_IDS):
        errors.append("PHOTO_MAP")
    result = {
        "contract_id": CONTRACT_ID,
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "ids": ids,
        "counts": counts,
        "article_cards": len(ids),
        "photo_map": dict(photo_map),
    }
    if errors:
        raise RepairError("AUDIT:" + ";".join(errors))
    return result


def backup_targets() -> tuple[pathlib.Path, dict[str, Any]]:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = BACKUPS / (stamp + "-" + sha(read(TARGETS[0]))[:12])
    root.mkdir(parents=True, exist_ok=False)
    manifest = {}
    for path in TARGETS:
        destination = root / path.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        manifest[str(path)] = {
            "backup": str(destination),
            "sha256": sha(read(path)),
            "mode": path.stat().st_mode & 0o777,
        }
    return root, manifest


def restore(manifest: dict[str, Any]) -> list[str]:
    restored = []
    for path_text, item in manifest.items():
        path = pathlib.Path(path_text)
        backup = pathlib.Path(item["backup"])
        if BACKUPS != backup and BACKUPS not in backup.parents:
            raise RepairError("BACKUP_SCOPE")
        data = read(backup)
        if sha(data) != item["sha256"]:
            raise RepairError("BACKUP_HASH:" + path_text)
        atomic(path, data, int(item["mode"]))
        restored.append(path_text)
    return restored


def install() -> dict[str, Any]:
    with lock():
        db_before = sha(read(DB))
        backup_root, manifest = backup_targets()
        photo_map: dict[str, str] = {}
        candidates = {}
        try:
            for path in TARGETS:
                candidates[path] = patch_catalog(read(path).decode("utf-8", "replace"), photo_map).encode()
            for path, data in candidates.items():
                atomic(path, data, int(manifest[str(path)]["mode"]))
            audits = {str(path): audit(read(path).decode("utf-8", "replace"), photo_map) for path in TARGETS}
            db_after = sha(read(DB))
            if db_after != db_before:
                raise RepairError("DB_CHANGED")
        except Exception:
            restore(manifest)
            raise
        success = {
            "contract_id": CONTRACT_ID,
            "backup_root": str(backup_root),
            "manifest": manifest,
            "photo_map": photo_map,
            "db_sha256": db_before,
            "installed_at_utc": now(),
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
        "changed_files": [str(path) for path in TARGETS],
        "audits": audits,
        "photo_map": photo_map,
        "db_before": db_before,
        "db_after": db_after,
        "errors": [],
        "finished_at_utc": now(),
    }


def postcheck() -> dict[str, Any]:
    with lock():
        if not LAST_SUCCESS.is_file():
            raise RepairError("LAST_SUCCESS_MISSING")
        success = json.loads(LAST_SUCCESS.read_text(encoding="utf-8"))
        if sha(read(DB)) != success["db_sha256"]:
            raise RepairError("POSTCHECK_DB_CHANGED")
        photo_map = dict(success["photo_map"])
        audits = {str(path): audit(read(path).decode("utf-8", "replace"), photo_map) for path in TARGETS}
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "mode": "POSTCHECK",
        "production_write": False,
        "crm_write": False,
        "media_write": False,
        "audits": audits,
        "errors": [],
        "finished_at_utc": now(),
    }


def rollback() -> dict[str, Any]:
    with lock():
        if not LAST_SUCCESS.is_file():
            raise RepairError("LAST_SUCCESS_MISSING")
        success = json.loads(LAST_SUCCESS.read_text(encoding="utf-8"))
        restored = restore(dict(success["manifest"]))
        if sha(read(DB)) != success["db_sha256"]:
            raise RepairError("ROLLBACK_DB_CHANGED")
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "mode": "ROLLBACK",
        "production_write": True,
        "crm_write": False,
        "media_write": False,
        "restored": restored,
        "errors": [],
        "finished_at_utc": now(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=tuple(RECEIPTS))
    args = parser.parse_args()
    try:
        value = {"install": install, "postcheck": postcheck, "rollback": rollback}[args.mode]()
    except Exception as exc:
        value = {
            "contract_id": CONTRACT_ID,
            "status": "FAIL",
            "mode": args.mode.upper(),
            "production_write": False,
            "crm_write": False,
            "media_write": False,
            "errors": [type(exc).__name__ + ":" + str(exc)],
            "finished_at_utc": now(),
        }
    atomic_json(RECEIPTS[args.mode], value)
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0 if value["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""
Common utilities for UA Cards Unified Gate A package (TASK 021).

Python 3.10 standard library only. No third-party imports.
"""
from __future__ import annotations

import hashlib
import html.parser
import os
import re
import sqlite3
import stat
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

REAL_CODES = [f"UA-{i:04d}" for i in range(1, 9)]  # UA-0001..UA-0008
UA0009 = "UA-0009"
ALL_CODES = REAL_CODES + [UA0009]

CARD_CANDIDATE_TEMPLATES = [
    "video/{code}.html",
    "video/cards/{code}.html",
    "video/cards/{code}/index.html",
    "site/{code}.html",
    "public_html/video/{code}.html",
    "public_html/cards/{code}.html",
    "mysite/{code}.html",
    "{code}.html",
]

GENERATOR_CANDIDATE_NAMES = ["master_card.py", "stranica.py", "yadro.py"]

CRM_CANDIDATE_NAME = "crm.db"

APPROVED_MEDIA_ROOTS = ["video", "site", "public_html", "mysite"]

REPORT_SUBDIR = "video/reports/ua_cards_unified"
PREVIEW_SUBDIR = "video/reports/ua_cards_unified/preview"

PURCHASE_CLASS_TOKENS = {"dejstvie", "kn_kupit"}

DIAG_START_MARKER = "<!-- LEGACY_DIAG_START -->"
DIAG_END_MARKER = "<!-- LEGACY_DIAG_END -->"
TRACK_START_MARKER = "<!-- LEGACY_TRACK_START -->"
TRACK_END_MARKER = "<!-- LEGACY_TRACK_END -->"

TRACKING_EMPTY_TEXT = "данные отслеживания уточняются"


class GateAError(Exception):
    pass


class PathEscapeError(GateAError):
    pass


class NotRegularFileError(GateAError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_resolve(path: Path) -> Path:
    return Path(os.path.realpath(str(path)))


def require_within_roots(path: Path, roots: Iterable[Path]) -> Path:
    resolved = canonical_resolve(path)
    for root in roots:
        root_resolved = canonical_resolve(root)
        try:
            resolved.relative_to(root_resolved)
            return resolved
        except ValueError:
            continue
    raise PathEscapeError(f"Path {path} escapes allowed roots {list(roots)}")


def require_regular_non_symlink(path: Path) -> None:
    if path.is_symlink():
        raise NotRegularFileError(f"{path} is a symlink")
    if not path.exists():
        raise NotRegularFileError(f"{path} does not exist")
    st = path.lstat()
    if not stat.S_ISREG(st.st_mode):
        raise NotRegularFileError(f"{path} is not a regular file")


@dataclass
class FileFingerprint:
    path: str
    mode: int
    size: int
    mtime_ns: int
    sha256: str


def fingerprint_file(path: Path) -> FileFingerprint:
    require_regular_non_symlink(path)
    st = path.stat()
    return FileFingerprint(
        path=str(canonical_resolve(path)),
        mode=stat.S_IMODE(st.st_mode),
        size=st.st_size,
        mtime_ns=st.st_mtime_ns,
        sha256=sha256_file(path),
    )


def candidate_card_paths(base_root: Path, code: str) -> list[Path]:
    return [base_root / tmpl.format(code=code) for tmpl in CARD_CANDIDATE_TEMPLATES]


def candidate_generator_paths(base_root: Path) -> list[Path]:
    paths: list[Path] = []
    for name in GENERATOR_CANDIDATE_NAMES:
        paths.append(base_root / name)
        paths.append(base_root / "generators" / name)
    return paths


def candidate_crm_paths(base_root: Path) -> list[Path]:
    return [base_root / CRM_CANDIDATE_NAME]


def find_existing_regular(paths: Iterable[Path]) -> Optional[Path]:
    for p in paths:
        try:
            if p.exists() and not p.is_symlink() and p.is_file():
                return p
        except OSError:
            continue
    return None


class AtomicWriter:
    """Centralized safe writer restricted to allowed roots."""

    def __init__(self, allowed_roots: Iterable[Path]):
        self.allowed_roots = [canonical_resolve(r) for r in allowed_roots]

    def _check(self, target: Path) -> Path:
        target_parent = target.parent
        target_parent.mkdir(parents=True, exist_ok=True)
        resolved_parent = canonical_resolve(target_parent)
        ok = any(
            resolved_parent == root or root in resolved_parent.parents
            for root in self.allowed_roots
        )
        if not ok:
            raise PathEscapeError(f"Refusing to write outside allowed roots: {target}")
        if target.exists():
            if target.is_symlink():
                raise PathEscapeError(f"Refusing to overwrite symlink: {target}")
            st = target.lstat()
            if not stat.S_ISREG(st.st_mode):
                raise NotRegularFileError(f"Refusing to overwrite non-regular file: {target}")
        return target

    def write_bytes(self, target: Path, data: bytes) -> None:
        target = self._check(target)
        tmp = target.with_name(target.name + f".tmp-{os.getpid()}-{time.time_ns()}")
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target)

    def write_text(self, target: Path, text: str) -> None:
        self.write_bytes(target, text.encode("utf-8"))


class _AnchorScanner(html.parser.HTMLParser):
    """Finds <a> tags whose class attribute contains all PURCHASE_CLASS_TOKENS."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.matches: list[str] = []  # exact source text of matching start tags

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        attrs_dict = dict(attrs)
        class_attr = attrs_dict.get("class", "") or ""
        tokens = set(class_attr.split())
        if PURCHASE_CLASS_TOKENS.issubset(tokens):
            self.matches.append(self.get_starttag_text() or "")


def find_purchase_anchor_matches(html_text: str) -> list[str]:
    scanner = _AnchorScanner()
    scanner.feed(html_text)
    scanner.close()
    return scanner.matches


def strip_legacy_blocks(html_text: str) -> str:
    pattern_diag = re.compile(
        re.escape(DIAG_START_MARKER) + r".*?" + re.escape(DIAG_END_MARKER),
        re.DOTALL,
    )
    pattern_track = re.compile(
        re.escape(TRACK_START_MARKER) + r".*?" + re.escape(TRACK_END_MARKER),
        re.DOTALL,
    )
    html_text = pattern_diag.sub("", html_text)
    html_text = pattern_track.sub("", html_text)
    return html_text


def insert_before_anchor(html_text: str, anchor_tag_text: str, insertion: str) -> str:
    idx = html_text.find(anchor_tag_text)
    if idx == -1:
        raise GateAError("Anchor tag text not found for insertion")
    return html_text[:idx] + insertion + html_text[idx:]


def build_diag_tracking_snippet(code: str) -> str:
    diag_href = f"{code}-diag.html"
    track_href = f"{code}-track.html"
    return (
        f'<a class="ua-diag-link" href="{diag_href}" data-ua-code="{code}">Diagnostics</a>'
        f'<a class="ua-track-link" href="{track_href}" data-ua-code="{code}">Tracking</a>'
    )


def open_crm_readonly(crm_path: Path) -> sqlite3.Connection:
    require_regular_non_symlink(crm_path)
    uri = f"file:{crm_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.execute("PRAGMA query_only=ON;")
    cur = conn.execute("PRAGMA quick_check;")
    result = cur.fetchone()
    if not result or result[0] != "ok":
        conn.close()
        raise GateAError("CRM quick_check did not return ok; refusing to proceed")
    return conn


def is_safe_http_url(url: str) -> bool:
    return url.startswith("http://") or url.startswith("https://")

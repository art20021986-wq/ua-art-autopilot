"""
Common utilities for UA Cards Unified Gate A package (TASK 021).

Python 3.10 standard library only. No third-party imports.
"""
from __future__ import annotations

import hashlib
import html
import html.parser
import os
import re
import sqlite3
import stat
import tempfile
import time
import urllib.parse
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
    if st.st_nlink != 1:
        raise NotRegularFileError(f"{path} has unexpected hard links")


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


def find_existing_regular(
    paths: Iterable[Path], allowed_roots: Optional[Iterable[Path]] = None
) -> Optional[Path]:
    for p in paths:
        try:
            if not p.exists():
                continue
            if allowed_roots is not None:
                require_within_roots(p, allowed_roots)
            require_regular_non_symlink(p)
            return p
        except GateAError:
            raise
        except OSError:
            continue
    return None


class AtomicWriter:
    """Centralized safe writer restricted to allowed roots."""

    def __init__(self, allowed_roots: Iterable[Path]):
        self.allowed_roots = [canonical_resolve(r) for r in allowed_roots]

    def _check(self, target: Path) -> Path:
        if ".." in target.parts:
            raise PathEscapeError(f"Traversal is forbidden: {target}")
        if target.is_symlink():
            raise PathEscapeError(f"Refusing to overwrite symlink: {target}")
        resolved_target = canonical_resolve(target)
        ok = any(
            resolved_target == root or root in resolved_target.parents
            for root in self.allowed_roots
        )
        if not ok:
            raise PathEscapeError(f"Refusing to write outside allowed roots: {target}")

        # Validate before mkdir so a rejected target cannot create directories
        # outside the report namespace as a side effect.
        target_parent = target.parent
        target_parent.mkdir(parents=True, exist_ok=True)
        resolved_parent = canonical_resolve(target_parent)
        ok = any(
            resolved_parent == root or root in resolved_parent.parents
            for root in self.allowed_roots
        )
        if not ok:
            raise PathEscapeError(f"Refusing to write outside allowed roots: {target}")
        if resolved_target.exists():
            if resolved_target.is_symlink():
                raise PathEscapeError(f"Refusing to overwrite symlink: {target}")
            require_regular_non_symlink(resolved_target)
        return resolved_target

    def write_bytes(self, target: Path, data: bytes) -> None:
        target = self._check(target)
        tmp: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".tmp",
                delete=False,
            ) as f:
                tmp = Path(f.name)
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, target)
            tmp = None
        finally:
            if tmp is not None:
                try:
                    tmp.unlink()
                except FileNotFoundError:
                    pass

    def write_text(self, target: Path, text: str) -> None:
        self.write_bytes(target, text.encode("utf-8"))


class _AnchorScanner(html.parser.HTMLParser):
    """Finds <a> tags whose class attribute contains all PURCHASE_CLASS_TOKENS."""

    def __init__(self, source_text: str) -> None:
        super().__init__(convert_charrefs=True)
        self.matches: list[tuple[int, int, str]] = []
        self.line_starts = [0]
        for match in re.finditer("\n", source_text):
            self.line_starts.append(match.end())

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        attrs_dict = dict(attrs)
        class_attr = attrs_dict.get("class", "") or ""
        tokens = set(class_attr.split())
        if PURCHASE_CLASS_TOKENS.issubset(tokens):
            tag_text = self.get_starttag_text() or ""
            line, column = self.getpos()
            start = self.line_starts[line - 1] + column
            self.matches.append((start, start + len(tag_text), tag_text))


def find_purchase_anchor_spans(html_text: str) -> list[tuple[int, int, str]]:
    scanner = _AnchorScanner(html_text)
    scanner.feed(html_text)
    scanner.close()
    return scanner.matches


def find_purchase_anchor_matches(html_text: str) -> list[str]:
    return [match[2] for match in find_purchase_anchor_spans(html_text)]


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


def insert_at_offset(html_text: str, offset: int, insertion: str) -> str:
    if offset < 0 or offset > len(html_text):
        raise GateAError("Anchor offset is outside the HTML document")
    return html_text[:offset] + insertion + html_text[offset:]


def build_diag_tracking_snippet(code: str) -> str:
    diag_href = f"{code}-diag.html"
    track_href = f"{code}-track.html"
    return (
        f'<a class="ua-diag-link" href="{diag_href}" data-ua-code="{code}">Diagnostics</a>'
        f'<a class="ua-track-link" href="{track_href}" data-ua-code="{code}">Tracking</a>'
    )


def build_diagnostics_page(code: str, evidence: Optional[dict] = None) -> str:
    evidence = evidence or {}
    note = evidence.get("diag_notes")
    state = html.escape(str(note)) if note else "диагностические данные уточняются"
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        f"<title>{html.escape(code)} Diagnostics</title></head><body>"
        f"<h1>{html.escape(code)} Diagnostics</h1>"
        f"<p data-state=\"{'evidence' if note else 'empty'}\">{state}</p>"
        "</body></html>\n"
    )


def build_tracking_page(code: str, evidence: Optional[dict] = None) -> str:
    evidence = evidence or {}
    url = evidence.get("carrier_url")
    if isinstance(url, str) and is_safe_http_url(url):
        body = (
            f'<a rel="noopener noreferrer" href="{html.escape(url, quote=True)}">'
            "Открыть отслеживание</a>"
        )
    else:
        body = f'<p data-state="empty">{TRACKING_EMPTY_TEXT}</p>'
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        f"<title>{html.escape(code)} Tracking</title></head><body>"
        f"<h1>{html.escape(code)} Tracking</h1>{body}</body></html>\n"
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
    if any(ord(ch) < 32 for ch in url):
        return False
    parsed = urllib.parse.urlsplit(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

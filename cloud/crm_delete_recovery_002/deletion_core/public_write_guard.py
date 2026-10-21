"""Uninstalled legacy final-write guard; read-only database inspection.

Every integration must enter this context before other writer locks and keep
it through the actual public file replacement or rollback. No schema or file
is created here. This module alone does not intercept legacy writers.
"""
from __future__ import annotations

from contextlib import contextmanager
from html.parser import HTMLParser
from pathlib import Path
import re
import sqlite3
from urllib.parse import unquote, urlsplit


class PublicWriteRejected(RuntimeError):
    pass


CODE = re.compile(r"UA-[0-9]{4}$")
CARD = re.compile(r"(UA-[0-9]{4})(?:-diag)?(?:-[0-9a-f]{6,10})?\.html$", re.I)
LINK_LITERAL = re.compile(r"(?<![A-Za-z0-9_-])(UA-[0-9]{4})(?:-diag)?(?:-[0-9a-f]{6,10})?\.html(?:[?#\s\"'<>]|$)", re.I)


def advertised_codes(text):
    """Canonical/alias page references and explicit vehicle markers only.

    A retained decorative image named stage/UA-0002.webp is not an ad link.
    Full HTML URL literals also cover metadata or JavaScript link constants.
    Dynamic/escaped JavaScript data requires the integrator's exact proposed
    membership validator; this parser alone cannot prove arbitrary scripts.
    """
    codes = {match[1].upper() for match in LINK_LITERAL.finditer(text)}

    class Parser(HTMLParser):
        def handle_starttag(self, tag, pairs):
            attrs = dict(pairs)
            for key in ("data-ua-card", "data-ua", "data-car-code"):
                candidate = str(attrs.get(key) or "").strip().upper()
                if CODE.fullmatch(candidate):
                    codes.add(candidate)
            href = unquote(urlsplit(attrs.get("href") or "").path).rsplit("/", 1)[-1]
            match = CARD.fullmatch(href)
            if match:
                codes.add(match[1].upper())

    parser = Parser()
    parser.feed(text)
    parser.close()
    return codes


class PublicWriteGuard:
    def __init__(self, *, root, db_path, publication_fence, require_fence):
        self.root, self.db_path = Path(root), Path(db_path)
        if not self.root.is_absolute() or self.root.resolve(strict=True) != self.root:
            raise ValueError("CANONICAL_PUBLIC_ROOT_REQUIRED")
        if not callable(publication_fence) or not callable(require_fence):
            raise ValueError("EXISTING_PUBLICATION_FENCE_REQUIRED")
        self.publication_fence, self.require_fence = publication_fence, require_fence

    def _public_path(self, path):
        path = Path(path)
        if not path.is_absolute():
            raise PublicWriteRejected("EXPLICIT_WRITER_DESTINATION_REQUIRED")
        if path.resolve(strict=False) != path:
            raise PublicWriteRejected("CANONICAL_PUBLIC_DESTINATION_REQUIRED")
        # Backup writes remain with their existing backup implementation.
        if not any(path.is_relative_to(folder) for folder in
                   (self.root / "video", self.root / "site")):
            return None
        if path.parent.resolve(strict=True) != path.parent or path.is_symlink():
            raise PublicWriteRejected("CANONICAL_PUBLIC_DESTINATION_REQUIRED")
        if path.suffix.lower() != ".html":
            return None
        if path.name.upper().startswith("UA-") and CARD.fullmatch(path.name) is None:
            raise PublicWriteRejected("UNBOUND_PUBLIC_CAR_ALIAS")
        return path

    def _check(self, path, payload):
        self.require_fence()
        path = self._public_path(path)
        if path is None:
            return
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        if not isinstance(payload, str):
            raise PublicWriteRejected("PUBLIC_HTML_TEXT_REQUIRED")
        codes = advertised_codes(payload)
        match = CARD.fullmatch(path.name)
        if match:
            codes.add(match[1].upper())
        if self.db_path.resolve(strict=True) != self.db_path:
            raise PublicWriteRejected("CANONICAL_CRM_DATABASE_REQUIRED")
        conn = sqlite3.connect(self.db_path.as_uri() + "?mode=ro", uri=True)
        try:
            conn.execute("BEGIN")
            # Missing migration is not permission to bypass the guard.
            if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ua_delete_intents'").fetchone() is None:
                raise PublicWriteRejected("DELETION_SCHEMA_NOT_INSTALLED")
            retired = {row[0] for row in conn.execute("SELECT car_code FROM ua_delete_intents")}
            if codes & retired:
                raise PublicWriteRejected("DELETED_CAR_PUBLIC_WRITE_REFUSED")
            for code in codes:
                rows = conn.execute("SELECT id,published FROM cars WHERE auto_number=?", (code,)).fetchall()
                if len(rows) != 1 or rows[0][1] != 1:
                    raise PublicWriteRejected("CURRENT_PUBLISHED_CAR_REQUIRED")
        finally:
            conn.close()

    @contextmanager
    def write(self, path, payload):
        # Acquire before the caller's spec/file locks. Checking and then
        # releasing this fence before replacement would reintroduce the race.
        with self.publication_fence():
            self._check(path, payload)
            yield

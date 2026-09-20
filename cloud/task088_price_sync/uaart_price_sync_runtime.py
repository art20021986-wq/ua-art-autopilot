"""Candidate CRM price publisher; installation requires an explicit verified binding.

No path, owner chat, production authority or writer fencing is inferred. Importing
this module performs no I/O. A claim, backup journal and all semantic observations
are real runtime records; they do not replace the site's canonical Gate B guard.
"""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from html.parser import HTMLParser
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat
import tempfile
import time
from datetime import datetime, timezone, time as wall_time
from urllib.parse import urlsplit, urlencode, parse_qsl, urlunsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import uaart_price_sync_outbox as outbox
from uaart_market_prices import START, END, normalized_usd, render_market_prices, georgia_price_visible
from owner_policy import Identity
from price_publication import PriceVersion, Readback, publication_decision


class SyncError(RuntimeError):
    pass


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def json_bytes(value) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()


def canonical(value, *, georgia=False):
    value = normalized_usd(value)
    return None if not value and georgia else format(Decimal(value or "0"), ".2f")


class _Anchors(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=False)
        self.source = source
        self.lines = [0]
        self.lines.extend(m.end() for m in re.finditer("\n", source))
        self.opened = None
        self.anchors = []
        self.article_opened = None
        self.articles = []
        self.feed(source)
        self.close()
        if self.opened is not None or self.article_opened is not None:
            raise SyncError("UNCLOSED_CATALOG_ANCHOR")

    def source_offset(self):
        line, column = self.getpos()
        return self.lines[line - 1] + column

    def handle_starttag(self, tag, attrs):
        if tag == "article":
            if self.article_opened is not None:
                raise SyncError("NESTED_CATALOG_ARTICLE")
            self.article_opened = self.source_offset()
        if tag == "a":
            if self.opened is not None:
                raise SyncError("NESTED_CATALOG_ANCHOR")
            self.opened = (self.source_offset(), dict(attrs).get("href", ""))

    def handle_endtag(self, tag):
        if tag == "article":
            if self.article_opened is None:
                raise SyncError("UNMATCHED_CATALOG_ARTICLE")
            self.articles.append((self.article_opened, self.source.find(">", self.source_offset()) + 1))
            self.article_opened = None
        if tag == "a":
            if self.opened is None:
                raise SyncError("UNMATCHED_CATALOG_ANCHOR")
            start, href = self.opened
            end = self.source.find(">", self.source_offset()) + 1
            self.anchors.append((start, end, href))
            self.opened = None


def fragment_span(source: str, *, kind: str, code: str) -> tuple[int, int]:
    if not re.fullmatch(r"UA-[0-9]{4}", code):
        raise SyncError("INVALID_CAR_CODE")
    left, right = 0, len(source)
    if kind == "CATALOG":
        parsed = _Anchors(source)
        anchors = [(start, end) for start, end, href in parsed.anchors
                   if urlsplit(href).path.rsplit("/", 1)[-1] == code + ".html"]
        # The installed modern catalog uses <article> with separate image/button
        # links. The legacy renderer wraps the entire tile in one <a>.
        articles = [(left, right) for left, right in parsed.articles
                    if any(left <= start < end <= right for start, end in anchors)]
        targets = articles or anchors
        if len(targets) != 1:
            raise SyncError("EXACTLY_ONE_CATALOG_TILE_REQUIRED")
        left, right = targets[0]
    elif kind != "CARD":
        raise SyncError("UNKNOWN_SURFACE_KIND")
    target = source[left:right]
    if target.count(START) != 1 or target.count(END) != 1:
        raise SyncError("EXACTLY_ONE_INSTALLED_PRICE_FRAGMENT_REQUIRED")
    begin = left + target.index(START)
    end = left + target.index(END) + len(END)
    if end <= begin:
        raise SyncError("INVALID_PRICE_MARKERS")
    return begin, end


class _Prices(HTMLParser):
    def __init__(self, fragment):
        super().__init__(convert_charrefs=True)
        self.values = []
        self.codes = []
        self.feed(fragment)
        self.close()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "data-ua-car" in attrs:
            self.codes.append(attrs["data-ua-car"])
        if "data-ua-market" in attrs:
            self.values.append(tuple(attrs.get(key) for key in
                                     ("data-ua-market", "data-ua-field", "data-ua-value", "data-ua-currency")))


def _event_price_row(code, event):
    """Use the committed car snapshot, including stage, for public visibility.

    V5 snapshots are already backed by the DB read-back and immutable commit
    audit. Do not discard their status or replace it with a display preference.
    The legacy worker binds status from its locked current CRM row instead.
    """
    if 'car_code' in event or 'after_json' in event:
        try:
            row = json.loads(event.get('after_json'))
        except (TypeError, ValueError) as error:
            raise SyncError('V5_RENDER_DB_SNAPSHOT_REQUIRED') from error
        required = {'id', 'auto_number', 'vin', 'status', 'price_uah', 'price_georgia'}
        if (type(row) is not dict or not required <= row.keys()
                or row['auto_number'] != code or row['id'] != event.get('car_id')
                or row['vin'] != event.get('vin')
                or (canonical(row['price_uah']), canonical(row['price_georgia'], georgia=True)) !=
                   (event['ukraine_usd'], event['georgia_usd'])):
            raise SyncError('V5_RENDER_DB_SNAPSHOT_MISMATCH')
        return row
    return dict(auto_number=code, price_uah=event['ukraine_usd'],
                price_georgia=event['georgia_usd'], status=event.get('status'))


def semantic_fragment(fragment: str, code: str, event) -> None:
    parsed = _Prices(fragment)
    if parsed.codes != [code]:
        raise SyncError("PRICE_CAR_IDENTITY_MISMATCH")
    row = _event_price_row(code, event)
    expected = [("ukraine", "price_uah", normalized_usd(row['price_uah']), "USD")]
    if georgia_price_visible(row):
        expected.append(("georgia", "price_georgia", normalized_usd(row['price_georgia']), "USD"))
    if parsed.values != expected:
        raise SyncError("PRICE_SEMANTICS_MISMATCH")


def replace_price(source: bytes, *, kind: str, code: str, event) -> bytes:
    text = source.decode("utf-8")
    begin, end = fragment_span(text, kind=kind, code=code)
    old = _Prices(text[begin:end])
    if old.codes != [code]:
        raise SyncError("EXISTING_PRICE_CAR_IDENTITY_MISMATCH")
    fragment = render_market_prices(_event_price_row(code, event),
                                    compact=kind == "CATALOG", require_car_id=True)
    semantic_fragment(fragment, code, event)
    candidate = (text[:begin] + fragment + text[end:]).encode("utf-8")
    check = candidate.decode("utf-8")
    new_begin, new_end = fragment_span(check, kind=kind, code=code)
    if text[:begin] != check[:new_begin] or text[end:] != check[new_end:]:
        raise SyncError("NON_PRICE_CONTENT_CHANGED")
    return candidate


@dataclass(frozen=True)
class Surface:
    kind: str
    path: Path
    url: str
    price_applicable: bool = True


@dataclass(frozen=True)
class Binding:
    db_path: Path
    publication_lock: Path
    journal_root: Path
    # resolve_surfaces(code) returns every served file/mirror for that code plus
    # catalog. authorize re-verifies the canonical guard, allowed exact paths,
    # active transaction and ALL external writer lock contracts on each attempt.
    resolve_surfaces: object
    authorize: object
    owner_chat_id: int
    detail_url: str
    owner_private_chat_verified: bool
    car_identities: tuple
    read_public: object = None
    clock: object = None
    resolve_identity: object = None
    worker_count: int = 4
    verify_hidden: object = None
    resolve_visibility_surfaces: object = None
    authorize_visibility: object = None

    def __post_init__(self):
        for hook in (self.resolve_visibility_surfaces, self.authorize_visibility):
            if hook is not None and not callable(hook):
                raise SyncError("VISIBILITY_BINDING_HOOK_MUST_BE_CALLABLE")
        if self.verify_hidden is not None and not callable(self.verify_hidden):
            raise SyncError("HIDDEN_VIEW_VERIFIER_MUST_BE_CALLABLE")
        if self.resolve_identity is not None and not callable(self.resolve_identity):
            raise SyncError("IDENTITY_RESOLVER_MUST_BE_CALLABLE")
        if type(self.worker_count) is not int or not 1 <= self.worker_count <= 8:
            raise SyncError("BOUNDED_WORKER_COUNT_REQUIRED")
        for path in (self.db_path, self.publication_lock, self.journal_root):
            if not isinstance(path, Path) or not path.is_absolute():
                raise SyncError("ABSOLUTE_BOUND_PATH_REQUIRED")
        if not callable(self.resolve_surfaces) or not callable(self.authorize):
            raise SyncError("CANONICAL_ADAPTER_BINDING_REQUIRED")
        if type(self.owner_chat_id) is not int or self.owner_chat_id <= 0 or self.owner_private_chat_verified is not True:
            raise SyncError("VERIFIED_OWNER_PRIVATE_CHAT_REQUIRED")
        if urlsplit(self.detail_url).scheme != "https":
            raise SyncError("HTTPS_DETAIL_REPORT_REQUIRED")
        if (type(self.car_identities) is not tuple or (not self.car_identities and self.resolve_identity is None) or
                any(type(pair) is not tuple or len(pair) != 2 or type(pair[0]) is not int or pair[0] <= 0 or
                    type(pair[1]) is not str or not re.fullmatch(r"UA-[0-9]{4}", pair[1]) for pair in self.car_identities) or
                len({pair[0] for pair in self.car_identities}) != len(self.car_identities) or
                len({pair[1] for pair in self.car_identities}) != len(self.car_identities)):
            raise SyncError("PINNED_UNIQUE_CAR_IDENTITIES_REQUIRED")


NOTICE_TABLE = "uaart_price_sync_notices_v1"
_NOTICE_DDL = f"""CREATE TABLE {NOTICE_TABLE} (
 notice_key TEXT PRIMARY KEY NOT NULL,
 event_key TEXT,
 kind TEXT NOT NULL CHECK(kind IN ('FAILURE','DELAY','LATE','DAILY')),
 text TEXT NOT NULL,
 created_ms INTEGER NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('PENDING','SENDING','SENT','AMBIGUOUS')),
 sent_ms INTEGER,
 telegram_message_id INTEGER
)"""


def install(conn):
    """Explicit migration inside the caller's backed-up transaction; never commit."""
    if not conn.in_transaction:
        raise SyncError("EXPLICIT_INSTALL_TRANSACTION_REQUIRED")
    outbox.install(conn)
    row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (NOTICE_TABLE,)).fetchone()
    if row is None:
        conn.execute(_NOTICE_DDL)
    elif row[0] != _NOTICE_DDL:
        raise SyncError("NOTICE_SCHEMA_MISMATCH")
    import uaart_price_sync_confirmation
    uaart_price_sync_confirmation.install(conn)


def _fsync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _safe_bytes(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > 8 * 1024 * 1024:
        raise SyncError("REGULAR_BOUNDED_FILE_REQUIRED")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            value = handle.read(8 * 1024 * 1024 + 1)
        if len(value) > 8 * 1024 * 1024:
            raise SyncError("REGULAR_BOUNDED_FILE_REQUIRED")
        return value
    finally:
        os.close(descriptor)


def _atomic_write(path, content, mode=0o600, *, before_replace=None):
    descriptor, name = tempfile.mkstemp(prefix=".ua-price-sync-", dir=path.parent)
    temporary = Path(name)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        # Forward public writes may expire during render/flush/fsync. Invoke
        # the caller's authority check at the actual replace boundary. Journal
        # and recovery writes omit this optional hook deliberately.
        if before_replace is not None:
            before_replace()
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def _read_public(url):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise SyncError("HTTPS_PUBLIC_SURFACE_REQUIRED")
    query = parse_qsl(parsed.query, keep_blank_values=True)
    query.append(("ua_price_verify", secrets.token_hex(12)))
    requested = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), ""))
    with urlopen(Request(requested, headers={"Cache-Control": "no-cache", "Pragma": "no-cache"}), timeout=5) as response:
        actual = urlsplit(response.geturl())
        if (actual.scheme, actual.netloc, actual.path) != (parsed.scheme, parsed.netloc, parsed.path):
            raise SyncError("PUBLIC_REDIRECT_CHANGED_BOUND_SURFACE")
        if response.status != 200:
            raise SyncError("PUBLIC_SURFACE_UNAVAILABLE")
        body = response.read(8 * 1024 * 1024 + 1)
        if len(body) > 8 * 1024 * 1024:
            raise SyncError("PUBLIC_RESPONSE_TOO_LARGE")
        return body


class Worker:
    def __init__(self, binding: Binding):
        self.binding = binding
        self._wall_clock = binding.clock or (lambda: time.time_ns() // 1_000_000)
        self._last_wall_ms = None
        self.clock = self._checked_clock
        self.read_public = binding.read_public or _read_public
        self._notice_async_lock = asyncio.Lock()

    def _checked_clock(self):
        value = self._wall_clock()
        if type(value) is not int or value < 0:
            raise SyncError("INVALID_RUNTIME_CLOCK")
        if self._last_wall_ms is not None and value < self._last_wall_ms:
            raise SyncError("RUNTIME_CLOCK_MOVED_BACKWARD")
        self._last_wall_ms = value
        return value

    def record_runtime_failure(self, error):
        """Independent durable STOP/notification path, including unavailable CRM DB."""
        reason = str(error) if isinstance(error, (SyncError, outbox.OutboxError)) else (
            "SQLITE_RUNTIME_FAILURE" if isinstance(error, sqlite3.Error) else "PRICE_SYNC_RUNTIME_IO_FAILURE")
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,99}", reason):
            reason = "PRICE_SYNC_RUNTIME_FAILURE"
        folder = self.binding.journal_root / "runtime_failures"
        folder.mkdir(mode=0o700, exist_ok=True)
        path = folder / (digest(reason.encode()) + ".json")
        with self.lock(self.binding.journal_root / "runtime_failure.lock"):
            active = []
            for item in folder.glob(digest(reason.encode()) + "*.json"):
                try:
                    if json.loads(_safe_bytes(item)).get("blocked") is True:
                        active.append(item)
                except (ValueError, OSError):
                    continue
            if active:
                return reason
            if path.exists():
                path = folder / (digest(reason.encode()) + "-" + secrets.token_hex(8) + ".json")
            if not path.exists():
                try:
                    observed = self._wall_clock()
                except Exception:
                    observed = None
                _atomic_write(path, json_bytes(dict(reason=reason, observed_wall_ms=observed,
                                                    state="PENDING", blocked=True,
                                                    text=f"🔴 Автопилот цен остановлен: {reason}. Подробно: {self.binding.detail_url}")))
        return reason

    def resolve_runtime_failure(self, failure_path, verify_recovery):
        """Clear only an independently verified runtime cause; never replay claims."""
        folder = self.binding.journal_root / "runtime_failures"
        failure_path = Path(failure_path)
        if failure_path.parent != folder or not re.fullmatch(r"[0-9a-f]{64}(?:-[0-9a-f]{16})?\.json", failure_path.name):
            raise SyncError("BOUND_RUNTIME_FAILURE_PATH_REQUIRED")
        if not callable(verify_recovery):
            raise SyncError("TRUSTED_RUNTIME_RECOVERY_VERIFIER_REQUIRED")
        with self.lock(), self.lock(self.binding.journal_root / "runtime_failure.lock"), self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                original = _safe_bytes(failure_path)
                failure = json.loads(original)
                if failure.get("blocked") is not True:
                    conn.rollback()
                    return "ALREADY_RESOLVED"
                for name, expected in ((outbox.TABLE, outbox._DDL), (outbox.RECOVERY_TABLE, outbox._RECOVERY_DDL),
                                       (NOTICE_TABLE, _NOTICE_DDL)):
                    row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
                    if row is None or row[0] != expected:
                        raise SyncError("RECOVERY_DATABASE_SCHEMA_MISMATCH")
                now = self.clock()
                latest_time = conn.execute(f"SELECT MAX(created_ms) FROM {outbox.TABLE}").fetchone()[0]
                if latest_time is not None and latest_time > now:
                    raise SyncError("RECOVERY_CLOCK_BEFORE_DURABLE_EVENTS")
                for identifier, code in self.binding.car_identities:
                    row = conn.execute("SELECT id,auto_number FROM cars WHERE id=?", (identifier,)).fetchone()
                    if row is None:
                        raise SyncError("RECOVERY_PINNED_CAR_MISSING")
                    self._identity(conn, dict(zip(("id", "auto_number"), row)))
                facts = dict(reason=failure["reason"], failure_sha256=digest(original), checked_ms=now,
                             database_schema_verified=True, car_identities_verified=True,
                             clock_after_all_events=True)
                proof = verify_recovery(dict(facts))
                required_true = ("cause_resolved", "preflight_verified", "gate_b_verified")
                if (not isinstance(proof, dict) or any(proof.get(key) is not True for key in required_true) or
                        any(proof.get(key) != facts[key] for key in ("reason", "failure_sha256")) or
                        not re.fullmatch(r"[0-9a-f]{64}", str(proof.get("gate_b_receipt_sha256", ""))) or
                        not re.fullmatch(r"[0-9a-f]{64}", str(proof.get("evidence_sha256", ""))) or
                        not now <= proof.get("checked_ms", -1) <= self.clock() or self.clock() - proof["checked_ms"] > 30_000):
                    raise SyncError("VERIFIED_RUNTIME_RECOVERY_PROOF_REQUIRED")
                receipt = json_bytes(dict(facts=facts, proof=proof))
                recovery_folder = folder / "recoveries"
                recovery_folder.mkdir(mode=0o700, exist_ok=True)
                _atomic_write(recovery_folder / (digest(receipt) + ".json"), receipt)
                failure.update(blocked=False, recovery_receipt_sha256=digest(receipt))
                _atomic_write(failure_path, json_bytes(failure))
                conn.rollback()  # The database was inspected; no prices or claims changed.
                return "RUNTIME_CAUSE_VERIFIED_RESOLVED"
            except Exception:
                if conn.in_transaction:
                    conn.rollback()
                raise

    def _runtime_blocked(self):
        folder = self.binding.journal_root / "runtime_failures"
        if not folder.exists():
            return False
        return any(json.loads(_safe_bytes(path)).get("blocked") is True for path in folder.glob("*.json"))

    @contextmanager
    def connection(self):
        # Never create an absent production database by a typo in configuration.
        descriptor = sqlite3.connect(self.binding.db_path.as_uri() + "?mode=rw", uri=True, timeout=2)
        try:
            yield descriptor
        finally:
            descriptor.close()

    @contextmanager
    def lock(self, path=None):
        descriptor = os.open(path or self.binding.publication_lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield
        finally:
            os.close(descriptor)

    def _notice(self, conn, event_key, kind, reason):
        key = digest(json_bytes((event_key, kind)))
        message = ("🔴 Обновление цены остановлено" if kind == "FAILURE" else
                   "🟠 Обновление цены задерживается")
        text = f"{message}. Причина: {reason}. Цена в CRM сохранена. Подробно: {self.binding.detail_url}"
        conn.execute(f"INSERT OR IGNORE INTO {NOTICE_TABLE} VALUES (?,?,?,?,?,'PENDING',NULL,NULL)",
                     (key, event_key, kind, text, self.clock()))

    def _interruptions(self, conn):
        # Called only with the shared publication lock: a healthy peer cannot be
        # executing a claim while this recovery scan runs. No replay or rollback.
        rows = conn.execute(f"SELECT event_key,claim_nonce FROM {outbox.TABLE} WHERE state='CLAIMED'").fetchall()
        for key, nonce in rows:
            outbox.stop(conn, event_key=key, nonce=nonce, reason="INTERRUPTED_REQUIRES_RECONCILIATION", now_ms=self.clock())
            self._notice(conn, key, "FAILURE", "INTERRUPTED_REQUIRES_RECONCILIATION")

    def _row(self, conn, event):
        cursor = conn.execute("SELECT * FROM cars WHERE id=?", (event["car_id"],))
        result = cursor.fetchone()
        if result is None:
            raise SyncError("CRM_CAR_MISSING")
        row = dict(zip((item[0] for item in cursor.description), result))
        if row["published"] != 1 or not re.fullmatch(r"UA-[0-9]{4}", str(row["auto_number"])):
            raise SyncError("EXISTING_PUBLISHED_CAR_REQUIRED")
        self._identity(conn, row)
        if (canonical(row["price_uah"]), canonical(row["price_georgia"], georgia=True)) != (
                event["ukraine_usd"], event["georgia_usd"]):
            raise SyncError("CRM_CHANGED_NEVER_REPLAY_OLD_PRICE")
        return row

    def _identity(self, conn, row):
        if dict(self.binding.car_identities).get(row["id"]) != row["auto_number"]:
            raise SyncError("PINNED_CAR_IDENTITY_CHANGED")
        if conn.execute("SELECT COUNT(*) FROM cars WHERE auto_number=?", (row["auto_number"],)).fetchone()[0] != 1:
            raise SyncError("DUPLICATE_CRM_CAR_CODE")

    def _surfaces(self, code):
        surfaces = tuple(self.binding.resolve_surfaces(code))
        if not surfaces or {item.kind for item in surfaces} != {"CARD", "CATALOG"}:
            raise SyncError("CARD_AND_CATALOG_BINDING_REQUIRED")
        if len({item.path for item in surfaces}) != len(surfaces):
            raise SyncError("DUPLICATE_BOUND_FILE")
        for item in surfaces:
            if not isinstance(item, Surface) or not item.path.is_absolute():
                raise SyncError("ABSOLUTE_SURFACE_PATH_REQUIRED")
            if item.kind == "CARD" and item.path.name != code + ".html":
                raise SyncError("CARD_FILENAME_IDENTITY_MISMATCH")
            if urlsplit(item.url).scheme != "https":
                raise SyncError("HTTPS_PUBLIC_SURFACE_REQUIRED")
        return surfaces

    def _authority(self, event, surfaces):
        proof = self.binding.authorize(event, surfaces)
        required = ("canonical_task_id", "canonical_claim_id", "canonical_transaction_id", "gate_b_receipt_sha256")
        if not isinstance(proof, dict) or any(not isinstance(proof.get(key), str) or not proof[key] for key in required):
            raise SyncError("VERIFIED_CANONICAL_AUTHORITY_REQUIRED")
        if (proof.get("writer_fence_verified") is not True or proof.get("event_key") != event["event_key"] or
                proof.get("claim_nonce") != event["claim_nonce"] or proof.get("expires_ms", 0) < self.clock() or
                sorted(proof.get("allowed_paths", [])) != sorted(str(item.path) for item in surfaces) or
                not re.fullmatch(r"[0-9a-f]{64}", proof["gate_b_receipt_sha256"])):
            raise SyncError("CANONICAL_AUTHORITY_BINDING_MISMATCH")
        return proof

    def _prepare(self, event, surfaces, code, authority):
        journal = self.binding.journal_root / event["event_key"]
        initial = json.loads(_safe_bytes(journal / "journal.json"))
        if (initial.get("phase"), initial.get("event_key"), initial.get("claim_nonce")) != (
                "CLAIMED_NO_EFFECTS", event["event_key"], event["claim_nonce"]):
            raise SyncError("FRESH_NO_EFFECT_JOURNAL_REQUIRED")
        prepared = []
        for index, surface in enumerate(surfaces):
            before = _safe_bytes(surface.path)
            if self.read_public(surface.url) != before:
                raise SyncError("PUBLIC_PREIMAGE_DIFFERS_FROM_BOUND_FILE")
            after = replace_price(before, kind=surface.kind, code=code, event=event)
            _atomic_write(journal / f"{index}.before", before)
            _atomic_write(journal / f"{index}.after", after)
            prepared.append((surface, before, after, stat.S_IMODE(surface.path.stat().st_mode)))
        manifest = {"event_key": event["event_key"], "claim_nonce": event["claim_nonce"],
                    "phase": "PREPARED", "prepared_ms": self.clock(), "authority": authority,
                    "files": [{"path": str(s.path), "url": s.url, "kind": s.kind,
                               "before_sha256": digest(before), "after_sha256": digest(after)}
                              for s, before, after, _ in prepared]}
        _atomic_write(journal / "journal.json", json_bytes(manifest))
        return journal, prepared, manifest

    def _switch(self, prepared):
        for surface, before, after, mode in prepared:
            if _safe_bytes(surface.path) != before:
                raise SyncError("LOCAL_PREIMAGE_CHANGED")
            _atomic_write(surface.path, after, mode)

    def _rollback_known(self, prepared):
        restored = True
        for surface, before, after, mode in reversed(prepared):
            try:
                current = _safe_bytes(surface.path)
                if current == before:
                    continue
                if current != after:
                    restored = False  # A foreign writer's bytes are never overwritten.
                    continue
                _atomic_write(surface.path, before, mode)
                restored &= _safe_bytes(surface.path) == before
            except Exception:
                restored = False
        return restored

    def _execute(self, conn, event):
        prepared = []
        journal = None
        switched = False
        commit_started = False
        attempt_started_monotonic = time.monotonic_ns()
        attempt_started_wall = self.clock()
        try:
            journal = self.binding.journal_root / event["event_key"]
            journal.mkdir(mode=0o700)  # Never overwrite/reuse an old attempt.
            _fsync_directory(journal.parent)
            _atomic_write(journal / "journal.json", json_bytes(dict(phase="CLAIMED_NO_EFFECTS",
                                                                  event_key=event["event_key"],
                                                                  claim_nonce=event["claim_nonce"], files=[])))
            # Held through all filesystem changes and semantic public readback.
            conn.execute("BEGIN IMMEDIATE")
            event = outbox.require_current_claim(conn, event_key=event["event_key"], nonce=event["claim_nonce"])
            row = self._row(conn, event)
            event = dict(event, status=row.get('status'))
            code = row["auto_number"]
            surfaces = self._surfaces(code)
            authority = self._authority(event, surfaces)
            journal, prepared, manifest = self._prepare(event, surfaces, code, authority)
            # A slow preflight must not silently consume the entire SLA.
            measured_elapsed = lambda: max(self.clock() - event["created_ms"],
                                           attempt_started_wall - event["created_ms"] +
                                           (time.monotonic_ns() - attempt_started_monotonic) // 1_000_000)
            if measured_elapsed() >= 60_000:
                raise SyncError("PUBLICATION_DEADLINE_MISSED_BEFORE_SWITCH")
            self._authority(event, surfaces)
            switched = True
            self._switch(prepared)
            observations = []
            for surface, before, after, _ in prepared:
                public = self.read_public(surface.url)
                if public != after or _safe_bytes(surface.path) != after:
                    raise SyncError("PUBLIC_READBACK_OR_LOCAL_POSTIMAGE_MISMATCH")
                source = public.decode("utf-8")
                begin, end = fragment_span(source, kind=surface.kind, code=code)
                semantic_fragment(source[begin:end], code, event)
                observations.append({"surface": surface.kind, "url": surface.url,
                                     "sha256": digest(public), "observed_ms": self.clock()})
            outbox.require_current_claim(conn, event_key=event["event_key"], nonce=event["claim_nonce"])
            self._row(conn, event)
            finished = self.clock()
            identity = Identity(authority["canonical_task_id"], event["event_key"], event["claim_nonce"])
            version = PriceVersion(code, event["revision"], event["ukraine_usd"], event["georgia_usd"])
            instant = lambda milliseconds: datetime.fromtimestamp(milliseconds / 1000, timezone.utc)
            readbacks = [Readback(identity, "CRM", version, instant(finished), digest(json_bytes(row)), True, True)]
            for kind in ("CARD", "CATALOG"):
                group = [item for item in observations if item["surface"] == kind]
                # Aggregate every bound mirror; the oldest observation controls
                # freshness while SLA completion is checked independently below.
                readbacks.append(Readback(identity, kind, version, instant(min(item["observed_ms"] for item in group)),
                                          digest(json_bytes(group)), True, True))
            decision = publication_decision(identity=identity, expected=version,
                                            committed_at=instant(event["created_ms"]), now=instant(finished),
                                            observations=tuple(readbacks), publication_failed=False)
            if decision.action not in ("ACK_PUBLISHED_ELIGIBLE", "PUBLISHED_LATE_NOTIFY"):
                raise SyncError(decision.reason)
            receipt = {"event_key": event["event_key"], "claim_nonce": event["claim_nonce"],
                       "car_id": code, "revision": event["revision"], "ukraine_usd": event["ukraine_usd"],
                       "georgia_usd": event["georgia_usd"], "committed_ms": event["created_ms"],
                       "verified_ms": finished, "observations": observations,
                       "crm_sha256": digest(json_bytes(row)), "authority": authority,
                       "files": manifest["files"],
                       "acknowledgement_policy_action": decision.action,
                       "non_price_bytes_preserved": True,
                       "within_60_seconds": measured_elapsed() <= 60_000}
            receipt_bytes = json_bytes(receipt)
            _atomic_write(journal / "receipt.json", receipt_bytes)
            outbox.record_verified_publication(conn, event_key=event["event_key"], nonce=event["claim_nonce"],
                                                receipt_sha256=digest(receipt_bytes), now_ms=finished)
            if not receipt["within_60_seconds"]:
                self._notice(conn, event["event_key"], "LATE", "VERIFIED_BUT_60_SECOND_SLA_MISSED")
            commit_started = True
            conn.commit()
            # receipt + committed ledger are authoritative even if this optional
            # summary phase write fails. Never roll back a committed publication.
            try:
                manifest["phase"] = "PUBLISHED"
                _atomic_write(journal / "journal.json", json_bytes(manifest))
            except OSError:
                pass
            return "PUBLISHED"
        except Exception as error:
            reason = str(error) if isinstance(error, (SyncError, outbox.OutboxError)) else "PRICE_PUBLICATION_IO_FAILURE"
            if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,99}", reason):
                reason = "PRICE_PUBLICATION_FAILURE"
            # Keep the DB lock while attempting reversal of only our own exact
            # postimages. An external change or ambiguous commit is not overwritten.
            if switched and not commit_started and not self._rollback_known(prepared):
                reason = "ROLLBACK_AMBIGUOUS_REQUIRES_RECONCILIATION"
            if commit_started:
                reason = "COMMIT_AMBIGUOUS_REQUIRES_RECONCILIATION"
            if conn.in_transaction:
                conn.rollback()
            conn.execute("BEGIN IMMEDIATE")
            current = outbox.get(conn, event["event_key"])
            if current and current["state"] == "PUBLISHED":
                conn.commit()
                return "PUBLISHED_COMMIT_OBSERVED"
            if current and current["state"] == "CLAIMED":
                outbox.stop(conn, event_key=event["event_key"], nonce=event["claim_nonce"], reason=reason, now_ms=self.clock())
                self._notice(conn, event["event_key"], "FAILURE", reason)
            conn.commit()
            return "STOPPED"

    def tick(self):
        """At most one actual price mutation per tick; safe cars may continue."""
        try:
            with self.lock(), self.connection() as conn:
                if self._runtime_blocked():
                    return "RUNTIME_STOPPED"
                conn.execute("BEGIN IMMEDIATE")
                self._interruptions(conn)
                rows = conn.execute(f"SELECT event_key,created_ms FROM {outbox.TABLE} pending WHERE state='PENDING' "
                                    f"AND NOT EXISTS (SELECT 1 FROM {outbox.TABLE} blocked WHERE blocked.car_id=pending.car_id "
                                    "AND blocked.state IN ('CLAIMED','STOPPED')) ORDER BY created_ms,event_key").fetchall()
                for key, created in rows:
                    if self.clock() - created > 300_000:
                        self._notice(conn, key, "DELAY", "READY_TASK_START_DELAY_OVER_5_MINUTES")
                event = None
                if rows:
                    event = outbox.claim(conn, event_key=rows[0][0], nonce=secrets.token_hex(32), now_ms=self.clock())
                conn.commit()  # Durable claim precedes any publication effect.
                return self._execute(conn, event) if event else "IDLE"
        except BlockingIOError:
            return "BUSY"
        except Exception as error:
            self.record_runtime_failure(error)
            return "RUNTIME_STOPPED"

    def queue_daily(self):
        local_date = datetime.fromtimestamp(self.clock() / 1000, ZoneInfo("Asia/Ho_Chi_Minh")).date().isoformat()
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            counts = dict(conn.execute(f"SELECT state,COUNT(*) FROM {outbox.TABLE} GROUP BY state").fetchall())
            unresolved = conn.execute(f"SELECT COUNT(*) FROM {NOTICE_TABLE} WHERE state IN ('SENDING','AMBIGUOUS')").fetchone()[0]
            folder = self.binding.journal_root / "runtime_failures"
            runtime_failures = [json.loads(_safe_bytes(path)) for path in folder.glob("*.json")] if folder.exists() else []
            runtime_blocks = sum(item.get("blocked") is True for item in runtime_failures)
            unresolved += sum(item.get("state") in ("SENDING", "AMBIGUOUS") for item in runtime_failures)
            text = (f"Автопилот цен — {local_date}: опубликовано {counts.get('PUBLISHED', 0)}, "
                    f"остановлено {counts.get('STOPPED', 0)}, ожидают {counts.get('PENDING', 0)}. "
                    f"Блокировок runtime: {runtime_blocks}. "
                    f"Уведомлений без подтверждения доставки: {unresolved}. Подробно: {self.binding.detail_url}")
            conn.execute(f"INSERT OR IGNORE INTO {NOTICE_TABLE} VALUES (?,NULL,'DAILY',?,?,'PENDING',NULL,NULL)",
                         (digest(json_bytes(("DAILY", local_date))), text, self.clock()))
            conn.commit()

    def queue_daily_unavailable(self):
        """The daily reminder remains possible while the CRM database is down."""
        today = datetime.fromtimestamp(self._wall_clock() / 1000, ZoneInfo("Asia/Ho_Chi_Minh")).date().isoformat()
        folder = self.binding.journal_root / "runtime_failures"
        folder.mkdir(mode=0o700, exist_ok=True)
        path = folder / ("daily-" + today + ".json")
        with self.lock(self.binding.journal_root / "runtime_failure.lock"):
            if not path.exists():
                _atomic_write(path, json_bytes(dict(reason="DAILY_DATABASE_UNAVAILABLE", blocked=False, state="PENDING",
                    text=f"🔴 Автопилот цен — {today}: статистика CRM недоступна, автоматическое обновление остановлено. Подробно: {self.binding.detail_url}")))

    def reconcile_recovered(self, event_key, build_evidence, *, resume_current=False, recovery_key=None):
        """Read/close a stopped attempt after a trusted recovery gate, never replay.

        build_evidence must independently prove the root-cause correction and
        fresh Gate B. This method verifies its bindings against actual current
        CRM, public bytes and the attempt's durable preimages. A missing initial
        journal needs the canonical recovery adapter's separate safe procedure.
        Nothing automatically calls this API merely because a timer expired.
        """
        if not callable(build_evidence):
            raise SyncError("TRUSTED_RECOVERY_EVIDENCE_BUILDER_REQUIRED")
        if type(resume_current) is not bool:
            raise SyncError("EXACT_RESUME_BOOLEAN_REQUIRED")
        with self.lock(), self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                event = outbox.get(conn, event_key)
                if recovery_key is not None and event is not None and event["state"] in ("RECONCILED", "PUBLISHED"):
                    recorded = outbox.get_recovery(conn, recovery_key)
                    if recorded and (recorded["event_key"], recorded["claim_nonce"], recorded["final_state"]) == (
                            event_key, event["claim_nonce"], event["state"]):
                        # Pure idempotent readback of an already recorded proof.
                        # Never enqueue another successor on this replay path.
                        conn.commit()
                        return event
                if event is None or event["state"] not in ("STOPPED", "CLAIMED"):
                    raise SyncError("UNCERTAIN_ATTEMPT_REQUIRED_FOR_RECOVERY")
                cursor = conn.execute("SELECT * FROM cars WHERE id=?", (event["car_id"],))
                values = cursor.fetchone()
                if values is None:
                    raise SyncError("CRM_CAR_MISSING")
                row = dict(zip((item[0] for item in cursor.description), values))
                self._identity(conn, row)
                code = row["auto_number"]
                if row["published"] != 1:
                    raise SyncError("EXISTING_PUBLISHED_CAR_REQUIRED")
                surfaces = self._surfaces(code)
                authority = self._authority(event, surfaces)
                latest = conn.execute(f"SELECT MAX(revision) FROM {outbox.TABLE} WHERE car_id=?", (event["car_id"],)).fetchone()[0]
                current = dict(ukraine_usd=canonical(row["price_uah"]),
                               georgia_usd=canonical(row["price_georgia"], georgia=True), status=row.get('status'))
                journal = self.binding.journal_root / event_key
                manifest = json.loads(_safe_bytes(journal / "journal.json"))
                if (manifest.get("event_key"), manifest.get("claim_nonce")) != (event_key, event["claim_nonce"]):
                    raise SyncError("RECOVERY_JOURNAL_IDENTITY_MISMATCH")
                before_files = {}
                no_effects_phase = manifest.get("phase") == "CLAIMED_NO_EFFECTS"
                for index, item in enumerate(manifest["files"]):
                    before = _safe_bytes(journal / f"{index}.before")
                    if digest(before) != item["before_sha256"]:
                        raise SyncError("RECOVERY_PREIMAGE_HASH_MISMATCH")
                    before_files[item["path"]] = before
                if not no_effects_phase and set(before_files) != {str(item.path) for item in surfaces}:
                    raise SyncError("RECOVERY_FILE_SET_MISMATCH")
                observations, prior_state_restored, prices_match, non_price_preserved = [], True, True, True
                for surface in surfaces:
                    actual = _safe_bytes(surface.path)
                    if self.read_public(surface.url) != actual:
                        raise SyncError("RECOVERY_PUBLIC_LOCAL_MISMATCH")
                    if no_effects_phase:
                        # The durable journal is written before preparation; only
                        # PREPARED may enter _switch. Re-validate the current
                        # target-only patch now, but perform no public write.
                        replace_price(actual, kind=surface.kind, code=code, event=current)
                        before_files[str(surface.path)] = actual
                    source = actual.decode("utf-8")
                    begin, end = fragment_span(source, kind=surface.kind, code=code)
                    try:
                        semantic_fragment(source[begin:end], code, current)
                    except SyncError:
                        prices_match = False
                    expected_fragment = render_market_prices(_event_price_row(code, current),
                                                             compact=surface.kind == "CATALOG", require_car_id=True)
                    prices_match &= source[begin:end] == expected_fragment
                    prior_source = before_files[str(surface.path)].decode("utf-8")
                    prior_begin, prior_end = fragment_span(prior_source, kind=surface.kind, code=code)
                    if surface.kind == "CATALOG":
                        outside_verified = self._catalog_recovery_history(conn, event, surface.path,
                                                                          before_files[str(surface.path)], actual, code)
                        preserved_here = outside_verified
                        restored_here = outside_verified and source[begin:end] == prior_source[prior_begin:prior_end]
                    else:
                        preserved_here = source[:begin] == prior_source[:prior_begin] and source[end:] == prior_source[prior_end:]
                        restored_here = actual == before_files[str(surface.path)]
                    prior_state_restored &= restored_here
                    non_price_preserved &= preserved_here
                    observations.append({"kind": surface.kind, "path": str(surface.path), "url": surface.url, "sha256": digest(actual)})
                observed_ms = self.clock()
                facts = {"event_key": event_key, "claim_nonce": event["claim_nonce"], "current_revision": latest,
                         "observed_ms": observed_ms, "crm_sha256": digest(json_bytes(row)),
                         "prices_match_current": prices_match, "prior_state_restored": prior_state_restored,
                         "non_price_content_preserved": non_price_preserved,
                         "journal_proves_no_public_effects": no_effects_phase,
                         "observations": observations, "authority": authority}
                for kind in ("CARD", "CATALOG"):
                    facts[kind.lower() + "_sha256"] = digest(json_bytes([item for item in observations if item["kind"] == kind]))
                observation_receipt = json_bytes(facts)
                evidence = build_evidence(event, dict(facts), digest(observation_receipt))
                if type(evidence) is not outbox.RecoveryEvidence:
                    raise SyncError("EXACT_RECOVERY_EVIDENCE_REQUIRED")
                if recovery_key is not None and evidence.recovery_key != recovery_key:
                    raise SyncError("RECOVERY_KEY_BINDING_MISMATCH")
                if no_effects_phase and evidence.outcome != "NO_EFFECT":
                    raise SyncError("NO_EFFECT_JOURNAL_CANNOT_CLAIM_PUBLICATION")
                for name in ("event_key", "claim_nonce", "current_revision", "observed_ms", "card_sha256", "catalog_sha256", "prices_match_current"):
                    if getattr(evidence, name) != facts[name]:
                        raise SyncError("RECOVERY_PROOF_ACTUAL_OBSERVATION_MISMATCH")
                if evidence.outcome in ("NO_EFFECT", "RESTORED") and not prior_state_restored:
                    raise SyncError("RECOVERY_PUBLIC_PREIMAGES_NOT_RESTORED")
                if evidence.outcome == "PUBLISHED":
                    if not non_price_preserved:
                        raise SyncError("RECOVERY_NON_PRICE_CONTENT_CHANGED")
                    if (not prices_match or latest != event["revision"]
                            or (current['ukraine_usd'], current['georgia_usd']) !=
                               (event['ukraine_usd'], event['georgia_usd'])):
                        raise SyncError("RECOVERY_CURRENT_PRICE_IDENTITY_MISMATCH")
                    if evidence.publication_receipt_sha256 != digest(observation_receipt):
                        raise SyncError("RECOVERY_PUBLICATION_RECEIPT_HASH_MISMATCH")
                    destination = journal / ("recovery_" + evidence.recovery_key + ".json")
                    if destination.exists() and _safe_bytes(destination) != observation_receipt:
                        raise SyncError("RECOVERY_RECEIPT_ALREADY_CONFLICTS")
                    _atomic_write(destination, observation_receipt)
                result = outbox.reconcile_verified(conn, event_key=event_key, nonce=event["claim_nonce"],
                                                   evidence=evidence, now_ms=self.clock())
                if resume_current and evidence.outcome in ("NO_EFFECT", "RESTORED") and latest == event["revision"]:
                    if authority.get("verified_recovery_successor_allowed") is not True:
                        raise SyncError("REVIEWED_RECOVERY_SUCCESSOR_DELEGATION_REQUIRED")
                    # One new attempt, bound to the immutable verified recovery
                    # proof. No CRM mutation, old-nonce reuse or elapsed-time retry.
                    recorded = outbox.get_recovery(conn, evidence.recovery_key)
                    successor_key = digest(json_bytes(("VERIFIED_PRICE_RECOVERY_SUCCESSOR_V1", event_key,
                                                       event["claim_nonce"], evidence.recovery_key,
                                                       recorded["evidence_payload_sha256"])))
                    outbox.enqueue(conn, event_key=successor_key, car_id=event["car_id"],
                                   ukraine_usd=current["ukraine_usd"], georgia_usd=current["georgia_usd"], now_ms=self.clock())
                conn.commit()
                return result
            except Exception:
                if conn.in_transaction:
                    conn.rollback()
                raise

    def _catalog_recovery_history(self, conn, event, path, before, actual, code):
        """Accept only proven intervening *other-car* price publications.

        The stopped car's fragment is masked; every other byte must form a chain
        of exact pre/postimages in committed receipts. No stale catalog is written.
        Unreceipted edits (including descriptions/stages) require separate review.
        """
        def outside(value):
            text = value.decode("utf-8")
            start, end = fragment_span(text, kind="CATALOG", code=code)
            if _Prices(text[start:end]).codes != [code]:
                raise SyncError("RECOVERY_PRICE_CAR_IDENTITY_MISMATCH")
            return (text[:start] + text[end:]).encode("utf-8")
        cursor, wanted = outside(before), outside(actual)
        if cursor == wanted:
            return True
        candidates = conn.execute(f"SELECT event_key FROM {outbox.TABLE} WHERE state='PUBLISHED' "
                                  "AND car_id<>? AND finished_ms>=? ORDER BY finished_ms,event_key LIMIT 1001",
                                  (event["car_id"], event["claimed_ms"])).fetchall()
        if len(candidates) > 1000:
            raise SyncError("RECOVERY_HISTORY_REQUIRES_CANONICAL_COMPACTION")
        edges = []
        for (key,) in candidates:
            other = outbox.get(conn, key)
            folder = self.binding.journal_root / key
            try:
                receipt_bytes = _safe_bytes(folder / "receipt.json")
            except FileNotFoundError:
                continue
            if digest(receipt_bytes) != other["receipt_sha256"]:
                continue
            receipt = json.loads(receipt_bytes)
            if (receipt.get("event_key"), receipt.get("claim_nonce")) != (key, other["claim_nonce"]):
                raise SyncError("RECOVERY_HISTORY_RECEIPT_IDENTITY_MISMATCH")
            for index, entry in enumerate(receipt.get("files", ())):
                if entry.get("kind") != "CATALOG" or entry.get("path") != str(path):
                    continue
                old, new = _safe_bytes(folder / f"{index}.before"), _safe_bytes(folder / f"{index}.after")
                if (digest(old), digest(new)) != (entry["before_sha256"], entry["after_sha256"]):
                    raise SyncError("RECOVERY_HISTORY_PREIMAGE_HASH_MISMATCH")
                if replace_price(old, kind="CATALOG", code=receipt["car_id"], event=other) != new:
                    raise SyncError("RECOVERY_HISTORY_UNRELATED_BYTES_CHANGED")
                edges.append((outside(old), outside(new)))
        # Global lock serializes the real chain; identical timestamps need not
        # impose an arbitrary order. Exact predecessor bytes select the next edge.
        for _ in range(len(edges)):
            found = next(((left, right) for left, right in edges if left == cursor and right != cursor), None)
            if found is None:
                return False
            edges.remove(found)
            cursor = found[1]
            if cursor == wanted:
                return True
        return False

    async def deliver_notices(self, bot):
        async with self._notice_async_lock:
            try:
                with self.lock(self.binding.journal_root / "notification_delivery.lock"):
                    await self._deliver_notices_locked(bot)
            except BlockingIOError:
                return

    async def _deliver_notices_locked(self, bot):
        # SENDING survives a crash. Telegram has no caller-supplied idempotency
        # key, so ambiguous delivery must never automatically send a duplicate.
        folder = self.binding.journal_root / "runtime_failures"
        if folder.exists():
            for path in sorted(folder.glob("*.json")):
                notice = json.loads(_safe_bytes(path))
                if notice["state"] == "SENDING":
                    notice["state"] = "AMBIGUOUS"
                    _atomic_write(path, json_bytes(notice))
                if notice["state"] != "PENDING":
                    continue
                notice["state"] = "SENDING"
                _atomic_write(path, json_bytes(notice))
                try:
                    sent = await bot.send_message(chat_id=self.binding.owner_chat_id, text=notice["text"], disable_web_page_preview=True)
                    if type(sent.message_id) is not int or sent.message_id <= 0:
                        raise SyncError("TELEGRAM_ACK_REQUIRED")
                    notice.update(state="SENT", telegram_message_id=sent.message_id)
                except Exception:
                    notice["state"] = "AMBIGUOUS"
                _atomic_write(path, json_bytes(notice))
        try:
            self._check_notice_database()
        except sqlite3.Error as error:
            self.record_runtime_failure(error)
            return
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(f"UPDATE {NOTICE_TABLE} SET state='AMBIGUOUS' WHERE state='SENDING'")
            rows = conn.execute(f"SELECT notice_key,text FROM {NOTICE_TABLE} WHERE state='PENDING' ORDER BY created_ms,notice_key LIMIT 10").fetchall()
            conn.commit()
        for key, text in rows:
            with self.connection() as conn:
                conn.execute("BEGIN IMMEDIATE")
                claimed = conn.execute(f"UPDATE {NOTICE_TABLE} SET state='SENDING' WHERE notice_key=? AND state='PENDING'", (key,)).rowcount
                conn.commit()

            if not claimed:
                continue
            try:
                sent = await bot.send_message(chat_id=self.binding.owner_chat_id, text=text, disable_web_page_preview=True)
                if type(sent.message_id) is not int or sent.message_id <= 0:
                    raise SyncError("TELEGRAM_ACK_REQUIRED")
                state, message_id = "SENT", sent.message_id
            except Exception:
                state, message_id = "AMBIGUOUS", None
            with self.connection() as conn:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(f"UPDATE {NOTICE_TABLE} SET state=?,sent_ms=?,telegram_message_id=? WHERE notice_key=? AND state='SENDING'",
                             (state, self.clock(), message_id, key))
                conn.commit()

    def _check_notice_database(self):
        with self.connection() as conn:
            conn.execute(f"SELECT notice_key FROM {NOTICE_TABLE} LIMIT 1").fetchone()


BINDING_KEY = "uaart_price_sync_verified_binding_v1"


def register(app):
    """Existing CRM application only; installer must bind verified live adapters."""
    binding = app.bot_data.get(BINDING_KEY)
    if not isinstance(binding, Binding):
        raise SyncError("PRICE_SYNC_NOT_INSTALLED_WITH_VERIFIED_BINDING")
    if app.job_queue is None:
        raise SyncError("EXISTING_CRM_JOB_QUEUE_REQUIRED")
    worker = V5Worker(binding)

    async def tick(context):
        try:
            await asyncio.to_thread(worker.tick)
        finally:
            await worker.deliver_notices(context.bot)

    async def daily(context):
        try:
            await asyncio.to_thread(worker.queue_daily)
        except (sqlite3.Error, OSError, SyncError, outbox.OutboxError) as error:
            worker.record_runtime_failure(error)
            worker.queue_daily_unavailable()
        finally:
            await worker.deliver_notices(context.bot)

    if not app.job_queue.get_jobs_by_name("uaart-price-sync-v1"):
        app.job_queue.run_repeating(tick, interval=5, first=1, name="uaart-price-sync-v1",
                                    job_kwargs={"max_instances": 1, "coalesce": True})
    if not app.job_queue.get_jobs_by_name("uaart-price-sync-daily-v1"):
        app.job_queue.run_daily(daily, time=wall_time(10, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")),
                                name="uaart-price-sync-daily-v1", job_kwargs={"max_instances": 1, "coalesce": True})
    return worker


class V5Worker(Worker):
    """FINAL v5 queue executor; register() activates this implementation.

    Per-car OS locks serialize intentions across processes and survive neither a
    process crash nor a restart. Checkpoints are durable SQLite records. No
    SQLite transaction or shared publication lock spans an HTTP/Telegram call.
    The older Worker is retained only for inspecting the previous candidate.
    """

    def __init__(self, binding):
        super().__init__(binding)
        # Independent worker threads must not compare their wall-clock samples
        # with one another. Transaction/checkpoint ordering is the durable clock.
        def wall():
            value = self._wall_clock()
            if type(value) is not int or value < 0:
                raise SyncError('V5_VALID_CLOCK_REQUIRED')
            return value
        self.clock = wall

    @contextmanager
    def _shared_lock(self):
        # Brief admission only: no HTTP, Telegram or long-lived DB transaction.
        deadline = time.monotonic() + 2
        descriptor = os.open(self.binding.publication_lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            while True:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.005)
            yield
        finally:
            os.close(descriptor)

    def _operation(self, key):
        with self.connection() as conn:
            result = outbox.get_operation(conn, key)
        if result is None:
            raise SyncError('V5_OPERATION_MISSING')
        return result

    @staticmethod
    def _schema_version(conn):
        schema=conn.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name").fetchall()
        return digest(json_bytes(schema))

    def _full_row(self, conn, event):
        cursor = conn.execute('SELECT * FROM cars WHERE id=?', (event['car_id'],))
        values = cursor.fetchone()
        if values is None:
            raise SyncError('V5_CAR_MISSING')
        row = dict(zip((item[0] for item in cursor.description), values))
        if row.get('published') not in (None, 0, 1):
            raise SyncError('V5_INVALID_VISIBILITY')
        if ((event['car_code'] and str(row.get('auto_number') or '') != event['car_code'])
                or (event['vin'] and str(row.get('vin') or '') != event['vin'])):
            raise SyncError('V5_CAR_IDENTITY_CHANGED')
        if event['car_code'] and conn.execute('SELECT COUNT(*) FROM cars WHERE auto_number=?', (event['car_code'],)).fetchone()[0] != 1:
            raise SyncError('V5_DUPLICATE_CAR_CODE')
        return row

    def _verified_identity(self, event):
        if self.binding.resolve_identity is None:
            if dict(self.binding.car_identities).get(event['car_id']) != event['car_code']:
                raise SyncError('V5_BOUND_CAR_IDENTITY_REQUIRED')
        else:
            actual = self.binding.resolve_identity(event['car_id'])
            if (type(actual) is not dict or actual.get('id') != event['car_id']
                    or (event['car_code'] and actual.get('auto_number') != event['car_code'])
                    or (event['vin'] and str(actual.get('vin') or '') != event['vin'])):
                raise SyncError('V5_AUTHENTICATED_CAR_IDENTITY_MISMATCH')

    def _v5_surfaces(self, event):
        self._verified_identity(event)
        with self.connection() as conn:
            row = self._full_row(conn, event)
        if row.get('published') != 1:
            return ()
        if not re.fullmatch(r'UA-[0-9]{4}', event['car_code']):
            raise SyncError('V5_PUBLICATION_BEFORE_DRAFT_INTENT_SETTLED')
        surfaces = tuple(self.binding.resolve_surfaces(event['car_code']))
        kinds = {s.kind for s in surfaces}
        if not {'CARD', 'CATALOG', 'HOME'} <= kinds or not kinds <= {'CARD', 'CATALOG', 'HOME'}:
            raise SyncError('V5_CARD_CATALOG_HOME_BINDING_REQUIRED')
        if len({str(s.path) for s in surfaces}) != len(surfaces):
            raise SyncError('V5_UNIQUE_PUBLIC_SURFACES_REQUIRED')
        for surface in surfaces:
            if not surface.path.is_absolute() or urlsplit(surface.url).scheme != 'https':
                raise SyncError('V5_EXPLICIT_PUBLIC_SURFACES_REQUIRED')
            if type(surface.price_applicable) is not bool or not surface.price_applicable and surface.kind != 'HOME':
                raise SyncError('V5_EXPLICIT_HOME_APPLICABILITY_REQUIRED')
            if surface.kind == 'CARD' and surface.path.name != event['car_code'] + '.html':
                raise SyncError('V5_CARD_FILENAME_IDENTITY_MISMATCH')
        return surfaces

    @staticmethod
    def _span(text, surface, code):
        if surface.kind != 'HOME':
            return fragment_span(text, kind=surface.kind, code=code)
        # HOME may use a wrapper other than <article>. Its installed marker and
        # immutable car identity delimit exactly the managed price fragment.
        matches = []
        for match in re.finditer(re.escape(START) + r'.*?' + re.escape(END), text, re.S):
            parser = _Prices(match.group())
            if parser.codes == [code]:
                matches.append((match.start(), match.end()))
        if len(matches) != 1:
            raise SyncError('V5_EXACTLY_ONE_HOME_PRICE_FRAGMENT_REQUIRED')
        return matches[0]

    @classmethod
    def _protected_hash(cls, data, surface, code):
        text = data.decode('utf-8')
        if not surface.price_applicable:
            # Binding must explicitly establish that this HOME contains no car
            # previews. A future homepage with a price marker cannot inherit it.
            if START in text or re.search(r'href=["\'][^"\']*UA-\d{4}\.html', text, re.I):
                raise SyncError('V5_HOME_APPLICABILITY_CHANGED')
            return digest(data)
        if surface.kind == 'CARD':
            begin, end = cls._span(text, surface, code)
            return digest((text[:begin] + '<MANAGED_PRICE>' + text[end:]).encode())
        fragments = list(re.finditer(re.escape(START) + r'.*?' + re.escape(END), text, re.S))
        if not fragments or len(fragments) != text.count(START) or len(fragments) != text.count(END):
            raise SyncError('V5_MALFORMED_SHARED_PRICE_FRAGMENTS')
        identities = []
        for fragment in fragments:
            parsed = _Prices(fragment.group())
            if len(parsed.codes) != 1:
                raise SyncError('V5_SHARED_FRAGMENT_IDENTITY_REQUIRED')
            identities.append(parsed.codes[0])
        # Include identities and their order; other cars may change only values.
        masked = re.sub(re.escape(START) + r'.*?' + re.escape(END), '<MANAGED_PRICE>', text, flags=re.S)
        return digest(json_bytes({'outside': masked, 'identities': identities}))

    @staticmethod
    def _desired(event, surface):
        return render_market_prices(_event_price_row(event['car_code'], event),
                                    compact=surface.kind != 'CARD', require_car_id=True)

    def _proof(self, event, surfaces):
        # Provider verifies installed source/schema, control bridge, durable
        # claim, actual actor/bot evidence and writer fence. Never synthesize it.
        return self._authority(event, surfaces)

    def _commit_selected_price(self, event, surfaces):
        with self._shared_lock(), self.connection() as conn:
            authority = self._proof(event, surfaces)
            conn.execute('BEGIN IMMEDIATE')
            try:
                current = outbox.require_head(conn, event['event_key'])
                if current['state'] != 'CLAIMED' or current['claim_nonce'] != event['claim_nonce']:
                    raise SyncError('V5_DB_CHECKPOINT_CHANGED')
                before = self._full_row(conn, current)
                if bool(surfaces) != (before.get('published') == 1):
                    raise SyncError('V5_VISIBILITY_CHANGED')
                schema_version = self._schema_version(conn)
                before_all = {r[0]: r for r in conn.execute('SELECT * FROM cars').fetchall()}
                if current['expected_old_json'] is not None:
                    expected_old = json.loads(current['expected_old_json'])[0]
                    if before[current['field']] != expected_old:
                        raise SyncError('V5_OPERATOR_CAS_CONFLICT')
                stored = None
                if current['value'] is not None:
                    amount = Decimal(current['value'])
                    if amount != amount.to_integral_value():
                        raise SyncError('V5_EXISTING_INTEGER_USD_STORAGE_REQUIRED')
                    stored = int(amount)
                expected = dict(before)
                expected[current['field']] = stored
                assignments = {current['field']: stored}
                if 'updated_at' in before:
                    assignments['updated_at'] = datetime.fromtimestamp(self.clock()/1000, timezone.utc).isoformat()
                    expected['updated_at'] = assignments['updated_at']
                # Capture validated HTML recovery points BEFORE any price DB
                # effect. The same short shared lock protects capture and commit.
                prepared = dict(current, before_json=json_bytes(before).decode(),
                                after_json=json_bytes(expected).decode(),
                                ukraine_usd=self._price_pair(expected)[0],
                                georgia_usd=canonical(expected['price_georgia'],georgia=True))
                if surfaces:
                    _, baseline = self._journal(prepared,surfaces)
                    if baseline['db_before'] != before:
                        raise SyncError('V5_PRECOMMIT_RECOVERY_BASELINE_CHANGED')
                    for surface,item in zip(surfaces,baseline['files']):
                        self._check_surface(_safe_bytes(surface.path),surface,prepared,item,require_desired=False)
                else:
                    folder = self._data_folder(current)
                    _atomic_write(folder / ('data_before_' + digest(json_bytes(before)) + '.json'), json_bytes(before))
                if self.clock() >= authority['expires_ms']:
                    raise SyncError('V5_AUTHORITY_EXPIRED_BEFORE_DB_COMMIT')
                conn.execute('UPDATE cars SET ' + ','.join(name + '=?' for name in assignments) + ' WHERE id=?',
                             [*assignments.values(), current['car_id']])
                after = self._full_row(conn, current)
                if after != expected:
                    raise SyncError('V5_DB_PROTECTED_DATA_CHANGED')
                # Keep compatibility with the existing internal audit, if that
                # observed schema is present. The v5 ledger separately links it.
                legacy_audit_id = None
                audit_columns = {row[1] for row in conn.execute('PRAGMA table_info(audit)')}
                required = {'actor_id','action','entity_type','entity_id','field','old_value','new_value','created_at'}
                if required <= audit_columns:
                    old = before[current['field']]
                    legacy_audit_id = conn.execute(
                        'INSERT INTO audit(actor_id,action,entity_type,entity_id,field,old_value,new_value,created_at) VALUES(?,?,?,?,?,?,?,?)',
                        (current['actor_id'],'card_edit','cars',current['car_id'],current['field'],
                         None if old is None else str(old),None if stored is None else str(stored),
                         assignments.get('updated_at',str(self.clock())))).lastrowid
                now = self.clock()
                after = self._full_row(conn, current)
                if after != expected:
                    raise SyncError('V5_AUDIT_TRIGGER_CROSS_WRITE')
                after_all = {r[0]: r for r in conn.execute('SELECT * FROM cars').fetchall()}
                if ({k:v for k,v in before_all.items() if k != current['car_id']} !=
                        {k:v for k,v in after_all.items() if k != current['car_id']}):
                    raise SyncError('V5_OTHER_CAR_CHANGED')
                event = outbox.transition_operation(conn,event_key=current['event_key'],nonce=current['claim_nonce'],
                    expected_state='CLAIMED',new_state='DB_COMMITTED',now_ms=now,
                    old_value=(None if before[current['field']] is None else canonical(before[current['field']],georgia=current['field']=='price_georgia')),
                    ukraine_usd=self._price_pair(after)[0],georgia_usd=self._price_pair(after)[1],
                    before_json=json_bytes(before).decode(),after_json=json_bytes(after).decode(),db_committed_ms=now)
                outbox.audit_operation(conn,event['event_key'],'DB_COMMITTED',
                    {'old_value':before[current['field']],'new_value':stored,'before':before,'after':after,
                     'legacy_audit_rowid':legacy_audit_id,'authority':authority,
                     'schema_sha256':schema_version,'operation_sequence':event['sequence'],
                     'record_version_before':digest(json_bytes(before)),
                     'record_version_after':digest(json_bytes(after))},now)
                if self._schema_version(conn)!=schema_version:
                    raise SyncError('V5_SCHEMA_CHANGED_DURING_PRICE_COMMIT')
                if self.clock() >= authority['expires_ms']:
                    raise SyncError('V5_AUTHORITY_EXPIRED_BEFORE_DB_COMMIT')
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        # This helper opens an independent connection after commit/close.
        if surfaces:
            self._db_readback(event, record=True)
        else:
            self._data_readback(event)
        return self._operation(event['event_key'])

    @staticmethod
    def _price_pair(row):
        # A draft may not have UA yet. Its missing value is preserved, not
        # silently converted to a synthetic zero for a public renderer.
        return (None if row.get('price_uah') is None else canonical(row['price_uah']),
                canonical(row.get('price_georgia'), georgia=True))

    def _data_folder(self, event):
        folder = self.binding.journal_root / ('v5_' + event['event_key'])
        folder.mkdir(mode=0o700, exist_ok=True)
        if folder.is_symlink() or stat.S_IMODE(folder.stat().st_mode) & 0o077:
            raise SyncError('V5_PRIVATE_JOURNAL_REQUIRED')
        return folder

    def _data_readback(self, event):
        # Reconcile the actual committed operation on a separate connection.
        # Visibility/description changes are preserved; a newer price is never
        # overwritten to make an old operation appear successful.
        with self.connection() as conn:
            actual_event = outbox.get_operation(conn, event['event_key'])
            row = self._full_row(conn, event)
            schema = self._schema_version(conn)
            item = conn.execute(f"SELECT payload_json FROM {outbox.V5_AUDIT} WHERE event_key=? AND fact='DB_COMMITTED'",
                                (event['event_key'],)).fetchone()
        if item is None or actual_event['claim_nonce'] != event['claim_nonce']:
            raise SyncError('V5_DB_COMMIT_AUDIT_MISSING')
        recorded = json.loads(item[0])
        details = recorded.get('details', {})
        after = json.loads(event['after_json'])
        if (recorded.get('operation_id') != event['event_key']
                or recorded.get('car_id') != event['car_id']
                or details.get('schema_sha256') != schema
                or details.get('operation_sequence') != event['sequence']
                or details.get('after') != after
                or details.get('record_version_after') != digest(json_bytes(after))):
            raise SyncError('V5_DATA_COMMIT_PROVENANCE_MISMATCH')
        pair = self._price_pair(row)
        if (self._price_pair(after) != pair or pair != (event['ukraine_usd'], event['georgia_usd'])
                or pair[0 if event['field'] == 'price_uah' else 1] != event['value']):
            raise SyncError('V5_NEWER_PRICE_PRESERVED_RECONCILIATION_REQUIRED')
        return row, schema

    def _complete_hidden(self, event):
        if not callable(self.binding.verify_hidden):
            raise SyncError('V5_BOUND_HIDDEN_VIEW_VERIFIER_REQUIRED')
        row, schema = self._data_readback(event)
        if row.get('published') == 1:
            raise SyncError('V5_VISIBILITY_CHANGED')
        # The canonical lifecycle verifier inspects all manifest-bound served
        # paths. It is separate from a price receipt and must not invent an
        # HTTP/site PASS from the CRM flag alone.
        visibility = self.binding.verify_hidden(event, row)
        required = dict(car_id=event['car_id'], published=0,
                        row_sha256=digest(json_bytes(row)), public_projection='NOT_APPLICABLE',
                        retired_public_views_verified=True)
        if (type(visibility) is not dict or any(visibility.get(k) != v for k, v in required.items())
                or not re.fullmatch(r'[0-9a-f]{64}', str(visibility.get('visibility_receipt_sha256', '')))):
            raise SyncError('V5_VERIFIED_HIDDEN_VIEW_RECEIPT_REQUIRED')
        with self._shared_lock(), self.connection() as conn:
            authority = self._proof(event, ())
            conn.execute('BEGIN IMMEDIATE')
            try:
                if self._full_row(conn, event) != row or self._schema_version(conn) != schema:
                    raise SyncError('V5_DATA_COMPLETION_CURRENT_ROW_CHANGED')
                # Revalidate local visibility under the same fence as the DB
                # checkpoint. No network is permitted by this callback contract.
                current_visibility = self.binding.verify_hidden(event, row)
                if current_visibility != visibility:
                    raise SyncError('V5_HIDDEN_VIEW_CHANGED_BEFORE_COMPLETION')
                now = self.clock()
                receipt = {'operation_id':event['event_key'], 'claim_nonce':event['claim_nonce'],
                    'car_id':event['car_id'], 'car_code':event['car_code'], 'vin':event['vin'],
                    'actor_id':event['actor_id'], 'chat_id':event['chat_id'], 'market':event['field'],
                    'old_value':event['old_value'], 'new_value':event['value'],
                    'ua':event['ukraine_usd'], 'ge':event['georgia_usd'],
                    'db_readback':'PASS', 'protected_data':'PASS', 'verification':'PASS',
                    'public_projection':'NOT_APPLICABLE', 'site_verification':'NOT_APPLICABLE',
                    'separate_connection':True, 'current_row_sha256':digest(json_bytes(row)),
                    'committed_row_sha256':digest(event['after_json'].encode()),
                    'schema_sha256':schema, 'visibility':visibility, 'authority':authority,
                    'verified_ms':now}
                encoded = json_bytes(receipt)
                receipt_path = self._data_folder(event) / ('data_receipt_' + digest(encoded) + '.json')
                if receipt_path.exists():
                    if _safe_bytes(receipt_path) != encoded:
                        raise SyncError('V5_DATA_RECEIPT_CONTENT_MISMATCH')
                else:
                    _atomic_write(receipt_path, encoded)
                if self.clock() >= authority['expires_ms']:
                    raise SyncError('V5_AUTHORITY_EXPIRED_BEFORE_DB_COMMIT')
                event = outbox.complete_data_operation(conn, event_key=event['event_key'],
                    nonce=event['claim_nonce'], receipt=receipt, receipt_sha256=digest(encoded), now_ms=now)
                label = event['car_code'] or ('CRM #' + str(event['car_id']))
                outbox.queue_operation_notice(conn, event_key=event['event_key'], kind='SUCCESS',
                    body=f'✅ Сохранено и проверено: {label}. Объявление не опубликовано; данные сохранены.', now_ms=now)
                if self.clock() >= authority['expires_ms']:
                    raise SyncError('V5_AUTHORITY_EXPIRED_BEFORE_DB_COMMIT')
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        completed = self._operation(event['event_key'])
        if completed['state'] != 'COMPLETED' or completed['receipt_sha256'] != digest(encoded):
            raise SyncError('V5_DATA_COMPLETION_LEDGER_READBACK_MISMATCH')
        return completed

    def _db_readback(self, event, *, record=False):
        with self.connection() as conn:
            actual_event = outbox.get_operation(conn,event['event_key'])
            row = self._full_row(conn,event)
            schema_version=self._schema_version(conn)
            committed=conn.execute(f"SELECT payload_json FROM {outbox.V5_AUDIT} WHERE event_key=? AND fact='DB_COMMITTED'",
                                   (event['event_key'],)).fetchone()
        expected = json.loads(event['after_json'])
        if committed is None:
            raise SyncError('V5_DB_COMMIT_AUDIT_MISSING')
        details=json.loads(committed[0]).get('details',{})
        if (details.get('schema_sha256')!=schema_version or details.get('operation_sequence')!=event['sequence']
                or details.get('record_version_after')!=digest(json_bytes(row))):
            raise SyncError('V5_DB_RECORD_OR_SCHEMA_VERSION_MISMATCH')
        if row != expected or actual_event['claim_nonce'] != event['claim_nonce']:
            raise SyncError('V5_SEPARATE_DB_READBACK_MISMATCH')
        if (canonical(row['price_uah']),canonical(row['price_georgia'],georgia=True)) != (
                event['ukraine_usd'],event['georgia_usd']):
            raise SyncError('V5_INDEPENDENT_PRICE_READBACK_MISMATCH')
        if record:
            with self.connection() as conn:
                conn.execute('BEGIN IMMEDIATE')
                outbox.audit_operation(conn,event['event_key'],'DB_READBACK',
                    {'separate_connection':True,'row_sha256':digest(json_bytes(row)),
                     'schema_sha256':schema_version,'operation_sequence':event['sequence'],
                     'ua':event['ukraine_usd'],'ge':event['georgia_usd']},self.clock())
                conn.commit()
        return row

    def _journal(self,event,surfaces):
        folder=self.binding.journal_root/('v5_'+event['event_key'])
        folder.mkdir(mode=0o700,exist_ok=True)
        if folder.is_symlink() or stat.S_IMODE(folder.stat().st_mode)&0o077:
            raise SyncError('V5_PRIVATE_JOURNAL_REQUIRED')
        manifest_path=folder/'manifest.json'
        if manifest_path.exists():
            manifest=json.loads(_safe_bytes(manifest_path))
            if (manifest.get('event_key'),manifest.get('claim_nonce')) != (event['event_key'],event['claim_nonce']):
                raise SyncError('V5_JOURNAL_IDENTITY_MISMATCH')
            if [(x['path'],x['url'],x['kind'],x['price_applicable']) for x in manifest['files']] != [
                    (str(s.path),s.url,s.kind,s.price_applicable) for s in surfaces]:
                raise SyncError('V5_JOURNAL_SURFACES_CHANGED')
            for i,item in enumerate(manifest['files']):
                if digest(_safe_bytes(folder/f'{i}.before')) != item['before_sha256']:
                    raise SyncError('V5_JOURNAL_PREIMAGE_CHANGED')
            if manifest['db_before']!=json.loads(event['before_json']):
                raise SyncError('V5_JOURNAL_DB_PREIMAGE_CHANGED')
            after=json.loads(event['after_json'])
            if manifest['db_after']!=after:
                if event['state']!='CLAIMED':
                    raise SyncError('V5_JOURNAL_DB_POSTIMAGE_CHANGED')
                # A rolled-back precommit attempt may retry with a fresh
                # updated_at. No DB/site effect exists at CLAIMED; keep the
                # original recovery preimages and refresh only proposed DB data.
                manifest['db_after']=after
                _atomic_write(manifest_path,json_bytes(manifest))
            return folder,manifest
        files=[]
        for index,surface in enumerate(surfaces):
            before=_safe_bytes(surface.path)
            old_fragment=None
            if surface.price_applicable:
                text=before.decode();left,right=self._span(text,surface,event['car_code'])
                old_fragment=text[left:right]
                old_row=json.loads(event['before_json'])
                expected_old=render_market_prices(old_row,compact=surface.kind!='CARD',require_car_id=True)
                if old_fragment != expected_old:
                    raise SyncError('V5_EXISTING_SITE_PRICE_DIFFERS_FROM_DB')
            shared_prices=self._shared_baseline(before,surface,event)
            _atomic_write(folder/f'{index}.before',before)
            files.append({'path':str(surface.path),'url':surface.url,'kind':surface.kind,
                          'price_applicable':surface.price_applicable,'before_sha256':digest(before),
                          'protected_sha256':self._protected_hash(before,surface,event['car_code']),
                          'old_fragment':old_fragment,'shared_prices':shared_prices})
        manifest={'event_key':event['event_key'],'claim_nonce':event['claim_nonce'],
                  'car_code':event['car_code'],'vin':event['vin'],'files':files,
                  'db_before':json.loads(event['before_json']),'db_after':json.loads(event['after_json'])}
        _atomic_write(manifest_path,json_bytes(manifest))
        return folder,manifest

    @staticmethod
    def _other_fragments(data,surface,code):
        if surface.kind=='CARD' or not surface.price_applicable:
            return {}
        result={}
        for match in re.finditer(re.escape(START)+r'.*?'+re.escape(END),data.decode(),re.S):
            parsed=_Prices(match.group())
            if len(parsed.codes)!=1:
                raise SyncError('V5_SHARED_FRAGMENT_IDENTITY_REQUIRED')
            other=parsed.codes[0]
            if other==code:
                continue
            if other in result:
                raise SyncError('V5_DUPLICATE_SHARED_CAR_FRAGMENT')
            result[other]=match.group()
        return result

    @staticmethod
    def _audited_other_version(conn,operation):
        """Only actual immutable DB-commit facts authorize concurrent versions."""
        if operation['state'] in ('QUEUED','CLAIMED') or not operation['after_json']:
            return None
        recorded=conn.execute(f"SELECT payload_json FROM {outbox.V5_AUDIT} WHERE event_key=? AND fact='DB_COMMITTED'",
                              (operation['event_key'],)).fetchone()
        if recorded is None:
            raise SyncError('V5_OTHER_PRICE_VERSION_LACKS_AUDIT')
        audit=json.loads(recorded[0]);after=json.loads(operation['after_json']);details=audit.get('details',{})
        authority=details.get('authority',{})
        if (audit.get('operation_id')!=operation['event_key'] or details.get('after')!=after
                or authority.get('event_key')!=operation['event_key']
                or authority.get('claim_nonce')!=operation['claim_nonce']
                or authority.get('writer_fence_verified') is not True
                or not authority.get('gate_b_receipt_sha256')):
            raise SyncError('V5_OTHER_PRICE_VERSION_PROVENANCE_MISMATCH')
        if (canonical(after['price_uah']),canonical(after['price_georgia'],georgia=True))!=(
                operation['ukraine_usd'],operation['georgia_usd']):
            raise SyncError('V5_OTHER_PRICE_VERSION_SNAPSHOT_MISMATCH')
        return render_market_prices(after,compact=True,require_car_id=True)

    def _shared_baseline(self,data,surface,event):
        baseline={}
        fragments=self._other_fragments(data,surface,event['car_code'])
        if not fragments:
            return baseline
        with self.connection() as conn:
            for code,fragment in fragments.items():
                cursor=conn.execute('SELECT * FROM cars WHERE auto_number=? AND published=1',(code,))
                names=[x[0] for x in cursor.description];rows=cursor.fetchall()
                if len(rows)!=1:
                    raise SyncError('V5_OTHER_CARD_CURRENT_DB_IDENTITY_REQUIRED')
                car=dict(zip(names,rows[0]));allowed={render_market_prices(car,compact=True,require_car_id=True)}
                keys=conn.execute(f'SELECT event_key FROM {outbox.V5_TABLE} WHERE car_id=? ORDER BY sequence DESC LIMIT 1',
                                  (car['id'],)).fetchall()
                sequence=0
                if keys:
                    operation=outbox.get_operation(conn,keys[0][0]);sequence=operation['sequence']
                    # A car can have queued future intentions; find its current
                    # committed head, whose old public version may still be live.
                    active=conn.execute(f"SELECT event_key FROM {outbox.V5_TABLE} WHERE car_id=? AND state IN ('DB_COMMITTED','SITE_PUBLISHED','VERIFIED') ORDER BY sequence LIMIT 1",
                                        (car['id'],)).fetchone()
                    if active:
                        operation=outbox.get_operation(conn,active[0])
                        after=self._audited_other_version(conn,operation)
                        allowed.add(after)
                        allowed.add(render_market_prices(json.loads(operation['before_json']),compact=True,require_car_id=True))
                    # Pending intentions have no public version yet; subsequent
                    # committed versions still need their own immutable proof.
                    sequence=conn.execute(f"SELECT COALESCE(MAX(sequence),0) FROM {outbox.V5_TABLE} WHERE car_id=? AND state NOT IN ('QUEUED','CLAIMED')",
                                          (car['id'],)).fetchone()[0]
                if fragment not in allowed:
                    raise SyncError('V5_OTHER_EXISTING_PRICE_DIFFERS_FROM_DB')
                baseline[code]={'car_id':car['id'],'sequence':sequence,'fragments':sorted(allowed)}
        return baseline

    def _verify_shared_prices(self,data,surface,event,baseline):
        fragments=self._other_fragments(data,surface,event['car_code'])
        if set(fragments)!=set(baseline):
            raise SyncError('V5_SHARED_PRICE_INVENTORY_CHANGED')
        with self.connection() as conn:
            for code,fragment in fragments.items():
                known=baseline[code]
                if fragment in known['fragments']:
                    continue
                keys=conn.execute(f'SELECT event_key FROM {outbox.V5_TABLE} WHERE car_id=? AND sequence>? ORDER BY sequence',
                                  (known['car_id'],known['sequence'])).fetchall()
                allowed=False
                for key, in keys:
                    operation=outbox.get_operation(conn,key)
                    if operation['car_code']!=code:
                        raise SyncError('V5_OTHER_CARD_IDENTITY_CHANGED')
                    if self._audited_other_version(conn,operation)==fragment:
                        allowed=True;break
                if not allowed:
                    raise SyncError('V5_UNAUTHORIZED_OTHER_CAR_PRICE_VERSION')

    def _check_surface(self,data,surface,event,item,*,require_desired):
        if self._protected_hash(data,surface,event['car_code']) != item['protected_sha256']:
            raise SyncError('V5_PROTECTED_SITE_CONTENT_CHANGED')
        if not surface.price_applicable:
            return
        self._verify_shared_prices(data,surface,event,item.get('shared_prices',{}))
        text=data.decode();left,right=self._span(text,surface,event['car_code'])
        fragment=text[left:right];desired=self._desired(event,surface)
        if require_desired:
            if fragment != desired:
                raise SyncError('V5_SITE_PRICE_READBACK_MISMATCH')
            semantic_fragment(fragment,event['car_code'],event)
        elif fragment not in (item['old_fragment'],desired):
            raise SyncError('V5_UNEXPECTED_TARGET_PRICE_WRITE')

    def _publish(self,event,surfaces):
        self._db_readback(event,record=True)
        with self._shared_lock(), self.connection() as conn:
            authority=self._proof(event,surfaces)
            def require_fresh_authority():
                if self.clock() >= authority['expires_ms']:
                    raise SyncError('V5_AUTHORITY_EXPIRED_BEFORE_DB_COMMIT')
            conn.execute('BEGIN IMMEDIATE')
            try:
                # The flag and entire rendered row stay fixed until the last
                # local file and its checkpoint are committed. A DB writer
                # cannot unpublish between authorization and an atomic replace.
                row = self._full_row(conn,event)
                if row.get('published') != 1:
                    raise SyncError('V5_VISIBILITY_CHANGED')
                if row != json.loads(event['after_json']):
                    raise SyncError('V5_PUBLIC_SWITCH_CURRENT_ROW_CHANGED')
                current = outbox.require_head(conn,event['event_key'])
                if current['state'] != 'DB_COMMITTED' or current['claim_nonce'] != event['claim_nonce']:
                    raise SyncError('V5_DB_CHECKPOINT_CHANGED')
                folder,manifest=self._journal(event,surfaces)
                for surface,item in zip(surfaces,manifest['files']):
                    self._check_surface(_safe_bytes(surface.path),surface,event,item,require_desired=False)
                for surface,item in zip(surfaces,manifest['files']):
                    if not surface.price_applicable:
                        continue
                    if self.clock() >= authority['expires_ms']:
                        raise SyncError('V5_AUTHORITY_EXPIRED_BEFORE_DB_COMMIT')
                    current=_safe_bytes(surface.path);text=current.decode()
                    left,right=self._span(text,surface,event['car_code'])
                    after=(text[:left]+self._desired(event,surface)+text[right:]).encode()
                    self._check_surface(after,surface,event,item,require_desired=True)
                    if after != current:
                        _atomic_write(surface.path,after,stat.S_IMODE(surface.path.stat().st_mode),
                                      before_replace=require_fresh_authority)
                require_fresh_authority()
                event=outbox.transition_operation(conn,event_key=event['event_key'],nonce=event['claim_nonce'],
                    expected_state='DB_COMMITTED',new_state='SITE_PUBLISHED',now_ms=self.clock())
                outbox.audit_operation(conn,event['event_key'],'SITE_PUBLISHED',
                    {'manifest_sha256':digest(json_bytes(manifest)),'authority':authority},self.clock())
                require_fresh_authority()
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
        return self._operation(event['event_key'])

    def _verify(self,event,surfaces):
        self._db_readback(event,record=True)
        with self._shared_lock():
            self._proof(event,surfaces)
            folder,manifest=self._journal(event,surfaces)
            for surface,item in zip(surfaces,manifest['files']):
                self._check_surface(_safe_bytes(surface.path),surface,event,item,require_desired=True)
        observations=[]
        # Deliberately outside shared publication and all SQLite locks. Other
        # cars may update their own fragments of the same catalog/homepage.
        for surface,item in zip(surfaces,manifest['files']):
            public=self.read_public(surface.url)
            try:
                self._check_surface(public,surface,event,item,require_desired=True)
            except SyncError as error:
                if str(error)=='V5_SITE_PRICE_READBACK_MISMATCH':
                    self._check_surface(_safe_bytes(surface.path),surface,event,item,require_desired=True)
                    raise SyncError('V5_PUBLIC_PRICE_NOT_CONVERGED') from error
                raise
            observations.append({'kind':surface.kind,'url':surface.url,'sha256':digest(public),
                                 'protected_sha256':self._protected_hash(public,surface,event['car_code']),
                                 'price_applicable':surface.price_applicable,'observed_ms':self.clock()})
        self._db_readback(event)
        with self._shared_lock():
            authority=self._proof(event,surfaces)
            for surface,item in zip(surfaces,manifest['files']):
                self._check_surface(_safe_bytes(surface.path),surface,event,item,require_desired=True)
            with self.connection() as conn:
                conn.execute('BEGIN IMMEDIATE')
                try:
                    if self._full_row(conn,event) != json.loads(event['after_json']):
                        raise SyncError('V5_FINAL_DB_CAS_MISMATCH')
                    now=self.clock()
                    receipt={'operation_id':event['event_key'],'claim_nonce':event['claim_nonce'],
                             'car_id':event['car_id'],'car_code':event['car_code'],'vin':event['vin'],
                             'actor_id':event['actor_id'],'chat_id':event['chat_id'],'market':event['field'],
                             'old_value':event['old_value'],'new_value':event['value'],
                             'ua':event['ukraine_usd'],'ge':event['georgia_usd'],
                             'db_readback':'PASS','protected_data':'PASS','verification':'PASS',
                             'observations':observations,'authority':authority,'verified_ms':now}
                    receipt_bytes=json_bytes(receipt)
                    _atomic_write(folder/'receipt.json',receipt_bytes)
                    event=outbox.transition_operation(conn,event_key=event['event_key'],nonce=event['claim_nonce'],
                        expected_state='SITE_PUBLISHED',new_state='VERIFIED',now_ms=now,
                        verified_ms=now,receipt_sha256=digest(receipt_bytes))
                    outbox.audit_operation(conn,event['event_key'],'VERIFIED',receipt,now)
                    conn.commit()
                except Exception:
                    conn.rollback();raise
        return self._operation(event['event_key'])

    def _complete(self,event,surfaces):
        folder=self.binding.journal_root/('v5_'+event['event_key'])
        if digest(_safe_bytes(folder/'receipt.json')) != event['receipt_sha256']:
            raise SyncError('V5_VERIFIED_RECEIPT_MISSING')
        # VERIFIED may have survived a process restart. Recheck authority, DB,
        # every public surface and protected bytes before the completion receipt.
        with self._shared_lock():
            self._proof(event,surfaces)
            _,manifest=self._journal(event,surfaces)
        for surface,item in zip(surfaces,manifest['files']):
            try:
                self._check_surface(self.read_public(surface.url),surface,event,item,require_desired=True)
            except SyncError as error:
                if str(error)=='V5_SITE_PRICE_READBACK_MISMATCH':
                    self._check_surface(_safe_bytes(surface.path),surface,event,item,require_desired=True)
                    raise SyncError('V5_PUBLIC_PRICE_NOT_CONVERGED') from error
                raise
        self._db_readback(event)
        with self._shared_lock(),self.connection() as conn:
            self._proof(event,surfaces)
            for surface,item in zip(surfaces,manifest['files']):
                self._check_surface(_safe_bytes(surface.path),surface,event,item,require_desired=True)
            conn.execute('BEGIN IMMEDIATE')
            try:
                if self._full_row(conn,event) != json.loads(event['after_json']):
                    raise SyncError('V5_COMPLETION_DB_READBACK_MISMATCH')
                now=self.clock()
                event=outbox.transition_operation(conn,event_key=event['event_key'],nonce=event['claim_nonce'],
                    expected_state='VERIFIED',new_state='COMPLETED',now_ms=now,completed_ms=now)
                market='Украины' if event['field']=='price_uah' else 'Грузии'
                amount='Цена уточняется' if event['value'] is None else f"{int(Decimal(event['value'])):,}".replace(',',' ')+' $'
                body=f"✅ Завершено. Цена {market} {event['car_code']}: {amount}. Сайт синхронизирован."
                outbox.audit_operation(conn,event['event_key'],'COMPLETED',
                    {'receipt_sha256':event['receipt_sha256'],'operator_chat_id':event['chat_id']},now)
                outbox.queue_operation_notice(conn,event_key=event['event_key'],kind='SUCCESS',body=body,now_ms=now)
                conn.commit()
            except Exception:
                conn.rollback();raise
        # Verify completion and queued receipt through another connection.
        verified=self._operation(event['event_key'])
        if verified['state']!='COMPLETED' or verified['receipt_sha256']!=event['receipt_sha256']:
            raise SyncError('V5_COMPLETION_LEDGER_READBACK_MISMATCH')
        return verified

    def _failed(self,key,error):
        reason=str(error) if isinstance(error,(SyncError,outbox.OutboxError)) else type(error).__name__.upper()
        reason=re.sub(r'[^A-Z0-9_]','_',reason.upper())[:100] or 'V5_OPERATION_FAILED'
        operational_controls={'ACTIVE_OR_UNRECONCILED_HALT_FILE','CONTROL_BLOCKS_PRICE_PUBLICATION',
                              'CONTROL_CACHE_STALE_OR_WRONG_SOURCE','RUNNING_CRM_BOT_NOT_YET_VERIFIED',
                              'V5_AUTHORITY_EXPIRED_BEFORE_DB_COMMIT','V5_PUBLIC_PRICE_NOT_CONVERGED','V5_VISIBILITY_CHANGED'}
        retryable=((isinstance(error,(OSError,sqlite3.OperationalError)) and not isinstance(error,SyncError))
                   or reason in operational_controls)
        with self.connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            event=outbox.get_operation(conn,key)
            if event is None or event['state']=='COMPLETED':
                conn.rollback();return
            now=self.clock()
            delay=min(30000,1000*(2**min(event['attempts'],5))) if retryable else 0
            conn.execute(f'UPDATE {outbox.V5_TABLE} SET blocked=?,last_error=?,next_attempt_ms=? WHERE event_key=?',
                         (0 if retryable else 1,reason,now+delay,key))
            outbox.audit_operation(conn,key,'ATTEMPT_%06d_FAILED'%event['attempts'],
                {'reason':reason,'checkpoint':event['state'],'automatic_revalidation':retryable},now)
            outbox.queue_operation_notice(conn,event_key=key,kind='FAILURE',
                body=f"🔴 Изменение цены {event['car_code']} не завершено. Операция сохранена; требуется проверка восстановления.",now_ms=now)
            conn.commit()

    def reconcile_hidden_operation(self, key):
        """One explicit actual-outcome check after canonical view retirement.

        This never clears blocked flags to replay a price write. It may only
        verify and finish the original durable DB-committed operation.
        """
        event = self._operation(key)
        with self.lock(self.binding.journal_root / ('car_%d.lock' % event['car_id'])):
            event = self._operation(key)
            if event['state'] == 'COMPLETED':
                return {'event_key':key, 'state':'COMPLETED', 'replay':True}
            if event['state'] not in ('DB_COMMITTED','SITE_PUBLISHED','VERIFIED'):
                raise SyncError('V5_HIDDEN_RECONCILIATION_REQUIRES_DURABLE_COMMIT')
            try:
                event = self._complete_hidden(event)
                return {'event_key':key, 'state':event['state'], 'public_projection':'NOT_APPLICABLE'}
            except Exception as error:
                reason = str(error) if isinstance(error,(SyncError,outbox.OutboxError)) else type(error).__name__
                reason = re.sub(r'[^A-Z0-9_]','_',reason.upper())[:100]
                # Content-bound diagnostic facts are idempotent; a second
                # bounded observation cannot mutate the first failed attempt.
                facts = {'reason':reason, 'checkpoint':event['state'], 'claim_nonce':event['claim_nonce']}
                with self.connection() as conn:
                    conn.execute('BEGIN IMMEDIATE')
                    outbox.audit_operation(conn,key,'HIDDEN_RECONCILIATION_' + digest(json_bytes(facts))[:32],facts,self.clock())
                    conn.commit()
                return {'event_key':key, 'state':event['state'], 'reconciliation_required':reason}

    def process_operation(self,key):
        event=self._operation(key)
        car_lock=self.binding.journal_root/('car_%d.lock'%event['car_id'])
        try:
            with self.lock(car_lock):
                event=self._operation(key)
                if event['blocked']:
                    return {'event_key':key,'state':event['state'],'blocked':True,'reconciliation_required':event['last_error']}
                with self.connection() as conn:
                    conn.execute('BEGIN IMMEDIATE')
                    event=outbox.claim_operation(conn,event_key=key,nonce=secrets.token_hex(32),now_ms=self.clock())
                    conn.commit()
                if event['state']=='COMPLETED':
                    return {'event_key':key,'state':'COMPLETED','replay':True}
                surfaces=self._v5_surfaces(event)
                if event['state']=='CLAIMED':
                    event=self._commit_selected_price(event,surfaces)
                if not surfaces:
                    event=self._complete_hidden(event)
                    return {'event_key':key,'state':event['state'],'public_projection':'NOT_APPLICABLE'}
                if event['state']=='DB_COMMITTED':
                    event=self._publish(event,surfaces)
                if event['state']=='SITE_PUBLISHED':
                    event=self._verify(event,surfaces)
                if event['state']=='VERIFIED':
                    event=self._complete(event,surfaces)
                return {'event_key':key,'state':event['state']}
        except BlockingIOError:
            return {'event_key':key,'state':'BUSY'}
        except Exception as error:
            self._failed(key,error)
            return {'event_key':key,'state':self._operation(key)['state'],'error':type(error).__name__}

    def tick(self):
        from concurrent.futures import ThreadPoolExecutor
        with self.connection() as conn:
            rows=conn.execute(f"SELECT pending.event_key FROM {outbox.V5_TABLE} pending WHERE pending.state!='COMPLETED' "
                "AND pending.blocked=0 AND pending.next_attempt_ms<=? AND NOT EXISTS ("
                f"SELECT 1 FROM {outbox.V5_TABLE} earlier WHERE earlier.car_id=pending.car_id "
                "AND earlier.sequence<pending.sequence AND earlier.state!='COMPLETED') "
                "ORDER BY pending.created_ms,pending.event_key LIMIT ?",(self.clock(),self.binding.worker_count)).fetchall()
        if not rows:
            return {'processed':[]}
        with ThreadPoolExecutor(max_workers=self.binding.worker_count,thread_name_prefix='ua-price-v5') as pool:
            return {'processed':list(pool.map(self.process_operation,[row[0] for row in rows]))}

    def queue_daily(self):
        """Report the active v5 ledger, including unresolved delivery ambiguity."""
        date=datetime.fromtimestamp(self.clock()/1000,ZoneInfo('Asia/Ho_Chi_Minh')).date().isoformat()
        with self.connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            unfinished=conn.execute(f"SELECT COUNT(*) FROM {outbox.V5_TABLE} WHERE state!='COMPLETED'").fetchone()[0]
            blocked=conn.execute(f"SELECT COUNT(*) FROM {outbox.V5_TABLE} WHERE state!='COMPLETED' AND blocked=1").fetchone()[0]
            undelivered=conn.execute(f"SELECT COUNT(*) FROM {outbox.V5_NOTICES} WHERE state!='SENT'").fetchone()[0]
            ambiguous=conn.execute(f"SELECT COUNT(*) FROM {outbox.V5_NOTICES} WHERE state='AMBIGUOUS'").fetchone()[0]
            body=(f"Отчёт по ценам за {date}: незавершённых операций — {unfinished}; "
                  f"требуют восстановления — {blocked}; уведомлений без подтверждения доставки — {undelivered} "
                  f"(неопределённая доставка — {ambiguous}).")
            conn.execute(f"INSERT OR IGNORE INTO {NOTICE_TABLE} VALUES (?,NULL,'DAILY',?,?,'PENDING',NULL,NULL)",
                         (digest(json_bytes(('V5_DAILY',date))),body,self.clock()))
            conn.commit()

    async def deliver_notices(self,bot):
        # Retain existing owner incident/daily delivery without using it as a
        # success route. The new queue always uses the initiating operator chat.
        await super().deliver_notices(bot)
        async with self._notice_async_lock:
            try:
                with self.lock(self.binding.journal_root/'v5_notification_delivery.lock'):
                    await self._deliver_v5_notices(bot)
            except BlockingIOError:
                return

    async def _deliver_v5_notices(self,bot):
        with self.connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            # Telegram has no sender idempotency key. A crash after dispatch
            # cannot justify automatically sending the same message a second time.
            conn.execute(f"UPDATE {outbox.V5_NOTICES} SET state='AMBIGUOUS' WHERE state='SENDING'")
            rows=conn.execute(f"SELECT notice_key,event_key,chat_id,body,kind FROM {outbox.V5_NOTICES} WHERE state='PENDING' ORDER BY created_ms,notice_key LIMIT 20").fetchall()
            conn.commit()
        for key,event_key,chat_id,body,kind in rows:
            with self.connection() as conn:
                conn.execute('BEGIN IMMEDIATE')
                claimed=conn.execute(f"UPDATE {outbox.V5_NOTICES} SET state='SENDING' WHERE notice_key=? AND state='PENDING'",(key,)).rowcount
                conn.commit()
            if not claimed:
                continue
            try:
                message=await bot.send_message(chat_id=chat_id,text=body,disable_web_page_preview=True)
                if type(message.message_id) is not int or message.message_id<=0:
                    raise SyncError('V5_TELEGRAM_ACK_REQUIRED')
                state,message_id='SENT',message.message_id
            except Exception:
                state,message_id='AMBIGUOUS',None
            with self.connection() as conn:
                conn.execute('BEGIN IMMEDIATE')
                conn.execute(f"UPDATE {outbox.V5_NOTICES} SET state=?,sent_ms=?,message_id=? WHERE notice_key=? AND state='SENDING'",
                             (state,self.clock(),message_id,key))
                outbox.audit_operation(conn,event_key,'TELEGRAM_'+kind+'_'+state,
                    {'notice_key':key,'chat_id':chat_id,'message_id':message_id},self.clock())
                conn.commit()

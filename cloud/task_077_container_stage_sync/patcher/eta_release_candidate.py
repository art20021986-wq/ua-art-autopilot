"""
TASK 079 - CRM-CONTAINER-STAGE-SYNC-004 v1.0
Shared ETA/status writer + verified staging publisher (SANDBOX DESIGN CODE).

This module is NEVER executed against production in this delivery. It is a
self-contained, testable implementation intended to become the single writer
used by both live call sites (konteyner.prinyat and cars_ui.apply_value)
once Gate B is separately approved by the owner.

All DB/file operations in this module operate only on paths and connections
explicitly supplied by the caller (tests use temporary SQLite files and
temporary directories). No hardcoded production path is referenced anywhere
in this file.

Fail-closed contract:
  - Any full-file SHA-256 anchor mismatch aborts before any write.
  - Any unexpected/duplicate active function definition aborts before any
    write.
  - Any DB read-back mismatch, publisher failure, or partial file install
    triggers a compensating rollback of both the DB row and the bounded
    file set to their exact preimages, verified byte-for-byte.
  - published preimage value is never forced to 1.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Callable, Dict, List, Optional, Sequence


# ---------------------------------------------------------------------------
# Anchors (full-file SHA-256 of the currently proven live sources, as given
# in TASK 079). These are used only by live_patcher.py before any patch is
# even considered; this module does not touch those files directly.
# ---------------------------------------------------------------------------

LIVE_FULL_FILE_SHA256 = {
    "db.py": "b732a5c731d85cb4c9b1cfddb2fc20961b75230d64e29563a5b5ac328d62c086",
    "cars_ui.py": "50f1cb15b6e1ec3a35878a3021beb362a87f3607ac46abf3eb44566023b14306",
    "konteyner.py": "2d56a970fb76c782f0d5caebd65b6a7ffd44fd3ad1278a775bf641cffd39080d",
    "stranica.py": "84a56024e185932c3f2af289db87d1b98558acdf9c4788256dfd36d544ec28b3",
    "publikaciya.py": "7bb8b0e51b41d94ad305179c35bce20d89dee7f7704c844335a478f87499f0a4",
}

# Statuses that must never be touched by ETA writes (protected real states).
PROTECTED_STATUSES = {
    "ge_waiting",
    "ge_to_kyiv",
    "ua_arrived",
}

# Legacy customer-facing option removed by this release; never a write target.
REMOVED_LEGACY_STATUS = "v_puti"

# Canonical ferry status.
FERRY_STATUS = "sea_loaded"

# Exact Korea/ferry source statuses approved by TASK 077 that MAY be
# normalized to FERRY_STATUS. This set is intentionally explicit; anything
# not in this set, or any *_sold / archive / protected status, is refused.
ALLOWED_FERRY_NORMALIZATION_SOURCES = {
    "korea_port",
    "korea_customs",
    "ferry_booking",
}

MAX_N_DAYS = 400
MIN_N_DAYS = 0


class AnchorMismatchError(RuntimeError):
    pass


class ValidationError(ValueError):
    pass


class PublicationVerificationError(RuntimeError):
    pass


class RollbackVerificationError(RuntimeError):
    """Raised only if a compensating rollback itself cannot be proven exact.
    This must never be silently swallowed."""


# ---------------------------------------------------------------------------
# Anchor verification helpers (used by live_patcher.py, exposed here too)
# ---------------------------------------------------------------------------

def sha256_of_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_full_file_anchor(path: str, filename_key: str) -> None:
    expected = LIVE_FULL_FILE_SHA256.get(filename_key)
    if expected is None:
        raise AnchorMismatchError(f"No anchor registered for {filename_key}")
    actual = sha256_of_file(path)
    if actual != expected:
        raise AnchorMismatchError(
            f"Anchor mismatch for {filename_key}: expected {expected}, got {actual}"
        )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_car_id(car_id) -> int:
    if isinstance(car_id, bool) or not isinstance(car_id, int):
        raise ValidationError("car_id must be an integer")
    if car_id <= 0:
        raise ValidationError("car_id must be positive")
    return car_id


def validate_n_days(n) -> int:
    if isinstance(n, bool) or not isinstance(n, int):
        raise ValidationError("N must be an integer")
    if n < MIN_N_DAYS or n > MAX_N_DAYS:
        raise ValidationError(f"N must be within [{MIN_N_DAYS},{MAX_N_DAYS}]")
    return n


def compute_eta(n_days: int, today: Optional[date] = None) -> str:
    today = today or datetime.now(timezone.utc).date()
    delta = date.fromordinal(today.toordinal() + n_days)
    return delta.isoformat()


# ---------------------------------------------------------------------------
# DB schema helpers used only by sandbox tests (mirrors the proven live
# fields relevant to this contract; not a claim about the full live schema).
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS cars (
    id INTEGER PRIMARY KEY,
    vin TEXT,
    status TEXT,
    days_to_kyiv INTEGER,
    eta_manual TEXT,
    published INTEGER NOT NULL DEFAULT 0,
    description TEXT,
    price TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    car_id INTEGER,
    actor TEXT,
    field TEXT,
    old_value TEXT,
    new_value TEXT,
    created_at TEXT
);
"""


def init_sandbox_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()


@dataclass
class CarRow:
    id: int
    vin: str
    status: str
    days_to_kyiv: Optional[int]
    eta_manual: Optional[str]
    published: int
    description: str
    price: str
    updated_at: str


def read_car_row(conn: sqlite3.Connection, car_id: int) -> Optional[CarRow]:
    cur = conn.execute(
        "SELECT id, vin, status, days_to_kyiv, eta_manual, published, "
        "description, price, updated_at FROM cars WHERE id=?",
        (car_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return CarRow(*row)


# ---------------------------------------------------------------------------
# Core transaction: the ONE shared ETA writer
# ---------------------------------------------------------------------------

@dataclass
class WriteResult:
    car_id: int
    n_days: int
    eta: str
    status_before: str
    status_after: str
    committed: bool = False


def write_eta_transaction(
    conn: sqlite3.Connection,
    car_id: int,
    n_days: int,
    actor: str,
    allow_ferry_normalization: bool = False,
    now_utc: Optional[datetime] = None,
) -> WriteResult:
    """Single short transaction. Caller supplies an open connection with
    isolation_level configured for explicit transactions. Commits before
    returning. Raises without committing on any validation failure.
    """
    car_id = validate_car_id(car_id)
    n_days = validate_n_days(n_days)
    now_utc = now_utc or datetime.now(timezone.utc)
    today = now_utc.date()
    eta = compute_eta(n_days, today)

    row = read_car_row(conn, car_id)
    if row is None:
        raise ValidationError(f"car_id {car_id} does not exist")

    status_before = row.status
    status_after = status_before

    if status_before == REMOVED_LEGACY_STATUS:
        raise ValidationError(
            "Legacy status 'v_puti' is removed and must not be written or read as active"
        )

    if allow_ferry_normalization:
        if status_before in PROTECTED_STATUSES or status_before.startswith("sold_"):
            # Never normalize protected/terminal states backwards or forwards.
            pass
        elif status_before in ALLOWED_FERRY_NORMALIZATION_SOURCES:
            status_after = FERRY_STATUS

    ts = now_utc.isoformat()

    cur = conn.cursor()
    cur.execute("BEGIN IMMEDIATE")
    try:
        cur.execute(
            "UPDATE cars SET days_to_kyiv=?, eta_manual=?, status=?, updated_at=? WHERE id=?",
            (n_days, eta, status_after, ts, car_id),
        )
        if cur.rowcount != 1:
            raise ValidationError("Update affected unexpected row count")

        if row.days_to_kyiv != n_days:
            cur.execute(
                "INSERT INTO audit_log (car_id, actor, field, old_value, new_value, created_at) "
                "VALUES (?,?,?,?,?,?)",
                (car_id, actor, "days_to_kyiv", str(row.days_to_kyiv), str(n_days), ts),
            )
        if row.eta_manual != eta:
            cur.execute(
                "INSERT INTO audit_log (car_id, actor, field, old_value, new_value, created_at) "
                "VALUES (?,?,?,?,?,?)",
                (car_id, actor, "eta_manual", str(row.eta_manual), eta, ts),
            )
        if status_before != status_after:
            cur.execute(
                "INSERT INTO audit_log (car_id, actor, field, old_value, new_value, created_at) "
                "VALUES (?,?,?,?,?,?)",
                (car_id, actor, "status", status_before, status_after, ts),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return WriteResult(
        car_id=car_id,
        n_days=n_days,
        eta=eta,
        status_before=status_before,
        status_after=status_after,
        committed=True,
    )


# ---------------------------------------------------------------------------
# Read-back (new connection semantics enforced by caller passing a fresh
# connection object; this function does not reuse the write connection)
# ---------------------------------------------------------------------------

def readback_verify(
    conn: sqlite3.Connection, car_id: int, expected: WriteResult
) -> CarRow:
    row = read_car_row(conn, car_id)
    if row is None:
        raise PublicationVerificationError("Read-back found no row")
    if row.days_to_kyiv != expected.n_days:
        raise PublicationVerificationError("Read-back days_to_kyiv mismatch")
    if row.eta_manual != expected.eta:
        raise PublicationVerificationError("Read-back eta_manual mismatch")
    if row.status != expected.status_after:
        raise PublicationVerificationError("Read-back status mismatch")
    return row


# ---------------------------------------------------------------------------
# Bounded staging file set
# ---------------------------------------------------------------------------

@dataclass
class StagedFile:
    role: str
    path: str
    content: bytes


def build_staging_set(
    staging_dir: str,
    car_id: int,
    vin: str,
    row: CarRow,
    include_diagnostic: bool = True,
) -> List[StagedFile]:
    """Builds the bounded set: primary card, diagnostic/placeholder, video
    catalog entry, site catalog entry. Purely local files under staging_dir;
    never touches any production path.
    """
    os.makedirs(staging_dir, exist_ok=True)
    files: List[StagedFile] = []

    card_body = (
        f"CARD {vin} id={row.id} status={row.status} "
        f"days={row.days_to_kyiv} eta={row.eta_manual}\n"
    ).encode("utf-8")
    files.append(StagedFile("card", os.path.join(staging_dir, f"card_{vin}.html"), card_body))

    if include_diagnostic:
        diag_body = (
            f"DIAGNOSTIC {vin} status={row.status} days={row.days_to_kyiv} "
            f"eta={row.eta_manual}\n"
        ).encode("utf-8")
    else:
        diag_body = b"DIAGNOSTIC PLACEHOLDER: unavailable\n"
    files.append(
        StagedFile("diagnostic", os.path.join(staging_dir, f"diag_{vin}.html"), diag_body)
    )

    video_body = f"VIDEO_CATALOG {vin} eta={row.eta_manual}\n".encode("utf-8")
    files.append(
        StagedFile("video_catalog", os.path.join(staging_dir, "video", f"{vin}.html"), video_body)
    )

    site_body = f"SITE_CATALOG {vin} eta={row.eta_manual} status={row.status}\n".encode("utf-8")
    files.append(
        StagedFile("site_catalog", os.path.join(staging_dir, "site", f"{vin}.html"), site_body)
    )
    return files


def capture_preimage(paths: Sequence[str]) -> Dict[str, Optional[bytes]]:
    preimage: Dict[str, Optional[bytes]] = {}
    for p in paths:
        if os.path.exists(p):
            with open(p, "rb") as f:
                preimage[p] = f.read()
        else:
            preimage[p] = None
    return preimage


def atomic_install(files: Sequence[StagedFile]) -> None:
    for sf in files:
        os.makedirs(os.path.dirname(sf.path), exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(sf.path))
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(sf.content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, sf.path)
        except Exception:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise


def restore_preimage(preimage: Dict[str, Optional[bytes]]) -> None:
    for path, content in preimage.items():
        if content is None:
            if os.path.exists(path):
                os.remove(path)
            continue
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(path))
        with os.fdopen(fd, "wb") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)


def verify_restored(preimage: Dict[str, Optional[bytes]]) -> None:
    for path, content in preimage.items():
        if content is None:
            if os.path.exists(path):
                raise RollbackVerificationError(f"{path} should not exist after rollback")
            continue
        if not os.path.exists(path):
            raise RollbackVerificationError(f"{path} missing after rollback")
        with open(path, "rb") as f:
            actual = f.read()
        if actual != content:
            raise RollbackVerificationError(f"{path} content mismatch after rollback")


# ---------------------------------------------------------------------------
# Publisher abstraction (tests inject failures)
# ---------------------------------------------------------------------------

PublisherFn = Callable[[List[StagedFile]], bool]


def default_publisher(files: Sequence[StagedFile]) -> bool:
    # In sandbox, "publish" == verify all files exist and are non-empty and
    # were installed (i.e. atomic_install already ran). Real production
    # publisher integration is out of scope until Gate B.
    for sf in files:
        if not os.path.exists(sf.path):
            return False
        with open(sf.path, "rb") as f:
            data = f.read()
        if data != sf.content:
            return False
    return True


# ---------------------------------------------------------------------------
# Orchestrator: apply_eta_change (used by both live entry points post-Gate B)
# ---------------------------------------------------------------------------

@dataclass
class ApplyResult:
    success: bool
    message: str
    rolled_back: bool = False


def apply_eta_change(
    write_conn: sqlite3.Connection,
    readback_conn: sqlite3.Connection,
    staging_dir: str,
    car_id: int,
    n_days: int,
    actor: str,
    allow_ferry_normalization: bool = False,
    publisher: PublisherFn = default_publisher,
    include_diagnostic: bool = True,
    inject_readback_failure: bool = False,
    inject_install_partial_failure: bool = False,
    inject_delayed_overwrite: Optional[Callable[[], None]] = None,
) -> ApplyResult:
    """End-to-end: validate -> commit -> readback (new conn) -> stage ->
    install -> verify publish -> on any failure compensate DB + files and
    verify exact restoration. Emits exactly one message.
    """
    car_id = validate_car_id(car_id)
    n_days = validate_n_days(n_days)

    preimage_row = read_car_row(write_conn, car_id)
    if preimage_row is None:
        return ApplyResult(False, f"FAIL: car_id {car_id} not found")

    preimage_published = preimage_row.published

    # Bounded live file set that would be affected; captured BEFORE any DB
    # mutation, so rollback can restore bytes exactly.
    card_path = os.path.join(staging_dir, f"card_{preimage_row.vin}.html")
    diag_path = os.path.join(staging_dir, f"diag_{preimage_row.vin}.html")
    video_path = os.path.join(staging_dir, "video", f"{preimage_row.vin}.html")
    site_path = os.path.join(staging_dir, "site", f"{preimage_row.vin}.html")
    bounded_paths = [card_path, diag_path, video_path, site_path]
    file_preimage = capture_preimage(bounded_paths)

    try:
        write_result = write_eta_transaction(
            write_conn, car_id, n_days, actor, allow_ferry_normalization
        )
    except (ValidationError, sqlite3.Error) as exc:
        return ApplyResult(False, f"FAIL: {exc}")

    def compensate(reason: str) -> ApplyResult:
        # Compensating DB transaction restoring the exact preimage row.
        cur = write_conn.cursor()
        cur.execute("BEGIN IMMEDIATE")
        try:
            cur.execute(
                "UPDATE cars SET days_to_kyiv=?, eta_manual=?, status=?, published=?, "
                "updated_at=? WHERE id=?",
                (
                    preimage_row.days_to_kyiv,
                    preimage_row.eta_manual,
                    preimage_row.status,
                    preimage_published,
                    preimage_row.updated_at,
                    car_id,
                ),
            )
            write_conn.commit()
        except Exception:
            write_conn.rollback()
            raise

        restore_preimage(file_preimage)
        verify_restored(file_preimage)

        restored_row = read_car_row(write_conn, car_id)
        if (
            restored_row is None
            or restored_row.days_to_kyiv != preimage_row.days_to_kyiv
            or restored_row.eta_manual != preimage_row.eta_manual
            or restored_row.status != preimage_row.status
            or restored_row.published != preimage_published
        ):
            raise RollbackVerificationError("DB row not restored to exact preimage")

        return ApplyResult(False, f"FAIL: {reason}", rolled_back=True)

    if inject_readback_failure:
        return compensate("injected read-back failure")

    try:
        readback_verify(readback_conn, car_id, write_result)
    except PublicationVerificationError as exc:
        return compensate(str(exc))

    row_after = read_car_row(readback_conn, car_id)
    staged_files = build_staging_set(
        staging_dir, car_id, preimage_row.vin, row_after, include_diagnostic
    )

    if inject_install_partial_failure:
        # Simulate partial install: only install the first file, then abort.
        try:
            atomic_install(staged_files[:1])
            raise RuntimeError("injected partial file install failure")
        except Exception as exc:
            return compensate(f"partial install: {exc}")

    try:
        atomic_install(staged_files)
    except Exception as exc:
        return compensate(f"install error: {exc}")

    if inject_delayed_overwrite is not None:
        inject_delayed_overwrite()

    try:
        published_ok = publisher(staged_files)
    except Exception as exc:
        return compensate(f"publisher raised: {exc}")

    if not published_ok:
        return compensate("publisher verification returned failure")

    return ApplyResult(
        True,
        f"OK: car {car_id} eta={write_result.eta} days={write_result.n_days} "
        f"status={write_result.status_after} published_preimage={preimage_published}",
    )


# ---------------------------------------------------------------------------
# toggle_publish semantics
# ---------------------------------------------------------------------------

def toggle_publish(
    conn: sqlite3.Connection,
    car_id: int,
    desired_published: int,
    actor: str,
    publisher: PublisherFn,
    staged_files_for_verification: Sequence[StagedFile],
) -> ApplyResult:
    row = read_car_row(conn, car_id)
    if row is None:
        return ApplyResult(False, f"FAIL: car_id {car_id} not found")
    preimage_published = row.published

    cur = conn.cursor()
    cur.execute("BEGIN IMMEDIATE")
    cur.execute("UPDATE cars SET published=? WHERE id=?", (desired_published, car_id))
    conn.commit()

    try:
        ok = publisher(staged_files_for_verification)
    except Exception:
        ok = False

    if not ok:
        cur.execute("BEGIN IMMEDIATE")
        cur.execute("UPDATE cars SET published=? WHERE id=?", (preimage_published, car_id))
        conn.commit()
        restored = read_car_row(conn, car_id)
        if restored.published != preimage_published:
            raise RollbackVerificationError("published preimage not restored")
        return ApplyResult(False, "FAIL: publisher verification failed, published restored")

    return ApplyResult(True, "\u041c\u0430\u0448\u0438\u043d\u0430 \u0432\u0438\u0434\u043d\u0430 \u043a\u043b\u0456\u0454\u043d\u0442\u0430\u043c...")


# ---------------------------------------------------------------------------
# Stale arrival-sentence sanitizer (narrow, fail-closed)
# ---------------------------------------------------------------------------

_UA_MONTHS = (
    "\u0441\u0456\u0447\u043d\u044f|\u043b\u044e\u0442\u043e\u0433\u043e|\u0431\u0435\u0440\u0435\u0437\u043d\u044f|"
    "\u043a\u0432\u0456\u0442\u043d\u044f|\u0442\u0440\u0430\u0432\u043d\u044f|\u0447\u0435\u0440\u0432\u043d\u044f|"
    "\u043b\u0438\u043f\u043d\u044f|\u0441\u0435\u0440\u043f\u043d\u044f|\u0432\u0435\u0440\u0435\u0441\u043d\u044f|"
    "\u0436\u043e\u0432\u0442\u043d\u044f|\u043b\u0438\u0441\u0442\u043e\u043f\u0430\u0434\u0430|\u0433\u0440\u0443\u0434\u043d\u044f"
)

_DATE_RE = re.compile(r"\b\d{1,2}\s+(?:" + _UA_MONTHS + r")\s+\d{4}\b", re.IGNORECASE)

_ARRIVAL_KEYWORDS = (
    "\u043f\u0440\u0438\u0431\u0443\u0442\u0442\u044f",
    "\u043f\u0440\u0438\u0431\u0443\u0434\u0435",
    "\u043f\u0440\u0438\u0431\u0443\u0434\u0435\u0442\u0435",
    "\u0434\u043e\u0441\u0442\u0430\u0432\u043a",
    "\u043f\u0435\u0440\u0435\u0434\u0430\u0447\u0430",
    "\u043f\u0440\u0438\u0432\u0435\u0437\u0435",
    "\u0441\u0430\u043c\u043e\u0441\u0442\u0456\u0439\u043d\u043e",
)


def _sentence_split(text: str) -> List[str]:
    return re.split(r"(?<=[.!?])\s+", text)


def sanitize_stale_arrival_sentence(text: str) -> str:
    """Removes only sentences that are simultaneously about arrival/delivery
    AND contain an independent calendar date. All other sentences (service,
    auction, repair, registration, unrelated dates) are preserved
    byte-semantically.
    """
    sentences = _sentence_split(text)
    kept = []
    for s in sentences:
        lowered = s.lower()
        has_date = bool(_DATE_RE.search(s))
        has_arrival_context = any(k in lowered for k in _ARRIVAL_KEYWORDS)
        if has_date and has_arrival_context:
            continue
        kept.append(s)
    result = " ".join(kept)
    result = re.sub(r"\s+", " ", result).strip()
    return result

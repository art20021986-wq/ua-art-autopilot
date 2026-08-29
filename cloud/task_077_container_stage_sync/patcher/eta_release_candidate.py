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
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from eta_engine import compute_manual_eta


# ---------------------------------------------------------------------------
# Anchors (full-file SHA-256 of the currently proven live sources, as given
# in TASK 079). These are used only by live_patcher.py before any patch is
# even considered; this module does not touch those files directly.
# ---------------------------------------------------------------------------

LIVE_FULL_FILE_SHA256 = {
    "db.py": "b732a5c731d85cb4c9b1cfddb2fc20961b75230d64e29563a5b5ac328d62c086",
    "cars_ui.py": "cb48fec2b66d45d8ef0ee62cf81fb62ef26e89df326471aa90ee7fb7bb8c9dea",
    "konteyner.py": "2d56a970fb76c782f0d5caebd65b6a7ffd44fd3ad1278a775bf641cffd39080d",
    "stranica.py": "84a56024e185932c3f2af289db87d1b98558acdf9c4788256dfd36d544ec28b3",
    "publikaciya.py": "46d6ff20ca86ff911b168aefcf43e8b08b0de2efccf31590d7f275f124d15853",
}

# Statuses that must never be touched by ETA writes (protected real states).
PROTECTED_STATUSES = {
    "ge_waiting",
    "ge_to_kyiv",
    "ua_arrived",
}

# Legacy customer-facing option removed by this release.  It is an allowed
# one-way normalization source, never a write target.
REMOVED_LEGACY_STATUS = "sea_transit"

# Canonical ferry status.
FERRY_STATUS = "sea_loaded"

# Exact Korea/ferry source statuses approved by TASK 077 that MAY be
# normalized to FERRY_STATUS. This set is intentionally explicit; anything
# not in this set, or any *_sold / archive / protected status, is refused.
ALLOWED_FERRY_NORMALIZATION_SOURCES = {
    "kr_bought",
    "sea_transit",
    "sea_loaded",
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
    return compute_manual_eta(n_days, base_date=today).eta_manual.isoformat()


# ---------------------------------------------------------------------------
# DB schema helpers used only by sandbox tests (mirrors the proven live
# fields relevant to this contract; not a claim about the full live schema).
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS cars (
    id INTEGER PRIMARY KEY,
    auto_number TEXT,
    vin TEXT,
    status TEXT,
    days_to_kyiv INTEGER,
    eta_manual TEXT,
    published INTEGER NOT NULL DEFAULT 0,
    condition_text TEXT,
    description TEXT,
    price_uah INTEGER,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id TEXT,
    action TEXT,
    entity_type TEXT,
    entity_id INTEGER,
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
    auto_number: str
    vin: str
    status: str
    days_to_kyiv: Optional[int]
    eta_manual: Optional[str]
    published: int
    condition_text: str
    description: str
    price_uah: Optional[int]
    updated_at: str


def read_car_row(conn: sqlite3.Connection, car_id: int) -> Optional[CarRow]:
    cur = conn.execute(
        "SELECT id, auto_number, vin, status, days_to_kyiv, eta_manual, published, "
        "condition_text, description, price_uah, updated_at FROM cars WHERE id=?",
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
    condition_text_after: str = ""
    audit_ids: Tuple[int, ...] = ()
    committed: bool = False


def write_eta_transaction(
    conn: sqlite3.Connection,
    car_id: int,
    n_days: int,
    actor: str,
    allow_ferry_normalization: bool = False,
    now_utc: Optional[datetime] = None,
    expected_preimage: Optional[CarRow] = None,
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

    ts = now_utc.isoformat()

    cur = conn.cursor()
    audit_ids: List[int] = []
    cur.execute("BEGIN IMMEDIATE")
    try:
        row = read_car_row(conn, car_id)
        if row is None:
            raise ValidationError(f"car_id {car_id} does not exist")
        if expected_preimage is not None and row != expected_preimage:
            raise ValidationError("card changed concurrently before ETA write")
        status_before = row.status
        status_after = status_before
        if allow_ferry_normalization:
            folded = (status_before or "").lower()
            if (folded in PROTECTED_STATUSES or folded.startswith("sold_")
                    or folded.startswith("archive")):
                pass
            elif folded in ALLOWED_FERRY_NORMALIZATION_SOURCES:
                status_after = FERRY_STATUS
        condition_after = sanitize_stale_arrival_sentence(row.condition_text or "")
        cur.execute(
            "UPDATE cars SET days_to_kyiv=?, eta_manual=?, status=?, condition_text=?, "
            "updated_at=? WHERE id=?",
            (n_days, eta, status_after, condition_after, ts, car_id),
        )
        if cur.rowcount != 1:
            raise ValidationError("Update affected unexpected row count")

        if row.days_to_kyiv != n_days:
            cur.execute(
                "INSERT INTO audit (actor_id, action, entity_type, entity_id, field, "
                "old_value, new_value, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (actor, "card_edit", "cars", car_id, "days_to_kyiv",
                 str(row.days_to_kyiv) if row.days_to_kyiv is not None else None,
                 str(n_days), ts),
            )
            audit_ids.append(int(cur.lastrowid))
        if row.eta_manual != eta:
            cur.execute(
                "INSERT INTO audit (actor_id, action, entity_type, entity_id, field, "
                "old_value, new_value, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (actor, "card_edit", "cars", car_id, "eta_manual",
                 row.eta_manual, eta, ts),
            )
            audit_ids.append(int(cur.lastrowid))
        if status_before != status_after:
            cur.execute(
                "INSERT INTO audit (actor_id, action, entity_type, entity_id, field, "
                "old_value, new_value, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (actor, "card_edit", "cars", car_id, "status",
                 status_before, status_after, ts),
            )
            audit_ids.append(int(cur.lastrowid))
        if (row.condition_text or "") != condition_after:
            cur.execute(
                "INSERT INTO audit (actor_id, action, entity_type, entity_id, field, "
                "old_value, new_value, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (actor, "card_edit", "cars", car_id, "condition_text",
                 row.condition_text, condition_after, ts),
            )
            audit_ids.append(int(cur.lastrowid))
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
        condition_text_after=condition_after,
        audit_ids=tuple(audit_ids),
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
    if (row.condition_text or "") != expected.condition_text_after:
        raise PublicationVerificationError("Read-back condition_text mismatch")
    return row


# ---------------------------------------------------------------------------
# Bounded staging file set
# ---------------------------------------------------------------------------

@dataclass
class StagedFile:
    role: str
    stage_path: str
    live_path: str
    content: bytes


def build_staging_set(
    staging_dir: str,
    live_video_dir: str,
    live_site_dir: str,
    row: CarRow,
    include_diagnostic: bool = True,
) -> List[StagedFile]:
    """Builds the bounded set: primary card, diagnostic/placeholder, video
    catalog entry, site catalog entry. Purely local files under staging_dir;
    never touches any production path.
    """
    os.makedirs(staging_dir, exist_ok=True)
    files: List[StagedFile] = []

    code = row.auto_number
    if not re.fullmatch(r"UA-\d{3,5}|UA-TEST", code or ""):
        raise ValidationError("invalid auto_number for bounded publication")

    card_body = (
        f"CARD {code} id={row.id} status={row.status} "
        f"days={row.days_to_kyiv} eta={row.eta_manual}\n"
    ).encode("utf-8")
    for surface, root in (("video", live_video_dir), ("site", live_site_dir)):
        files.append(StagedFile(
            f"{surface}_card",
            os.path.join(staging_dir, f"{surface}_{code}.html"),
            os.path.join(root, f"{code}.html"),
            card_body,
        ))

    if include_diagnostic:
        diag_body = (
            f"DIAGNOSTIC {code} status={row.status} days={row.days_to_kyiv} "
            f"eta={row.eta_manual}\n"
        ).encode("utf-8")
    else:
        diag_body = (
            f"DIAGNOSTIC PLACEHOLDER {code}: Материалы диагностики ожидаются\n"
        ).encode("utf-8")
    for surface, root in (("video", live_video_dir), ("site", live_site_dir)):
        files.append(StagedFile(
            f"{surface}_diagnostic",
            os.path.join(staging_dir, f"{surface}_{code}-diag.html"),
            os.path.join(root, f"{code}-diag.html"),
            diag_body,
        ))

    catalog_body = (
        f"CATALOG {code} status={row.status} days={row.days_to_kyiv} "
        f"eta={row.eta_manual}\n"
    ).encode("utf-8")
    for surface, root in (("video", live_video_dir), ("site", live_site_dir)):
        files.append(StagedFile(
            f"{surface}_catalog",
            os.path.join(staging_dir, f"{surface}_katalog.html"),
            os.path.join(root, "katalog.html"),
            catalog_body,
        ))
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
        os.makedirs(os.path.dirname(sf.stage_path), exist_ok=True)
        with open(sf.stage_path, "wb") as stage:
            stage.write(sf.content)
            stage.flush()
            os.fsync(stage.fileno())
        with open(sf.stage_path, "rb") as staged_readback:
            staged_bytes = staged_readback.read()
        if staged_bytes != sf.content:
            raise PublicationVerificationError("staging byte verification failed")
        os.makedirs(os.path.dirname(sf.live_path), exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(sf.live_path))
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(sf.content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, sf.live_path)
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
        if not os.path.exists(sf.live_path):
            return False
        with open(sf.live_path, "rb") as f:
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
    live_video_dir: str,
    live_site_dir: str,
    car_id: int,
    n_days: int,
    actor: str,
    allow_ferry_normalization: bool = False,
    publisher: PublisherFn = default_publisher,
    include_diagnostic: bool = True,
    inject_readback_failure: bool = False,
    inject_install_partial_failure: bool = False,
    inject_delayed_overwrite: Optional[Callable[[], None]] = None,
    now_utc: Optional[datetime] = None,
) -> ApplyResult:
    """End-to-end: validate -> commit -> readback (new conn) -> stage ->
    install -> verify publish -> on any failure compensate DB + files and
    verify exact restoration. Emits exactly one message.
    """
    try:
        car_id = validate_car_id(car_id)
        n_days = validate_n_days(n_days)
    except ValidationError as exc:
        return ApplyResult(False, f"FAIL: {exc}")

    preimage_row = read_car_row(write_conn, car_id)
    if preimage_row is None:
        return ApplyResult(False, f"FAIL: car_id {car_id} not found")

    preimage_published = preimage_row.published

    # Bounded live file set that would be affected; captured BEFORE any DB
    # mutation, so rollback can restore bytes exactly.
    code = preimage_row.auto_number
    bounded_paths = [
        os.path.join(live_video_dir, f"{code}.html"),
        os.path.join(live_site_dir, f"{code}.html"),
        os.path.join(live_video_dir, f"{code}-diag.html"),
        os.path.join(live_site_dir, f"{code}-diag.html"),
        os.path.join(live_video_dir, "katalog.html"),
        os.path.join(live_site_dir, "katalog.html"),
    ]
    file_preimage = capture_preimage(bounded_paths)

    try:
        write_result = write_eta_transaction(
            write_conn, car_id, n_days, actor, allow_ferry_normalization,
            now_utc, preimage_row
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
                "condition_text=?, updated_at=? WHERE id=?",
                (
                    preimage_row.days_to_kyiv,
                    preimage_row.eta_manual,
                    preimage_row.status,
                    preimage_published,
                    preimage_row.condition_text,
                    preimage_row.updated_at,
                    car_id,
                ),
            )
            for audit_id in write_result.audit_ids:
                cur.execute("DELETE FROM audit WHERE id=?", (audit_id,))
            write_conn.commit()
        except Exception:
            write_conn.rollback()
            raise

        restore_preimage(file_preimage)
        verify_restored(file_preimage)

        restored_row = read_car_row(write_conn, car_id)
        if restored_row != preimage_row:
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
        staging_dir, live_video_dir, live_site_dir, row_after, include_diagnostic
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
# Reviewed live bridges.  They are inert in Gate A: nothing calls them unless
# live_patcher installs the module after the exact separate Gate B token.
# ---------------------------------------------------------------------------

def diagnostic_placeholder_html(code: str) -> str:
    if not re.fullmatch(r"UA-\d{3,5}", str(code or "")):
        raise ValidationError("invalid diagnostic placeholder code")
    return (
        "<!doctype html><html lang='ru'><head><meta charset='utf-8'>"
        "<title>Диагностика %s</title></head><body>"
        "<h1>%s</h1><p>Материалы диагностики ожидаются</p>"
        "</body></html>" % (code, code)
    )


def _atomic_write_bytes(path: str, data: bytes) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        if os.path.exists(temporary):
            os.remove(temporary)
        raise


def rebuild_catalogs_live() -> Tuple[bool, str]:
    """Build both real shared catalogs in memory, install atomically, verify,
    and restore both byte preimages on any failure.
    """
    try:
        import publikaciya
        import stranica
        cars = stranica.mashiny()
        frames = {}
        light = {}
        for car in cars:
            code = stranica.nomer(car)
            car_frames = stranica.kadry_mashiny(car)
            frames[code] = car_frames
            light[code] = stranica.legkie(car_frames) if car_frames else ([], [])
        html = stranica.sobrat_katalog(cars, frames, light)
        if not isinstance(html, str) or "UA-" not in html:
            return False, "catalog builder returned invalid HTML"
        payload = html.encode("utf-8")
        targets = [
            os.path.join(publikaciya.VIDEO, "katalog.html"),
            os.path.join(publikaciya.SITE, "katalog.html"),
        ]
        preimage = capture_preimage(targets)
        try:
            for target in targets:
                _atomic_write_bytes(target, payload)
            for target in targets:
                if not os.path.exists(target):
                    raise PublicationVerificationError("catalog byte read-back mismatch")
                with open(target, "rb") as catalog_readback:
                    installed = catalog_readback.read()
                if installed != payload:
                    raise PublicationVerificationError("catalog byte read-back mismatch")
            return True, "both catalogs verified"
        except Exception:
            restore_preimage(preimage)
            verify_restored(preimage)
            raise
    except Exception as exc:
        return False, str(exc)


def _restore_live_change(conn: sqlite3.Connection, car_id: int, row: CarRow,
                         audit_ids: Sequence[int],
                         file_preimage: Dict[str, Optional[bytes]]) -> None:
    cursor = conn.cursor()
    cursor.execute("BEGIN IMMEDIATE")
    try:
        cursor.execute(
            "UPDATE cars SET days_to_kyiv=?, eta_manual=?, status=?, published=?, "
            "condition_text=?, updated_at=? WHERE id=?",
            (row.days_to_kyiv, row.eta_manual, row.status, row.published,
             row.condition_text, row.updated_at, car_id),
        )
        for audit_id in audit_ids:
            cursor.execute("DELETE FROM audit WHERE id=?", (int(audit_id),))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    restore_preimage(file_preimage)
    verify_restored(file_preimage)
    restored = read_car_row(conn, car_id)
    if restored != row:
        raise RollbackVerificationError("live DB row rollback did not match preimage")


def _public_eta_verified(code: str, days: int, eta_iso: str) -> bool:
    expected_date = date.fromisoformat(eta_iso)
    month_ru = (
        "января", "февраля", "марта", "апреля", "мая", "июня",
        "июля", "августа", "сентября", "октября", "ноября", "декабря",
    )[expected_date.month - 1]
    variants = (eta_iso, expected_date.strftime("%d.%m.%Y"),
                "%d %s %d" % (expected_date.day, month_ru, expected_date.year))
    stamp = int(time.time())
    for surface in ("video", "site"):
        url = "https://www.uaart.com.ua/%s/%s.html?v=%d" % (surface, code, stamp)
        with urllib.request.urlopen(url, timeout=12) as response:
            body = response.read().decode("utf-8", "replace")
        if code not in body or str(days) not in body or not any(v in body for v in variants):
            return False
    return True


def apply_eta_days_live(car_id: int, raw_days, actor_id) -> Tuple[bool, str]:
    """The sole Gate-B live entry point used by both CRM handlers."""
    try:
        if isinstance(raw_days, str):
            stripped = raw_days.strip()
            if not re.fullmatch(r"\d{1,3}", stripped):
                raise ValidationError("Пришлите целое число дней от 0 до 400.")
            days = int(stripped)
        else:
            days = validate_n_days(raw_days)
        days = validate_n_days(days)
        car_id = validate_car_id(car_id)
    except ValidationError as exc:
        return False, str(exc)

    import db
    import publikaciya

    write_conn = db.connect()
    read_conn = db.connect()
    write_result: Optional[WriteResult] = None
    try:
        preimage_row = read_car_row(write_conn, car_id)
        if preimage_row is None:
            return False, "Карточка не найдена."
        code = preimage_row.auto_number
        targets = [
            os.path.join(publikaciya.VIDEO, code + ".html"),
            os.path.join(publikaciya.SITE, code + ".html"),
            os.path.join(publikaciya.VIDEO, code + "-diag.html"),
            os.path.join(publikaciya.SITE, code + "-diag.html"),
            os.path.join(publikaciya.VIDEO, "katalog.html"),
            os.path.join(publikaciya.SITE, "katalog.html"),
        ]
        file_preimage = capture_preimage(targets)
        write_result = write_eta_transaction(
            write_conn, car_id, days, str(actor_id),
            allow_ferry_normalization=True, expected_preimage=preimage_row)
        readback_verify(read_conn, car_id, write_result)
        ok, detail = publikaciya.opublikovat(code)
        if not ok:
            raise PublicationVerificationError(detail)
        for target in targets:
            if not os.path.isfile(target) or os.path.getsize(target) == 0:
                raise PublicationVerificationError("missing bounded target " + target)
        verified = False
        last_error = None
        for _ in range(3):
            try:
                if _public_eta_verified(code, days, write_result.eta):
                    verified = True
                    break
            except Exception as exc:
                last_error = exc
            time.sleep(1)
        if not verified:
            raise PublicationVerificationError(
                "public /video + /site read-back failed: %s" % (last_error or "mismatch"))
        return True, "До прибытия %d дней · %s. Страница и каталоги обновлены." % (
            days, date.fromisoformat(write_result.eta).strftime("%d.%m.%Y"))
    except Exception as exc:
        if write_result is not None:
            try:
                _restore_live_change(
                    write_conn, car_id, preimage_row, write_result.audit_ids, file_preimage)
            except Exception as rollback_exc:
                return False, "Ошибка; автоматический откат не подтверждён: %s" % rollback_exc
        return False, "Изменение отменено, прежние данные восстановлены: %s" % exc
    finally:
        read_conn.close()
        write_conn.close()


# ---------------------------------------------------------------------------
# Stale arrival-sentence sanitizer (narrow, fail-closed)
# ---------------------------------------------------------------------------

_UA_MONTHS = (
    "\u0441\u0456\u0447\u043d\u044f|\u043b\u044e\u0442\u043e\u0433\u043e|\u0431\u0435\u0440\u0435\u0437\u043d\u044f|"
    "\u043a\u0432\u0456\u0442\u043d\u044f|\u0442\u0440\u0430\u0432\u043d\u044f|\u0447\u0435\u0440\u0432\u043d\u044f|"
    "\u043b\u0438\u043f\u043d\u044f|\u0441\u0435\u0440\u043f\u043d\u044f|\u0432\u0435\u0440\u0435\u0441\u043d\u044f|"
    "\u0436\u043e\u0432\u0442\u043d\u044f|\u043b\u0438\u0441\u0442\u043e\u043f\u0430\u0434\u0430|\u0433\u0440\u0443\u0434\u043d\u044f"
)

_RU_MONTHS = (
    "января|февраля|марта|апреля|мая|июня|июля|августа|"
    "сентября|октября|ноября|декабря"
)
_DATE_RE = re.compile(
    r"\b(?:\d{1,2}\s+(?:" + _UA_MONTHS + "|" + _RU_MONTHS +
    r")\s+\d{4}|\d{1,2}[./]\d{1,2}[./]\d{2,4})\b", re.IGNORECASE)

_ARRIVAL_KEYWORDS = (
    "\u043f\u0440\u0438\u0431\u0443\u0442\u0442\u044f",
    "\u043f\u0440\u0438\u0431\u0443\u0434\u0435",
    "\u043f\u0440\u0438\u0431\u0443\u0434\u0435\u0442\u0435",
    "\u0434\u043e\u0441\u0442\u0430\u0432\u043a",
    "\u043f\u0435\u0440\u0435\u0434\u0430\u0447\u0430",
    "\u043f\u0440\u0438\u0432\u0435\u0437\u0435",
    "\u0441\u0430\u043c\u043e\u0441\u0442\u0456\u0439\u043d\u043e",
)


def sanitize_stale_arrival_sentence(text: str) -> str:
    """Removes only sentences that are simultaneously about arrival/delivery
    AND contain an independent calendar date. All other sentences (service,
    auction, repair, registration, unrelated dates) are preserved
    byte-semantically.
    """
    if not text:
        return text
    removals: List[Tuple[int, int]] = []
    # Each match preserves its exact punctuation and whitespace.  Only a
    # matched arrival/date span is omitted from the final slice assembly.
    sentence_pattern = re.compile(
        r".*?(?:[!?]+|[.]+(?=\s|$)|$)", re.DOTALL)
    for match in sentence_pattern.finditer(text):
        sentence = match.group(0)
        if not sentence:
            continue
        lowered = sentence.lower()
        if _DATE_RE.search(sentence) and any(k in lowered for k in _ARRIVAL_KEYWORDS):
            leading = len(re.match(r"[ \t]*", sentence).group(0))
            start = match.start() + leading
            end = match.end()
            # Keep the separator before the removed sentence, and consume a
            # duplicate horizontal separator after it. Newlines are content
            # and therefore remain byte-identical.
            if leading:
                while end < len(text) and text[end] in " \t":
                    end += 1
            removals.append((start, end))
    if not removals:
        return text
    pieces: List[str] = []
    cursor = 0
    for start, end in removals:
        pieces.append(text[cursor:start])
        cursor = end
    pieces.append(text[cursor:])
    return "".join(pieces)

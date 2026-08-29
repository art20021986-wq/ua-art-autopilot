"""
eta_release_candidate.py — TASK 079 shared ETA/status writer and release
orchestrator for CRM-CONTAINER-STAGE-SYNC-004 v1.0.

This module implements the single shared writer required by TASK 077/079 so
that konteyner.prinyat and cars_ui.apply_value can be made to call exactly the
same code path. It is SANDBOX ONLY in this delivery: nothing in this file
opens, reads, or writes any real production path. All file/DB operations are
parameterized by paths supplied by the caller (tests use temporary copies).

Architecture implemented here (see task contract for full text):
  1. write_eta_sync(...)      -> single short SQLite transaction, commits
                                  before any renderer/publisher call.
  2. read_back(...)           -> new-connection verified read-back.
  3. FileStager               -> bounded file set preimage capture, atomic
                                  install, exact-byte restoration.
  4. compensate_rollback(...) -> compensating DB transaction restoring the
                                  exact preimage row, including `published`.
  5. run_eta_sync_release(...) -> full orchestration: DB commit -> read-back
                                  -> stage/build -> install -> publish verify
                                  -> compensate on any failure. Emits exactly
                                  one PASS or FAIL message.
  6. sanitize_stale_arrival_sentence(...) -> narrow stale-date sanitizer that
                                  removes only sentences that are both about
                                  arrival/delivery AND contain an independent
                                  calendar date, preserving everything else.
  7. verify_anchor / extract_function_sources -> fail-closed source guards
                                  used by live_patcher.py.

No generic search-and-replace is performed anywhere in this module.
"""

import ast
import datetime
import hashlib
import os
import re
import sqlite3
import tempfile


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class ETASyncError(Exception):
    """Base class for all fail-closed errors in this module."""


class InvalidInputError(ETASyncError):
    pass


class CarNotFoundError(ETASyncError):
    pass


class AnchorMismatchError(ETASyncError):
    def __init__(self, filename, expected, actual):
        super().__init__(
            "anchor mismatch for %s: expected %s got %s" % (filename, expected, actual)
        )
        self.filename = filename
        self.expected = expected
        self.actual = actual


class PublishError(ETASyncError):
    pass


class ReadBackError(ETASyncError):
    pass


class RollbackVerificationError(ETASyncError):
    pass


# ---------------------------------------------------------------------------
# Proven live full-file SHA-256 anchors (TASK 076/077 evidence).
# These are the ONLY anchors trusted by verify_anchor(). No other filename is
# ever accepted.
# ---------------------------------------------------------------------------

ANCHOR_SHA256 = {
    "db.py": "b732a5c731d85cb4c9b1cfddb2fc20961b75230d64e29563a5b5ac328d62c086",
    "cars_ui.py": "50f1cb15b6e1ec3a35878a3021beb362a87f3607ac46abf3eb44566023b14306",
    "konteyner.py": "2d56a970fb76c782f0d5caebd65b6a7ffd44fd3ad1278a775bf641cffd39080d",
    "stranica.py": "84a56024e185932c3f2af289db87d1b98558acdf9c4788256dfd36d544ec28b3",
    "publikaciya.py": "7bb8b0e51b41d94ad305179c35bce20d89dee7f7704c844335a478f87499f0a4",
}


CANONICAL_FERRY_STATUS = "sea_loaded"

# Protected real statuses that must never be normalized backwards, and must
# never be overwritten by the ferry-normalization branch even if a caller
# mistakenly includes them in allowed_ferry_statuses.
PROTECTED_STATUSES = frozenset({"ge_waiting", "ge_to_kyiv", "ua_arrived"})
SOLD_PREFIX = "sold_"

MIN_N = 0
MAX_N = 400


def is_protected_status(status, extra_terminal_statuses=frozenset()):
    if status is None:
        return False
    if status in PROTECTED_STATUSES:
        return True
    if status.startswith(SOLD_PREFIX):
        return True
    if status in extra_terminal_statuses:
        return True
    return False


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def validate_car_id(car_id):
    if isinstance(car_id, bool) or not isinstance(car_id, int):
        raise InvalidInputError("car_id must be a plain int")
    if car_id <= 0:
        raise InvalidInputError("car_id must be positive")
    return car_id


def validate_n(n):
    if isinstance(n, bool) or not isinstance(n, int):
        raise InvalidInputError("n must be a plain int")
    if n < MIN_N or n > MAX_N:
        raise InvalidInputError("n must be between %d and %d inclusive" % (MIN_N, MAX_N))
    return n


def utc_today():
    return datetime.datetime.now(datetime.timezone.utc).date()


def compute_eta(n):
    return (utc_today() + datetime.timedelta(days=n)).isoformat()


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def verify_anchor(filename, content_bytes):
    expected = ANCHOR_SHA256.get(filename)
    if expected is None:
        raise AnchorMismatchError(filename, "NO_ANCHOR_CONFIGURED", "N/A")
    actual = sha256_bytes(content_bytes)
    if actual != expected:
        raise AnchorMismatchError(filename, expected, actual)
    return True


def extract_function_sources(source_text, function_names):
    """
    Fail-closed AST extraction: requires exactly one definition per requested
    function name. Refuses on duplicates or missing definitions.
    """
    tree = ast.parse(source_text)
    counts = {}
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in function_names:
            counts[node.name] = counts.get(node.name, 0) + 1
            seg = ast.get_source_segment(source_text, node)
            found.setdefault(node.name, []).append(seg)
    for name in function_names:
        if counts.get(name, 0) != 1:
            raise ETASyncError(
                "function anchor refusal: %s found %d time(s) (expected exactly 1)"
                % (name, counts.get(name, 0))
            )
    return {name: found[name][0] for name in function_names}


# ---------------------------------------------------------------------------
# DB writer
# ---------------------------------------------------------------------------

def capture_row_preimage(conn, car_id):
    cur = conn.cursor()
    cur.execute(
        "SELECT id, days_to_kyiv, eta_manual, status, published, updated_at "
        "FROM cars WHERE id=?",
        (car_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise CarNotFoundError("car %s not found" % car_id)
    return {
        "id": row[0],
        "days_to_kyiv": row[1],
        "eta_manual": row[2],
        "status": row[3],
        "published": row[4],
        "updated_at": row[5],
    }


def write_eta_sync(conn, car_id, n, actor, normalize_status=False,
                    allowed_ferry_statuses=frozenset(),
                    extra_terminal_statuses=frozenset()):
    """
    Single short SQLite transaction. Writes only days_to_kyiv, eta_manual,
    optional status normalization, and updated_at. Never touches `published`.
    Commits before returning. Returns {"preimage":..., "postimage":...}.
    """
    car_id = validate_car_id(car_id)
    n = validate_n(n)
    if not actor:
        raise InvalidInputError("actor is required")

    preimage = capture_row_preimage(conn, car_id)
    current_status = preimage["status"]

    new_status = current_status
    if normalize_status:
        if is_protected_status(current_status, extra_terminal_statuses):
            new_status = current_status
        elif current_status in allowed_ferry_statuses:
            new_status = CANONICAL_FERRY_STATUS

    new_eta = compute_eta(n)
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    cur = conn.cursor()
    cur.execute("BEGIN IMMEDIATE")
    try:
        cur.execute(
            "UPDATE cars SET days_to_kyiv=?, eta_manual=?, status=?, updated_at=? WHERE id=?",
            (n, new_eta, new_status, now_iso, car_id),
        )
        if preimage["days_to_kyiv"] != n:
            cur.execute(
                "INSERT INTO audit(car_id, field, old_value, new_value, actor, created_at) "
                "VALUES (?,?,?,?,?,?)",
                (car_id, "days_to_kyiv", str(preimage["days_to_kyiv"]), str(n), actor, now_iso),
            )
        if preimage["eta_manual"] != new_eta:
            cur.execute(
                "INSERT INTO audit(car_id, field, old_value, new_value, actor, created_at) "
                "VALUES (?,?,?,?,?,?)",
                (car_id, "eta_manual", str(preimage["eta_manual"]), str(new_eta), actor, now_iso),
            )
        if preimage["status"] != new_status:
            cur.execute(
                "INSERT INTO audit(car_id, field, old_value, new_value, actor, created_at) "
                "VALUES (?,?,?,?,?,?)",
                (car_id, "status", str(preimage["status"]), str(new_status), actor, now_iso),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    postimage = {
        "id": car_id,
        "days_to_kyiv": n,
        "eta_manual": new_eta,
        "status": new_status,
        "published": preimage["published"],
        "updated_at": now_iso,
    }
    return {"preimage": preimage, "postimage": postimage}


def read_back(db_path, car_id):
    """Independent-connection verified read-back after commit."""
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, days_to_kyiv, eta_manual, status, published, updated_at "
            "FROM cars WHERE id=?",
            (car_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise ReadBackError("car %s missing on read-back" % car_id)
        return {
            "id": row[0], "days_to_kyiv": row[1], "eta_manual": row[2],
            "status": row[3], "published": row[4], "updated_at": row[5],
        }
    finally:
        conn.close()


def compensate_rollback(conn, preimage, actor):
    """Compensating transaction restoring the exact preimage row."""
    cur = conn.cursor()
    cur.execute("BEGIN IMMEDIATE")
    try:
        cur.execute(
            "UPDATE cars SET days_to_kyiv=?, eta_manual=?, status=?, published=?, updated_at=? "
            "WHERE id=?",
            (preimage["days_to_kyiv"], preimage["eta_manual"], preimage["status"],
             preimage["published"], preimage["updated_at"], preimage["id"]),
        )
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        cur.execute(
            "INSERT INTO audit(car_id, field, old_value, new_value, actor, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (preimage["id"], "compensating_rollback", "post_failure", "restored_preimage",
             actor, now_iso),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def verify_rollback(db_path, preimage):
    current = read_back(db_path, preimage["id"])
    for key in ("days_to_kyiv", "eta_manual", "status", "published"):
        if current[key] != preimage[key]:
            raise RollbackVerificationError(
                "rollback mismatch on %s: expected %r got %r" % (key, preimage[key], current[key])
            )
    return True


# ---------------------------------------------------------------------------
# Bounded file staging
# ---------------------------------------------------------------------------

class FileStager:
    """
    Captures byte preimages of a bounded, named file set, installs staged
    content atomically (temp file + os.replace), and restores exact preimage
    bytes (or exact absence) on failure.
    """

    def __init__(self, file_paths):
        # file_paths: dict[logical_name] -> absolute path
        self.file_paths = dict(file_paths)
        self.preimages = {}

    def capture_preimages(self):
        for name, path in self.file_paths.items():
            if os.path.exists(path):
                with open(path, "rb") as f:
                    data = f.read()
            else:
                data = None
            self.preimages[name] = {
                "existed": data is not None,
                "bytes": data,
                "sha256": sha256_bytes(data) if data is not None else None,
            }
        return self.preimages

    def install(self, staged_content):
        """staged_content: dict[logical_name] -> bytes. Atomic per-file install."""
        installed = []
        try:
            for name, content in staged_content.items():
                path = self.file_paths[name]
                directory = os.path.dirname(path) or "."
                fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".stage_")
                try:
                    with os.fdopen(fd, "wb") as f:
                        f.write(content)
                    os.replace(tmp_path, path)
                    installed.append(name)
                except Exception:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                    raise
        except Exception:
            self.restore(only=installed)
            raise
        return installed

    def restore(self, only=None):
        names = only if only is not None else list(self.preimages.keys())
        restored = []
        for name in names:
            pre = self.preimages.get(name)
            path = self.file_paths[name]
            if pre is None:
                continue
            if pre["existed"]:
                directory = os.path.dirname(path) or "."
                fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".restore_")
                with os.fdopen(fd, "wb") as f:
                    f.write(pre["bytes"])
                os.replace(tmp_path, path)
            else:
                if os.path.exists(path):
                    os.remove(path)
            restored.append(name)
        return restored

    def verify_restored(self):
        for name, pre in self.preimages.items():
            path = self.file_paths[name]
            if pre["existed"]:
                if not os.path.exists(path):
                    raise RollbackVerificationError("%s missing after restore" % name)
                with open(path, "rb") as f:
                    actual = f.read()
                if sha256_bytes(actual) != pre["sha256"]:
                    raise RollbackVerificationError("%s bytes mismatch after restore" % name)
            else:
                if os.path.exists(path):
                    raise RollbackVerificationError("%s unexpectedly present after restore" % name)
        return True


# ---------------------------------------------------------------------------
# Full orchestration
# ---------------------------------------------------------------------------

def run_eta_sync_release(db_path, car_id, n, actor, file_paths, build_staged_content,
                          publisher, normalize_status=False,
                          allowed_ferry_statuses=frozenset(),
                          extra_terminal_statuses=frozenset()):
    """
    Full release-candidate flow used by both live entry points:
      DB commit -> independent read-back -> build bounded staged files ->
      atomic install -> publisher verification -> on ANY failure:
      compensating DB rollback + exact file restoration, verified.

    build_staged_content(row_dict) -> dict[logical_name] -> bytes
    publisher(car_id, row_dict) -> bool (True = verified PASS)

    Returns {"status": "PASS"|"FAIL", "message": <exactly one string>, ...}
    """
    stager = FileStager(file_paths)
    stager.capture_preimages()

    conn = sqlite3.connect(db_path)
    try:
        result = write_eta_sync(
            conn, car_id, n, actor,
            normalize_status=normalize_status,
            allowed_ferry_statuses=allowed_ferry_statuses,
            extra_terminal_statuses=extra_terminal_statuses,
        )
    finally:
        conn.close()

    preimage = result["preimage"]

    try:
        rb = read_back(db_path, car_id)
        expected = result["postimage"]
        for key in ("days_to_kyiv", "eta_manual", "status", "published"):
            if rb[key] != expected[key]:
                raise ReadBackError("post-write read-back mismatch on %s" % key)

        staged_content = build_staged_content(rb)
        installed = stager.install(staged_content)

        publish_ok = publisher(car_id, rb)
        if not publish_ok:
            raise PublishError("publisher returned failure")

        return {
            "status": "PASS",
            "message": "SUCCESS: ETA sync verified and published.",
            "row": rb,
            "installed": installed,
        }
    except Exception as exc:
        conn2 = sqlite3.connect(db_path)
        try:
            compensate_rollback(conn2, preimage, actor)
        finally:
            conn2.close()
        verify_rollback(db_path, preimage)
        stager.restore()
        stager.verify_restored()
        return {
            "status": "FAIL",
            "message": "FAILURE: ETA sync rolled back (%s)." % exc,
            "error": str(exc),
        }


# ---------------------------------------------------------------------------
# Narrow stale-date sanitizer
# ---------------------------------------------------------------------------

_UKR_MONTHS = (
    "січня|лютого|березня|квітня|травня|червня|липня|серпня|вересня|жовтня|"
    "листопада|грудня"
)
DATE_PATTERN = re.compile(r"\d{1,2}\s+(?:" + _UKR_MONTHS + r")\s+\d{4}", re.IGNORECASE)
ARRIVAL_KEYWORDS = ("прибу", "достав", "переда", "приїде", "приїзд")


def split_sentences(text):
    return re.split(r"(?<=[.!?])\s+", text)


def sanitize_stale_arrival_sentence(text, must_contain_fragment=None):
    """
    Removes only sentences that simultaneously:
      - contain an arrival/delivery/hand-over keyword, AND
      - contain an independent calendar date (Ukrainian month name form).
    If must_contain_fragment is given, the sentence must also contain that
    exact fragment (e.g. "9 вересня 2026") to be removed.
    Returns (sanitized_text, removed_sentences).
    """
    sentences = split_sentences(text)
    kept, removed = [], []
    for s in sentences:
        has_date = DATE_PATTERN.search(s) is not None
        has_keyword = any(k in s.lower() for k in ARRIVAL_KEYWORDS)
        fragment_ok = (must_contain_fragment is None) or (must_contain_fragment in s)
        if has_date and has_keyword and fragment_ok:
            removed.append(s)
            continue
        kept.append(s)
    return " ".join(kept).strip(), removed


# ---------------------------------------------------------------------------
# Gate B owner token (documentation only — never accepted as approval by any
# code path in this module).
# ---------------------------------------------------------------------------

GATE_B_OWNER_TOKEN = "CRM-CONTAINER-STAGE-SYNC-004-V1.0-PRODUCTION-APPROVED"

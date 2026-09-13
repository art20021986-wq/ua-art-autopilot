"""Durable price-publication intent, candidate only; no live imports or I/O.

Every write uses a caller-owned SQLite transaction on the CRM connection.
Nothing here commits, retries, publishes, sends Telegram or verifies receipts.
The adapter must roll back the whole CRM transaction on any enqueue exception.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
import re
import sqlite3


TABLE = "uaart_price_publication_outbox_v1"
RECOVERY_TABLE = "uaart_price_publication_recovery_v1"
MAX_RECOVERY_EVIDENCE_AGE_MS = 30000
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_USD = re.compile(r"(?:0|[1-9][0-9]*)\.[0-9]{2}\Z")
_DDL = f"""CREATE TABLE {TABLE} (
 event_key TEXT PRIMARY KEY NOT NULL,
 car_id INTEGER NOT NULL CHECK(car_id > 0),
 revision INTEGER NOT NULL CHECK(revision > 0),
 ukraine_usd TEXT NOT NULL,
 georgia_usd TEXT,
 created_ms INTEGER NOT NULL CHECK(created_ms >= 0),
 state TEXT NOT NULL CHECK(state IN ('PENDING','CLAIMED','STOPPED','PUBLISHED','SUPERSEDED','RECONCILED')),
 claim_nonce TEXT UNIQUE,
 claimed_ms INTEGER,
 finished_ms INTEGER,
 reason TEXT,
 receipt_sha256 TEXT,
 UNIQUE(car_id, revision),
 CHECK((state IN ('CLAIMED','STOPPED','PUBLISHED','RECONCILED') AND claim_nonce IS NOT NULL)
       OR (state IN ('PENDING','SUPERSEDED') AND claim_nonce IS NULL))
)"""
_RECOVERY_DDL = f"""CREATE TABLE {RECOVERY_TABLE} (
 recovery_key TEXT PRIMARY KEY NOT NULL,
 event_key TEXT NOT NULL,
 claim_nonce TEXT NOT NULL,
 prior_state TEXT NOT NULL CHECK(prior_state IN ('CLAIMED','STOPPED')),
 prior_reason TEXT,
 prior_finished_ms INTEGER,
 outcome TEXT NOT NULL CHECK(outcome IN ('NO_EFFECT','RESTORED','PUBLISHED')),
 final_state TEXT NOT NULL CHECK(final_state IN ('RECONCILED','PUBLISHED')),
 evidence_json TEXT NOT NULL,
 evidence_payload_sha256 TEXT NOT NULL,
 recorded_ms INTEGER NOT NULL CHECK(recorded_ms >= 0),
 UNIQUE(event_key, claim_nonce),
 FOREIGN KEY(event_key) REFERENCES {TABLE}(event_key)
)"""
_RECOVERY_TRIGGERS = tuple(
    (f"{RECOVERY_TABLE}_no_{action.lower()}",
     f"CREATE TRIGGER {RECOVERY_TABLE}_no_{action.lower()} BEFORE {action} ON {RECOVERY_TABLE} "
     "BEGIN SELECT RAISE(ABORT, 'RECOVERY_LEDGER_APPEND_ONLY'); END")
    for action in ("UPDATE", "DELETE")
)


class OutboxError(RuntimeError):
    pass


@dataclass(frozen=True)
class RecoveryEvidence:
    """Trusted runtime's verified observations; this value performs no I/O.

    The runtime must bind its actual cause fix, fresh preflight, original
    publication attempt and public file observations in the evidence artifact.
    Hash syntax and true flags alone are not proof of those operations.
    NO_EFFECT/RESTORED mean the prior verified public state was proved intact
    or restored. PUBLISHED means CRM, card and catalog match the current event,
    with non-price preservation verified and a real publication receipt.
    """
    recovery_key: str
    event_key: str
    claim_nonce: str
    current_revision: int
    outcome: str
    reason: str
    cause_resolved: bool
    preflight_verified: bool
    public_state_verified: bool
    prices_match_current: bool
    cause_fix_sha256: str
    preflight_sha256: str
    preflight_ms: int
    observed_ms: int
    card_sha256: str
    catalog_sha256: str
    evidence_sha256: str
    publication_receipt_sha256: str | None = None


def _integer(value, name):
    if type(value) is not int or not 0 <= value < 2**63:
        raise OutboxError("INVALID_" + name)


def _hash(value, name):
    if type(value) is not str or not _SHA.fullmatch(value):
        raise OutboxError("INVALID_" + name)


def _transaction(conn):
    if not isinstance(conn, sqlite3.Connection) or not conn.in_transaction:
        raise OutboxError("EXPLICIT_CALLER_TRANSACTION_REQUIRED")


def _write_lock(conn):
    _transaction(conn)
    # Obtain SQLite's write lock before read/modify checks, even with BEGIN
    # DEFERRED. BEGIN IMMEDIATE remains the required adapter convention.
    conn.execute(f"UPDATE {TABLE} SET revision=revision WHERE 0")


def install(conn):
    """Explicit schema installation only. Refuse unknown existing schema.

    Caller must begin, back up, inspect, verify and commit; no cars DDL occurs.
    SQLite CREATE TABLE is transactional (do not replace this with executescript).
    """
    _transaction(conn)
    for name, ddl in ((TABLE, _DDL), (RECOVERY_TABLE, _RECOVERY_DDL)):
        row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                           (name,)).fetchone()
        if row is None:
            conn.execute(ddl)
        elif row[0] != ddl:
            raise OutboxError("EXISTING_OUTBOX_SCHEMA_MISMATCH")
    for name, ddl in _RECOVERY_TRIGGERS:
        row = conn.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?",
                           (name,)).fetchone()
        if row is None:
            conn.execute(ddl)
        elif row[0] != ddl:
            raise OutboxError("EXISTING_RECOVERY_TRIGGER_MISMATCH")


def get(conn, event_key):
    _hash(event_key, "EVENT_KEY")
    cursor = conn.execute(f"SELECT * FROM {TABLE} WHERE event_key=?", (event_key,))
    row = cursor.fetchone()
    return dict(zip((column[0] for column in cursor.description), row)) if row else None


def enqueue(conn, *, event_key, car_id, ukraine_usd, georgia_usd, now_ms):
    """Call after cars/audit UPDATE and checks, before that same conn.commit().

    event_key binds the stable CRM mutation identity, not a fresh delivery UUID.
    Both prices must be read from the updated row on this exact connection.
    Revisions become visible to workers only when the encompassing commit does.
    """
    _hash(event_key, "EVENT_KEY")
    _integer(car_id, "CAR_ID")
    _integer(now_ms, "NOW_MS")
    if car_id == 0:
        raise OutboxError("INVALID_CAR_ID")
    if type(ukraine_usd) is not str or not _USD.fullmatch(ukraine_usd):
        raise OutboxError("CANONICAL_UKRAINE_USD_REQUIRED")
    if georgia_usd is not None and (type(georgia_usd) is not str or not _USD.fullmatch(georgia_usd)):
        raise OutboxError("CANONICAL_GEORGIA_USD_REQUIRED")
    _write_lock(conn)
    existing = get(conn, event_key)
    if existing:
        if (existing["car_id"], existing["ukraine_usd"], existing["georgia_usd"]) != (
                car_id, ukraine_usd, georgia_usd):
            raise OutboxError("EVENT_KEY_PAYLOAD_CONFLICT")
        latest = conn.execute(f"SELECT MAX(revision) FROM {TABLE} WHERE car_id=?",
                              (car_id,)).fetchone()[0]
        if existing["revision"] != latest:
            raise OutboxError("OLD_MUTATION_ALREADY_SUPERSEDED")
        return existing
    revision = conn.execute(f"SELECT COALESCE(MAX(revision),0)+1 FROM {TABLE} WHERE car_id=?",
                            (car_id,)).fetchone()[0]
    conn.execute(f"INSERT INTO {TABLE} (event_key,car_id,revision,ukraine_usd,georgia_usd,"
                 "created_ms,state) VALUES (?,?,?,?,?,?,'PENDING')",
                 (event_key, car_id, revision, ukraine_usd, georgia_usd, now_ms))
    # Never clear an uncertain in-flight/stopped operation by a later edit.
    conn.execute(f"UPDATE {TABLE} SET state='SUPERSEDED',finished_ms=?,reason='NEWER_REVISION' "
                 "WHERE car_id=? AND revision<? AND state='PENDING'", (now_ms, car_id, revision))
    return get(conn, event_key)


def claim(conn, *, event_key, nonce, now_ms):
    """One committed claim; no timeout expiry or automatic reclaim exists."""
    _hash(nonce, "CLAIM_NONCE")
    _integer(now_ms, "NOW_MS")
    _write_lock(conn)
    event = get(conn, event_key)
    if event is None or event["state"] != "PENDING":
        raise OutboxError("EVENT_NOT_PENDING")
    if now_ms < event["created_ms"]:
        raise OutboxError("CLAIM_BEFORE_EVENT")
    blocked = conn.execute(f"SELECT 1 FROM {TABLE} WHERE car_id=? AND state IN ('CLAIMED','STOPPED')",
                           (event["car_id"],)).fetchone()
    latest = conn.execute(f"SELECT MAX(revision) FROM {TABLE} WHERE car_id=?",
                          (event["car_id"],)).fetchone()[0]
    if blocked or latest != event["revision"]:
        raise OutboxError("CAR_REQUIRES_RECONCILIATION")
    conn.execute(f"UPDATE {TABLE} SET state='CLAIMED',claim_nonce=?,claimed_ms=? WHERE event_key=?",
                 (nonce, now_ms, event_key))
    return get(conn, event_key)


def _claimed(conn, event_key, nonce):
    _hash(nonce, "CLAIM_NONCE")
    _write_lock(conn)
    event = get(conn, event_key)
    if event is None or event["state"] != "CLAIMED" or event["claim_nonce"] != nonce:
        raise OutboxError("CURRENT_CLAIM_NONCE_REQUIRED")
    return event


def require_current_claim(conn, *, event_key, nonce):
    """Fence before publish and after semantic readback, with publication lock held.

    A DB transaction alone cannot fence filesystem/network publishers. The
    adapter must serialize all catalog writers and re-read current CRM prices.
    """
    event = _claimed(conn, event_key, nonce)
    latest = conn.execute(f"SELECT MAX(revision) FROM {TABLE} WHERE car_id=?",
                          (event["car_id"],)).fetchone()[0]
    if latest != event["revision"]:
        raise OutboxError("NEWER_CRM_REVISION_NEVER_REPLAY_OLD_PRICE")
    return event


def stop(conn, *, event_key, nonce, reason, now_ms):
    """Durably stop an uncertain/failed attempt; keep committed CRM prices."""
    if type(reason) is not str or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,99}", reason):
        raise OutboxError("SANITIZED_FAILURE_CODE_REQUIRED")
    _integer(now_ms, "NOW_MS")
    event = _claimed(conn, event_key, nonce)
    if now_ms < event["claimed_ms"]:
        raise OutboxError("FINISH_BEFORE_CLAIM")
    conn.execute(f"UPDATE {TABLE} SET state='STOPPED',finished_ms=?,reason=? WHERE event_key=?",
                 (now_ms, reason, event_key))
    return get(conn, event_key)


def record_verified_publication(conn, *, event_key, nonce, receipt_sha256, now_ms):
    """Record adapter-verified receipt only; a hash does NOT verify a receipt.

    Adapter must first apply price_publication.publication_decision to fresh CRM,
    card and catalog semantic evidence and check all non-price preservation.
    Do not call after failures or for HTTP-200-only observations.
    """
    _hash(receipt_sha256, "PUBLICATION_RECEIPT")
    _integer(now_ms, "NOW_MS")
    event = require_current_claim(conn, event_key=event_key, nonce=nonce)
    if now_ms < event["claimed_ms"]:
        raise OutboxError("FINISH_BEFORE_CLAIM")
    conn.execute(f"UPDATE {TABLE} SET state='PUBLISHED',finished_ms=?,receipt_sha256=? "
                 "WHERE event_key=?", (now_ms, receipt_sha256, event_key))
    return get(conn, event_key)


def get_recovery(conn, recovery_key):
    """Read the immutable record of one reconciled attempt."""
    _hash(recovery_key, "RECOVERY_KEY")
    cursor = conn.execute(f"SELECT * FROM {RECOVERY_TABLE} WHERE recovery_key=?", (recovery_key,))
    row = cursor.fetchone()
    return dict(zip((column[0] for column in cursor.description), row)) if row else None


def _recovery_payload(evidence):
    if type(evidence) is not RecoveryEvidence:
        raise OutboxError("EXACT_RECOVERY_EVIDENCE_REQUIRED")
    for name in ("recovery_key", "event_key", "claim_nonce", "cause_fix_sha256",
                 "preflight_sha256", "card_sha256", "catalog_sha256", "evidence_sha256"):
        _hash(getattr(evidence, name), name.upper())
    for name in ("current_revision", "preflight_ms", "observed_ms"):
        _integer(getattr(evidence, name), name.upper())
    if evidence.current_revision < 1:
        raise OutboxError("POSITIVE_RECOVERY_REVISION_REQUIRED")
    if evidence.outcome not in ("NO_EFFECT", "RESTORED", "PUBLISHED"):
        raise OutboxError("VERIFIED_RECOVERY_OUTCOME_REQUIRED")
    if type(evidence.reason) is not str or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,99}", evidence.reason):
        raise OutboxError("SANITIZED_RECOVERY_REASON_REQUIRED")
    for name in ("cause_resolved", "preflight_verified", "public_state_verified", "prices_match_current"):
        if type(getattr(evidence, name)) is not bool:
            raise OutboxError("EXACT_RECOVERY_BOOLEAN_REQUIRED")
    if not (evidence.cause_resolved and evidence.preflight_verified and evidence.public_state_verified):
        raise OutboxError("VERIFIED_CAUSE_PREFLIGHT_PUBLIC_STATE_REQUIRED")
    if evidence.outcome == "PUBLISHED":
        if not evidence.prices_match_current:
            raise OutboxError("RECOVERED_PUBLICATION_CURRENT_PRICES_REQUIRED")
        _hash(evidence.publication_receipt_sha256, "RECOVERED_PUBLICATION_RECEIPT")
    elif evidence.publication_receipt_sha256 is not None:
        raise OutboxError("NONPUBLICATION_RECOVERY_CANNOT_HAVE_PUBLICATION_RECEIPT")
    payload = json.dumps(asdict(evidence), sort_keys=True, separators=(",", ":"))
    return payload, hashlib.sha256(payload.encode("utf-8")).hexdigest()


def reconcile_verified(conn, *, event_key, nonce, evidence, now_ms):
    """Close one uncertain attempt using runtime-verified evidence, never retry.

    Hold the global publication lock and caller's BEGIN IMMEDIATE through
    observations and this transition. This only stores the runtime's proof;
    it never reads/writes public files, restores prices or validates a receipt.
    CLAIMED/STOPPED -> RECONCILED releases a *newer* pending event, retaining the
    old nonce and failure history. The old attempt never becomes PENDING.
    A proved complete publication can instead close as PUBLISHED only while
    its revision remains current. Exact proof replay is a read-only no-op.
    Caller must roll back the entire DB transaction on every exception.
    """
    _hash(event_key, "EVENT_KEY")
    _hash(nonce, "CLAIM_NONCE")
    _integer(now_ms, "NOW_MS")
    payload, payload_hash = _recovery_payload(evidence)
    if (evidence.event_key, evidence.claim_nonce) != (event_key, nonce):
        raise OutboxError("RECOVERY_ATTEMPT_BINDING_REQUIRED")
    _write_lock(conn)
    event = get(conn, event_key)
    if event is None or event["claim_nonce"] != nonce:
        raise OutboxError("CURRENT_RECOVERY_CLAIM_NONCE_REQUIRED")
    recorded = get_recovery(conn, evidence.recovery_key)
    if recorded is not None:
        if recorded["evidence_json"] != payload or recorded["evidence_payload_sha256"] != payload_hash:
            raise OutboxError("RECOVERY_KEY_EVIDENCE_CONFLICT")
        if (recorded["event_key"], recorded["claim_nonce"], recorded["final_state"]) != (
                event_key, nonce, event["state"]):
            raise OutboxError("RECOVERY_LEDGER_EVENT_DRIFT")
        # No new decision is made. Original proof may now be old, or a newer
        # CRM edit may exist; returning the existing terminal event replays no
        # side effect and cannot acknowledge that newer edit.
        return event
    if event["state"] not in ("CLAIMED", "STOPPED"):
        raise OutboxError("UNCERTAIN_ATTEMPT_REQUIRED_FOR_RECOVERY")
    prior_recovery = conn.execute(
        f"SELECT 1 FROM {RECOVERY_TABLE} WHERE event_key=? AND claim_nonce=?", (event_key, nonce)
    ).fetchone()
    if prior_recovery is not None:
        raise OutboxError("ATTEMPT_ALREADY_HAS_RECOVERY_PROOF")
    boundary = max(event["claimed_ms"], event["finished_ms"] or 0)
    if not boundary <= evidence.preflight_ms <= evidence.observed_ms <= now_ms:
        raise OutboxError("RECOVERY_EVIDENCE_OUTSIDE_ATTEMPT_WINDOW")
    if now_ms - evidence.preflight_ms > MAX_RECOVERY_EVIDENCE_AGE_MS:
        raise OutboxError("RECOVERY_PREFLIGHT_STALE")
    if now_ms - evidence.observed_ms > MAX_RECOVERY_EVIDENCE_AGE_MS:
        raise OutboxError("RECOVERY_PUBLIC_READBACK_STALE")
    latest = conn.execute(f"SELECT MAX(revision) FROM {TABLE} WHERE car_id=?",
                          (event["car_id"],)).fetchone()[0]
    if evidence.current_revision != latest:
        raise OutboxError("RECOVERY_CURRENT_REVISION_CHANGED")
    if evidence.outcome == "PUBLISHED" and event["revision"] != latest:
        raise OutboxError("OLD_REVISION_CANNOT_BE_RECOVERED_AS_PUBLISHED")
    final_state = "PUBLISHED" if evidence.outcome == "PUBLISHED" else "RECONCILED"
    conn.execute(f"INSERT INTO {RECOVERY_TABLE} (recovery_key,event_key,claim_nonce,prior_state,"
                 "prior_reason,prior_finished_ms,outcome,final_state,evidence_json,evidence_payload_sha256,"
                 "recorded_ms) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                 (evidence.recovery_key, event_key, nonce, event["state"], event["reason"],
                  event["finished_ms"], evidence.outcome, final_state, payload, payload_hash, now_ms))
    conn.execute(f"UPDATE {TABLE} SET state=?,finished_ms=?,receipt_sha256=? WHERE event_key=?",
                 (final_state, now_ms, evidence.publication_receipt_sha256, event_key))
    return get(conn, event_key)

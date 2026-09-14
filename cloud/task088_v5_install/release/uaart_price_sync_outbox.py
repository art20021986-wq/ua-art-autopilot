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
    install_v5(conn)


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


# FINAL v5: durable operator intentions precede price mutation. The legacy v1
# functions above remain for migration inspection and compatibility tests only.
V5_TABLE = 'uaart_price_operations_v5'
V5_AUDIT = 'uaart_price_audit_v5'
V5_NOTICES = 'uaart_price_notices_v5'
V5_STATES = ('QUEUED', 'CLAIMED', 'DB_COMMITTED', 'SITE_PUBLISHED', 'VERIFIED', 'COMPLETED')
_V5_DDL = f"""CREATE TABLE {V5_TABLE} (
 event_key TEXT PRIMARY KEY NOT NULL,
 car_id INTEGER NOT NULL CHECK(car_id > 0),
 car_code TEXT NOT NULL,
 vin TEXT NOT NULL,
 sequence INTEGER NOT NULL CHECK(sequence > 0),
 field TEXT NOT NULL CHECK(field IN ('price_uah','price_georgia')),
 value TEXT,
 actor_id INTEGER NOT NULL CHECK(actor_id > 0),
 chat_id INTEGER NOT NULL CHECK(chat_id != 0),
 provenance_json TEXT NOT NULL,
 expected_old_json TEXT,
 created_ms INTEGER NOT NULL CHECK(created_ms >= 0),
 state TEXT NOT NULL CHECK(state IN ('QUEUED','CLAIMED','DB_COMMITTED','SITE_PUBLISHED','VERIFIED','COMPLETED')),
 claim_nonce TEXT UNIQUE,
 claimed_ms INTEGER,
 old_value TEXT,
 ukraine_usd TEXT,
 georgia_usd TEXT,
 before_json TEXT,
 after_json TEXT,
 db_committed_ms INTEGER,
 verified_ms INTEGER,
 completed_ms INTEGER,
 receipt_sha256 TEXT,
 attempts INTEGER NOT NULL DEFAULT 0,
 next_attempt_ms INTEGER NOT NULL DEFAULT 0,
 blocked INTEGER NOT NULL DEFAULT 0 CHECK(blocked IN (0,1)),
 last_error TEXT,
 UNIQUE(car_id,sequence),
 CHECK(field='price_georgia' OR value IS NOT NULL),
 CHECK((state='QUEUED' AND claim_nonce IS NULL) OR (state!='QUEUED' AND claim_nonce IS NOT NULL))
)"""
_V5_AUDIT_DDL = f"""CREATE TABLE {V5_AUDIT} (
 audit_id INTEGER PRIMARY KEY,
 event_key TEXT NOT NULL,
 fact TEXT NOT NULL,
 payload_json TEXT NOT NULL,
 created_ms INTEGER NOT NULL,
 UNIQUE(event_key,fact),
 FOREIGN KEY(event_key) REFERENCES {V5_TABLE}(event_key)
)"""
_V5_NOTICE_DDL = f"""CREATE TABLE {V5_NOTICES} (
 notice_key TEXT PRIMARY KEY NOT NULL,
 event_key TEXT NOT NULL,
 chat_id INTEGER NOT NULL CHECK(chat_id != 0),
 kind TEXT NOT NULL CHECK(kind IN ('SUCCESS','FAILURE')),
 body TEXT NOT NULL,
 created_ms INTEGER NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('PENDING','SENDING','SENT','AMBIGUOUS')),
 sent_ms INTEGER,
 message_id INTEGER,
 UNIQUE(event_key,kind),
 FOREIGN KEY(event_key) REFERENCES {V5_TABLE}(event_key)
)"""
_V5_INTENT_FIELDS = ('event_key','car_id','car_code','vin','sequence','field','value',
                     'actor_id','chat_id','provenance_json','expected_old_json','created_ms')
_V5_TRIGGERS = (
    (V5_TABLE + '_immutable_intent',
     f"CREATE TRIGGER {V5_TABLE}_immutable_intent BEFORE UPDATE ON {V5_TABLE} WHEN " +
     ' OR '.join('NEW.' + field + ' IS NOT OLD.' + field for field in _V5_INTENT_FIELDS) +
     " BEGIN SELECT RAISE(ABORT,'V5_INTENT_IMMUTABLE'); END"),
    (V5_TABLE + '_no_delete',
     f"CREATE TRIGGER {V5_TABLE}_no_delete BEFORE DELETE ON {V5_TABLE} "
     "BEGIN SELECT RAISE(ABORT,'V5_OPERATION_HISTORY_PERMANENT'); END"),
    *tuple((V5_AUDIT + '_no_' + action.lower(),
            f"CREATE TRIGGER {V5_AUDIT}_no_{action.lower()} BEFORE {action} ON {V5_AUDIT} "
            "BEGIN SELECT RAISE(ABORT,'V5_AUDIT_APPEND_ONLY'); END")
           for action in ('UPDATE', 'DELETE')),
)


def install_v5(conn):
    """Add only the reviewed queue/audit/notice schema; caller commits explicitly."""
    _transaction(conn)
    for name, ddl in ((V5_TABLE, _V5_DDL), (V5_AUDIT, _V5_AUDIT_DDL), (V5_NOTICES, _V5_NOTICE_DDL)):
        row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
        if row is None:
            conn.execute(ddl)
        elif row[0] != ddl:
            raise OutboxError('V5_INSTALLED_SCHEMA_MISMATCH')
    for name, ddl in _V5_TRIGGERS:
        row = conn.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?", (name,)).fetchone()
        if row is None:
            conn.execute(ddl)
        elif row[0] != ddl:
            raise OutboxError('V5_INSTALLED_TRIGGER_MISMATCH')


def v5_json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':'), allow_nan=False)


def v5_amount(value, *, nullable=False):
    from decimal import Decimal, InvalidOperation
    if value is None and nullable:
        return None
    if type(value) not in (str, int):
        raise OutboxError('V5_EXPLICIT_USD_AMOUNT_REQUIRED')
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise OutboxError('V5_EXPLICIT_USD_AMOUNT_REQUIRED') from exc
    if (not amount.is_finite() or amount <= 0 or amount >= 2**63
            or amount != amount.quantize(Decimal('0.01'))):
        raise OutboxError('V5_POSITIVE_EXACT_USD_REQUIRED')
    return format(amount, '.2f')


def _v5_dict(cursor):
    row = cursor.fetchone()
    if row is None:
        return None
    result = dict(zip((column[0] for column in cursor.description), row))
    result['provenance'] = json.loads(result['provenance_json'])
    return result


def get_operation(conn, event_key):
    _hash(event_key, 'EVENT_KEY')
    return _v5_dict(conn.execute(f'SELECT * FROM {V5_TABLE} WHERE event_key=?', (event_key,)))


def audit_operation(conn, event_key, fact, payload, now_ms):
    """Append an operation-bound fact. Repeated exact facts are read-only no-ops."""
    _transaction(conn)
    _integer(now_ms, 'NOW_MS')
    if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,99}', fact):
        raise OutboxError('V5_SANITIZED_AUDIT_FACT_REQUIRED')
    op = get_operation(conn, event_key)
    if op is None:
        raise OutboxError('V5_OPERATION_MISSING')
    envelope = {'operation_id': event_key, 'car_id': op['car_id'], 'car_code': op['car_code'],
                'vin': op['vin'], 'actor_id': op['actor_id'], 'chat_id': op['chat_id'],
                'market': 'UA' if op['field'] == 'price_uah' else 'GE',
                'field': op['field'], 'requested_value': op['value'], 'fact': fact, 'details': payload}
    encoded = v5_json(envelope)
    old = conn.execute(f'SELECT audit_id,payload_json FROM {V5_AUDIT} WHERE event_key=? AND fact=?',
                       (event_key, fact)).fetchone()
    if old:
        if old[1] != encoded:
            raise OutboxError('V5_AUDIT_FACT_CONFLICT')
        return old[0]
    return conn.execute(f'INSERT INTO {V5_AUDIT}(event_key,fact,payload_json,created_ms) VALUES(?,?,?,?)',
                        (event_key, fact, encoded, now_ms)).lastrowid


def submit(conn, *, event_key, car_id, field, value, actor_id, chat_id, now_ms,
           car_code=None, vin=None, expected_old=None, provenance=None, **unsupported):
    """Persist one conscious intention without changing a price or existing audit.

    Caller owns BEGIN IMMEDIATE, the verified Telegram/ACL provenance, commit and
    a separate connection read-back. Repeating an identical event key is a no-op;
    a distinct event key ALWAYS creates a separate FIFO entry, even for the same
    amount. No old operation is superseded. Provider checks provenance before
    execution; an absent provenance record never authorizes Production.
    """
    if unsupported:
        raise OutboxError('V5_UNKNOWN_SUBMIT_ARGUMENT')
    _transaction(conn)
    _hash(event_key, 'EVENT_KEY')
    for name, number in (('CAR_ID', car_id), ('ACTOR_ID', actor_id), ('NOW_MS', now_ms)):
        _integer(number, name)
    if car_id <= 0 or actor_id <= 0 or type(chat_id) is not int or not -(2**63) < chat_id < 2**63 or chat_id == 0:
        raise OutboxError('V5_AUTHENTICATED_OPERATOR_IDENTITY_REQUIRED')
    if field not in ('price_uah', 'price_georgia'):
        raise OutboxError('V5_SELECTED_MARKET_REQUIRED')
    canonical_value = v5_amount(value, nullable=field == 'price_georgia')
    if expected_old is not None and (type(expected_old) is not tuple or len(expected_old) != 1):
        raise OutboxError('V5_EXPLICIT_CAS_TUPLE_REQUIRED')
    expected_json = None if expected_old is None else v5_json(list(expected_old))
    if provenance is not None and type(provenance) is not dict:
        raise OutboxError('V5_PROVENANCE_OBJECT_REQUIRED')
    provenance_json = v5_json(provenance or {})
    # Obtain a write lock before choosing FIFO position even under BEGIN DEFERRED.
    conn.execute(f'UPDATE {V5_TABLE} SET attempts=attempts WHERE 0')
    cursor = conn.execute('SELECT * FROM cars WHERE id=?', (car_id,))
    row = cursor.fetchone()
    if row is None:
        raise OutboxError('V5_CAR_MISSING')
    row = dict(zip((item[0] for item in cursor.description), row))
    observed_code, observed_vin = str(row.get('auto_number') or ''), str(row.get('vin') or '')
    if row.get('published') != 1 or re.fullmatch(r'UA-[0-9]{4}', observed_code) is None:
        raise OutboxError('V5_PUBLISHED_CAR_REQUIRED')
    if car_code is not None and car_code != observed_code or vin is not None and vin != observed_vin:
        raise OutboxError('V5_CAR_IDENTITY_MISMATCH')
    identity = dict(car_id=car_id, car_code=observed_code, vin=observed_vin, field=field,
                    value=canonical_value, actor_id=actor_id, chat_id=chat_id,
                    provenance_json=provenance_json, expected_old_json=expected_json)
    old = get_operation(conn, event_key)
    if old:
        if any(old[key] != val for key, val in identity.items()):
            raise OutboxError('V5_EVENT_ID_PAYLOAD_CONFLICT')
        return old
    sequence = conn.execute(f'SELECT COALESCE(MAX(sequence),0)+1 FROM {V5_TABLE} WHERE car_id=?', (car_id,)).fetchone()[0]
    columns = list(identity) + ['event_key','sequence','created_ms','state']
    values = list(identity.values()) + [event_key, sequence, now_ms, 'QUEUED']
    conn.execute(f"INSERT INTO {V5_TABLE} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})", values)
    audit_operation(conn, event_key, 'ACCEPTED', {'provenance': provenance or {}, 'sequence': sequence}, now_ms)
    return get_operation(conn, event_key)


def require_head(conn, event_key):
    event = get_operation(conn, event_key)
    if event is None:
        raise OutboxError('V5_OPERATION_MISSING')
    earlier = conn.execute(f"SELECT event_key FROM {V5_TABLE} WHERE car_id=? AND sequence<? AND state!='COMPLETED' LIMIT 1",
                           (event['car_id'], event['sequence'])).fetchone()
    if earlier:
        raise OutboxError('V5_EARLIER_CAR_OPERATION_UNFINISHED')
    return event


def claim_operation(conn, *, event_key, nonce, now_ms):
    """Claim a FIFO head, or resume its original committed claim after restart."""
    _transaction(conn)
    _hash(nonce, 'CLAIM_NONCE')
    _integer(now_ms, 'NOW_MS')
    conn.execute(f'UPDATE {V5_TABLE} SET attempts=attempts WHERE 0')
    event = require_head(conn, event_key)
    if event['state'] == 'COMPLETED':
        return event
    if event['blocked'] or event['next_attempt_ms'] > now_ms:
        raise OutboxError('V5_OPERATION_WAITING_FOR_RECOVERY')
    if event['state'] == 'QUEUED':
        if now_ms < event['created_ms']:
            raise OutboxError('V5_CLAIM_BEFORE_INPUT')
        conn.execute(f"UPDATE {V5_TABLE} SET state='CLAIMED',claim_nonce=?,claimed_ms=? WHERE event_key=?",
                     (nonce, now_ms, event_key))
        audit_operation(conn, event_key, 'CLAIMED', {'claim_nonce': nonce}, now_ms)
    conn.execute(f'UPDATE {V5_TABLE} SET attempts=attempts+1 WHERE event_key=?', (event_key,))
    return get_operation(conn, event_key)


def transition_operation(conn, *, event_key, nonce, expected_state, new_state, now_ms, **values):
    _transaction(conn)
    event = require_head(conn, event_key)
    if event['claim_nonce'] != nonce or event['state'] != expected_state:
        raise OutboxError('V5_CHECKPOINT_CAS_CONFLICT')
    if new_state not in V5_STATES or V5_STATES.index(new_state) != V5_STATES.index(expected_state) + 1:
        raise OutboxError('V5_SEQUENTIAL_CHECKPOINT_REQUIRED')
    allowed = {'old_value','ukraine_usd','georgia_usd','before_json','after_json',
               'db_committed_ms','verified_ms','completed_ms','receipt_sha256'}
    if not set(values) <= allowed:
        raise OutboxError('V5_CHECKPOINT_FIELDS_FORBIDDEN')
    assignment = dict(values, state=new_state, blocked=0, last_error=None, next_attempt_ms=0)
    conn.execute(f"UPDATE {V5_TABLE} SET {','.join(k+'=?' for k in assignment)} WHERE event_key=? AND claim_nonce=? AND state=?",
                 [*assignment.values(), event_key, nonce, expected_state])
    return get_operation(conn, event_key)


def queue_operation_notice(conn, *, event_key, kind, body, now_ms):
    _transaction(conn)
    event = get_operation(conn, event_key)
    if event is None or kind not in ('SUCCESS','FAILURE') or type(body) is not str or not body:
        raise OutboxError('V5_VALID_NOTICE_REQUIRED')
    if kind == 'SUCCESS' and event['state'] != 'COMPLETED':
        raise OutboxError('V5_COMPLETION_RECEIPT_REQUIRES_VERIFIED_COMPLETION')
    key = hashlib.sha256(v5_json((event_key, kind)).encode()).hexdigest()
    existing = conn.execute(f'SELECT chat_id,body FROM {V5_NOTICES} WHERE notice_key=?', (key,)).fetchone()
    if existing:
        if existing != (event['chat_id'], body):
            raise OutboxError('V5_NOTICE_CONTENT_CONFLICT')
        return key
    conn.execute(f"INSERT INTO {V5_NOTICES}(notice_key,event_key,chat_id,kind,body,created_ms,state) VALUES(?,?,?,?,?,?,'PENDING')",
                 (key,event_key,event['chat_id'],kind,body,now_ms))
    return key

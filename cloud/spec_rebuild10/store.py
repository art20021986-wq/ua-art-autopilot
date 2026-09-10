"""Local-only, revision-isolated specification storage and enrichment queue.

This module never opens a network connection, imports the live CRM, renders HTML,
or publishes a vehicle. Python 3.10 and the standard library are sufficient.
"""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import math
import sqlite3
import time
import uuid
from typing import Any


class StoreError(ValueError):
    """A caller supplied invalid data or attempted an unsafe transition."""


class StaleJobError(StoreError):
    """A result no longer owns a live lease for the current vehicle revision."""


# Prices, photos, descriptions and logistics deliberately do not identify a car.
IDENTITY_FIELDS = frozenset({
    "vin", "make", "manufacturer", "brand", "model", "year", "model_year",
    "generation", "market", "origin_market", "engine", "engine_code", "engine_cc",
    "displacement", "displacement_cc", "fuel", "fuel_type", "transmission",
    "gearbox", "drive", "drivetrain", "body", "body_type", "trim", "variant",
    "chassis", "chassis_code", "frame_number",
})
_ZERO_INVALID_KEYS = frozenset({
    "length", "width", "height", "wheelbase", "length_mm", "width_mm", "height_mm",
    "wheelbase_mm", "engine_cc", "displacement", "displacement_cc", "doors", "seats",
    "cylinders", "power", "power_hp", "power_kw", "torque", "torque_nm",
    "curb_weight", "curb_weight_kg", "max_speed", "max_speed_kmh", "fuel_tank_l",
})
_EMPTY_VALUES = frozenset({"", "unknown", "n/a", "null", "none", "неизвестно", "невідомо", "—", "-"})


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _identity(value: dict) -> tuple[dict, str]:
    if not isinstance(value, dict):
        raise StoreError("identity must be an object")
    result = {}
    for key, item in value.items():
        key = str(key).strip().lower()
        if key not in IDENTITY_FIELDS or item is None or item == "":
            continue
        if isinstance(item, str):
            item = " ".join(item.strip().split())
            item = item.upper() if key in {"vin", "frame_number", "chassis_code", "engine_code"} else item.casefold()
        if key in {"year", "model_year", "engine_cc", "displacement_cc"}:
            try:
                parsed = float(item)
                if not math.isfinite(parsed) or not parsed.is_integer():
                    raise ValueError
                item = int(parsed)
            except (ValueError, TypeError, OverflowError):
                raise StoreError("invalid identity number: " + key)
        if isinstance(item, (dict, list, bool)) or not isinstance(item, (str, int, float)):
            raise StoreError("identity values must be scalar: " + key)
        result[key] = item
    if not result:
        raise StoreError("at least one recognized identity field is required")
    return result, _hash(result)


def _fact(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise StoreError("fact must be an object")
    # Preserve caller metadata, including its original verification/provenance.
    fact = json.loads(_json(raw))
    if "key" not in fact and "field_key" in fact:
        fact["key"] = fact["field_key"]
    if "value" not in fact and "field_value" in fact:
        fact["value"] = fact["field_value"]
    if "manual" not in fact and "is_manual" in fact:
        if fact["is_manual"] not in (0, 1, False, True):
            raise StoreError("is_manual must be a boolean or 0/1")
        fact["manual"] = bool(fact["is_manual"])
    if "hidden" not in fact and "is_visible" in fact:
        if fact["is_visible"] not in (0, 1, False, True):
            raise StoreError("is_visible must be a boolean or 0/1")
        fact["hidden"] = not bool(fact["is_visible"])
    if "verification" not in fact and "verification_status" in fact:
        fact["verification"] = fact["verification_status"]
    key = fact.get("key")
    if not isinstance(key, str) or not key.strip() or len(key) > 200:
        raise StoreError("fact requires a nonempty key")
    fact["key"] = key.strip()
    value = fact.get("value")
    if value is None or (isinstance(value, str) and value.strip().casefold() in _EMPTY_VALUES):
        raise StoreError("missing values cannot replace accepted facts")
    if isinstance(value, (dict, list)):
        raise StoreError("fact value must be scalar")
    if fact.get("placeholder") is True:
        raise StoreError("placeholder facts are not publishable")
    zero = value == 0 or (isinstance(value, str) and value.strip() in {"0", "0.0", "0,0"})
    if zero and fact["key"].casefold() in _ZERO_INVALID_KEYS:
        raise StoreError("zero is not valid for this physical specification")
    for flag in ("manual", "hidden"):
        if flag in fact and not isinstance(fact[flag], bool):
            raise StoreError(flag + " must be a boolean")
        fact.setdefault(flag, False)
    return fact


def _value_signature(fact: dict) -> str:
    return _json([fact["value"], fact.get("unit")])


def _verified(fact: dict) -> bool:
    value = fact.get("verification")
    return value is True or value in ("verified", "confirmed", "official", "manual")


def _source_verified(fact: dict, raw: dict, job) -> bool:
    """Accept resolver statuses only with a digest bound to this exact job.

    This verifies integrity/binding, not the authenticity of an external source.
    The trusted collector is responsible for executing the approved policy.
    """
    if "verification_status" not in raw:
        return _verified(fact)
    if raw["verification_status"] not in ("MODEL_VERIFIED", "VEHICLE_VERIFIED"):
        return False
    approval = raw.get("policy_acceptance")
    if not isinstance(approval, dict):
        return False
    expected = {
        "policy_id": "UA-ART-SPEC-REBUILD-10-001:v1", "decision": "ACCEPTED",
        "uid": job["uid"], "revision": job["revision"], "identity_hash": job["identity_hash"],
    }
    if any(approval.get(key) != value for key, value in expected.items()):
        return False
    if isinstance(approval.get("revision"), bool) or not isinstance(approval.get("revision"), int):
        return False
    source_ids = approval.get("source_ids")
    if not isinstance(source_ids, list) or not source_ids or len(source_ids) > 10:
        return False
    if any(not isinstance(item, str) or not item.strip() for item in source_ids) or len(set(source_ids)) != len(source_ids):
        return False
    original = {key: value for key, value in raw.items() if key != "policy_acceptance"}
    return approval.get("evidence_sha256") == _hash(original)


def _merge_same_value(old: dict, incoming: dict) -> dict:
    merged = dict(old)
    evidence = list(old.get("evidence", []))
    if incoming not in evidence and incoming != old:
        evidence.append(incoming)
    if evidence:
        merged["evidence"] = evidence
    # An automatic refresh is never allowed to clear owner flags or overwrite
    # the original verification/source. Additional evidence remains separately.
    return merged


class SpecStore:
    def __init__(self, path: str, max_attempts: int = 3):
        if isinstance(max_attempts, bool) or not 1 <= max_attempts <= 10:
            raise StoreError("max_attempts must be between 1 and 10")
        self.max_attempts = max_attempts
        self.db = sqlite3.connect(str(path), timeout=5, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        existing_tables = {
            row[0] for row in self.db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        store_tables = {"vehicles", "jobs", "facts", "candidates", "import_receipts", "publication_snapshots"}
        if existing_tables and not (store_tables <= existing_tables <= store_tables | {"refresh_requests", "lifecycle_receipts"}):
            self.db.close()
            raise StoreError("refusing to initialize a specification store inside an unrelated database")
        self.db.execute("PRAGMA foreign_keys=ON")
        # PythonAnywhere storage may be shared/NFS-backed: do not assume the
        # shared-memory locking semantics required by SQLite WAL are available.
        self.db.execute("PRAGMA journal_mode=DELETE")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
        BEGIN IMMEDIATE;
        CREATE TABLE IF NOT EXISTS vehicles (
            uid TEXT PRIMARY KEY, revision INTEGER NOT NULL, identity_json TEXT NOT NULL,
            identity_hash TEXT NOT NULL, published INTEGER NOT NULL DEFAULT 0,
            tombstoned INTEGER NOT NULL DEFAULT 0, updated_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY, uid TEXT NOT NULL REFERENCES vehicles(uid),
            revision INTEGER NOT NULL, identity_hash TEXT NOT NULL, state TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL,
            next_attempt REAL NOT NULL, lease_token TEXT, lease_until REAL, worker_id TEXT,
            error TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL,
            UNIQUE(uid, revision)
        );
        CREATE INDEX IF NOT EXISTS jobs_ready ON jobs(state, next_attempt);
        CREATE TABLE IF NOT EXISTS facts (
            uid TEXT NOT NULL REFERENCES vehicles(uid), revision INTEGER NOT NULL,
            key TEXT NOT NULL, payload TEXT NOT NULL, updated_at REAL NOT NULL,
            PRIMARY KEY(uid, revision, key)
        );
        CREATE TABLE IF NOT EXISTS candidates (
            id TEXT PRIMARY KEY, job_id TEXT NOT NULL, uid TEXT NOT NULL,
            revision INTEGER NOT NULL, key TEXT, payload TEXT NOT NULL,
            decision TEXT NOT NULL, reason TEXT NOT NULL, created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS import_receipts (
            uid TEXT NOT NULL, revision INTEGER NOT NULL, receipt_id TEXT NOT NULL,
            payload_hash TEXT NOT NULL, result_json TEXT NOT NULL, created_at REAL NOT NULL,
            PRIMARY KEY(uid, receipt_id)
        );
        CREATE TABLE IF NOT EXISTS publication_snapshots (
            id TEXT PRIMARY KEY, uid TEXT NOT NULL, revision INTEGER NOT NULL,
            identity_hash TEXT NOT NULL, facts_digest TEXT NOT NULL, facts_json TEXT NOT NULL,
            receipt_id TEXT NOT NULL, receipt_json TEXT NOT NULL, created_at REAL NOT NULL,
            UNIQUE(uid, receipt_id)
        );
        CREATE TABLE IF NOT EXISTS refresh_requests (
            uid TEXT NOT NULL, revision INTEGER NOT NULL, request_id TEXT NOT NULL,
            reason TEXT NOT NULL, result_json TEXT NOT NULL, previous_job_json TEXT NOT NULL,
            created_at REAL NOT NULL, PRIMARY KEY(uid, request_id)
        );
        CREATE TABLE IF NOT EXISTS lifecycle_receipts (
            uid TEXT NOT NULL, receipt_id TEXT NOT NULL, revision INTEGER NOT NULL,
            action TEXT NOT NULL, receipt_json TEXT NOT NULL, created_at REAL NOT NULL,
            PRIMARY KEY(uid, receipt_id)
        );
        COMMIT;
        """)

    def close(self) -> None:
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    @contextmanager
    def _tx(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        else:
            self.db.execute("COMMIT")

    @staticmethod
    def _now(value=None) -> float:
        result = time.time() if value is None else float(value)
        if not math.isfinite(result):
            raise StoreError("invalid timestamp")
        return result

    def _vehicle(self, uid: str, allow_deleted=False):
        row = self.db.execute("SELECT * FROM vehicles WHERE uid=?", (uid,)).fetchone()
        if row is None or (row["tombstoned"] and not allow_deleted):
            raise StoreError("unknown or deleted vehicle")
        return row

    def get_vehicle(self, uid: str) -> dict:
        row = dict(self._vehicle(uid, allow_deleted=True))
        row["identity"] = json.loads(row.pop("identity_json"))
        row["published"] = bool(row["published"])
        row["tombstoned"] = bool(row["tombstoned"])
        return row

    def upsert_vehicle(self, uid: str, identity: dict, published: bool = False) -> dict:
        if not isinstance(uid, str) or not uid.strip() or len(uid) > 128:
            raise StoreError("uid must be a nonempty stable identifier")
        if not isinstance(published, bool):
            raise StoreError("published must be boolean")
        normalized, identity_hash = _identity(identity)
        now = self._now()
        with self._tx():
            existing = self.db.execute("SELECT * FROM vehicles WHERE uid=?", (uid,)).fetchone()
            if existing is not None and existing["tombstoned"]:
                raise StoreError("a deleted uid cannot be implicitly reused")
            changed = existing is None or existing["identity_hash"] != identity_hash
            revision = 1 if existing is None else existing["revision"] + int(changed)
            self.db.execute("""INSERT INTO vehicles VALUES(?,?,?,?,?,0,?)
                ON CONFLICT(uid) DO UPDATE SET revision=excluded.revision,
                identity_json=excluded.identity_json, identity_hash=excluded.identity_hash,
                published=excluded.published, updated_at=excluded.updated_at""",
                (uid, revision, _json(normalized), identity_hash, int(published), now))
            if changed:
                self.db.execute("""UPDATE jobs SET state='cancelled', lease_token=NULL,
                    lease_until=NULL, updated_at=? WHERE uid=? AND state IN ('ready','retry','leased')""", (now, uid))
                self.db.execute("""INSERT INTO jobs(id,uid,revision,identity_hash,state,
                    max_attempts,next_attempt,created_at,updated_at) VALUES(?,?,?,?,'ready',?,?,?,?)""",
                    (uuid.uuid4().hex, uid, revision, identity_hash, self.max_attempts, now, now, now))
        return {"uid": uid, "revision": revision, "identity_hash": identity_hash, "queued": changed}

    def claim_job(self, worker_id: str, lease_seconds: float = 60, now=None) -> dict | None:
        now = self._now(now)
        if not isinstance(worker_id, str) or not worker_id.strip():
            raise StoreError("worker_id is required")
        if not 1 <= lease_seconds <= 900:
            raise StoreError("lease_seconds must be between 1 and 900")
        with self._tx():
            # Expired leases are recovered from durable state after a crash; a
            # previous worker's token becomes invalid even if it later returns.
            self.db.execute("""UPDATE jobs SET state=CASE WHEN attempts>=max_attempts
                THEN 'exhausted' ELSE 'retry' END, lease_token=NULL, lease_until=NULL,
                next_attempt=?, error='LEASE_EXPIRED', updated_at=?
                WHERE state='leased' AND lease_until<=?""", (now, now, now))
            job = self.db.execute("""SELECT j.* FROM jobs j JOIN vehicles v ON v.uid=j.uid
                WHERE j.state IN ('ready','retry') AND j.next_attempt<=? AND j.attempts<j.max_attempts
                AND v.tombstoned=0 AND v.revision=j.revision AND v.identity_hash=j.identity_hash
                ORDER BY j.next_attempt,j.created_at,j.id LIMIT 1""", (now,)).fetchone()
            if job is None:
                return None
            token = uuid.uuid4().hex
            self.db.execute("""UPDATE jobs SET state='leased', attempts=attempts+1,
                lease_token=?, lease_until=?, worker_id=?, updated_at=? WHERE id=?""",
                (token, now + lease_seconds, worker_id, now, job["id"]))
            result = dict(self.db.execute("SELECT * FROM jobs WHERE id=?", (job["id"],)).fetchone())
            result["job_id"] = result["id"]
            result["identity"] = json.loads(self._vehicle(job["uid"])["identity_json"])
            return result

    def _live_job(self, job_id: str, lease_token: str, now: float):
        job = self.db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if job is None or job["state"] != "leased" or not lease_token or job["lease_token"] != lease_token or job["lease_until"] <= now:
            raise StaleJobError("result does not own a live lease")
        vehicle = self._vehicle(job["uid"], allow_deleted=True)
        if vehicle["tombstoned"] or vehicle["revision"] != job["revision"] or vehicle["identity_hash"] != job["identity_hash"]:
            raise StaleJobError("vehicle identity changed or was deleted")
        return job

    def fail_job(self, job_id: str, lease_token: str, error: str, retry_after: float = 30, now=None) -> dict:
        now = self._now(now)
        if not 0 <= retry_after <= 86400:
            raise StoreError("retry_after must be between 0 and 86400")
        with self._tx():
            job = self._live_job(job_id, lease_token, now)
            state = "exhausted" if job["attempts"] >= job["max_attempts"] else "retry"
            self.db.execute("""UPDATE jobs SET state=?, next_attempt=?, lease_token=NULL,
                lease_until=NULL,error=?,updated_at=? WHERE id=?""",
                (state, now + retry_after, str(error)[:1000], now, job_id))
        return {"job_id": job_id, "state": state}

    def request_refresh(self, uid: str, reason: str, request_id: str) -> dict:
        """Explicitly rearm completed work once per approved operator request.

        Do not call from ordinary save hooks or an unbounded automatic retry.
        Caller authorization and source-access approval remain external.
        """
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 1000:
            raise StoreError("refresh requires a nonempty bounded reason")
        if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 200:
            raise StoreError("refresh requires a stable bounded request_id")
        now = self._now()
        with self._tx():
            vehicle = self._vehicle(uid)
            previous = self.db.execute("SELECT * FROM refresh_requests WHERE uid=? AND request_id=?", (uid, request_id)).fetchone()
            if previous:
                if previous["reason"] != reason or previous["revision"] != vehicle["revision"]:
                    raise StoreError("refresh request id cannot be reused for changed reason or identity")
                result = json.loads(previous["result_json"])
                result["idempotent"] = True
                return result
            job = self.db.execute("SELECT * FROM jobs WHERE uid=? AND revision=?", (uid, vehicle["revision"])).fetchone()
            if job is None or job["state"] not in ("succeeded", "exhausted"):
                raise StoreError("refresh requires completed or exhausted work; active work is not replaced")
            self.db.execute("""UPDATE jobs SET state='ready', attempts=0, next_attempt=?,
                lease_token=NULL, lease_until=NULL, worker_id=NULL, error=NULL,updated_at=? WHERE id=?""", (now, now, job["id"]))
            result = {"uid": uid, "revision": vehicle["revision"], "job_id": job["id"], "queued": True, "idempotent": False}
            self.db.execute("INSERT INTO refresh_requests VALUES(?,?,?,?,?,?,?)", (
                uid, vehicle["revision"], request_id, reason, _json(result), _json(dict(job)), now))
            return result

    def _get_fact(self, uid, revision, key):
        row = self.db.execute("SELECT payload FROM facts WHERE uid=? AND revision=? AND key=?", (uid, revision, key)).fetchone()
        return json.loads(row[0]) if row else None

    def _save_fact(self, uid, revision, fact, now):
        self.db.execute("""INSERT INTO facts VALUES(?,?,?,?,?) ON CONFLICT(uid,revision,key)
            DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at""",
            (uid, revision, fact["key"], _json(fact), now))

    def approve_candidates(self, job_id: str, lease_token: str, facts: list[dict], now=None,
                           *, retry_error: str | None = None, retry_after: float = 30) -> dict:
        """Finish a leased collection and merge only nonconflicting verified facts.

        The name denotes factual acceptance, never permission to publish a car.
        Conflicts and unverified candidates are persisted for owner review.
        A partial collection can atomically retain accepted facts and retry the
        same job. Attempts are never reset, even when some sources succeed.
        """
        if not isinstance(facts, list):
            raise StoreError("facts must be a list")
        if retry_error is not None and (not isinstance(retry_error, str)
                or not retry_error.strip() or len(retry_error) > 1000):
            raise StoreError("retry_error must be a nonempty bounded code")
        if isinstance(retry_after, bool) or not isinstance(retry_after, (int, float)) or not 0 <= retry_after <= 86400:
            raise StoreError("retry_after must be between 0 and 86400")
        now = self._now(now)
        result = {"job_id": job_id, "accepted": 0, "review": 0, "rejected": 0}
        normalized = []
        for raw in facts:
            try:
                normalized.append((_fact(raw), None))
            except (StoreError, TypeError, ValueError) as exc:
                normalized.append((raw, str(exc)))
        signatures = {}
        for fact, error in normalized:
            if error is None:
                signatures.setdefault(fact["key"], set()).add(_value_signature(fact))
        with self._tx():
            job = self._live_job(job_id, lease_token, now)
            for raw, (fact, error) in zip(facts, normalized):
                decision, reason = "accepted", "verified_nonconflicting"
                key = fact.get("key") if isinstance(fact, dict) else None
                if key is not None and not isinstance(key, str):
                    key = str(key)[:200]
                existing = self._get_fact(job["uid"], job["revision"], key) if key else None
                if error:
                    decision, reason = "rejected", error
                elif fact.get("identity_hash", job["identity_hash"]) != job["identity_hash"]:
                    decision, reason = "rejected", "identity_mismatch"
                elif fact["manual"]:
                    decision, reason = "review", "automatic_worker_cannot_assert_manual_override"
                elif fact["hidden"] and not (existing and existing["hidden"]):
                    decision, reason = "review", "automatic_worker_cannot_hide_owner_data"
                elif len(signatures[key]) > 1:
                    decision, reason = "review", "sources_disagree"
                elif existing and _value_signature(existing) != _value_signature(fact):
                    decision, reason = "review", "manual_override_conflict" if existing["manual"] else "accepted_value_conflict"
                elif not _source_verified(fact, raw, job):
                    decision, reason = "review", "verification_required"
                elif not isinstance(fact.get("source_url"), str) or not fact["source_url"].startswith(("https://", "http://")):
                    decision, reason = "review", "source_url_required"
                if decision == "accepted":
                    if fact.get("verification_status") in ("MODEL_VERIFIED", "VEHICLE_VERIFIED"):
                        # Retain precise source status and its binding while
                        # normalizing the internal accepted-value indicator.
                        fact["verification"] = "verified"
                    self._save_fact(job["uid"], job["revision"], _merge_same_value(existing, fact) if existing else fact, now)
                # Invalid input remains inspectable without invalid JSON breaking
                # the whole batch. It is never copied into accepted facts.
                try:
                    payload = _json(fact)
                except (TypeError, ValueError):
                    payload = _json({"invalid_payload": repr(fact)[:1000]})
                self.db.execute("INSERT INTO candidates VALUES(?,?,?,?,?,?,?,?,?)", (
                    uuid.uuid4().hex, job_id, job["uid"], job["revision"], key, payload, decision, reason, now))
                result[decision] += 1
            state = "succeeded" if retry_error is None else (
                "exhausted" if job["attempts"] >= job["max_attempts"] else "retry")
            self.db.execute("""UPDATE jobs SET state=?, next_attempt=?, lease_token=NULL,
                lease_until=NULL,error=?,updated_at=? WHERE id=?""",
                (state, now + retry_after if retry_error is not None else now,
                 retry_error, now, job_id))
            result["state"] = state
        return result

    def import_legacy(self, uid: str, facts: list[dict], receipt_id: str) -> dict:
        if not receipt_id or not isinstance(receipt_id, str) or not isinstance(facts, list):
            raise StoreError("a receipt_id and fact list are required")
        payload_hash = _hash(facts)
        now = self._now()
        with self._tx():
            vehicle = self._vehicle(uid)
            old_receipt = self.db.execute("SELECT * FROM import_receipts WHERE uid=? AND receipt_id=?", (uid, receipt_id)).fetchone()
            if old_receipt:
                if old_receipt["payload_hash"] != payload_hash or old_receipt["revision"] != vehicle["revision"]:
                    raise StoreError("legacy receipt cannot be reused for different data or identity")
                result = json.loads(old_receipt["result_json"])
                result["idempotent"] = True
                return result
            result = {"uid": uid, "revision": vehicle["revision"], "imported": 0, "review": 0, "rejected": 0, "idempotent": False}
            for raw in facts:
                try:
                    fact = _fact(raw)
                except (StoreError, ValueError, TypeError) as exc:
                    result["rejected"] += 1
                    self.db.execute("INSERT INTO candidates VALUES(?,?,?,?,?,?,?,?,?)", (
                        uuid.uuid4().hex, "legacy:" + receipt_id, uid, vehicle["revision"],
                        str(raw.get("key", raw.get("field_key", "")))[:200] if isinstance(raw, dict) else None,
                        _json(raw), "rejected", str(exc), now))
                    continue
                existing = self._get_fact(uid, vehicle["revision"], fact["key"])
                fact["legacy_import"] = {"receipt_id": receipt_id, "fresh_verification": False}
                if existing and _value_signature(existing) != _value_signature(fact):
                    result["review"] += 1
                    self.db.execute("INSERT INTO candidates VALUES(?,?,?,?,?,?,?,?,?)", (
                        uuid.uuid4().hex, "legacy:" + receipt_id, uid, vehicle["revision"], fact["key"],
                        _json(fact), "review", "legacy_value_conflict", now))
                    continue
                merged = _merge_same_value(existing, fact) if existing else fact
                if existing:
                    merged["manual"] = existing["manual"] or fact["manual"]
                    merged["hidden"] = existing["hidden"] or fact["hidden"]
                self._save_fact(uid, vehicle["revision"], merged, now)
                result["imported"] += 1
            self.db.execute("INSERT INTO import_receipts VALUES(?,?,?,?,?,?)", (
                uid, vehicle["revision"], receipt_id, payload_hash, _json(result), now))
            return result

    def get_facts(self, uid: str, include_hidden: bool = False) -> list[dict]:
        vehicle = self._vehicle(uid)
        rows = self.db.execute("SELECT payload FROM facts WHERE uid=? AND revision=? ORDER BY key", (uid, vehicle["revision"])).fetchall()
        values = [json.loads(row[0]) for row in rows]
        return values if include_hidden else [fact for fact in values if not fact["hidden"]]

    def set_manual_fact(self, uid: str, fact: dict) -> dict:
        explicit_hidden = "hidden" in fact or "is_visible" in fact
        fact = _fact(fact)
        fact["manual"] = True
        fact["verification"] = "manual"
        with self._tx():
            vehicle = self._vehicle(uid)
            old = self._get_fact(uid, vehicle["revision"], fact["key"])
            # Preserve hidden status unless the owner explicitly supplies it.
            if old and not explicit_hidden:
                fact["hidden"] = old["hidden"]
            self._save_fact(uid, vehicle["revision"], fact, self._now())
        return fact

    def set_hidden(self, uid: str, key: str, hidden: bool) -> dict:
        if not isinstance(hidden, bool):
            raise StoreError("hidden must be boolean")
        with self._tx():
            vehicle = self._vehicle(uid)
            fact = self._get_fact(uid, vehicle["revision"], key)
            if fact is None:
                raise StoreError("unknown fact")
            fact["hidden"] = hidden
            self._save_fact(uid, vehicle["revision"], fact, self._now())
        return fact

    def set_published(self, uid: str, published: bool) -> None:
        """Record observed CRM inventory status; performs no site publication."""
        if not isinstance(published, bool):
            raise StoreError("published must be boolean")
        with self._tx():
            self._vehicle(uid)
            self.db.execute("UPDATE vehicles SET published=?, updated_at=? WHERE uid=?", (int(published), self._now(), uid))

    def delete_vehicle(self, uid: str) -> None:
        with self._tx():
            self._vehicle(uid, allow_deleted=True)
            now = self._now()
            self.db.execute("UPDATE vehicles SET tombstoned=1,published=0,updated_at=? WHERE uid=?", (now, uid))
            self.db.execute("""UPDATE jobs SET state='cancelled',lease_token=NULL,
                lease_until=NULL,updated_at=? WHERE uid=? AND state IN ('ready','retry','leased')""", (now, uid))

    def get_jobs(self, uid: str | None = None) -> list[dict]:
        rows = self.db.execute("SELECT * FROM jobs ORDER BY created_at,id" if uid is None else "SELECT * FROM jobs WHERE uid=? ORDER BY created_at,id", () if uid is None else (uid,))
        return [dict(row) for row in rows]

    def get_candidates(self, uid: str) -> list[dict]:
        vehicle = self._vehicle(uid)
        rows = self.db.execute("SELECT * FROM candidates WHERE uid=? AND revision=? ORDER BY created_at,id", (uid, vehicle["revision"]))
        result = []
        for row in rows:
            item = dict(row)
            item["fact"] = json.loads(item.pop("payload"))
            result.append(item)
        return result

    def facts_digest(self, uid: str) -> str:
        """Digest the exact visible payload a renderer/readback must attest."""
        return _hash(self.get_facts(uid))

    def mark_publication_verified(self, uid: str, revision: int, receipt: dict) -> dict:
        """Record an external route's explicit readback, never publish implicitly.

        The caller must already have validated the route receipt's authenticity.
        A database row is not itself an external-writer or deployment proof.
        """
        if not isinstance(receipt, dict):
            raise StoreError("an explicit publication receipt is required")
        with self._tx():
            vehicle = self._vehicle(uid)
            if isinstance(revision, bool) or revision != vehicle["revision"]:
                raise StoreError("publication receipt is not for the current vehicle revision")
            facts = self.get_facts(uid)
            digest = _hash(facts)
            required = {
                "uid": uid, "revision": revision, "identity_hash": vehicle["identity_hash"],
                "facts_digest": digest, "status": "PASS", "specification_visible": True,
                "single_vin": True, "shell_preserved": True,
            }
            if any(receipt.get(key) != value for key, value in required.items()):
                raise StoreError("receipt must bind exact visible facts, identity and shell checks")
            if any(receipt.get(key) is not True for key in ("specification_visible", "single_vin", "shell_preserved")):
                raise StoreError("receipt checks must be explicit booleans")
            for key in ("receipt_id", "route_id", "verified_at", "page_url"):
                if not isinstance(receipt.get(key), str) or not receipt[key].strip():
                    raise StoreError("receipt is missing " + key)
            if not receipt["page_url"].startswith("https://"):
                raise StoreError("receipt must contain the actual HTTPS page URL")
            existing = self.db.execute("SELECT * FROM publication_snapshots WHERE uid=? AND receipt_id=?", (uid, receipt["receipt_id"])).fetchone()
            if existing:
                if existing["receipt_json"] != _json(receipt):
                    raise StoreError("publication receipt id cannot be reused with different content")
                if not vehicle["published"]:
                    raise StoreError("an old publication receipt cannot reverse an unpublish")
                return self._snapshot(existing)
            sid = uuid.uuid4().hex
            self.db.execute("INSERT INTO publication_snapshots VALUES(?,?,?,?,?,?,?,?,?)", (
                sid, uid, revision, vehicle["identity_hash"], digest, _json(facts), receipt["receipt_id"], _json(receipt), self._now()))
            self.db.execute("UPDATE vehicles SET published=1,updated_at=? WHERE uid=?", (self._now(), uid))
            return self._snapshot(self.db.execute("SELECT * FROM publication_snapshots WHERE id=?", (sid,)).fetchone())

    @staticmethod
    def _snapshot(row) -> dict:
        result = dict(row)
        result["facts"] = json.loads(result.pop("facts_json"))
        result["receipt"] = json.loads(result.pop("receipt_json"))
        return result

    def get_publication_snapshot(self, uid: str) -> dict | None:
        vehicle = self._vehicle(uid)
        row = self.db.execute("""SELECT * FROM publication_snapshots WHERE uid=? AND
            revision=? AND identity_hash=? ORDER BY created_at DESC,rowid DESC LIMIT 1""",
            (uid, vehicle["revision"], vehicle["identity_hash"])).fetchone()
        return self._snapshot(row) if row else None

    def mark_lifecycle_verified(self, uid: str, action: str, revision: int,
                                identity_hash: str, facts_digest: str, receipt: dict) -> dict:
        """Atomically record an authenticated hide/sold/delete readback.

        The caller must authenticate the actual external receipt and bind its
        plan_id to the owner ticket. Current identity and facts are rechecked
        inside the write transaction, after that potentially slow readback.
        """
        if action not in ("hide", "sold", "delete") or not isinstance(receipt, dict):
            raise StoreError("a supported action and explicit lifecycle receipt are required")
        if isinstance(revision, bool) or not isinstance(revision, int):
            raise StoreError("lifecycle revision must be an integer")
        expected = {"uid": uid, "action": action, "revision": revision,
                    "identity_hash": identity_hash, "facts_digest": facts_digest, "status": "PASS"}
        if any(receipt.get(key) != value for key, value in expected.items()):
            raise StoreError("lifecycle receipt is not bound to the exact operation")
        for key in ("receipt_id", "route_id", "verified_at", "plan_id"):
            if not isinstance(receipt.get(key), str) or not receipt[key].strip():
                raise StoreError("lifecycle receipt is missing " + key)
        now = self._now()
        with self._tx():
            vehicle = self._vehicle(uid, allow_deleted=True)
            if vehicle["revision"] != revision or vehicle["identity_hash"] != identity_hash:
                raise StoreError("lifecycle identity changed during readback")
            rows = self.db.execute("SELECT payload FROM facts WHERE uid=? AND revision=? ORDER BY key", (uid, revision)).fetchall()
            facts = [json.loads(row[0]) for row in rows]
            facts = [fact for fact in facts if not fact["hidden"]]
            if _hash(facts) != facts_digest:
                raise StoreError("lifecycle facts changed during readback")
            previous = self.db.execute("SELECT * FROM lifecycle_receipts WHERE uid=? AND receipt_id=?", (uid, receipt["receipt_id"])).fetchone()
            if previous:
                if previous["receipt_json"] != _json(receipt):
                    raise StoreError("lifecycle receipt id cannot be reused with different content")
                still_applied = bool(vehicle["tombstoned"]) if action == "delete" else not vehicle["published"] and not vehicle["tombstoned"]
                if not still_applied:
                    raise StoreError("an old lifecycle receipt cannot reverse a newer operation")
                return {"uid": uid, "revision": revision, "action": action, "status": "VERIFIED", "idempotent": True}
            if vehicle["tombstoned"]:
                raise StoreError("a new lifecycle operation cannot target a deleted vehicle")
            if action == "delete":
                self.db.execute("UPDATE vehicles SET tombstoned=1,published=0,updated_at=? WHERE uid=?", (now, uid))
                self.db.execute("""UPDATE jobs SET state='cancelled',lease_token=NULL,
                    lease_until=NULL,updated_at=? WHERE uid=? AND state IN ('ready','retry','leased')""", (now, uid))
            else:
                self.db.execute("UPDATE vehicles SET published=0,updated_at=? WHERE uid=?", (now, uid))
            self.db.execute("INSERT INTO lifecycle_receipts VALUES(?,?,?,?,?,?)", (
                uid, receipt["receipt_id"], revision, action, _json(receipt), now))
            return {"uid": uid, "revision": revision, "action": action, "status": "VERIFIED", "idempotent": False}

#!/usr/bin/env python3
"""Durable, bounded post-publication enrichment; never writes CRM or HTML.

Integration supplies read_card, commit_guard and additive commit callbacks.
The guard MUST serialize with CRM VIN/status changes and publication writers.
Collector is a pure read-only ``module:function`` executed in a child process;
it must use request_timeout for each network request, and must not write files,
facts or publication state. Child results are applied only by the parent after
checking both current CRM identity and the durable lease/generation again.
"""
from __future__ import annotations

import contextlib
import concurrent.futures
import importlib
import json
import os
import pathlib
import re
import selectors
import sqlite3
import subprocess
import sys
import threading
import time
import uuid

APPROVED_SOURCES = {
    "kia_korea": "Kia Korea",
    "hyundai_korea": "Hyundai Korea",
    "mercedes_archive": "Mercedes-Benz Public Archive",
    "audi_mediacenter": "Audi MediaCenter",
    "danawa": "Danawa Auto",
    "carisyou": "Carisyou",
    "auto_data": "Auto-Data.net",
    "cars_data": "Cars-Data.com",
    "ultimatespecs": "UltimateSpecs",
    "nhtsa_vpic": "NHTSA vPIC",
}
DOMAIN_TO_SOURCE = {
    "auto.danawa.com": "danawa", "carisyou.com": "carisyou",
    "auto-data.net": "auto_data", "cars-data.com": "cars_data",
    "ultimatespecs.com": "ultimatespecs", "vpic.nhtsa.dot.gov": "nhtsa_vpic",
}
SLOTS = (0, 600, 1200, 1800)
PROTOCOL = b"SPEC84 "
MAX_MESSAGE_BYTES = 2 * 1024 * 1024


def identity(card):
    if not card:
        return None
    published = card.get("published")
    if isinstance(published, str):
        published = published.strip().casefold() in {"1", "true", "yes", "да", "так", "published"}
    if not published:
        return None
    uid = str(card.get("car_uid") or "")
    vin = str(card.get("vin") or "").strip().upper()
    # Legacy service already normalizes chassis numbers as well as full VINs.
    if not re.fullmatch(r"UA-\d{4,6}", uid) or not re.fullmatch(r"[A-Z0-9-]{5,30}", vin):
        return None
    return uid, vin


class Queue:
    """Only this dedicated DB is writable; no main CRM connection exists here."""
    def __init__(self, path):
        self.path = pathlib.Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS spec84_generations(
                    uid TEXT PRIMARY KEY, vin TEXT NOT NULL, generation INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS spec84_cycles(
                    id INTEGER PRIMARY KEY, uid TEXT NOT NULL, vin TEXT NOT NULL,
                    generation INTEGER NOT NULL, started_at REAL NOT NULL, reason TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'ACTIVE', UNIQUE(uid,generation));
                CREATE TABLE IF NOT EXISTS spec84_slots(
                    cycle_id INTEGER NOT NULL REFERENCES spec84_cycles(id), slot INTEGER NOT NULL,
                    due_at REAL NOT NULL, state TEXT NOT NULL DEFAULT 'PENDING',
                    first_started_at REAL, last_started_at REAL, finished_at REAL,
                    runs INTEGER NOT NULL DEFAULT 0, lease_until REAL, token TEXT,
                    result_json TEXT, PRIMARY KEY(cycle_id,slot), CHECK(slot BETWEEN 0 AND 3));
                CREATE TABLE IF NOT EXISTS spec84_sources(
                    cycle_id INTEGER NOT NULL, slot INTEGER NOT NULL, source_id TEXT NOT NULL,
                    outcome_json TEXT NOT NULL, PRIMARY KEY(cycle_id,slot,source_id),
                    FOREIGN KEY(cycle_id,slot) REFERENCES spec84_slots(cycle_id,slot));
                CREATE INDEX IF NOT EXISTS spec84_due ON spec84_slots(state,due_at);
            """)
        os.chmod(self.path, 0o600)

    @contextlib.contextmanager
    def connect(self):
        db = sqlite3.connect(str(self.path), timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA synchronous=FULL")
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def ensure_cycle(self, card, *, reason="publish", now=None):
        """Call after successful publish; recovery scans pass published CRM rows.

        A repeated event cannot reset due times, slot numbers or finished work.
        A VIN change always creates a new generation, including A -> B -> A.
        """
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            return self.ensure_cycle_transaction(db, card, reason=reason, now=now)

    def ensure_cycle_transaction(self, db, card, *, reason="publish", now=None, schema=""):
        """Caller may atomically seed a cycle with facts in an attached DB."""
        if not db.in_transaction or schema not in ("", "schedule."):
            raise ValueError("CALLER_TRANSACTION_AND_FIXED_SCHEMA_REQUIRED")
        ident = identity(card)
        if ident is None:
            return None
        uid, vin = ident
        now = time.time() if now is None else now
        generations, cycles, slots = (schema + name for name in
                                       ("spec84_generations", "spec84_cycles", "spec84_slots"))
        old = db.execute(f"SELECT * FROM {generations} WHERE uid=?", (uid,)).fetchone()
        generation = int(old["generation"]) if old else 1
        if old and old["vin"] != vin:
            generation += 1
            db.execute(f"UPDATE {cycles} SET state='SUPERSEDED' WHERE uid=?", (uid,))
            db.execute(f"""UPDATE {slots} SET state='STALE',token=NULL,lease_until=NULL
                WHERE cycle_id IN (SELECT id FROM {cycles} WHERE uid=?)
                AND state IN ('PENDING','RUNNING','PAUSED')""", (uid,))
        db.execute(f"""INSERT INTO {generations} VALUES(?,?,?)
            ON CONFLICT(uid) DO UPDATE SET vin=excluded.vin,generation=excluded.generation""",
            (uid, vin, generation))
        db.execute(f"""INSERT OR IGNORE INTO {cycles}(uid,vin,generation,started_at,reason)
            VALUES(?,?,?,?,?)""", (uid, vin, generation, now, reason))
        row = db.execute(f"SELECT * FROM {cycles} WHERE uid=? AND generation=?", (uid, generation)).fetchone()
        for slot, offset in enumerate(SLOTS):
            db.execute(f"INSERT OR IGNORE INTO {slots}(cycle_id,slot,due_at) VALUES(?,?,?)",
                       (row["id"], slot, row["started_at"] + offset))
        if row["state"] == "PAUSED":
            db.execute(f"UPDATE {cycles} SET state='ACTIVE' WHERE id=?", (row["id"],))
            db.execute(f"UPDATE {slots} SET state='PENDING' WHERE cycle_id=? AND state='PAUSED'", (row["id"],))
        return dict(db.execute(f"SELECT * FROM {cycles} WHERE id=?", (row["id"],)).fetchone())

    def claim(self, *, now=None, lease_seconds=90):
        now = time.time() if now is None else now
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            # Reclaim same logical slot, preserving original due/start times and run audit.
            db.execute("""UPDATE spec84_slots SET state='PENDING',token=NULL,lease_until=NULL
                WHERE state='RUNNING' AND lease_until<=?""", (now,))
            row = db.execute("""SELECT s.*,c.uid,c.vin,c.generation,c.started_at
                FROM spec84_slots s JOIN spec84_cycles c ON c.id=s.cycle_id
                WHERE s.state='PENDING' AND s.due_at<=? AND c.state='ACTIVE'
                AND NOT EXISTS (SELECT 1 FROM spec84_slots older
                    WHERE older.cycle_id=s.cycle_id AND
                    (older.state='RUNNING' OR (older.slot<s.slot AND older.state IN ('PENDING','PAUSED'))))
                ORDER BY s.due_at,c.id,s.slot LIMIT 1""", (now,)).fetchone()
            if row is None:
                return None
            token = uuid.uuid4().hex
            db.execute("""UPDATE spec84_slots SET state='RUNNING',token=?,lease_until=?,
                first_started_at=COALESCE(first_started_at,?),last_started_at=?,runs=runs+1
                WHERE cycle_id=? AND slot=?""",
                (token, now + lease_seconds, now, now, row["cycle_id"], row["slot"]))
            result = dict(row)
            result.update(token=token, lease_until=now + lease_seconds,
                          last_started_at=now, delay_seconds=max(0, now - row["due_at"]))
            return result

    def lease_valid(self, job, *, now=None):
        now = time.time() if now is None else now
        with self.connect() as db:
            return db.execute("""SELECT 1 FROM spec84_slots s
                JOIN spec84_cycles c ON c.id=s.cycle_id
                JOIN spec84_generations g ON g.uid=c.uid AND g.generation=c.generation AND g.vin=c.vin
                WHERE s.cycle_id=? AND s.slot=? AND s.token=? AND s.state='RUNNING'
                AND s.lease_until>? AND c.state='ACTIVE'""",
                (job["cycle_id"], job["slot"], job["token"], now)).fetchone() is not None

    def finish(self, job, outcomes, result, *, state="DONE", now=None):
        now = time.time() if now is None else now
        if set(outcomes) != set(APPROVED_SOURCES):
            raise ValueError("EXACT_APPROVED_TEN_OUTCOMES_REQUIRED")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            changed = db.execute("""UPDATE spec84_slots SET state=?,finished_at=?,token=NULL,
                lease_until=NULL,result_json=? WHERE cycle_id=? AND slot=? AND token=? AND state='RUNNING'
                AND lease_until>?""", (state, now, json.dumps(result, ensure_ascii=False),
                job["cycle_id"], job["slot"], job["token"], now)).rowcount
            if not changed:
                return False
            for source_id, outcome in outcomes.items():
                db.execute("INSERT OR REPLACE INTO spec84_sources VALUES(?,?,?,?)",
                    (job["cycle_id"], job["slot"], source_id, json.dumps(outcome, ensure_ascii=False)))
            if not db.execute("SELECT 1 FROM spec84_slots WHERE cycle_id=? AND state IN ('PENDING','RUNNING','PAUSED')",
                              (job["cycle_id"],)).fetchone():
                db.execute("UPDATE spec84_cycles SET state='COMPLETE' WHERE id=? AND state='ACTIVE'", (job["cycle_id"],))
            return True

    def pause(self, job, outcomes=None):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            # A stale claimant must not pause a newer VIN generation.
            row = db.execute("SELECT 1 FROM spec84_slots WHERE cycle_id=? AND slot=? AND token=?",
                             (job["cycle_id"], job["slot"], job["token"])).fetchone()
            if row:
                if outcomes is not None:
                    for sid, outcome in outcomes.items():
                        if sid in APPROVED_SOURCES:
                            db.execute("INSERT OR REPLACE INTO spec84_sources VALUES(?,?,?,?)",
                                       (job["cycle_id"], job["slot"], sid, json.dumps(outcome, ensure_ascii=False)))
                db.execute("UPDATE spec84_cycles SET state='PAUSED' WHERE id=? AND state='ACTIVE'", (job["cycle_id"],))
                db.execute("""UPDATE spec84_slots SET state='PAUSED',token=NULL,lease_until=NULL
                    WHERE cycle_id=? AND state IN ('PENDING','RUNNING')""", (job["cycle_id"],))

    def report(self):
        with self.connect() as db:
            return {"cycles": [dict(r) for r in db.execute("SELECT * FROM spec84_cycles ORDER BY id")],
                    "slots": [dict(r) for r in db.execute("SELECT * FROM spec84_slots ORDER BY cycle_id,slot")],
                    "sources": [dict(r) for r in db.execute("SELECT * FROM spec84_sources ORDER BY cycle_id,slot,source_id")]}

    def card_state(self, uid):
        with self.connect() as db:
            cycle = db.execute("""SELECT c.* FROM spec84_cycles c
                JOIN spec84_generations g ON g.uid=c.uid AND g.generation=c.generation
                WHERE c.uid=?""", (uid,)).fetchone()
            if not cycle:
                return {"status": "NOT_QUEUED", "slots": [], "sources": []}
            slots = [dict(r) for r in db.execute("SELECT * FROM spec84_slots WHERE cycle_id=? ORDER BY slot", (cycle["id"],))]
            sources = [dict(r) for r in db.execute("SELECT * FROM spec84_sources WHERE cycle_id=? ORDER BY slot,source_id", (cycle["id"],))]
            return {"status": cycle["state"], "cycle": dict(cycle), "slots": slots, "sources": sources}


def blank_outcomes(connected=(), status="NOT_STARTED"):
    return {sid: {"name": name, "status": status if sid in connected else "NOT_CONNECTED"}
            for sid, name in APPROVED_SOURCES.items()}


def collect_bounded(card, collector, connected_sources, *, seconds=18, request_timeout=5):
    """Hard killable, read-only collection; retain emitted partial outcomes.

    collector(card, request_timeout, emit) can emit(sid, outcome, facts=[]).
    Its final return is {"sources": {approved_id: outcome}, "facts": [...]}.
    Unavailable adapters stay NOT_CONNECTED; the registry is never relabelled.
    """
    connected = frozenset(connected_sources)
    if not connected <= set(APPROVED_SOURCES):
        raise ValueError("UNAPPROVED_SOURCE")
    if not re.fullmatch(r"[a-zA-Z_][\w.]*:[a-zA-Z_]\w*", collector):
        raise ValueError("INVALID_COLLECTOR_IMPORT")
    outcomes = blank_outcomes(connected)
    facts = []
    started = time.monotonic()
    proc = subprocess.Popen([sys.executable, "-B", str(pathlib.Path(__file__).resolve()), "--collect"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    payload = {"card": card, "collector": collector, "request_timeout": request_timeout}
    proc.stdin.write(json.dumps(payload).encode() + b"\n")
    proc.stdin.close()
    buf = b""
    failure = None
    selector = selectors.DefaultSelector()
    selector.register(proc.stdout, selectors.EVENT_READ)
    try:
        while True:
            remaining = seconds - (time.monotonic() - started)
            if remaining <= 0:
                failure = "TIMEOUT"
                break
            events = selector.select(min(remaining, 0.1))
            if not events:
                continue
            chunk = os.read(proc.stdout.fileno(), 65536)
            if not chunk:
                break
            buf += chunk
            if len(buf) > MAX_MESSAGE_BYTES:
                failure = "OUTPUT_LIMIT"
                break
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if not line.startswith(PROTOCOL):
                    continue
                msg = json.loads(line[len(PROTOCOL):])
                if "source_id" in msg:
                    sid = msg["source_id"]
                    if sid in connected:
                        outcomes[sid] = dict(msg["outcome"], name=APPROVED_SOURCES[sid])
                        facts.extend(msg.get("facts") or [])
                elif "result" in msg:
                    result = msg["result"]
                    for sid, outcome in (result.get("sources") or {}).items():
                        if sid in connected:
                            outcomes[sid] = dict(outcome, name=APPROVED_SOURCES[sid])
                    facts.extend(result.get("facts") or [])
                elif "error" in msg:
                    failure = "ERROR"
    except (OSError, ValueError, TypeError):
        failure = "COLLECTOR_PROTOCOL_ERROR"
    finally:
        selector.close()
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=0.5)
        elif proc.returncode and failure is None:
            failure = "COLLECTOR_EXIT"
        proc.stdout.close()
    for sid in connected:
        if outcomes[sid].get("status") == "NOT_STARTED":
            outcomes[sid]["status"] = failure or "NO_RESULT"
    # Duplicate transport emissions cannot create duplicate fact writes.
    unique = {json.dumps(f, sort_keys=True, ensure_ascii=False): f for f in facts}
    return {"facts": list(unique.values()), "sources": outcomes,
            "collection_error": failure, "elapsed_seconds": time.monotonic() - started}


def _collector_child():
    payload = json.loads(sys.stdin.buffer.readline(MAX_MESSAGE_BYTES))
    def send(obj):
        sys.stdout.write(PROTOCOL.decode() + json.dumps(obj, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    def emit(source_id, outcome, facts=None):
        send({"source_id": source_id, "outcome": outcome, "facts": facts or []})
    try:
        module, name = payload["collector"].split(":", 1)
        callback = getattr(importlib.import_module(module), name)
        result = callback(payload["card"], payload["request_timeout"], emit)
        send({"result": result or {}})
    except BaseException as exc:
        send({"error": type(exc).__name__})


class Runtime:
    """Six bounded slots run outside Telegram handlers; one runtime per process.

    commit(card, generation, facts, outcomes) MUST be additive, preserve manual
    values/hidden fields and VIN histories, and use a narrow existing-page
    renderer. It must not call first-publication or enqueue a new legacy job.
    read_card and commit are called under commit_guard immediately before writes.
    """
    def __init__(self, queue, *, read_card, collector, connected_sources,
                 commit_guard, commit, workers=6, collection_seconds=18,
                 request_timeout=5, clock=time.time, collect_fn=collect_bounded):
        self.queue, self.read_card, self.collector = queue, read_card, collector
        self.connected = tuple(connected_sources)
        self.guard, self.commit = commit_guard, commit
        self.workers = max(1, min(int(workers), 6))
        self.seconds, self.request_timeout = min(float(collection_seconds), 18), request_timeout
        self.clock, self.collect_fn = clock, collect_fn
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=self.workers,
                                                         thread_name_prefix="spec84")
        self.pending = set()
        self.tick_lock = threading.Lock()

    def execute(self, job):
        initial = self.read_card(job["uid"])
        if identity(initial) != (job["uid"], job["vin"]):
            self.queue.pause(job)
            return "STALE_OR_UNPUBLISHED"
        try:
            result = self.collect_fn(initial, self.collector, self.connected,
                seconds=self.seconds, request_timeout=self.request_timeout)
            with self.guard(job["uid"]):
                current = self.read_card(job["uid"])
                if identity(current) != (job["uid"], job["vin"]):
                    self.queue.pause(job, result["sources"])
                    return "STALE_OR_UNPUBLISHED"
                if not self.queue.lease_valid(job, now=self.clock()):
                    return "LOST_LEASE_OR_GENERATION"
                # Callback runs under guard; history/merge and HTML refresh stay there.
                detail = self.commit(current, job["generation"], result["facts"], result["sources"])
                receipt = {"commit": detail, "delay_seconds": job["delay_seconds"],
                           "collection_error": result.get("collection_error"),
                           "elapsed_seconds": result.get("elapsed_seconds")}
                done = self.queue.finish(job, result["sources"], receipt, now=self.clock())
                return "DONE" if done else "LOST_LEASE_AFTER_IDEMPOTENT_COMMIT"
        except Exception as exc:
            # One failed logical attempt does not cancel the remaining scheduled slots.
            outcomes = locals().get("result", {}).get("sources") or blank_outcomes(self.connected, "ERROR")
            self.queue.finish(job, outcomes, {"error": type(exc).__name__}, state="FAILED", now=self.clock())
            return "FAILED"

    def tick(self):
        """Call at most every 5 seconds; nonblocking relative to collector work."""
        with self.tick_lock:
            finished = [f for f in self.pending if f.done()]
            for future in finished:
                # Observe exceptions; individual failure must not kill the CRM loop.
                try:
                    future.result()
                except Exception:
                    pass
                self.pending.remove(future)
            for _ in range(self.workers - len(self.pending)):
                job = self.queue.claim(now=self.clock(), lease_seconds=90)
                if not job:
                    break
                self.pending.add(self.pool.submit(self.execute, job))
            return len(self.pending)

    def close(self, wait=True):
        self.pool.shutdown(wait=wait)


if __name__ == "__main__" and sys.argv[1:] == ["--collect"]:
    _collector_child()

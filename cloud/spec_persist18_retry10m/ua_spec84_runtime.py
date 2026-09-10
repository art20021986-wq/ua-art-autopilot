"""Issue 84 integration: published-only durable retries and narrow page sync.

No import-time work. Existing vin_spec_service delegates its four public entry
points here. All main-CRM connections remain read-only. The old worker, old
enqueue deletion policy and whole-catalog publisher are never called.
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import logging
import os
import pathlib
import sqlite3
import tempfile
import threading
import time

from spec_retry84 import APPROVED_SOURCES, DOMAIN_TO_SOURCE, Queue, Runtime, blank_outcomes, collect_bounded, identity

ROOT = pathlib.Path(os.environ.get("UA_ART_ROOT", "/home/Carix"))
QUEUE_DB = pathlib.Path(os.environ.get("UA_ART_SPEC84_QUEUE_DB", str(ROOT / "vin_specs_issue84_queue.db")))
WRITER_LOCKS = (".task082_catalog_stage_repair.lock", ".task082_catalog_stage_guard.lock",
                ".task083_catalog_dedup.lock", ".ua_art_publish_transaction.lock", ".crm_db.lock")
MAX_HTML = 32 * 1024 * 1024
LOG = logging.getLogger(__name__)
_lock = threading.Lock()
_thread = None
_stop = threading.Event()
_queue = None
_queue_lock = threading.Lock()


class RuntimeDeferred(RuntimeError):
    pass


def _legacy():
    import vin_spec_service
    return vin_spec_service


def _cards():
    service = _legacy()
    result = []
    with service.connect_main() as db:
        rows = [dict(row) for row in db.execute("SELECT rowid AS __rowid__,* FROM cars ORDER BY rowid")]
    for row in rows:
        card = service._card_from_row(row)
        if card is None:
            # Japanese chassis numbers are honest no-match collection inputs,
            # never grounds to omit a published card's permanent empty section.
            uid = service.canonical_uid(service._pick(row, "auto_number", "car_uid", "uid", "code"))
            raw = str(service._pick(row, "vin", "vin_code") or "").strip().upper()
            card = {"car_uid": uid, "vin": raw, "published": service._published(row),
                    "car_id": row.get("id"), "brand": row.get("brand"), "model": row.get("model"),
                    "year": row.get("year"), "engine_cc": service._engine_cc(row)}
            if identity(dict(card, published=True)) is None:
                continue
        result.append(card)
    return result


def _card(uid):
    return next((row for row in _cards() if row["car_uid"] == uid), None)


@contextlib.contextmanager
def _writer_guard(uid):
    """Same preexisting inodes and ordering as installation; bounded waits."""
    deadline = time.monotonic() + 2.0
    handles = []
    try:
        while True:
            if (ROOT / ".uaart_writer_coordination" / "active-intent.json").exists():
                raise RuntimeDeferred("COORDINATED_WRITER_ACTIVE")
            try:
                for name in WRITER_LOCKS:
                    path = ROOT / name
                    if path.is_symlink() or not path.is_file():
                        raise RuntimeDeferred("EXISTING_WRITER_LOCK_MISSING")
                    fd = os.open(str(path), os.O_RDWR | getattr(os, "O_NOFOLLOW", 0))
                    handles.append(fd)
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                for fd in reversed(handles):
                    fcntl.flock(fd, fcntl.LOCK_UN)
                    os.close(fd)
                handles = []
                if time.monotonic() >= deadline:
                    raise RuntimeDeferred("WRITER_BUSY")
                _stop.wait(0.05)
        if (ROOT / ".uaart_writer_coordination" / "active-intent.json").exists():
            raise RuntimeDeferred("COORDINATED_WRITER_ACTIVE")
        import ua_spec_permanent
        with ua_spec_permanent.write_lock(ROOT, timeout=2.0):
            yield
    finally:
        for fd in reversed(handles):
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)


def _init_queue():
    global _queue
    with _queue_lock:
        if _queue is None:
            queue = Queue(QUEUE_DB)
            with queue.connect() as db:
                db.execute("""CREATE TABLE IF NOT EXISTS spec84_sync(
                    uid TEXT PRIMARY KEY,vin TEXT NOT NULL,generation INTEGER NOT NULL,
                    requested_at REAL NOT NULL,state TEXT NOT NULL DEFAULT 'PENDING',
                    attempts INTEGER NOT NULL DEFAULT 0,next_try REAL NOT NULL DEFAULT 0,
                    result_json TEXT)""")
                db.execute("CREATE TABLE IF NOT EXISTS spec84_runtime_state(key TEXT PRIMARY KEY,value_json TEXT NOT NULL,updated_at REAL NOT NULL)")
            _queue = queue
    return _queue


def _heartbeat(status, **detail):
    queue = _init_queue()
    detail.update(status=status, worker_pid=os.getpid(), observed_at=time.time())
    with queue.connect() as db:
        db.execute("INSERT OR REPLACE INTO spec84_runtime_state VALUES('heartbeat',?,?)",
                   (json.dumps(detail), time.time()))


def _spec_transaction():
    return _legacy().connect_spec(False)


def _attached(db):
    db.execute("ATTACH DATABASE ? AS schedule", (str(QUEUE_DB),))
    databases = {row[1]: row[2] for row in db.execute("PRAGMA database_list")}
    if not databases.get("main") or not databases.get("schedule"):
        raise RuntimeDeferred("FILE_BACKED_ATOMIC_DATABASES_REQUIRED")
    for schema in ("main", "schedule"):
        mode = str(db.execute("PRAGMA " + schema + ".journal_mode").fetchone()[0]).lower()
        if mode not in {"delete", "truncate", "persist"}:
            raise RuntimeDeferred("ROLLBACK_JOURNAL_REQUIRED")
        db.execute("PRAGMA " + schema + ".synchronous=FULL")
    db.execute("PRAGMA busy_timeout=1500")


def _request_sync(db, schema, card, generation, now):
    db.execute("""INSERT INTO %sspec84_sync(uid,vin,generation,requested_at,state,next_try)
        VALUES(?,?,?,?,'PENDING',0) ON CONFLICT(uid) DO UPDATE SET
        vin=excluded.vin,generation=excluded.generation,requested_at=excluded.requested_at,
        state='PENDING',next_try=0,result_json=NULL""" % schema,
        (card["car_uid"], card["vin"], generation, now))


def _legacy_vin(db, uid):
    row = db.execute("SELECT vin FROM vin_spec_jobs WHERE car_uid=? ORDER BY id DESC LIMIT 1", (uid,)).fetchone()
    return str(row[0]) if row else None


def _enqueue(uid, reason):
    queue = _init_queue()
    with _writer_guard(uid):
        card = _card(uid)
        if identity(card) is None:
            return False
        import spec84_collector
        with _spec_transaction() as db:
            _attached(db)
            db.execute("BEGIN IMMEDIATE")
            cycle = queue.ensure_cycle_transaction(db, card, reason=reason, schema="schedule.")
            generation = cycle["generation"]
            spec84_collector.ensure_identity_schema(db)
            spec84_collector.ensure_binding(db, card, generation, legacy_vin=_legacy_vin(db, uid))
            existing = db.execute("SELECT vin,generation FROM schedule.spec84_sync WHERE uid=?", (uid,)).fetchone()
            if existing is None or tuple(existing) != (card["vin"], generation):
                _request_sync(db, "schedule.", card, generation, time.time())
            db.commit()
    return True


def fact_binding_matches(uid):
    """Read-only renderer guard; no queue creation, scanning, or thread startup."""
    card = _card(uid)
    if identity(card) is None:
        return False
    with _legacy().connect_spec(True) as db:
        table = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='spec84_fact_bindings'").fetchone()
        if not table:
            return _legacy_vin(db, uid) == card["vin"]
        binding = db.execute("SELECT vin,generation FROM spec84_fact_bindings WHERE car_uid=?", (uid,)).fetchone()
        if binding is None:
            return _legacy_vin(db, uid) == card["vin"]
    if binding["vin"] != card["vin"]:
        return False
    if not QUEUE_DB.is_file():
        return True
    db = sqlite3.connect("file:" + str(QUEUE_DB) + "?mode=ro", uri=True, timeout=2)
    try:
        db.execute("PRAGMA query_only=ON")
        gen = db.execute("SELECT vin,generation FROM spec84_generations WHERE uid=?", (uid,)).fetchone()
        return gen is None or tuple(gen) == (binding["vin"], binding["generation"])
    finally:
        db.close()


def _lease_guard(db, job, card):
    if _stop.is_set() or identity(_card(job["uid"])) != (job["uid"], job["vin"]):
        raise RuntimeDeferred("CARD_CHANGED_OR_STOPPED")
    row = db.execute("""SELECT 1 FROM schedule.spec84_slots s
        JOIN schedule.spec84_cycles c ON c.id=s.cycle_id
        JOIN schedule.spec84_generations g ON g.uid=c.uid AND g.vin=c.vin AND g.generation=c.generation
        WHERE s.cycle_id=? AND s.slot=? AND s.token=? AND s.state='RUNNING'
        AND s.lease_until>? AND c.state='ACTIVE'""",
        (job["cycle_id"], job["slot"], job["token"], time.time())).fetchone()
    if row is None:
        raise RuntimeDeferred("LOST_LEASE_OR_GENERATION")
    binding = db.execute("SELECT vin,generation FROM spec84_fact_bindings WHERE car_uid=?", (job["uid"],)).fetchone()
    if binding is None or tuple(binding) != (job["vin"], job["generation"]):
        raise RuntimeDeferred("FACT_BINDING_CHANGED")
    return True


class _IntegratedRuntime(Runtime):
    def execute(self, job):
        card = _card(job["uid"])
        if identity(card) != (job["uid"], job["vin"]):
            self.queue.pause(job)
            return "STALE_OR_UNPUBLISHED"
        result = None
        try:
            result = collect_bounded(card, "spec84_collector:collect_scheduled",
                                     tuple(DOMAIN_TO_SOURCE.values()), seconds=18, request_timeout=4)
            if set(result["sources"]) != set(APPROVED_SOURCES):
                raise RuntimeError("EXACT_TEN_SOURCE_OUTCOMES_REQUIRED")
            if _stop.is_set():
                return "INTERRUPTED_SAME_SLOT"
            with _writer_guard(job["uid"]):
                current = _card(job["uid"])
                if identity(current) != (job["uid"], job["vin"]):
                    self.queue.pause(job, result["sources"])
                    return "STALE_OR_UNPUBLISHED"
                import spec84_collector
                with _spec_transaction() as db:
                    _attached(db)
                    db.execute("BEGIN IMMEDIATE")
                    counts = spec84_collector.merge_in_transaction(
                        db, current, result["facts"], guard=lambda conn, c: _lease_guard(conn, job, c))
                    now = time.time()
                    _request_sync(db, "schedule.", current, job["generation"], now)
                    receipt = {"merge": counts, "delay_seconds": job["delay_seconds"],
                               "collection_error": result["collection_error"], "site_sync": "PENDING"}
                    for sid, outcome in result["sources"].items():
                        db.execute("INSERT OR REPLACE INTO schedule.spec84_sources VALUES(?,?,?,?)",
                                   (job["cycle_id"], job["slot"], sid, json.dumps(outcome, ensure_ascii=False)))
                    _lease_guard(db, job, current)
                    db.execute("""UPDATE schedule.spec84_slots SET state='DONE',finished_at=?,token=NULL,
                        lease_until=NULL,result_json=? WHERE cycle_id=? AND slot=? AND token=?""",
                        (now, json.dumps(receipt, ensure_ascii=False), job["cycle_id"], job["slot"], job["token"]))
                    if not db.execute("SELECT 1 FROM schedule.spec84_slots WHERE cycle_id=? AND state IN ('PENDING','RUNNING','PAUSED')",
                                      (job["cycle_id"],)).fetchone():
                        db.execute("UPDATE schedule.spec84_cycles SET state='COMPLETE' WHERE id=?", (job["cycle_id"],))
                    db.commit()
            return "DONE_SYNC_PENDING"
        except RuntimeDeferred:
            # A paused or contested writer is retried as the same logical slot
            # when its lease expires; no successful fields are discarded.
            return "DEFERRED_SAME_SLOT"
        except Exception as exc:
            LOG.warning("spec84 collection/merge %s failed (%s)", job["uid"], type(exc).__name__)
            outcomes = result["sources"] if result else blank_outcomes(DOMAIN_TO_SOURCE.values(), "ERROR")
            self.queue.finish(job, outcomes, {"error": type(exc).__name__}, state="FAILED")
            return "FAILED"


def _atomic_existing(path, before, after):
    if path.is_symlink() or not path.is_file() or path.read_bytes() != before:
        raise RuntimeDeferred("PAGE_CHANGED_BEFORE_REPLACE")
    info = path.stat()
    fd, name = tempfile.mkstemp(prefix="." + path.name + ".spec84-", dir=str(path.parent))
    temporary = pathlib.Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(after)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, info.st_mode & 0o777)
        if path.is_symlink() or path.read_bytes() != before:
            raise RuntimeDeferred("PAGE_CHANGED_BEFORE_REPLACE")
        os.replace(temporary, path)
        dirfd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
        if path.read_bytes() != after:
            raise RuntimeDeferred("PAGE_READBACK_CHANGED")
    finally:
        temporary.unlink(missing_ok=True)


def _sync_one(row):
    uid = row["uid"]
    with _writer_guard(uid):
        current = _card(uid)
        if identity(current) != (uid, row["vin"]) or not fact_binding_matches(uid):
            return {"state": "STALE", "pages": []}
        with _queue.connect() as db:
            generation = db.execute("SELECT generation FROM spec84_generations WHERE uid=?", (uid,)).fetchone()
            if generation is None or generation[0] != row["generation"]:
                return {"state": "STALE", "pages": []}
        import ua_spec_permanent
        prepared = []
        for folder in ("video", "site"):
            path = ROOT / folder / (uid + ".html")
            if path.is_symlink() or not path.is_file():
                # Never create an initial listing or revive a deleted one.
                raise RuntimeDeferred("EXISTING_PUBLIC_PAGE_MISSING")
            before = path.read_bytes()
            if len(before) > MAX_HTML:
                raise RuntimeDeferred("PAGE_TOO_LARGE")
            after = ua_spec_permanent.ensure_html(before.decode("utf-8"), uid).encode("utf-8")
            prepared.append((path, before, after))
        if _stop.is_set() or identity(_card(uid)) != (uid, row["vin"]):
            raise RuntimeDeferred("CARD_CHANGED_OR_STOPPED")
        changed = []
        try:
            for path, before, after in prepared:
                if after != before:
                    _atomic_existing(path, before, after)
                    changed.append((path, before, after))
        except Exception:
            # Conditional rollback restores only our own still-current bytes.
            for path, before, after in reversed(changed):
                if path.is_file() and not path.is_symlink() and path.read_bytes() == after:
                    _atomic_existing(path, after, before)
            raise
        return {"state": "DONE", "pages": [{"path": str(p), "sha256": hashlib.sha256(a).hexdigest(),
                "changed": b != a} for p, b, a in prepared]}


def _sync_pending(limit=18):
    with _queue.connect() as db:
        rows = [dict(r) for r in db.execute("SELECT * FROM spec84_sync WHERE state='PENDING' AND next_try<=? ORDER BY requested_at LIMIT ?",
                                           (time.time(), limit))]
    for row in rows:
        if _stop.is_set():
            break
        try:
            result = _sync_one(row)
            state, next_try = result["state"], 0
        except Exception as exc:
            result = {"error": type(exc).__name__}
            state, next_try = "PENDING", time.time() + min(60, 5 * (1 + row["attempts"]))
        with _queue.connect() as db:
            db.execute("""UPDATE spec84_sync SET state=?,attempts=attempts+1,next_try=?,result_json=?
                WHERE uid=? AND vin=? AND generation=? AND requested_at=?""",
                (state, next_try, json.dumps(result), row["uid"], row["vin"], row["generation"], row["requested_at"]))


def _loop():
    runtime = None
    worker_fd = None
    try:
        worker_fd = os.open(str(ROOT / ".ua_spec84_worker.lock"), os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        fcntl.flock(worker_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        queue = _init_queue()
        runtime = _IntegratedRuntime(queue, read_card=_card, collector="spec84_collector:collect_scheduled",
            connected_sources=DOMAIN_TO_SOURCE.values(), commit_guard=_writer_guard, commit=lambda *args: None)
        last_scan = 0.0
        last_heartbeat = 0.0
        published_count = 0
        _heartbeat("STARTED", connected_sources=list(DOMAIN_TO_SOURCE.values()), unavailable_sources=[s for s in APPROVED_SOURCES if s not in DOMAIN_TO_SOURCE.values()])
        while not _stop.is_set():
            try:
                if time.monotonic() - last_scan >= 15:
                    cards = _cards()
                    published_count = sum(bool(c.get("published")) for c in cards)
                    for card in cards:
                        if card.get("published"):
                            try:
                                _enqueue(card["car_uid"], "recovery")
                            except RuntimeDeferred:
                                pass
                            except Exception as exc:
                                LOG.warning("spec84 enqueue %s failed (%s)", card["car_uid"], type(exc).__name__)
                    last_scan = time.monotonic()
                runtime.tick()
                _sync_pending()
                if time.monotonic() - last_heartbeat >= 15:
                    _heartbeat("RUNNING", published_count=published_count, active_collectors=len(runtime.pending),
                               last_scan_at=time.time() - (time.monotonic() - last_scan))
                    last_heartbeat = time.monotonic()
            except Exception as exc:
                LOG.warning("spec84 worker tick failed (%s)", type(exc).__name__)
            _stop.wait(2)
    except Exception as exc:
        LOG.error("spec84 worker not started (%s)", type(exc).__name__)
        try:
            _heartbeat("NOT_RUNNING", error=type(exc).__name__)
        except Exception:
            pass
    finally:
        if runtime:
            runtime.close(wait=True)
        if worker_fd is not None:
            fcntl.flock(worker_fd, fcntl.LOCK_UN)
            os.close(worker_fd)
        if _stop.is_set():
            try:
                _heartbeat("STOPPED")
            except Exception:
                pass


def start_worker():
    global _thread
    with _lock:
        if _thread is not None and _thread.is_alive():
            return False
        _stop.clear()
        _thread = threading.Thread(target=_loop, name="uaart-spec84-scheduler", daemon=True)
        _thread.start()
        return True


def stop_worker(timeout=5.0):
    _stop.set()
    thread = _thread
    if thread is not None and thread.is_alive() and thread is not threading.current_thread():
        thread.join(timeout=max(0.0, float(timeout)))


def retry_card(value):
    uid = _legacy().canonical_uid(value)
    if not uid:
        return False
    return _enqueue(uid, "publish")


def card_state(value):
    uid = _legacy().canonical_uid(value)
    if not uid or not QUEUE_DB.is_file():
        return {"status": "NOT_QUEUED", "facts_count": 0, "site_sync_status": "NOT_REQUIRED"}
    state = _init_queue().card_state(uid)
    with _legacy().connect_spec(True) as db:
        count = db.execute("""SELECT count(*) FROM additional_specification a
            LEFT JOIN additional_specification_meta m ON m.car_uid=a.car_uid AND m.field_key=a.field_key
            WHERE a.car_uid=? AND COALESCE(m.is_visible,1)=1""", (uid,)).fetchone()[0]
    with _queue.connect() as db:
        sync = db.execute("SELECT state FROM spec84_sync WHERE uid=?", (uid,)).fetchone()
    state.update(facts_count=count, site_sync_status=sync[0] if sync else "NOT_REQUIRED")
    return state

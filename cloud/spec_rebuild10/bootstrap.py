"""Concrete runtime providers. Importing this module starts and writes nothing.

Authority is supplied by the reviewed controller; this module cannot manufacture
writer-drain, installation or owner authorization from local status strings.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import inspect
import types
import os
from pathlib import Path
import sqlite3
import stat
import threading
import time
from typing import Callable, Mapping
from urllib.parse import urlsplit

from . import crm_bridge, render
from .store import SpecStore
from .worker import bind_worker

MAX_FILE = 4 * 1024 * 1024
RUNTIME_PINS = {
    "card_lifecycle.py": "a0f65fedcf91cbe01f0b891ddde31b97186e9c7ae77e51cef905cf29a81b55b7",
    "publish_transaction_guard.py": "eb8a37c5bba85b74cf3d6ed4c326d20d69a92274dee1e75f80108b5fa9834912",
    "publikaciya.py": "224d140151e26ff597962f17f45ec928f0716fb873e139e9686aac0256de87e8",
    "master_card.py": "1141dbab9d31baca570b6eb9c3470000a6847c9f20e5c67cc0de9ba7b7cfc3c8",
}


class BootstrapError(RuntimeError):
    pass


def require(value, code):
    if not value:
        raise BootstrapError(code)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def read_regular(path, limit=MAX_FILE):
    path = Path(path).absolute()
    require(not any(p.is_symlink() for p in (path, *path.parents)), "SYMLINK_FORBIDDEN")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size <= limit,
                "REGULAR_BOUNDED_FILE_REQUIRED")
        with os.fdopen(os.dup(fd), "rb") as stream:
            data = stream.read(limit + 1)
        after, linked = os.fstat(fd), path.stat()
        stamp = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        require(len(data) <= limit and stamp(before) == stamp(after) == stamp(linked),
                "FILE_CHANGED_DURING_READ")
        return data
    finally:
        os.close(fd)


class CrmRows:
    """Current complete SQLite rows, no imports of the monkeypatching legacy DB."""
    def __init__(self, path):
        self.path = Path(path).absolute()
        require(self.path.is_file() and not self.path.is_symlink(), "CRM_DATABASE_REQUIRED")

    @contextmanager
    def connection(self):
        require(not any(p.is_symlink() for p in (self.path, *self.path.parents)), "CRM_SYMLINK_FORBIDDEN")
        # Do not use immutable=1 on a running database: it could ignore its WAL.
        db = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=3)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            yield db
        finally:
            db.rollback()
            db.close()

    def snapshot(self):
        with self.connection() as db:
            require(db.execute("PRAGMA quick_check").fetchone()[0] == "ok", "CRM_INTEGRITY_FAILED")
            rows = [dict(row) for row in db.execute("SELECT * FROM cars ORDER BY id")]
        seen = set()
        for row in rows:
            uid = crm_bridge.canonical_uid(row.get("auto_number"))
            require(uid not in seen, "DUPLICATE_CRM_UID")
            seen.add(uid)
        return {"rows": rows, "rows_sha256": digest(rows), "complete": True}

    def __call__(self, uid):
        uid = crm_bridge.canonical_uid(uid)
        rows = self.snapshot()["rows"]
        return next((row for row in rows if crm_bridge.canonical_uid(row["auto_number"]) == uid), None)

    def completed(self, uid, action, actor_id, before_sha256):
        with self.connection() as db:
            rows = [dict(row) for row in db.execute(
                "SELECT * FROM ua_spec_lifecycle_archive WHERE auto_number=? AND action=? "
                "AND actor_id=? AND state='COMPLETED'", (uid, action, actor_id))]
        rows = [row for row in rows if digest(json.loads(row["previous_row_json"])) == before_sha256]
        require(len(rows) == 1, "EXACT_COMPLETED_LIFECYCLE_RECEIPT_REQUIRED")
        return rows[0]


class ExactPlan:
    """Authenticate an exact persisted controller plan, never echo request hashes.

    authenticate checks separate owner/controller authority and current writer
    ownership. Its absence is a hard boundary, not replaceable by plan[PASS].
    The exact plan file includes approved ordinary-generator source hashes and
    precomputed HTML before/after hashes, even when only a price is changed.
    """
    def __init__(self, path, expected_sha256, *, authenticate: Callable, rows: CrmRows,
                 store_path, clock=time.time):
        require(callable(authenticate), "AUTHENTICATED_CONTROLLER_REQUIRED")
        self.path, self.expected = Path(path), expected_sha256
        self.authenticate, self.rows, self.store_path, self.clock = authenticate, rows, str(store_path), clock
        self.local = threading.local()
        self.load()

    def load(self):
        raw = read_regular(self.path)
        require(hashlib.sha256(raw).hexdigest() == self.expected, "EXACT_APPROVED_PLAN_CHANGED")
        plan = json.loads(raw)
        require(plan.get("schema") == "UA-ART-SPEC-REBUILD10-RUNTIME-PLAN-1", "PLAN_SCHEMA")
        require(plan.get("module") == "spec_rebuild10" and isinstance(plan.get("operations"), list), "PLAN_SCOPE")
        require(type(plan.get("not_before")) in (int, float) and type(plan.get("expires_at")) in (int, float)
                and plan["not_before"] <= self.clock() < plan["expires_at"], "PLAN_EXPIRED_OR_NOT_CURRENT")
        require(plan.get("source_pins") == RUNTIME_PINS, "ORDINARY_GENERATOR_PINS_REQUIRED")
        require(self.authenticate(plan, self.expected) is True, "AUTHENTICATED_OWNER_ROUTE_REQUIRED")
        return plan

    def operation(self, uid, action, plan_id=None):
        matches = [op for op in self.load()["operations"] if op.get("uid") == uid
                   and op.get("action") == action and (plan_id is None or op.get("plan_id") == plan_id)]
        require(len(matches) == 1, "EXACT_OPERATION_REQUIRED")
        return matches[0]

    def readiness(self, request):
        op = self.operation(request["uid"], request["action"])
        for key, value in request.items():
            require(op.get(key) == value, "APPROVED_OPERATION_SCOPE_MISMATCH:" + key)
        require(digest(self.rows(request["uid"])) == op["crm_row_sha256"], "CRM_CHANGED_SINCE_PLAN")
        require(op.get("owner_manual_action") is True, "MANUAL_OWNER_ACTION_REQUIRED")
        require(all(op.get(k) == "PASS" for k in ("gate_b", "route", "external_writers")),
                "REVIEWED_RUNTIME_GATE_REQUIRED")
        if request["uid"] == "UA-0018" and request["action"] == "publish":
            with SpecStore(self.store_path) as store:
                prior = store.get_publication_snapshot("UA-0017")
                vehicle = store.get_vehicle("UA-0017")
                require(prior and vehicle["published"] and prior["identity_hash"] == vehicle["identity_hash"]
                    and prior["facts_digest"] == store.facts_digest("UA-0017"), "OWNER_17_READBACK_BEFORE_18_REQUIRED")
        self.local.started = self.clock()
        return {**request, "plan_id": op["plan_id"], "gate_b": "PASS", "route": "PASS",
                "external_writers": "PASS", "owner_action": "PASS", "fresh": "PASS"}

    def page_change(self, request):
        op = self.operation(request["uid"], "publish", request["plan_id"])
        for key in ("uid", "action", "revision", "facts_digest"):
            require(request.get(key) == op.get(key), "PAGE_OPERATION_SCOPE_MISMATCH")
        pages = [page for page in op.get("pages", []) if all(page.get(k) == request.get(k)
            for k in ("before_sha256", "after_sha256", "shell_assets_sha256", "render_facts_sha256"))]
        require(len(pages) >= 1, "HTML_NOT_IN_APPROVED_GENERATOR_PLAN")
        before, current = op.get("crm_row_before"), self.rows(request["uid"])
        require(isinstance(before, dict) and digest(before) == op["crm_row_sha256"], "PLAN_CRM_PREIMAGE_INVALID")
        require(current and digest(current) == request["crm_row_sha256"], "PAGE_CURRENT_CRM_HASH_MISMATCH")
        expected = dict(before, published=1)
        if "publish_pending" in before:
            expected["publish_pending"] = 0
        if "updated_at" in before:
            require(hasattr(self.local, "started"), "ACTIVE_OPERATION_REQUIRED")
            try:
                stamp = datetime.fromisoformat(current["updated_at"])
                require(stamp.tzinfo is not None and self.local.started - 1 <= stamp.timestamp() <= self.clock() + 1,
                        "LIFECYCLE_TIMESTAMP_OUTSIDE_OPERATION")
            except (ValueError, TypeError):
                raise BootstrapError("LIFECYCLE_TIMESTAMP_INVALID")
            expected["updated_at"] = current["updated_at"]
        require(current == expected, "UNAPPROVED_CRM_BUSINESS_CHANGE")
        return {**request, "authorization": "PASS"}


@dataclass(frozen=True)
class HttpReadback:
    url: str
    status: int
    body: bytes


class PublicReadback:
    """Transport must be the approved bounded HTTPS provider; no fallback route."""
    def __init__(self, plan: ExactPlan, store_path, *, transport: Callable):
        require(callable(transport), "APPROVED_READBACK_TRANSPORT_REQUIRED")
        self.plan, self.store_path, self.transport = plan, str(store_path), transport

    def verify(self, ticket, receipt):
        op = self.plan.operation(ticket.uid, ticket.action, ticket.plan_id)
        require(all(receipt.get(k) == v for k, v in asdict(ticket).items()
                    if k not in {"actor_id", "crm_row_sha256"}), "RECEIPT_SCOPE_MISMATCH")
        with SpecStore(self.store_path) as store:
            vehicle, facts = store.get_vehicle(ticket.uid), store.get_facts(ticket.uid)
            require(vehicle["identity_hash"] == ticket.identity_hash and vehicle["revision"] == ticket.revision
                    and store.facts_digest(ticket.uid) == ticket.facts_digest, "READBACK_FACTS_CHANGED")
        targets = op.get("readback")
        require(isinstance(targets, list) and targets, "READBACK_TARGETS_REQUIRED")
        primary = 0
        expected = {
            "/video/" + ticket.uid + ".html": "primary",
            "/video/" + ticket.uid + "-diag.html": "diagnostic",
            "/video/katalog.html": "catalog",
        }
        supplied = {}
        for target in targets:
            parsed_target = urlsplit(target["url"])
            require(not parsed_target.query and parsed_target.path not in supplied, "READBACK_TARGET_DUPLICATE_OR_QUERY")
            supplied[parsed_target.path] = target
        require(set(expected).issubset(supplied), "PRIMARY_DIAGNOSTIC_CATALOG_READBACK_REQUIRED")
        for path, kind in expected.items():
            require(supplied[path].get("kind") == kind, "READBACK_SURFACE_KIND_MISMATCH")
            require((supplied[path].get("absent") is True) == (ticket.action != "publish" and kind != "catalog"),
                    "READBACK_SURFACE_PRESENCE_MISMATCH")
        for target in targets:
            url = target["url"]
            parsed = urlsplit(url)
            require(parsed.scheme == "https" and parsed.hostname in {"uaart.com.ua", "www.uaart.com.ua"}
                    and not parsed.username and parsed.port in (None, 443) and not parsed.fragment,
                    "READBACK_URL_NOT_APPROVED")
            allowed_paths = set(expected) | {p.replace("/video/", "/site/", 1) for p in expected}
            require(parsed.path in allowed_paths, "READBACK_PATH_NOT_OPERATION_SURFACE")
            response = self.transport(url, timeout_seconds=15, max_bytes=MAX_FILE)
            require(isinstance(response, HttpReadback) and response.url == url and
                    isinstance(response.body, bytes) and len(response.body) <= MAX_FILE,
                    "BOUNDED_EXACT_HTTP_RESPONSE_REQUIRED")
            if target.get("absent") is True:
                require(ticket.action != "publish" and response.status in (404, 410), "WITHDRAWN_PAGE_STILL_PUBLIC")
                continue
            require(response.status == 200 and hashlib.sha256(response.body).hexdigest() == target.get("sha256"),
                    "PUBLIC_READBACK_HASH_MISMATCH")
            if target.get("kind") == "catalog":
                catalog = render.shell_guard._Page(response.body.decode("utf-8"))
                links = [node for node in catalog.nodes if node.tag == "a" and
                         urlsplit(node.attrs.get("href") or "").path.rsplit("/", 1)[-1] == ticket.uid + ".html"]
                require(bool(links) == (ticket.action == "publish"), "PUBLIC_CATALOG_VISIBILITY_MISMATCH")
            if target.get("kind") == "primary":
                require(ticket.action == "publish" and parsed.path.endswith("/" + ticket.uid + ".html"),
                        "PRIMARY_READBACK_SCOPE")
                html = response.body.decode("utf-8")
                render.validate_page(html, ticket.uid, facts, previous=html)
                _, identity = crm_bridge.identity_from_crm(self.plan.rows(ticket.uid))
                page = render.shell_guard._Page(html)
                require(render.shell_guard._main_vin(page, ticket.uid)[1] == identity["vin"], "PUBLIC_VIN_DIFFERS_FROM_CRM")
                primary += 1
        require(primary >= 1 if ticket.action == "publish" else any(t.get("absent") is True for t in targets),
                "PRIMARY_OR_WITHDRAWAL_READBACK_REQUIRED")
        return True


class WorkerService:
    """The existing supervisor invokes tick; startup never creates another daemon."""
    def __init__(self, store_path, rows, collectors, installation_receipt, verify_installation, *, register=None):
        self.store_path, self.rows, self.collectors = str(store_path), rows, collectors
        self.receipt, self.verify_installation, self.register = installation_receipt, verify_installation, register
        self._lock, self._registered = threading.RLock(), False
        self.public_sync = None

    def _handoff(self):
        require(callable(self.verify_installation) and self.verify_installation(self.receipt) is True
                and self.receipt.get("module") == "spec_rebuild10"
                and self.receipt.get("old_workers_stopped") is True
                and self.receipt.get("exclusive_owner") is True
                and self.receipt.get("receipt_id"), "VERIFIED_INSTALLATION_HANDOFF_REQUIRED")

    def tick(self):
        self._handoff()
        with self._lock:
            if self.public_sync is not None and self.public_sync.blocked():
                return {"worker": {"status": "NOT_RUN_SYNC_RECONCILIATION_REQUIRED"},
                        "public_sync": {"status": "BLOCKED_SYNC_RECONCILIATION_REQUIRED"}}
            with SpecStore(self.store_path) as store:
                worker = bind_worker(store, self.collectors, installation_receipt=self.receipt,
                                     verify_installation=self.verify_installation)
                scan = self.rows.snapshot()
                require(scan["complete"] is True, "COMPLETE_CRM_SCAN_REQUIRED")
                reconciliation = crm_bridge.CrmBridge(store).reconcile_saved_rows(scan["rows"])
                require(not reconciliation["needs_input"], "CRM_RECONCILIATION_NEEDS_INPUT")
                result = {"reconciliation": reconciliation, "worker": worker.run_once()}
            if self.public_sync is not None:
                if result["worker"]["status"] in {"RETRY_SCHEDULED", "EXHAUSTED", "STALE_RESULT_DISCARDED"}:
                    result["public_sync"] = {"status": "NOT_RUN_COLLECTION_ERROR"}
                else:
                    result["public_sync"] = self.public_sync.tick()
            return result

    def start(self):
        self._handoff()
        with self._lock:
            with SpecStore(self.store_path) as store:
                bind_worker(store, self.collectors, installation_receipt=self.receipt,
                            verify_installation=self.verify_installation)
            require(callable(self.register), "EXISTING_VERIFIED_SUPERVISOR_REQUIRED")
            if self._registered:
                return {"started": True, "status": "ALREADY_REGISTERED"}
            result = self.register("spec_rebuild10", self.tick)
            require(isinstance(result, dict) and result.get("registered") is True
                    and result.get("worker") == "spec_rebuild10" and result.get("receipt_id"),
                    "SUPERVISOR_REGISTRATION_NOT_CONFIRMED")
            self._registered = True
            return {"started": True, "status": "REGISTERED_WITH_EXISTING_SUPERVISOR",
                    "receipt_id": result["receipt_id"]}


def configure(store_path, rows, plan, readback, worker, *, execute_lifecycle):
    """Explicit controller call only, after authenticated code/data/runtime handoff.

    execute_lifecycle must hold the existing reentrant transaction lock and return
    its durable COMPLETED archive receipt. No legacy import occurs in this call.
    """
    require(callable(execute_lifecycle), "VERIFIED_LOCKED_LIFECYCLE_EXECUTOR_REQUIRED")
    worker._handoff()
    with SpecStore(store_path) as store:
        bind_worker(store, worker.collectors, installation_receipt=worker.receipt,
                    verify_installation=worker.verify_installation)
        scan = rows.snapshot()
        reconciled = crm_bridge.CrmBridge(store).reconcile_saved_rows(scan["rows"])
        require(not reconciled["needs_input"], "CRM_RECONCILIATION_NEEDS_INPUT")
    crm_bridge.configure_runtime_factory(str(store_path), read_current_row=rows,
        verify_readiness=plan.readiness, execute_lifecycle=execute_lifecycle,
        verify_readback=readback.verify, start_worker=worker.start,
        verify_page_change=plan.page_change)
    return {"status": "RUNTIME_CONFIGURED", "tracked": len(reconciled["tracked"]),
            "worker_started": False, "production_publication_performed": False}


class LockedLifecycle:
    """Bind the actual pinned legacy lifecycle, retain its lock, backup and recovery.

    Modules must already have been loaded by the verified server bootstrap. This
    adapter never imports application modules. A durable per-plan ledger refuses
    a second execution after an unknown outcome, including process death.
    """
    def __init__(self, *, root, rows, plan, readback, lifecycle, guard, publisher, ledger_path):
        self.root, self.rows, self.plan, self.readback = Path(root).absolute(), rows, plan, readback
        self.lifecycle, self.guard, self.publisher = lifecycle, guard, publisher
        self.ledger_path = Path(ledger_path).absolute()
        require(not self.ledger_path.exists() or not self.ledger_path.is_symlink(), "LEDGER_SYMLINK_FORBIDDEN")
        self._pins()

    def _pins(self):
        for name, expected in RUNTIME_PINS.items():
            require(hashlib.sha256(read_regular(self.root / name)).hexdigest() == expected,
                    "RUNTIME_SOURCE_PIN_CHANGED:" + name)
        for module, name in ((self.lifecycle, "card_lifecycle.py"),
                             (self.guard, "publish_transaction_guard.py"),
                             (self.publisher, "publikaciya.py")):
            require(Path(module.__file__).absolute() == self.root / name, "UNREVIEWED_LOADED_MODULE")
        for module, name, functions in (
                (self.lifecycle, "card_lifecycle.py", ("_transition", "_mutate", "recover_pending")),
                (self.guard, "publish_transaction_guard.py", ("_exclusive_lock",)),
                (self.publisher, "publikaciya.py", ("opublikovat",))):
            filename = str(self.root / name)
            compiled = compile(read_regular(self.root / name), filename, "exec", dont_inherit=True)
            definitions = {value.co_name: value for value in compiled.co_consts if isinstance(value, types.CodeType)}
            for function in functions:
                actual = inspect.unwrap(getattr(module, function))
                require(function in definitions and hasattr(actual, "__code__") and
                        actual.__code__ == definitions[function] and actual.__code__.co_filename == filename,
                        "LOADED_FUNCTION_DIFFERS_FROM_PIN:" + function)
        require(self.guard.LIFECYCLE_REENTRANT_LOCK is True
                and Path(self.guard.ROOT).absolute() == self.root
                and Path(self.guard.DB).absolute() == self.rows.path, "SHARED_LIFECYCLE_LOCK_SCOPE_REQUIRED")

    @contextmanager
    def _ledger(self):
        require(not any(p.is_symlink() for p in (self.ledger_path, *self.ledger_path.parents)),
                "LEDGER_SYMLINK_FORBIDDEN")
        db = sqlite3.connect(str(self.ledger_path), timeout=3)
        try:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("CREATE TABLE IF NOT EXISTS operations (operation_key TEXT PRIMARY KEY, "
                       "state TEXT NOT NULL, receipt TEXT)")
            db.commit()
            yield db
        finally:
            db.close()

    def __call__(self, ticket, row):
        require(digest(row) == ticket.crm_row_sha256, "LIFECYCLE_INPUT_PREIMAGE_MISMATCH")
        self._pins()
        op = self.plan.operation(ticket.uid, ticket.action, ticket.plan_id)
        require(all(op.get(k) == v for k, v in asdict(ticket).items()), "LIFECYCLE_APPROVED_SCOPE_MISMATCH")
        key = digest(asdict(ticket))
        with self.guard._exclusive_lock(), self._ledger() as ledger:
            self._pins()
            self.plan.load()  # reauthenticate current exclusive authority inside lock
            ledger.execute("BEGIN IMMEDIATE")
            prior = ledger.execute("SELECT state, receipt FROM operations WHERE operation_key=?", (key,)).fetchone()
            if prior:
                ledger.rollback()
                if prior[0] == "VERIFIED":
                    receipt = json.loads(prior[1])
                    self.readback.verify(ticket, receipt)
                    return {"ok": True, "receipt": receipt, "detail": "Попередню дію повторно перевірено."}
                raise BootstrapError("PRIOR_OPERATION_REQUIRES_RECONCILIATION")
            require(digest(self.rows(ticket.uid)) == ticket.crm_row_sha256, "LIFECYCLE_CURRENT_PREIMAGE_MISMATCH")
            ledger.execute("INSERT INTO operations VALUES(?, 'STARTED', NULL)", (key,))
            ledger.commit()
            # Crash after this point is never retried automatically.
            result = self.lifecycle._transition(row["id"], ticket.action, ticket.actor_id,
                publisher=self.publisher.opublikovat, guard=self.guard)
            if not isinstance(result, (tuple, list)) or len(result) < 2 or result[0] is not True:
                ledger.execute("UPDATE operations SET state='FAILED_REVIEW_REQUIRED' WHERE operation_key=?", (key,))
                ledger.commit()
                return {"ok": False, "detail": "Дію скасовано; потрібна перевірка журналу відновлення."}
            archive = self.rows.completed(ticket.uid, ticket.action, ticket.actor_id, ticket.crm_row_sha256)
            backup = Path(archive["backup_path"]).absolute()
            require(backup.parent == self.root / "rezerv_publikacii" / "SPEC_LIFECYCLE", "BACKUP_SCOPE")
            manifest_raw = read_regular(backup / "manifest.json")
            manifest = json.loads(manifest_raw)
            require(manifest.get("operation_id") == archive["operation_id"]
                    and manifest.get("state") == "COMPLETED"
                    and digest(manifest.get("row_before")) == ticket.crm_row_sha256, "DURABLE_COMPLETION_MISMATCH")
            receipt = {**asdict(ticket), "receipt_id": archive["operation_id"],
                "route_id": "pinned-card-lifecycle-rebuild10", "status": "READBACK_PENDING",
                "verified_at": datetime.now(timezone.utc).isoformat(),
                "backup_manifest_sha256": hashlib.sha256(manifest_raw).hexdigest()}
            if ticket.action == "publish":
                primary = next((target for target in op["readback"] if target.get("kind") == "primary"), None)
                require(primary, "PRIMARY_URL_REQUIRED")
                receipt["page_url"] = primary["url"]
            self.readback.verify(ticket, receipt)
            receipt["status"] = "PASS"
            if ticket.action == "publish":
                receipt.update(specification_visible=True, single_vin=True, shell_preserved=True)
            ledger.execute("UPDATE operations SET state='VERIFIED', receipt=? WHERE operation_key=?",
                (json.dumps(receipt, ensure_ascii=False, sort_keys=True), key))
            ledger.commit()
            return {"ok": True, "receipt": receipt,
                    "detail": "Зміни перевірено. " + receipt.get("page_url", "")}


def attach_public_sync(worker, runtime, outbox_path, *, authorize_sync, transport):
    """Bind the automatic specification-only outbox to the same supervisor tick."""
    from .sync import SpecSync
    require(worker.public_sync is None, "PUBLIC_SYNC_ALREADY_CONFIGURED")
    worker.public_sync = SpecSync(worker.store_path, worker.rows, runtime, outbox_path,
                                 authorize_sync=authorize_sync, transport=transport)
    return worker.public_sync

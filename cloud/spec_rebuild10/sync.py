"""Durable specification-only synchronization for already verified public cards.

No first publication, CRM mutation, legacy collector or process start exists here.
The verified controller authorizes each exact plan under the existing writer lock.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
import time
from urllib.parse import urlsplit

from . import crm_bridge, render
from .bootstrap import BootstrapError, HttpReadback, MAX_FILE, digest, read_regular, require
from .store import SpecStore, StoreError, _identity

SCHEMA = "UA-ART-SPEC-REBUILD10-PUBLIC-SYNC-1"


def sha(data):
    return hashlib.sha256(data).hexdigest()


class SyncOutbox:
    """One execution per accepted fact generation; unknown work never auto-retries."""
    def __init__(self, path):
        self.path = Path(path).absolute()
        require(not any(p.is_symlink() for p in (self.path, *self.path.parents)), "OUTBOX_SYMLINK")
        try:
            self.fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            self.fd = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        self.db = None
        try:
            self._check()
            self.db = sqlite3.connect(str(self.path), timeout=3)
            self.db.row_factory = sqlite3.Row
            self._check()
            tables = {row[0] for row in self.db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
            require(tables <= {"spec_sync"}, "OUTBOX_UNRELATED_DATABASE")
            if tables:
                columns = [row[1] for row in self.db.execute("PRAGMA table_info(spec_sync)")]
                require(columns == ["job_id", "uid", "generation_json", "state", "plan_json", "error", "receipt_json"],
                        "OUTBOX_SCHEMA_MISMATCH")
            self._check()
            self.db.execute("PRAGMA journal_mode=DELETE")
            self.db.execute("PRAGMA synchronous=FULL")
            self.db.execute("CREATE TABLE IF NOT EXISTS spec_sync (job_id TEXT PRIMARY KEY, uid TEXT NOT NULL, "
                "generation_json TEXT NOT NULL, state TEXT NOT NULL, plan_json TEXT, error TEXT, receipt_json TEXT)")
            self.db.commit()
            self._check()
        except BaseException:
            self.close()
            raise

    def _check(self):
        require(not any(p.is_symlink() for p in (self.path, *self.path.parents)), "OUTBOX_SYMLINK")
        held, current = os.fstat(self.fd), self.path.stat()
        require(stat.S_ISREG(held.st_mode) and held.st_nlink == current.st_nlink == 1
                and (held.st_dev, held.st_ino) == (current.st_dev, current.st_ino), "OUTBOX_FILE_CHANGED_OR_LINKED")

    def close(self):
        if self.db is not None:
            self.db.close()
            self.db = None
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def enqueue(self, generation):
        self._check()
        job_id = digest(generation)
        self.db.execute("INSERT OR IGNORE INTO spec_sync VALUES(?,?,?,'READY',NULL,NULL,NULL)",
            (job_id, generation["uid"], json.dumps(generation, sort_keys=True)))
        self.db.commit()
        return job_id

    def claim(self):
        self._check()
        self.db.execute("BEGIN IMMEDIATE")
        try:
            if self.db.execute("SELECT 1 FROM spec_sync WHERE state IN ('STARTED','FAILED_REVIEW_REQUIRED') LIMIT 1").fetchone():
                self.db.rollback()
                return {"status": "BLOCKED_SYNC_RECONCILIATION_REQUIRED"}
            row = self.db.execute("SELECT * FROM spec_sync WHERE state='READY' ORDER BY rowid LIMIT 1").fetchone()
            if row is None:
                self.db.rollback()
                return {"status": "IDLE"}
            self.db.execute("UPDATE spec_sync SET state='STARTED' WHERE job_id=?", (row["job_id"],))
            self.db.commit()
            return dict(row, status="CLAIMED", generation=json.loads(row["generation_json"]))
        except BaseException:
            self.db.rollback(); raise

    def plan(self, job_id, plan):
        self._check()
        self.db.execute("UPDATE spec_sync SET plan_json=? WHERE job_id=? AND state='STARTED'",
            (json.dumps(plan, ensure_ascii=False, sort_keys=True), job_id))
        self.db.commit()

    def finish(self, job_id, state, *, receipt=None, error=None):
        self._check()
        require(state in {"VERIFIED", "STALE_CANCELLED", "FAILED_REVIEW_REQUIRED"}, "OUTBOX_TERMINAL_STATE")
        self.db.execute("UPDATE spec_sync SET state=?,receipt_json=?,error=? WHERE job_id=? AND state='STARTED'",
            (state, json.dumps(receipt, sort_keys=True) if receipt else None, error, job_id))
        self.db.commit()


class SpecSync:
    def __init__(self, store_path, rows, runtime, outbox_path, *, authorize_sync, transport):
        require(callable(authorize_sync) and callable(transport), "VERIFIED_SYNC_CONTROLLER_AND_TRANSPORT_REQUIRED")
        self.store_path, self.rows, self.runtime = str(store_path), rows, runtime
        self.outbox_path, self.authorize, self.transport = outbox_path, authorize_sync, transport
        self.root, self.guard = runtime.root, runtime.guard

    @contextmanager
    def _outbox(self):
        outbox = SyncOutbox(self.outbox_path)
        try:
            yield outbox
        finally:
            outbox.close()

    def _state(self, store, uid):
        row = self.rows(uid)
        require(row is not None and row.get("published") in (1, True), "SYNC_DRAFT_OR_REMOVED_CARD")
        current_uid, identity = crm_bridge.identity_from_crm(row)
        vehicle = store.get_vehicle(uid)
        snapshot = store.get_publication_snapshot(uid)
        require(current_uid == uid and vehicle["published"] and not vehicle["tombstoned"]
                and snapshot is not None and snapshot["identity_hash"] == vehicle["identity_hash"]
                and snapshot["revision"] == vehicle["revision"]
                and _identity(identity)[1] == vehicle["identity_hash"], "SYNC_VERIFIED_CURRENT_PUBLICATION_REQUIRED")
        facts = store.get_facts(uid)
        require(facts, "SYNC_ACCEPTED_FACTS_REQUIRED")
        return row, vehicle, snapshot, facts

    def enqueue_changed(self):
        """Periodic scan repairs a crash between fact acceptance and outbox insert."""
        scan = self.rows.snapshot()
        require(scan["complete"] is True, "SYNC_COMPLETE_CRM_SCAN_REQUIRED")
        queued = []
        with SpecStore(self.store_path) as store, self._outbox() as outbox:
            for row in scan["rows"]:
                if row.get("published") not in (1, True):
                    continue
                try:
                    uid = crm_bridge.canonical_uid(row.get("auto_number"))
                    current, vehicle, snapshot, facts = self._state(store, uid)
                except (BootstrapError, StoreError, crm_bridge.BridgeError):
                    continue  # A legacy published flag is never initial-publication authority.
                fact_digest = store.facts_digest(uid)
                if snapshot["facts_digest"] == fact_digest:
                    continue
                generation = {"uid": uid, "revision": vehicle["revision"],
                    "identity_hash": vehicle["identity_hash"], "facts_digest": fact_digest,
                    "previous_snapshot_id": snapshot["id"], "crm_row_sha256": digest(current)}
                queued.append(outbox.enqueue(generation))
        return {"queued": queued, "first_publication_performed": False}

    def _current(self, store, generation):
        row, vehicle, snapshot, facts = self._state(store, generation["uid"])
        expected = {"uid": generation["uid"], "revision": vehicle["revision"],
            "identity_hash": vehicle["identity_hash"], "facts_digest": store.facts_digest(generation["uid"]),
            "previous_snapshot_id": snapshot["id"], "crm_row_sha256": digest(row)}
        require(expected == generation, "SYNC_GENERATION_CHANGED")
        return row, snapshot, facts

    def _authorize(self, plan, phase):
        self.runtime._pins()
        require(self.authorize(plan, phase) is True, "SYNC_CURRENT_EXACT_PLAN_AUTHORITY_REQUIRED")

    def _prepare(self, store, job):
        generation, uid = job["generation"], job["uid"]
        row, snapshot, facts = self._current(store, generation)
        before, after, protected = {}, {}, {}
        for folder in ("video", "site"):
            path = self.root / folder / (uid + ".html")
            data = read_regular(path)
            text = data.decode("utf-8")
            render.validate_page(text, uid, snapshot["facts"], previous=text)
            require(render.shell_guard._main_vin(render.shell_guard._Page(text), uid)[1] ==
                    str(row["vin"]).strip().upper(), "SYNC_PRIMARY_VIN_DIFFERS_FROM_CRM")
            candidate = render.compose_page(text, uid, facts).encode("utf-8")
            render.validate_page(candidate.decode(), uid, facts, previous=text)
            before[path], after[path] = data, candidate
            for name in (uid + "-diag.html", "katalog.html"):
                other = self.root / folder / name
                protected[other] = read_regular(other)
        plan = {"schema": SCHEMA, "scope": "EXISTING_PUBLISHED_SPEC_REGION_ONLY", "job_id": job["job_id"],
            "generation": generation, "crm_row_sha256": digest(row),
            "files": {str(p.relative_to(self.root)): {"before_sha256": sha(before[p]), "after_sha256": sha(after[p])}
                for p in before},
            "protected": {str(p.relative_to(self.root)): sha(data) for p, data in protected.items()},
            "render_facts_sha256": render.facts_digest(facts), "first_publication": False,
            "owner_manual_publish_required": False}
        plan["plan_sha256"] = digest(plan)
        return plan, before, after, protected, facts

    @staticmethod
    def _atomic_exact(path, data, mode):
        # Used only for exact manifest backups or hash-bound rollback; normal
        # forward publication always invokes the existing guarded atomic writer.
        fd, name = tempfile.mkstemp(prefix=".spec-sync-", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data); os.fchmod(stream.fileno(), mode); stream.flush(); os.fsync(stream.fileno())
            os.replace(name, path)
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def _backup(self, plan, before):
        directory = self.root / "rezerv_publikacii" / "SPEC_REBUILD10_SYNC" / plan["job_id"]
        require(not any(p.is_symlink() for p in (directory, *directory.parents)), "SYNC_BACKUP_SYMLINK")
        directory.mkdir(mode=0o700, parents=True, exist_ok=False)
        modes = {}
        for path, data in before.items():
            name = path.parent.name + "-" + path.name
            mode = path.stat().st_mode & 0o777
            self._atomic_exact(directory / name, data, 0o600)
            modes[path] = mode
        manifest = {"plan": plan, "modes": {str(p.relative_to(self.root)): mode for p, mode in modes.items()}}
        self._atomic_exact(directory / "manifest.json", json.dumps(manifest, sort_keys=True).encode(), 0o600)
        return directory, modes

    def _readback(self, plan, after, protected, facts):
        uid = plan["generation"]["uid"]
        responses = {}
        expected = {uid + ".html": after[self.root / "video" / (uid + ".html")],
            uid + "-diag.html": protected[self.root / "video" / (uid + "-diag.html")],
            "katalog.html": protected[self.root / "video" / "katalog.html"]}
        for name, data in expected.items():
            url = "https://www.uaart.com.ua/video/" + name
            result = self.transport(url, timeout_seconds=15, max_bytes=MAX_FILE)
            require(isinstance(result, HttpReadback) and result.url == url and result.status == 200
                    and isinstance(result.body, bytes) and len(result.body) <= MAX_FILE and result.body == data,
                    "SYNC_PUBLIC_READBACK_MISMATCH")
            responses[name] = sha(result.body)
        primary = expected[uid + ".html"].decode()
        render.validate_page(primary, uid, facts, previous=primary)
        catalog = render.shell_guard._Page(expected["katalog.html"].decode())
        require(any(node.tag == "a" and urlsplit(node.attrs.get("href") or "").path.rsplit("/", 1)[-1]
                    == uid + ".html" for node in catalog.nodes), "SYNC_PUBLIC_CATALOG_MISSING_CARD")
        return responses

    def run_once(self):
        """At most one durable job; no lease-based repeat of ambiguous HTML writes."""
        with self._outbox() as outbox:
            job = outbox.claim()
            if job["status"] != "CLAIMED":
                return job
            changed, plan, backup = [], None, None
            try:
                with self.guard._exclusive_lock(), SpecStore(self.store_path) as store:
                    try:
                        plan, before, after, protected, facts = self._prepare(store, job)
                    except (BootstrapError, StoreError) as exc:
                        if str(exc) in {"SYNC_GENERATION_CHANGED", "SYNC_DRAFT_OR_REMOVED_CARD",
                                        "SYNC_VERIFIED_CURRENT_PUBLICATION_REQUIRED", "unknown or deleted vehicle"}:
                            outbox.finish(job["job_id"], "STALE_CANCELLED")
                            return {"status": "STALE_CANCELLED", "uid": job["uid"], "page_writes": 0}
                        raise
                    self._authorize(plan, "BEFORE_BACKUP")
                    outbox.plan(job["job_id"], plan)
                    backup, modes = self._backup(plan, before)
                    receipt_commit_started = False
                    try:
                        for path, candidate in after.items():
                            self._current(store, job["generation"])
                            self._authorize(plan, "BEFORE_WRITE:" + str(path.relative_to(self.root)))
                            require(read_regular(path) == before[path], "SYNC_PREIMAGE_CHANGED")
                            if candidate != before[path]:
                                # This calls the current canonical guard; no full-card bypass.
                                changed.append(path)  # Persisted plan + write intent precede a possible replace-then-error.
                                self.guard._atomic(path, candidate, modes[path])
                        self._current(store, job["generation"])
                        require(all(read_regular(p) == value for p, value in after.items()), "SYNC_LOCAL_READBACK_MISMATCH")
                        require(all(read_regular(p) == value for p, value in protected.items()), "SYNC_PROTECTED_SURFACE_CHANGED")
                        self._authorize(plan, "BEFORE_PUBLIC_READBACK")
                        public = self._readback(plan, after, protected, facts)
                        self._current(store, job["generation"])
                        self._authorize(plan, "BEFORE_RECEIPT_COMMIT")
                        receipt = {**job["generation"], "status": "PASS", "action": "sync", "plan_id": plan["plan_sha256"],
                            "receipt_id": "spec-sync-" + job["job_id"], "route_id": "existing-reentrant-spec-sync",
                            "page_url": "https://www.uaart.com.ua/video/" + job["uid"] + ".html",
                            "verified_at": datetime.now(timezone.utc).isoformat(), "specification_visible": True,
                            "single_vin": True, "shell_preserved": True, "public_sha256": public}
                        receipt_commit_started = True
                        store.mark_publication_verified(job["uid"], job["generation"]["revision"], receipt)
                    except Exception:
                        if receipt_commit_started:
                            # SQLite COMMIT may have succeeded before an exception.
                            # Keep valid postimages; reconciliation checks the exact
                            # durable receipt. Never restore HTML behind that receipt.
                            raise BootstrapError("SYNC_RECEIPT_COMMIT_REQUIRES_RECONCILIATION")
                        if changed:
                            self._authorize(plan, "ROLLBACK_EXACT_OWN_POSTIMAGES")
                            restore = []
                            # Preflight EVERY intended file and saved preimage before
                            # any compensation. A foreign file aborts the whole rollback.
                            for path in reversed(changed):
                                current = read_regular(path)
                                require(current in (before[path], after[path]), "SYNC_ROLLBACK_CONCURRENT_CHANGE")
                                saved = read_regular(backup / (path.parent.name + "-" + path.name))
                                require(saved == before[path] and sha(saved) == plan["files"][str(path.relative_to(self.root))]["before_sha256"],
                                        "SYNC_ROLLBACK_BACKUP_MISMATCH")
                                if current == after[path] and current != before[path]:
                                    restore.append((path, saved))
                            for path, saved in restore:
                                require(read_regular(path) == after[path], "SYNC_ROLLBACK_CONCURRENT_CHANGE")
                                self._atomic_exact(path, saved, modes[path])
                            require(all(read_regular(p) == value for p, value in before.items()), "SYNC_ROLLBACK_READBACK_MISMATCH")
                        raise
                    outbox.finish(job["job_id"], "VERIFIED", receipt=receipt)
                    return {"status": "VERIFIED", "uid": job["uid"], "page_writes": len(changed),
                            "receipt_id": receipt["receipt_id"], "first_publication_performed": False}
            except Exception as exc:
                # Never copy provider exception bodies or credentials into status.
                code = str(exc) if isinstance(exc, BootstrapError) else "SYNC_EXECUTION_REQUIRES_REVIEW"
                outbox.finish(job["job_id"], "FAILED_REVIEW_REQUIRED", error=code)
                return {"status": "FAILED_REVIEW_REQUIRED", "uid": job["uid"], "error": code,
                        "automatic_retry": False, "first_publication_performed": False}

    def blocked(self):
        with self._outbox() as outbox:
            return outbox.db.execute("SELECT 1 FROM spec_sync WHERE state IN ('STARTED','FAILED_REVIEW_REQUIRED') LIMIT 1").fetchone() is not None

    def tick(self):
        enqueued = self.enqueue_changed()
        return {"outbox": enqueued, "sync": self.run_once()}

"""Durable native visibility transitions; no import-time I/O.

Local receipts attest exact pinned files only. Live URL retirement is a separate
deployment acceptance fact. No source media or CRM record is removed here.
"""
from __future__ import annotations

import hashlib
import base64
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import tempfile
import time
import threading
import contextlib

from publication_fence import publication_fence

_authority = threading.local()


def require_active_authority():
    check = getattr(_authority, "check", None)
    if check is not None:
        _check_authority_owner()
        if not getattr(_authority, "recovery", False):
            check()


def _check_authority_owner():
    if getattr(_authority, "owner", None) != (os.getpid(), threading.get_ident()):
        raise VisibilityError("VISIBILITY_AUTHORITY_OWNER_CHANGED")


@contextlib.contextmanager
def authority_scope(check, recovery_check=None):
    prior = getattr(_authority, "check", None)
    prior_recovery = getattr(_authority, "recovery_check", None)
    prior_owner = getattr(_authority, "owner", None)
    _authority.check = check
    _authority.recovery_check = recovery_check
    _authority.owner = (os.getpid(), threading.get_ident())
    try:
        check()
        yield
    finally:
        _authority.check = prior
        _authority.recovery_check = prior_recovery
        _authority.owner = prior_owner


@contextlib.contextmanager
def recovery_scope():
    """Only an existing fenced snapshot restore may finish after TTL expiry."""
    if getattr(_authority, "check", None) is None:
        yield
        return
    _check_authority_owner()
    from publication_fence import require_publication_fence
    require_publication_fence()
    check = getattr(_authority, "recovery_check", None)
    if not callable(check):
        raise VisibilityError("JOURNALED_VISIBILITY_RECOVERY_REQUIRED")
    check()
    prior = getattr(_authority, "recovery", False)
    _authority.recovery = True
    try:
        yield
    finally:
        _authority.recovery = prior


class VisibilityError(RuntimeError):
    pass


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def row_sha(row):
    return digest(encoded(row))


def safe_path(path):
    path = Path(path)
    if not path.is_absolute() or path.parent.resolve(strict=True) != path.parent or path.is_symlink():
        raise VisibilityError("UNSAFE_VISIBILITY_PATH")
    if path.exists() and not stat.S_ISREG(path.stat().st_mode):
        raise VisibilityError("REGULAR_VISIBILITY_FILE_REQUIRED")
    return path


def read(path):
    path = safe_path(path)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as handle:
        data = handle.read(16 * 1024 * 1024 + 1)
    if len(data) > 16 * 1024 * 1024:
        raise VisibilityError("VISIBILITY_FILE_TOO_LARGE")
    return data


def atomic(path, value):
    atomic_bytes(path, encoded(value), 0o600, forward=False)


def atomic_bytes(path, data, mode, *, forward=True):
    path = safe_path(path)
    descriptor, name = tempfile.mkstemp(prefix=".visibility-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data); handle.flush(); os.fsync(handle.fileno())
        os.chmod(name, mode)
        if forward:
            require_active_authority()
        os.replace(name, path)
        descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def current_row(binding, car_id):
    safe_path(binding.db_path)
    with sqlite3.connect(binding.db_path.as_uri() + "?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        value = conn.execute("SELECT * FROM cars WHERE id=?", (car_id,)).fetchone()
    if value is None:
        raise VisibilityError("VISIBILITY_CAR_NOT_FOUND")
    return dict(value)


def _code(row):
    code = row.get("auto_number")
    if not isinstance(code, str) or re.fullmatch(r"UA-[0-9]{4}", code) is None:
        raise VisibilityError("PUBLIC_VISIBILITY_IDENTITY_REQUIRED")
    return code


def _paths(binding, code):
    """Exact legacy roots plus installer-verified runtime surfaces.

    Unrecognised code-owned HTML fails rather than guessing whether it is an
    alias, a media document, or a different public representation.
    """
    root = binding.db_path.parent
    cards, shared = set(), set()
    pattern = re.compile(re.escape(code) + r"(?:-diag)?(?:-[0-9a-f]{6,10})?\.html$")
    for folder in (root / "video", root / "site"):
        if folder.resolve(strict=True) != folder:
            raise VisibilityError("UNSAFE_VISIBILITY_ROOT")
        cards.update((folder / (code + ".html"), folder / (code + "-diag.html")))
        for path in folder.glob(code + "*.html"):
            if not pattern.fullmatch(path.name):
                raise VisibilityError("UNBOUND_PUBLIC_ALIAS")
            cards.add(path)
        shared.add(folder / "katalog.html")
    resolver = getattr(binding, "resolve_visibility_surfaces", None) or binding.resolve_surfaces
    for surface in resolver(code):
        path = safe_path(surface.path)
        if surface.kind in {"CARD", "DIAGNOSTIC"}:
            if not pattern.fullmatch(path.name):
                raise VisibilityError("UNBOUND_CARD_ROUTE")
            cards.add(path)
        elif surface.kind in {"CATALOG", "HOME"}:
            shared.add(path)
        else:
            raise VisibilityError("UNSUPPORTED_VISIBILITY_SURFACE")
    for path in cards | shared:
        safe_path(path)
    return sorted(cards), sorted(shared)


def verify_hidden(binding, row, event=None):
    """Observe local closure; no mutation and no fabricated HTTP evidence."""
    if row.get("published") not in (None, 0):
        raise VisibilityError("HIDDEN_ROW_REQUIRED")
    code = _code(row)
    cards, shared = _paths(binding, code)
    if any(path.exists() for path in cards):
        raise VisibilityError("PUBLIC_CARD_NOT_RETIRED")
    files = {}
    for path in shared:
        content = read(path)
        if listing_present(content.decode("utf-8"), code):
            raise VisibilityError("PUBLIC_LISTING_NOT_RETIRED")
        files[str(path)] = digest(content)
    proof = {"car_id": row["id"], "published": 0, "row_sha256": row_sha(row),
             "car_code": code, "public_projection": "NOT_APPLICABLE",
             "retired_public_views_verified": True,
             "verification_scope": "LOCAL_PINNED_ROUTE_FILES", "live_http_verified": False,
             "absent": [str(path) for path in cards], "shared_sha256": files}
    proof["visibility_receipt_sha256"] = digest(encoded(proof))
    return proof


def listing_present(source, code):
    """Public advertisement identity excludes retained generic media assets."""
    from html.parser import HTMLParser
    from urllib.parse import urlsplit
    pattern = re.compile(re.escape(code) + r"(?:-diag)?(?:-[0-9a-f]{6,10})?\.html")
    class Listings(HTMLParser):
        present = False
        def handle_starttag(self, tag, attributes):
            attrs = dict(attributes)
            if (pattern.fullmatch(urlsplit(attrs.get("href") or "").path.rsplit("/", 1)[-1])
                    or any(attrs.get(name) == code for name in ("data-ua-card", "data-ua", "data-car-code"))):
                self.present = True
    parser = Listings(); parser.feed(source); parser.close()
    return parser.present


def retire_lists(binding, code, operation_id):
    """Remove only the exact car's existing tile; never render another price.

    Uses the installed catalog parser/counter implementation. Every other tile
    survives byte-for-byte; a residual unknown representation fails closed.
    Planning precedes the first write, and recorded file preimages guard CAS.
    """
    from uaart_price_sync_runtime import _Anchors
    from urllib.parse import urlsplit
    import ua_site_counters as counters
    _, paths = _paths(binding, code)
    plan_path = binding.journal_root / "visibility" / (operation_id + ".retirement")
    if plan_path.exists():
        plan = json.loads(read(plan_path))
        if (plan["operation_id"] != operation_id or plan["code"] != code
                or set(plan["files"]) != {str(path) for path in paths}):
            raise VisibilityError("RETIREMENT_ROUTE_BINDING_CHANGED")
        for name, item in plan["files"].items():
            path = safe_path(name)
            actual = digest(read(path))
            data = base64.b64decode(item["after_base64"], validate=True)
            if digest(data) != item["after_sha256"]:
                raise VisibilityError("RETIREMENT_PLAN_HASH_MISMATCH")
            if actual == item["after_sha256"]:
                continue
            if actual != item["before_sha256"]:
                raise VisibilityError("NEWER_PUBLIC_LIST_PRESERVED")
            atomic_bytes(path, data, item["mode"])
        return True, "Retirement reconciled from exact saved pre/postimages"
    proposed = {}
    records = None
    for path in paths:
        before = read(path)
        source = before.decode("utf-8")
        parsed = _Anchors(source)
        anchors = [(left, right) for left, right, href in parsed.anchors
                   if re.fullmatch(re.escape(code) + r"(?:-diag)?(?:-[0-9a-f]{6,10})?\.html",
                                   urlsplit(href).path.rsplit("/", 1)[-1])]
        articles = [(left, right) for left, right in parsed.articles
                    if any(left <= start < end <= right for start, end in anchors)]
        spans = sorted(set(articles + [(left, right) for left, right in anchors
                            if not any(start <= left < right <= end for start, end in articles)]))
        for left, right in reversed(spans):
            source = source[:left] + source[right:]
        if listing_present(source, code):
            raise VisibilityError("UNRECOGNIZED_PUBLIC_LISTING")
        if path.name == "katalog.html":
            original_records, _ = counters.catalog_snapshot(before.decode("utf-8"))
            current_records, _ = counters.catalog_snapshot(source)
            if current_records != {key: value for key, value in original_records.items() if key != code}:
                raise VisibilityError("UNRELATED_CATALOG_TILE_CHANGED")
            if records is not None and records != current_records:
                raise VisibilityError("CATALOG_MIRROR_MEMBERSHIP_MISMATCH")
            records = current_records
        proposed[path] = (before, source)
    if records is None:
        raise VisibilityError("CANONICAL_CATALOG_REQUIRED")
    counts = {"all": len(records), **{stage: 0 for stage in counters.STAGES}}
    for stage in records.values():
        if stage:
            counts[stage] += 1
    planned = []
    for path, (before, source) in proposed.items():
        if path.name == "katalog.html":
            result = counters.patch_catalog(source, counts)
        elif path.name == "index.html":
            result = counters.patch_home(source, counts)
        else:
            raise VisibilityError("UNSUPPORTED_SHARED_VISIBILITY_PATH")
        planned.append((path, before, result.encode("utf-8")))
    plan = {"operation_id": operation_id, "code": code, "files": {
        str(path): {"before_sha256": digest(before), "after_sha256": digest(after),
                    "after_base64": base64.b64encode(after).decode(), "mode": path.stat().st_mode & 0o777}
        for path, before, after in planned}}
    atomic(plan_path, plan)
    for path, before, after in planned:
        if read(path) != before:
            raise VisibilityError("NEWER_PUBLIC_LIST_PRESERVED")
        if before != after:
            atomic_bytes(path, after, path.stat().st_mode & 0o777)
    return True, "Exact listing retired; other tiles preserved"


class Lifecycle:
    """One native request, one durable ID, bounded pending-operation drain.

    An ambiguous publication is verified on resume and never repeated. Known
    file retirement resumes by inspecting the persisted preimages. Failures do
    not restore old CRM fields over later operator changes.
    """
    def __init__(self, binding, *, publish, rebuild, verify_published,
                 verify_shared, ready, worker=None, fence=None):
        self.binding = binding
        self.publish, self.rebuild = publish, rebuild
        self.verify_published, self.verify_shared, self.ready = verify_published, verify_shared, ready
        if worker is None:
            from uaart_price_sync_runtime import V5Worker
            worker = V5Worker(binding)
        self.worker = worker
        self.fence = fence or publication_fence
        self.directory = binding.journal_root / "visibility"
        self.directory.mkdir(mode=0o700, exist_ok=True)
        if self.directory.is_symlink() or self.directory.resolve() != self.directory or self.directory.stat().st_mode & 0o077:
            raise VisibilityError("PRIVATE_VISIBILITY_JOURNAL_REQUIRED")

    def intent(self, key):
        if re.fullmatch(r"[a-f0-9]{64}", key or "") is None:
            raise VisibilityError("VISIBILITY_OPERATION_ID_REQUIRED")
        path = self.directory / (key + ".json")
        return json.loads(read(path)) if path.exists() else None

    def save(self, record):
        atomic(self.directory / (record["operation_id"] + ".json"), record)

    def _pending(self, cid):
        import uaart_price_sync_outbox as outbox
        with self.worker.connection() as conn:
            return [item[0] for item in conn.execute(
                "SELECT event_key FROM " + outbox.V5_TABLE + " WHERE car_id=? AND state!='COMPLETED' ORDER BY sequence", (cid,))]

    def _after_retirement(self, result):
        if result["target"] or current_row(self.binding, result["car_id"])["published"] != 0:
            return result
        # Never hold a publication/per-car lock while calling price recovery.
        # The original visibility receipt remains immutable; these are fresh
        # results of continuing the original accepted price operation IDs.
        pending = self._pending(result["car_id"])
        if len(pending) > 32:
            return dict(result, price_reconciliation="BOUNDED_DRAIN_DEFERRED")
        outcomes = []
        for key in pending:
            reconcile = getattr(self.worker, "reconcile_hidden_operation", None)
            import uaart_price_sync_outbox as outbox
            with self.worker.connection() as conn:
                checkpoint = conn.execute("SELECT state FROM " + outbox.V5_TABLE + " WHERE event_key=?", (key,)).fetchone()
            recoverable = checkpoint and checkpoint[0] in {"DB_COMMITTED", "SITE_PUBLISHED", "VERIFIED"}
            outcome = (reconcile(key) if callable(reconcile) and recoverable
                       else self.worker.process_operation(key))
            outcomes.append(outcome)
            if outcome.get("state") != "COMPLETED":
                break
        return dict(result, price_reconciliation=outcomes)

    def transition(self, *, key, car_id, target, actor_id, status=None):
        if type(car_id) is not int or car_id <= 0 or type(target) is not int or target not in (0, 1) or status not in (None, "sold"):
            raise VisibilityError("VISIBILITY_REQUEST_INVALID")
        old = self.intent(key)
        if old:
            if (old["car_id"], old["target"], old["actor_id"], old["status"]) != (car_id, target, actor_id, status):
                raise VisibilityError("VISIBILITY_REQUEST_ID_COLLISION")
            if old["state"] == "VERIFIED":
                return self._after_retirement(dict(old, replay=True))
        # Network/worker operations happen outside both publication and DB locks.
        pending = self._pending(car_id) if target else []
        if len(pending) > 32:
            raise VisibilityError("VISIBILITY_PENDING_DRAIN_BOUND_EXCEEDED")
        for event_key in pending:
            result = self.worker.process_operation(event_key)
            if result.get("state") != "COMPLETED":
                raise VisibilityError("VISIBILITY_ACCEPTED_PRICE_PENDING")
        authorizer = getattr(self.binding, "authorize_visibility", None)
        if not callable(authorizer):
            raise VisibilityError("FRESH_VISIBILITY_AUTHORITY_REQUIRED")
        authority = authorizer(car_id, actor_id)
        if (authority.get("car_id") != car_id or authority.get("actor_id") != actor_id
                or authority.get("permission") != "EDIT_CAR"
                or authority.get("writer_fence_verified") is not True):
            raise VisibilityError("VISIBILITY_AUTHORITY_MISMATCH")
        def check_authority():
            clock = getattr(self.binding, "clock", None) or (lambda: time.time_ns() // 1000000)
            now = clock()
            if not authority.get("observed_ms", now + 1) <= now < authority.get("expires_ms", 0):
                raise VisibilityError("VISIBILITY_AUTHORITY_EXPIRED")
        def check_recovery():
            record = self.intent(key)
            revisions = [json.loads(read(path)) for path in self.directory.glob("*.json")]
            latest = max((item["revision"] for item in revisions if item["car_id"] == car_id), default=0)
            row = current_row(self.binding, car_id)
            if (record is None or record["car_id"] != car_id or record["revision"] != latest
                    or record["state"] not in {"PROJECTION_STARTED", "PROJECTION_WRITTEN"}
                    or row_sha(row) != record.get("projection_row_sha256")):
                raise VisibilityError("VISIBILITY_RECOVERY_EPOCH_CONFLICT")
        with self.worker.lock(self.binding.journal_root / ("car_%d.lock" % car_id)), self.fence(), authority_scope(check_authority, check_recovery):
            if target and self._pending(car_id):
                raise VisibilityError("VISIBILITY_NEW_PRICE_PENDING")
            row = current_row(self.binding, car_id)
            code = _code(row)
            if authority.get("identity", {}).get("auto_number") != code:
                raise VisibilityError("VISIBILITY_AUTHORITY_IDENTITY_CHANGED")
            old = self.intent(key)
            records = [json.loads(read(path)) for path in self.directory.glob("*.json")]
            prior = sorted((item for item in records if item["car_id"] == car_id), key=lambda item: item["revision"])
            if old is None:
                if prior and prior[-1]["state"] != "VERIFIED":
                    raise VisibilityError("PRIOR_VISIBILITY_OUTCOME_REQUIRED")
                if target and self.ready(row):
                    raise VisibilityError("PUBLIC_CARD_NOT_READY")
                cards, _ = _paths(self.binding, code)
                before = {str(path): digest(read(path)) for path in cards if path.exists()}
                old = {"operation_id": key, "car_id": car_id, "car_code": code, "target": target,
                       "actor_id": actor_id, "status": status, "before_published": row["published"],
                       "before_status": row.get("status"), "revision": 1 + (prior[-1]["revision"] if prior else 0),
                       "state": "PREPARED", "retire_sha256": before, "row_before_sha256": row_sha(row)}
                self.save(old)
            elif prior and prior[-1]["operation_id"] != key:
                raise VisibilityError("NEWER_VISIBILITY_REVISION_PRESERVED")
            if old["state"] == "PREPARED":
                # This is also recovery after a lost commit response. No write
                # occurs if the exact requested values are already present.
                with self.worker.connection() as conn:
                    conn.execute("BEGIN IMMEDIATE")
                    import uaart_price_sync_outbox as outbox
                    if target and conn.execute("SELECT 1 FROM " + outbox.V5_TABLE +
                                    " WHERE car_id=? AND state!='COMPLETED' LIMIT 1", (car_id,)).fetchone():
                        raise VisibilityError("VISIBILITY_NEW_PRICE_PENDING")
                    conn.row_factory = sqlite3.Row
                    row = dict(conn.execute("SELECT * FROM cars WHERE id=?", (car_id,)).fetchone())
                    if row["published"] not in (old["before_published"], target):
                        raise VisibilityError("VISIBILITY_EXTERNAL_STATUS_CONFLICT")
                    if status and row.get("status") not in (old["before_status"], status):
                        raise VisibilityError("VISIBILITY_NEW_OPERATOR_STATUS_PRESERVED")
                    if row["published"] != target:
                        count = conn.execute("UPDATE cars SET published=? WHERE id=? AND published IS ?", (target, car_id, row["published"])).rowcount
                        if count != 1:
                            raise VisibilityError("VISIBILITY_COMPARE_AND_SET_FAILED")
                    if status and row.get("status") != status:
                        count = conn.execute("UPDATE cars SET status=? WHERE id=? AND status IS ?", (status, car_id, row["status"])).rowcount
                        if count != 1:
                            raise VisibilityError("VISIBILITY_STATUS_COMPARE_AND_SET_FAILED")
                    require_active_authority()
                    conn.commit()
                old["state"] = "DB_COMMITTED"; self.save(old)
            row = current_row(self.binding, car_id)
            if (row["published"] != target or _code(row) != old["car_code"]
                    or (status is not None and row.get("status") != status)):
                raise VisibilityError("VISIBILITY_NEW_OPERATOR_CHANGE_PRESERVED")
            if not target:
                for name, expected in old["retire_sha256"].items():
                    path = safe_path(name)
                    if path.exists():
                        if digest(read(path)) != expected:
                            raise VisibilityError("VISIBILITY_NEW_PUBLIC_FILE_PRESERVED")
                        require_active_authority()
                        path.unlink()
                        descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
                        try:
                            os.fsync(descriptor)
                        finally:
                            os.close(descriptor)
            if old["state"] == "DB_COMMITTED":
                old["state"] = "PROJECTION_STARTED"
                old["projection_row_sha256"] = row_sha(row)
                self.save(old)
                require_active_authority()
                ok, detail = self.publish(code) if target else self.rebuild(code, key)
                if ok is not True:
                    # Canonical tuple failure is a known outcome: its guard
                    # restored its own snapshot or refused before any write.
                    # Exceptions/interrupts retain PROJECTION_STARTED instead.
                    old["failure"] = str(detail)[:2000]
                    old["state"] = "DB_COMMITTED"; self.save(old)
                    raise VisibilityError("CANONICAL_VISIBILITY_PROJECTION_FAILED")
                old["state"] = "PROJECTION_WRITTEN"; self.save(old)
            elif (not target and old["state"] == "PROJECTION_STARTED"
                  and (self.directory / (key + ".retirement")).exists()):
                # Retirements have exact persisted file pre/postimages. Resume
                # only by comparing each actual path against that same plan.
                ok, _ = self.rebuild(code, key)
                if ok is not True:
                    raise VisibilityError("RETIREMENT_RECONCILIATION_FAILED")
            # On uncertain PROJECTION_STARTED, inspect only. The unknown write
            # is never repeated, and a failed inspection leaves its ID open.
            self.verify_shared(code)
            row = current_row(self.binding, car_id)
            if row["published"] != target:
                raise VisibilityError("VISIBILITY_CHANGED_DURING_VERIFICATION")
            proof = self.verify_published(code) if target else verify_hidden(self.binding, row)
            old.update(state="VERIFIED", row_verified_sha256=row_sha(row), proof=proof,
                       verification_scope="LOCAL_PINNED_ROUTE_FILES", live_http_verified=False)
            require_active_authority()
            old["receipt_sha256"] = digest(encoded(old)); self.save(old)
        return self._after_retirement(old)


def handoff_spec_once(binding, result, schedule):
    """Preserve the existing async spec handoff without replaying unknown enqueue.

    SCHEDULED means the existing event-loop task was scheduled, not that the
    specification job or supplier work completed. The separate ledger never
    alters the accepted visibility receipt.
    """
    if result.get("state") != "VERIFIED" or result.get("target") != 1 or result.get("replay"):
        return "NOT_REQUESTED"
    key = result["operation_id"]
    if re.fullmatch(r"[a-f0-9]{64}", key) is None:
        raise VisibilityError("VISIBILITY_OPERATION_ID_REQUIRED")
    path = binding.journal_root / "visibility" / (key + ".spec")
    with publication_fence():
        if path.exists():
            return json.loads(read(path))["state"]
        row = current_row(binding, result["car_id"])
        if row["published"] != 1 or _code(row) != result["car_code"]:
            raise VisibilityError("SPEC_HANDOFF_VISIBILITY_CHANGED")
        record = {"operation_id": key, "car_id": row["id"], "car_code": result["car_code"],
                  "state": "STARTED", "queue_completion_verified": False}
        atomic(path, record)
        schedule(record["car_code"])
        record["state"] = "SCHEDULED"; atomic(path, record)
        return record["state"]


def native(binding, ready):
    import publikaciya
    import publish_transaction_guard as guard

    def verify_shared(code):
        import ua_site_counters as counters
        rows, _ = guard._row_map()
        counts = None
        for folder in guard.ROOTS:
            source = read(folder / "katalog.html").decode("utf-8")
            # Visibility retirement cannot validate every unrelated price
            # while that car has a pending edit. Validate identity and counts;
            # exact source-span removal already preserves other price bytes.
            records, current = counters.catalog_snapshot(source)
            if set(records) != set(rows):
                raise VisibilityError("CURRENT_CATALOG_MEMBERSHIP_REQUIRED")
            if any(records[identifier] != counters.ALIASES.get(guard._category(guard._stage(rows[identifier])))
                   for identifier in records):
                raise VisibilityError("CURRENT_CATALOG_STAGES_REQUIRED")
            if counts is not None and current != counts:
                raise VisibilityError("CURRENT_CATALOG_COUNTS_MISMATCH")
            counts = current
            if counters.patch_catalog(source, counts) != source:
                raise VisibilityError("CURRENT_CATALOG_COUNTERS_REQUIRED")
        resolver = getattr(binding, "resolve_visibility_surfaces", None) or binding.resolve_surfaces
        for surface in resolver(code):
            if surface.kind == "HOME":
                source = read(surface.path).decode("utf-8")
                if counters.patch_home(source, counts) != source:
                    raise VisibilityError("CURRENT_VISIBILITY_COUNTERS_REQUIRED")

    return Lifecycle(binding, publish=publikaciya.opublikovat, rebuild=lambda code, key: retire_lists(binding, code, key),
                     verify_published=lambda code: guard._verify_bundle([code]),
                     verify_shared=verify_shared, ready=ready)

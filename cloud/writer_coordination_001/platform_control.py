"""Bounded PythonAnywhere task configuration coordination; never runs on import.

This verifies task *configuration*. Disabled schedules can already have running
children. A separate, current server/process fence is mandatory before any data
write. No function here clears HALT, edits application data, or proves quiescence.
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
import urllib.error
import urllib.request

BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
MAX_BYTES = 262144
JOURNAL_ROOT = Path("/home/Carix/autopilot_state/writer_coordination_001")
KNOWN = {
    ("always_on", 266084): {"command": "python3.10 /home/Carix/start_safe.py", "description": ""},
    ("schedule", 1502215): {
        "command": "cd /home/Carix/autopilot_inbox/cloud/seo_rehab_guard_068 && python3.10 seo_rehab_guard_068_repair.py --dry-run",
        "description": "seo068 ten-run production dry-run fallback", "interval": "daily", "hour": 21, "minute": 28, "expiry": None},
    ("schedule", 1502679): {
        "command": "cd /home/Carix/autopilot_inbox/cloud/task_083_catalog_dedup && python3.10 installer.py install",
        "description": "task083 install fallback", "interval": "daily", "hour": 8, "minute": 2, "expiry": None},
    ("schedule", 1505035): {
        "command": "set -e; mkdir -p '/home/Carix/autopilot_inbox/cloud/task_096_tech_spec_ai_crm/data_enrichment'",
        "description": "TASK096 v7 1788202686 fallback-1", "interval": "daily", "hour": 19, "minute": 0, "expiry": None},
}


class CoordinationError(RuntimeError):
    """Messages are fixed codes, never remote response bodies or credentials."""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise CoordinationError("PA_REDIRECT_REFUSED")


class PATransport:
    """Only two list GETs and enabled-only PATCHs for four pinned task IDs.

    Construct explicitly. A token is read from the documented API_TOKEN
    environment variable; it is neither accepted as a command line argument nor
    emitted in errors, journals or repr. No automatic request retries.
    """
    def __init__(self):
        token = os.environ.get("API_TOKEN", "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{20,256}", token):
            raise CoordinationError("PA_TOKEN_UNAVAILABLE")
        self._token = token
        self._opener = urllib.request.build_opener(_NoRedirect())
        self._last_request = 0.0

    def _request(self, kind, ident=None, enabled=None):
        if kind not in ("always_on", "schedule"):
            raise CoordinationError("PA_ENDPOINT_REFUSED")
        if ident is None:
            if enabled is not None:
                raise CoordinationError("PA_OPERATION_REFUSED")
            method, suffix, body = "GET", kind + "/", None
        else:
            if type(ident) is not int or (kind, ident) not in KNOWN or type(enabled) is not bool:
                raise CoordinationError("PA_OPERATION_REFUSED")
            method, suffix = "PATCH", f"{kind}/{ident}/"
            body = canonical({"enabled": enabled})
        # Conservative 30/minute across all endpoints; caller cannot burst.
        delay = 2.0 - (time.monotonic() - self._last_request)
        if delay > 0:
            time.sleep(delay)
        self._last_request = time.monotonic()
        req = urllib.request.Request(BASE + suffix, data=body, method=method, headers={
            "Authorization": "Token " + self._token, "Accept": "application/json",
            "Content-Type": "application/json"})
        try:
            with self._opener.open(req, timeout=20) as response:
                if response.geturl() != BASE + suffix:
                    raise CoordinationError("PA_RESPONSE_ORIGIN_REFUSED")
                if response.status not in ((200,) if method == "GET" else (200, 204)):
                    raise CoordinationError("PA_UNEXPECTED_STATUS")
                data = response.read(MAX_BYTES + 1)
                if len(data) > MAX_BYTES:
                    raise CoordinationError("PA_RESPONSE_TOO_LARGE")
                if method == "PATCH":
                    return None  # Full list readback is authoritative.
                value = json.loads(data)
                if type(value) is not list:
                    raise CoordinationError("PA_INVENTORY_SCHEMA")
                return value
        except CoordinationError:
            raise
        except urllib.error.HTTPError as error:
            raise CoordinationError("PA_HTTP_" + str(error.code)) from None
        except Exception:
            raise CoordinationError("PA_REQUEST_UNCERTAIN" if method == "PATCH" else "PA_READ_FAILED") from None

    def inventory(self):
        return {kind: self._request(kind) for kind in ("always_on", "schedule")}

    def set_enabled(self, kind, ident, enabled):
        self._request(kind, ident, enabled)


def normalize_inventory(inventory):
    if type(inventory) is not dict or set(inventory) != {"always_on", "schedule"}:
        raise CoordinationError("INVENTORY_SCHEMA")
    rows = []
    seen = set()
    for kind in ("always_on", "schedule"):
        if type(inventory[kind]) is not list:
            raise CoordinationError("INVENTORY_SCHEMA")
        for item in inventory[kind]:
            if type(item) is not dict or type(item.get("id")) is not int:
                raise CoordinationError("INVENTORY_SCHEMA")
            key = kind, item["id"]
            if key in seen or key not in KNOWN:
                raise CoordinationError("INVENTORY_UNKNOWN_OR_DUPLICATE")
            seen.add(key)
            expected = KNOWN[key]
            for name, value in expected.items():
                if name not in item or item[name] != value or type(item[name]) is not type(value):
                    raise CoordinationError("INVENTORY_CONFIGURATION_DRIFT")
            if type(item.get("enabled")) is not bool:
                raise CoordinationError("INVENTORY_ENABLED_SCHEMA")
            row = {"kind": kind, "id": item["id"], "enabled": item["enabled"], **expected}
            # Preserve unexpected fields too; only documented runtime state is
            # excluded. New provider fields therefore require review on drift.
            row["extra"] = {k: v for k, v in item.items() if k not in set(expected) | {"id", "enabled", "state"}}
            rows.append(row)
    if seen != set(KNOWN):
        raise CoordinationError("INVENTORY_TASK_MISSING")
    return sorted(rows, key=lambda row: (row["kind"], row["id"]))


def build_plan(inventory, *, main_sha, run_id, nonce, epoch, owner_review):
    if not isinstance(main_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", main_sha):
        raise CoordinationError("PLAN_MAIN_SHA")
    if not isinstance(run_id, str) or not re.fullmatch(r"[1-9][0-9]{0,19}", run_id):
        raise CoordinationError("PLAN_RUN_ID")
    if not isinstance(nonce, str) or not re.fullmatch(r"[0-9a-f]{64}", nonce):
        raise CoordinationError("PLAN_NONCE")
    if type(epoch) is not int or not 1 <= epoch < 2**63:
        raise CoordinationError("PLAN_EPOCH")
    if not isinstance(owner_review, str) or not 1 <= len(owner_review) <= 512:
        raise CoordinationError("PLAN_OWNER_REVIEW_REFERENCE")
    plan = {"schema": "UA-ART-PA-QUIET-PLAN-1", "main_sha": main_sha, "run_id": run_id,
            "nonce": nonce, "epoch": epoch, "owner_review": owner_review,
            "tasks": normalize_inventory(inventory)}
    return {**plan, "plan_sha256": digest(plan)}


def validate_plan(plan):
    if type(plan) is not dict or set(plan) != {"schema", "main_sha", "run_id", "nonce", "epoch", "owner_review", "tasks", "plan_sha256"}:
        raise CoordinationError("PLAN_SCHEMA")
    try:
        if type(plan["tasks"]) is not list or len(plan["tasks"]) != len(KNOWN):
            raise CoordinationError("PLAN_TASK_SCHEMA")
        inventory = {"always_on": [], "schedule": []}
        for row in plan["tasks"]:
            if type(row) is not dict or type(row.get("extra")) is not dict:
                raise CoordinationError("PLAN_TASK_SCHEMA")
            inventory[row["kind"]].append({**row["extra"], **{k: v for k, v in row.items() if k not in {"kind", "extra"}}})
        rebuilt = build_plan(inventory, **{k: plan[k] for k in ("main_sha", "run_id", "nonce", "epoch", "owner_review")})
        if rebuilt != plan:
            raise CoordinationError("PLAN_HASH_OR_SCHEMA")
    except CoordinationError:
        raise
    except Exception:
        raise CoordinationError("PLAN_TASK_SCHEMA") from None


class Controller:
    """Local durable single-plan coordinator; orchestrator supplies trust checks.

    verify_plan(plan) must independently validate current main/run/epoch and
    owner authorization, returning the exact bound fields and AUTHORIZED status.
    The returned mapping is not a substitute for that independent implementation.
    """
    def __init__(self, api, journal_dir, *, verify_plan):
        self.api = api
        self.directory = Path(journal_dir)
        self.verify_plan = verify_plan
        if isinstance(api, PATransport) and self.directory != JOURNAL_ROOT:
            raise CoordinationError("LIVE_JOURNAL_ROOT_MUST_BE_FIXED")

    @contextlib.contextmanager
    def _locked(self, plan):
        validate_plan(plan)
        if not self.directory.is_absolute() or self.directory.parent.resolve() != self.directory.parent:
            raise CoordinationError("JOURNAL_PARENT_SYMLINK_OR_RELATIVE")
        self.directory.mkdir(mode=0o700, parents=False, exist_ok=True)
        if self.directory.is_symlink() or not self.directory.is_dir():
            raise CoordinationError("JOURNAL_DIRECTORY")
        dirfd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        lockfd = None
        try:
            lockfd = os.open("coordinator.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=dirfd)
            def resources_valid(journalfd=None):
                ds = os.fstat(dirfd)
                if ds.st_uid != os.geteuid() or ds.st_mode & 0o077:
                    raise CoordinationError("JOURNAL_DIRECTORY_PERMISSIONS")
                visible_dir = os.stat(self.directory, follow_symlinks=False)
                if (visible_dir.st_dev, visible_dir.st_ino) != (ds.st_dev, ds.st_ino):
                    raise CoordinationError("JOURNAL_DIRECTORY_REPLACED")
                for fd, name in ((lockfd, "coordinator.lock"), (journalfd, "journal.jsonl")):
                    if fd is None:
                        continue
                    fs = os.fstat(fd)
                    visible = os.stat(name, dir_fd=dirfd, follow_symlinks=False)
                    if (not stat.S_ISREG(fs.st_mode) or fs.st_nlink != 1 or fs.st_uid != os.geteuid()
                            or fs.st_mode & 0o077 or (fs.st_dev, fs.st_ino) != (visible.st_dev, visible.st_ino)):
                        raise CoordinationError("JOURNAL_RESOURCE_CHANGED_OR_UNSAFE")
            resources_valid()
            try:
                fcntl.flock(lockfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise CoordinationError("COORDINATOR_BUSY") from None
            self._authorize(plan)
            journalfd = os.open("journal.jsonl", os.O_CREAT | os.O_RDWR | os.O_APPEND | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=dirfd)
            try:
                resources_valid(journalfd)
                os.lseek(journalfd, 0, os.SEEK_SET)
                raw = os.read(journalfd, MAX_BYTES + 1)
                if len(raw) > MAX_BYTES or (raw and not raw.endswith(b"\n")):
                    raise CoordinationError("JOURNAL_INCOMPLETE")
                try:
                    events = [json.loads(line) for line in raw.splitlines()]
                except Exception:
                    raise CoordinationError("JOURNAL_INVALID") from None
                for seq, event in enumerate(events):
                    if type(event) is not dict or event.get("seq") != seq or event.get("plan_sha256") != plan["plan_sha256"]:
                        raise CoordinationError("JOURNAL_OWNERSHIP_OR_SEQUENCE")
                def append(event, **fields):
                    resources_valid(journalfd)
                    record = {"seq": len(events), "plan_sha256": plan["plan_sha256"], "event": event, **fields}
                    self._state(plan, events + [record])
                    payload = canonical(record) + b"\n"
                    if os.write(journalfd, payload) != len(payload):
                        raise CoordinationError("JOURNAL_SHORT_WRITE")
                    os.fsync(journalfd)
                    os.fsync(dirfd)
                    events.append(record)
                    return record["seq"]
                yield events, append
            finally:
                os.close(journalfd)
        finally:
            if lockfd is not None:
                os.close(lockfd)
            os.close(dirfd)

    def _authorize(self, plan):
        result = self.verify_plan(plan)
        keys = ("plan_sha256", "main_sha", "run_id", "nonce", "epoch")
        if type(result) is not dict or result.get("status") != "AUTHORIZED" or any(result.get(k) != plan[k] for k in keys):
            raise CoordinationError("PLAN_AUTHORIZATION_REQUIRED")

    @staticmethod
    def _state(plan, events):
        flags = {(r["kind"], r["id"]): r["enabled"] for r in plan["tasks"]}
        pending = None
        phase = "NEW"
        for event in events:
            code = event.get("event")
            base = {"seq", "plan_sha256", "event"}
            fields = {
                "BEGIN": set(), "INTENT": {"kind", "id", "enabled"},
                "APPLIED": {"intent_seq"}, "APPLIED_VERIFIED_COMPLETION": {"intent_seq", "completion_sha256"},
                "UNCERTAIN": {"intent_seq"}, "PAUSED": set(),
                "RESTORING": {"receipt_sha256"}, "RESTORED": {"receipt_sha256"},
            }
            if code not in fields or set(event) != base | fields[code] or type(event["seq"]) is not int:
                raise CoordinationError("JOURNAL_EVENT_SCHEMA")
            if code == "BEGIN":
                if phase != "NEW" or pending or event["seq"] != 0:
                    raise CoordinationError("JOURNAL_TRANSITION")
                phase = "PAUSING"
            elif code == "INTENT":
                if type(event["kind"]) is not str or type(event["id"]) is not int:
                    raise CoordinationError("JOURNAL_EVENT_SCHEMA")
                key = event["kind"], event["id"]
                if (pending is not None or phase not in {"PAUSING", "RESTORING"}
                        or key not in flags or type(event["id"]) is not int or type(event["enabled"]) is not bool
                        or event["enabled"] == flags[key] or event["enabled"] != (phase == "RESTORING")):
                    raise CoordinationError("JOURNAL_TRANSITION")
                pending = event
            elif code in {"APPLIED", "APPLIED_VERIFIED_COMPLETION"}:
                if pending is None or type(event["intent_seq"]) is not int or event.get("intent_seq") != pending["seq"]:
                    raise CoordinationError("JOURNAL_APPLIED_WITHOUT_INTENT")
                if code == "APPLIED_VERIFIED_COMPLETION" and not re.fullmatch(r"[0-9a-f]{64}", str(event["completion_sha256"])):
                    raise CoordinationError("JOURNAL_COMPLETION_SHA")
                flags[(pending["kind"], pending["id"])] = pending["enabled"]
                pending = None
            elif code == "UNCERTAIN":
                if pending is None or type(event["intent_seq"]) is not int or event.get("intent_seq") != pending["seq"]:
                    raise CoordinationError("JOURNAL_UNCERTAIN_WITHOUT_INTENT")
            elif code in {"PAUSED", "RESTORING", "RESTORED"}:
                expected_phase = {"PAUSED": "PAUSING", "RESTORING": "PAUSED", "RESTORED": "RESTORING"}[code]
                if pending or phase != expected_phase:
                    raise CoordinationError("JOURNAL_TRANSITION")
                if code in {"PAUSED", "RESTORING"} and any(flags.values()):
                    raise CoordinationError("JOURNAL_TRANSITION")
                if code == "RESTORED" and flags != {(r["kind"], r["id"]): r["enabled"] for r in plan["tasks"]}:
                    raise CoordinationError("JOURNAL_TRANSITION")
                if code in {"RESTORING", "RESTORED"} and not re.fullmatch(r"[0-9a-f]{64}", str(event["receipt_sha256"])):
                    raise CoordinationError("JOURNAL_TERMINAL_SHA")
                phase = code
        return flags, pending, phase

    def _readback(self, plan, flags):
        rows = normalize_inventory(self.api.inventory())
        expected = [{**row, "enabled": flags[(row["kind"], row["id"])]} for row in plan["tasks"]]
        if rows != expected:
            raise CoordinationError("INVENTORY_CHANGED_DURING_WINDOW")
        return rows

    def _change(self, plan, flags, append, kind, ident, enabled):
        self._authorize(plan)
        self._readback(plan, flags)
        # INTENT must be durable before a potentially ambiguous remote write.
        intent_seq = append("INTENT", kind=kind, id=ident, enabled=enabled)
        try:
            self.api.set_enabled(kind, ident, enabled)
            target = {**flags, (kind, ident): enabled}
            self._readback(plan, target)
            append("APPLIED", intent_seq=intent_seq)
            flags.update(target)
        except Exception:
            append("UNCERTAIN", intent_seq=intent_seq)
            raise CoordinationError("MUTATION_UNCERTAIN_RECONCILE_REQUIRED") from None

    @staticmethod
    def _sequence_append(events, append):
        def sequenced(event, **fields):
            seq = len(events)
            append(event, **fields)
            return seq
        return sequenced

    def pause(self, plan):
        with self._locked(plan) as (events, append):
            flags, pending, phase = self._state(plan, events)
            if pending:
                raise CoordinationError("MUTATION_UNCERTAIN_RECONCILE_REQUIRED")
            if phase in {"RESTORING", "RESTORED"}:
                raise CoordinationError("PLAN_ALREADY_RESTORING_OR_RESTORED")
            self._readback(plan, flags)
            if phase == "NEW":
                append("BEGIN")
            write = self._sequence_append(events, append)
            for row in plan["tasks"]:
                key = row["kind"], row["id"]
                if flags[key]:
                    self._change(plan, flags, write, *key, False)
            if phase != "PAUSED":
                append("PAUSED")
            return {"status": "PAUSED_CONFIGURATION_VERIFIED", "plan_sha256": plan["plan_sha256"],
                    "external_writer_proof": False, "task_count": len(flags)}

    def reconcile(self, plan, *, verify_completion=None):
        """Read-only remote reconciliation. Never retries a PATCH.

        Seeing the old value cannot prove a timed-out request will never apply;
        such an operation remains blocked, rather than being retried blindly.
        """
        with self._locked(plan) as (events, append):
            flags, pending, phase = self._state(plan, events)
            if pending is None:
                self._readback(plan, flags)
                return {"status": "NO_UNCERTAIN_OPERATION", "phase": phase}
            target = {**flags, (pending["kind"], pending["id"]): pending["enabled"]}
            self._readback(plan, target)
            if verify_completion is None:
                return {"status": "INTENT_EFFECT_OBSERVED_UNSETTLED", "phase": phase, "external_writer_proof": False}
            completion = verify_completion(plan, dict(pending))
            if (type(completion) is not dict or completion.get("status") != "REMOTE_REQUEST_COMPLETED"
                    or completion.get("plan_sha256") != plan["plan_sha256"]
                    or completion.get("intent_seq") != pending["seq"]
                    or not re.fullmatch(r"[0-9a-f]{64}", str(completion.get("receipt_sha256", "")))):
                raise CoordinationError("REMOTE_COMPLETION_PROOF_REQUIRED")
            append("APPLIED_VERIFIED_COMPLETION", intent_seq=pending["seq"], completion_sha256=completion["receipt_sha256"])
            return {"status": "INTENT_EFFECT_OBSERVED", "phase": phase, "external_writer_proof": False}

    def restore(self, plan, terminal_receipt, *, verify_terminal):
        with self._locked(plan) as (events, append):
            flags, pending, phase = self._state(plan, events)
            if pending:
                raise CoordinationError("MUTATION_UNCERTAIN_RECONCILE_REQUIRED")
            if phase not in {"PAUSED", "RESTORING", "RESTORED"}:
                raise CoordinationError("RESTORE_REQUIRES_OWNED_PAUSE")
            terminal = verify_terminal(terminal_receipt, plan)
            keys = ("plan_sha256", "run_id", "nonce", "epoch")
            if (type(terminal) is not dict or terminal.get("status") not in
                    {"VERIFIED_COMMITTED", "VERIFIED_ROLLED_BACK", "VERIFIED_NO_DATA_WRITE"}
                    or any(terminal.get(k) != plan[k] for k in keys)
                    or not re.fullmatch(r"[0-9a-f]{64}", str(terminal.get("receipt_sha256", "")))):
                raise CoordinationError("VERIFIED_TERMINAL_RECEIPT_REQUIRED")
            previous = [e for e in events if e["event"] == "RESTORING"]
            if previous and previous[0]["receipt_sha256"] != terminal["receipt_sha256"]:
                raise CoordinationError("TERMINAL_RECEIPT_CHANGED")
            self._readback(plan, flags)
            if phase == "PAUSED":
                if any(flags.values()):
                    raise CoordinationError("RESTORE_REQUIRES_ALL_TASKS_DISABLED")
                append("RESTORING", receipt_sha256=terminal["receipt_sha256"])
            write = self._sequence_append(events, append)
            # Restore schedules first, CRM last. Original disabled flags stay off.
            for row in sorted(plan["tasks"], key=lambda r: (r["kind"] == "always_on", r["id"])):
                key = row["kind"], row["id"]
                if flags[key] != row["enabled"]:
                    self._change(plan, flags, write, *key, row["enabled"])
            if phase != "RESTORED":
                append("RESTORED", receipt_sha256=terminal["receipt_sha256"])
            return {"status": "TASK_CONFIGURATION_RESTORED", "plan_sha256": plan["plan_sha256"],
                    "runtime_health_verified": False}

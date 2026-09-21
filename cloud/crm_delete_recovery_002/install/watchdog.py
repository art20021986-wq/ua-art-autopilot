"""Source-bound recovery watchdog for the new CRM installation owner.

Import and the default CLI only inspect code; neither starts recovery.  The
owner must durably persist a private context, enter its own session, and call
``launch_watchdog`` before it pauses any service.  Recovery is delegated only to
the exact pinned lifecycle source with the fixed ``--recover`` argument shape.
No shell, arbitrary argument, unfiltered environment, or output capture exists.

This module assumes the owning Unix account is trusted.  File hashes and inode
checks reject accidental/replaced inputs; they are not a security boundary
against another process with the same UID intentionally modifying both code
and its approved context.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import signal
import stat
import subprocess
import sys
import time


HEX = re.compile(r"[0-9a-f]{64}")
MAX_DEADLINE_SECONDS = 1200
READY_SECONDS = 8
TERM_SECONDS = 5
KILL_SECONDS = 3
RECOVERY_SECONDS = 900
ALLOWED_CREDENTIALS = frozenset({"PYTHONANYWHERE_API_TOKEN"})
CONTEXT_HASH_MARKER = "@CONTEXT_SHA256@"
TERMINAL = frozenset({"COMPLETE", "ROLLED_BACK", "RECOVERED"})
REQUIRED = frozenset({
    "owner_pid", "start_ticks", "pgid", "deadline_epoch", "result_path",
    "recovery_argv", "recovery_source_sha256", "package_manifest_sha256",
    "package_manifest_path", "watchdog_source_sha256",
})
OPTIONAL = frozenset({"lifecycle_plan_path", "lifecycle_plan_sha256", "credential_env_names"})


class WatchdogError(RuntimeError):
    """Only static error codes are emitted; context and credentials stay private."""


def require(condition, code):
    if not condition:
        raise WatchdogError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _json(raw):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, "DUPLICATE_JSON_KEY")
            value[key] = item
        return value
    try:
        return json.loads(raw, object_pairs_hook=unique)
    except (ValueError, UnicodeError) as exc:
        raise WatchdogError("INVALID_JSON") from exc


def canonical(path, *, exists=True):
    require(isinstance(path, (str, Path)), "PATH_TYPE")
    path = Path(path)
    require(path.is_absolute() and path == path.resolve(strict=exists), "CANONICAL_PATH_REQUIRED")
    require(not path.is_symlink(), "SYMLINK_REFUSED")
    return path


def _read(path, *, private=True):
    path = canonical(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid(), "OWNED_REGULAR_FILE_REQUIRED")
        require(before.st_mode & 0o022 == 0, "SHARED_WRITE_FILE_REFUSED")
        require(not private or before.st_mode & 0o077 == 0, "PRIVATE_FILE_REQUIRED")
        require(before.st_size <= 1024 * 1024 * 4, "FILE_TOO_LARGE")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(1024 * 1024 * 4 + 1)
        after = os.fstat(fd)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        require(identity(before) == identity(after) and len(raw) == after.st_size, "FILE_CHANGED_DURING_READ")
        require(path.stat(follow_symlinks=False).st_ino == after.st_ino, "FILE_REPLACED_DURING_READ")
        return raw, identity(after)
    finally:
        os.close(fd)


def _private_directory(path):
    path = canonical(path)
    info = path.stat(follow_symlinks=False)
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and
            info.st_mode & 0o077 == 0, "PRIVATE_CONTEXT_DIRECTORY_REQUIRED")
    return path


def _inside(root, path, *, exists=True):
    path = canonical(path, exists=exists)
    require(path != root and path.is_relative_to(root), "CONTEXT_PATH_ESCAPE")
    # Every directory beneath the trusted context root stays private.
    for parent in path.parents:
        if parent == root:
            break
        _private_directory(parent)
    return path


def _sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def durable_json(path, value):
    """Persist a private receipt without following an existing symlink."""
    path = canonical(path, exists=False)
    _private_directory(path.parent)
    temporary = path.with_name(path.name + ".tmp-" + secrets.token_hex(8))
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _sync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


class BoundContext:
    def __init__(self, context_path, context_sha256, expected_watchdog_sha256, recovery_argv=None,
                 *, watchdog_source=None):
        require(HEX.fullmatch(str(context_sha256)) and HEX.fullmatch(str(expected_watchdog_sha256)),
                "DIGEST_REQUIRED")
        self.path = canonical(context_path)
        self.root = _private_directory(self.path.parent)
        self.sha256 = context_sha256
        self.watchdog_source = canonical(watchdog_source or Path(__file__).absolute())
        self.watchdog_sha256 = expected_watchdog_sha256
        self.pins = {}
        raw = self.pin(self.path, context_sha256)
        self.data = d = _json(raw)
        require(isinstance(d, dict) and REQUIRED <= set(d) <= REQUIRED | OPTIONAL, "EXACT_CONTEXT_FIELDS")
        for key in ("owner_pid", "start_ticks", "pgid"):
            require(type(d[key]) is int and d[key] > (1 if key != "start_ticks" else 0), "PROCESS_IDENTITY_REQUIRED")
        require(d["owner_pid"] == d["pgid"], "ISOLATED_OWNER_GROUP_REQUIRED")
        require(type(d["deadline_epoch"]) in (int, float) and math.isfinite(d["deadline_epoch"]), "FINITE_DEADLINE_REQUIRED")
        for key in ("recovery_source_sha256", "package_manifest_sha256", "watchdog_source_sha256"):
            require(HEX.fullmatch(str(d[key])), "DIGEST_REQUIRED")
        require(d["watchdog_source_sha256"] == expected_watchdog_sha256, "WATCHDOG_CONTEXT_HASH_MISMATCH")
        self.pin(self.watchdog_source, expected_watchdog_sha256, private=False)
        argv = d["recovery_argv"]
        require(isinstance(argv, list) and len(argv) == 8 and all(type(x) is str for x in argv), "FIXED_RECOVERY_ARGV_REQUIRED")
        self.source = _inside(self.root, argv[3])
        require(self.source.suffix == ".py", "PYTHON_RECOVERY_SOURCE_REQUIRED")
        persisted = [sys.executable, "-I", "-B", str(self.source), "--recover", str(self.path),
                     "--context-sha256", CONTEXT_HASH_MARKER]
        self.recovery_argv = persisted[:-1] + [context_sha256]
        require(argv == persisted and (recovery_argv is None or recovery_argv == self.recovery_argv),
                "FIXED_RECOVERY_ARGV_REQUIRED")
        self.pin(self.source, d["recovery_source_sha256"])
        self.manifest = _inside(self.root, d["package_manifest_path"])
        self.pin(self.manifest, d["package_manifest_sha256"])
        require(("lifecycle_plan_path" in d) == ("lifecycle_plan_sha256" in d), "PLAN_BINDING_PAIR_REQUIRED")
        if "lifecycle_plan_path" in d:
            self.pin(_inside(self.root, d["lifecycle_plan_path"]), d["lifecycle_plan_sha256"])
        names = d.get("credential_env_names", [])
        require(isinstance(names, list) and all(type(name) is str and name in ALLOWED_CREDENTIALS for name in names) and
                len(names) == len(set(names)), "CREDENTIAL_ALLOWLIST")
        self.result = _inside(self.root, d["result_path"], exists=False)
        self.ready = self.root / "watchdog-ready.json"
        self.outcome = self.root / "watchdog-result.json"
        self.lock = self.root / "watchdog.lock"
        require(len({self.path, self.source, self.manifest, self.result, self.ready, self.outcome, self.lock}) == 7,
                "CONTEXT_PATH_COLLISION")

    def pin(self, path, digest, *, private=True):
        require(HEX.fullmatch(str(digest)), "DIGEST_REQUIRED")
        raw, identity = _read(path, private=private)
        require(sha(raw) == digest, "BOUND_FILE_HASH_MISMATCH")
        self.pins[path] = (digest, identity, private)
        return raw

    def revalidate(self):
        _private_directory(self.root)
        for path, (digest, identity, private) in self.pins.items():
            raw, actual = _read(path, private=private)
            require(actual == identity and sha(raw) == digest, "BOUND_FILE_CHANGED")

    def binding(self):
        return {"context_sha256": self.sha256, "package_manifest_sha256": self.data["package_manifest_sha256"],
                **{key: self.data[key] for key in ("owner_pid", "start_ticks", "pgid")}}

    def terminal(self, *, allow_blocked=False):
        if not self.result.exists() and not self.result.is_symlink():
            return None
        result = _json(_read(self.result)[0])
        require(isinstance(result, dict) and all(result.get(k) == v for k, v in self.binding().items()),
                "TERMINAL_RESULT_BINDING")
        require(result.get("status") in TERMINAL | {"BLOCKED"}, "TERMINAL_RESULT_STATUS")
        return result if result["status"] in TERMINAL or allow_blocked else None

    def environment(self):
        result = {"PATH": os.defpath, "LANG": "C.UTF-8"}
        for key in self.data.get("credential_env_names", []):
            value = os.environ.get(key)
            require(isinstance(value, str) and bool(value) and "\x00" not in value, "REQUIRED_CREDENTIAL_MISSING")
            result[key] = value
        return result


class LinuxProcesses:
    """Process signals use pidfds, never a recycled PID or an unguarded killpg."""
    def identity(self, pid):
        try:
            raw = Path("/proc") / str(pid) / "stat"
            text = raw.read_text()
        except FileNotFoundError:
            return None
        # comm may contain spaces and closing parentheses: use the final one.
        fields = text[text.rfind(")") + 2:].split()
        require(len(fields) > 19, "PROC_STAT_FORMAT")
        return {"pid": pid, "start_ticks": int(fields[19]), "pgid": int(fields[2]),
                "session": int(fields[3]), "state": fields[0]}

    def members(self, pgid):
        values = []
        for path in Path("/proc").iterdir():
            if path.name.isdigit():
                item = self.identity(int(path.name))
                if item and item["pgid"] == pgid and item["state"] not in ("Z", "X"):
                    values.append(item)
        return values

    def send(self, identity, sig):
        require(hasattr(os, "pidfd_open") and hasattr(signal, "pidfd_send_signal"), "PIDFD_REQUIRED")
        try:
            fd = os.pidfd_open(identity["pid"], 0)
        except ProcessLookupError:
            return
        try:
            actual = self.identity(identity["pid"])
            require(actual is None or same_process(actual, identity), "PID_REUSE_REFUSED")
            if actual is not None and actual["state"] not in ("Z", "X"):
                signal.pidfd_send_signal(fd, sig)
        except ProcessLookupError:
            pass
        finally:
            os.close(fd)

    def preflight(self, identity):
        """Signal zero checks pidfd support/access without changing a process."""
        self.send(identity, 0)


def same_process(left, right):
    return all(left.get(key) == right.get(key) for key in ("pid", "start_ticks", "pgid", "session"))


def owner_identity(context):
    d = context.data
    return {"pid": d["owner_pid"], "start_ticks": d["start_ticks"], "pgid": d["pgid"], "session": d["owner_pid"]}


def _owner_alive(context, processes):
    expected = owner_identity(context)
    actual = processes.identity(expected["pid"])
    if actual is None:
        return False
    require(same_process(actual, expected), "OWNER_PID_REUSE_REFUSED")
    return actual["state"] not in ("Z", "X")


def remember_group(context, processes, known, *, snapshot=False):
    alive = _owner_alive(context, processes)
    anchor = processes.identity(context.data["owner_pid"])
    anchored = anchor is not None and same_process(anchor, owner_identity(context))
    members = processes.members(context.data["pgid"])
    for item in members:
        require(item["session"] == context.data["owner_pid"] and item["start_ticks"] >= context.data["start_ticks"],
                "FOREIGN_GROUP_MEMBER")
        previous = known.get(item["pid"])
        require(previous is None or same_process(previous, item), "GROUP_PID_REUSE_REFUSED")
        # An unreaped matching zombie still reserves the owner's PID and group
        # identity, so its descendants can safely be discovered before reap.
        require(anchored or previous is not None, "UNOBSERVED_SURVIVING_GROUP_MEMBER")
        known[item["pid"]] = item
    return (alive, members) if snapshot else alive


def stop_owner_group(context, processes, known, *, monotonic=time.monotonic, sleep=time.sleep):
    """Only previously observed members of the exact isolated group get signals."""
    require(context.data["pgid"] != os.getpgrp(), "REFUSE_WATCHDOG_OWN_GROUP")
    for sig, seconds in ((signal.SIGTERM, TERM_SECONDS), (signal.SIGKILL, KILL_SECONDS)):
        context.revalidate()
        sent = set()
        deadline = monotonic() + seconds
        while True:
            _, members = remember_group(context, processes, known, snapshot=True)
            for item in members:
                key = (item["pid"], item["start_ticks"])
                if key not in sent:
                    processes.send(item, sig)
                    sent.add(key)
            if not members:
                return
            if monotonic() >= deadline:
                break
            sleep(0.1)
    require(not processes.members(context.data["pgid"]), "OWNER_GROUP_STILL_RUNNING")


@contextmanager
def watchdog_lock(context):
    path = canonical(context.lock, exists=False)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_mode & 0o077 == 0,
                "PRIVATE_LOCK_REQUIRED")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise WatchdogError("WATCHDOG_ALREADY_ACTIVE") from exc
        yield
    finally:
        os.close(fd)


def _recover(context):
    """Bound recovery lifetime includes its children, before leader PID reap.

    The pinned lifecycle must keep recovery subprocesses in its group; detached
    recovery writers are forbidden by this lifecycle contract.
    """
    process = subprocess.Popen(context.recovery_argv, shell=False, cwd=context.root,
                               env=context.environment(), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, close_fds=True, start_new_session=True)
    processes = LinuxProcesses()
    try:
        identity = processes.identity(process.pid)
        require(identity is not None and identity["pgid"] == process.pid and identity["session"] == process.pid,
                "RECOVERY_PROCESS_IDENTITY")
    except BaseException:
        # Popen owns this child even if /proc identity acquisition failed. Stop
        # that child, but do not claim its unobserved descendant group is clean.
        process.terminate()
        try:
            process.wait(timeout=TERM_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=KILL_SECONDS)
        raise WatchdogError("RECOVERY_IDENTITY_UNPROVEN_GROUP_CLEANUP_REQUIRED") from None
    class Group:
        data = {"owner_pid": process.pid, "pgid": process.pid, "start_ticks": identity["start_ticks"]}
        # Recovery cleanup uses this cached identity even if a bound source is
        # subsequently changed; drift must never leave launched writers alive.
        @staticmethod
        def revalidate():
            return None
    group = Group()
    known = {}
    deadline = time.monotonic() + RECOVERY_SECONDS
    expired = False
    try:
        while True:
            context.revalidate()
            alive = remember_group(group, processes, known)
            if not alive:
                break
            if time.monotonic() >= deadline:
                expired = True
                break
            time.sleep(0.1)
    finally:
        # No poll()/wait() above: a zombie leader anchors identity until its
        # group is empty, preventing PID reuse during descendant cleanup.
        stop_owner_group(group, processes, known, monotonic=time.monotonic, sleep=time.sleep)
        result = process.wait(timeout=KILL_SECONDS)
    require(not expired, "RECOVERY_DEADLINE_EXCEEDED")
    return result


def watch(context, *, processes=None, now=time.time, sleep=time.sleep, monotonic=time.monotonic,
          recover=_recover):
    """One owner, one recovery dispatch.  Dependencies are injectable offline."""
    processes = processes or LinuxProcesses()
    known = {}
    with watchdog_lock(context):
        # Existing outcome means this transaction has already consumed its
        # watchdog lifecycle; restart must be reconciled by the owner.
        require(not context.outcome.exists() and not context.outcome.is_symlink(), "WATCHDOG_ALREADY_CONSUMED")
        try:
            context.revalidate()
            require(_owner_alive(context, processes), "OWNER_MUST_BE_ALIVE_AT_READINESS")
            remaining = context.data["deadline_epoch"] - now()
            require(0 < remaining <= MAX_DEADLINE_SECONDS, "READINESS_DEADLINE")
            deadline = monotonic() + remaining
            processes.preflight(owner_identity(context))
            require(remember_group(context, processes, known), "OWNER_MUST_BE_ALIVE_AT_READINESS")
            this = processes.identity(os.getpid())
            require(this is not None and this["pgid"] != context.data["pgid"], "WATCHDOG_GROUP_ISOLATION")
            durable_json(context.ready, {**context.binding(), "status": "READY", "watchdog_pid": os.getpid(),
                         "watchdog_start_ticks": this["start_ticks"], "watchdog_source_sha256": context.watchdog_sha256,
                         "recovery_source_sha256": context.data["recovery_source_sha256"]})
            while True:
                context.revalidate()
                terminal = context.terminal()
                if terminal:
                    durable_json(context.outcome, {**context.binding(), "status": "OWNER_TERMINAL", "owner_status": terminal["status"]})
                    return 0
                alive = remember_group(context, processes, known)
                if not alive or monotonic() >= deadline:
                    break
                sleep(0.2)
            stop_owner_group(context, processes, known, monotonic=monotonic, sleep=sleep)
            context.revalidate()
            # Owner may have committed success during TERM; do not undo it.
            terminal = context.terminal()
            if terminal:
                durable_json(context.outcome, {**context.binding(), "status": "OWNER_TERMINAL", "owner_status": terminal["status"]})
                return 0
            # Durable claim precedes dispatch so a watchdog crash cannot replay
            # an uncertain recovery.  A recovery implementation must journal its
            # own substeps and expose explicit reconciliation for this case.
            durable_json(context.outcome, {**context.binding(), "status": "RECOVERY_DISPATCHED"})
            code = recover(context)
            context.revalidate()
            terminal = context.terminal(allow_blocked=True)
            success = terminal is not None and (code == 0 and terminal["status"] in TERMINAL or
                                               code == 1 and terminal["status"] == "ROLLED_BACK")
            durable_json(context.outcome, {**context.binding(), "status": "RECOVERY_COMPLETE" if success else "BLOCKED",
                         "recovery_returncode": code, "owner_status": terminal["status"] if terminal else None})
            return 0 if success else 1
        except (WatchdogError, OSError, ValueError, subprocess.SubprocessError) as exc:
            # No raw exception messages, tracebacks, captured subprocess output,
            # URLs, or environment values enter the durable record.
            error = str(exc) if isinstance(exc, WatchdogError) else type(exc).__name__
            durable_json(context.outcome, {**context.binding(), "status": "BLOCKED", "error_code": error})
            return 1


def launch_watchdog(context_path, context_sha256, expected_watchdog_sha256, recovery_argv):
    """Launch detached; return validated durable readiness, or raise before pause.

    The owner's context must already have been flushed and directory-fsynced.
    Persist recovery_argv ending in literal ``@CONTEXT_SHA256@`` to avoid a
    circular self-hash. The caller supplies the exact expanded argv; only this
    one fixed marker is expanded, after raw context SHA-256 verification.
    """
    context = BoundContext(context_path, context_sha256, expected_watchdog_sha256, recovery_argv)
    require(context.data["owner_pid"] == os.getpid(), "LAUNCHER_MUST_OWN_CONTEXT")
    require(all(not path.exists() and not path.is_symlink() for path in (context.ready, context.outcome, context.result)),
            "FRESH_WATCHDOG_CONTEXT_REQUIRED")
    processes = LinuxProcesses()
    require(_owner_alive(context, processes), "LIVE_OWNER_REQUIRED")
    processes.preflight(owner_identity(context))
    require(0 < context.data["deadline_epoch"] - time.time() <= MAX_DEADLINE_SECONDS, "READINESS_DEADLINE")
    process = subprocess.Popen([sys.executable, "-I", "-B", str(context.watchdog_source), "--watch", str(context.path),
                               "--context-sha256", context_sha256, "--watchdog-sha256", expected_watchdog_sha256],
                               shell=False, cwd=context.root, env=context.environment(), stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, start_new_session=True)
    deadline = time.monotonic() + READY_SECONDS
    try:
        while time.monotonic() < deadline:
            require(process.poll() is None, "WATCHDOG_EXITED_BEFORE_READY")
            if context.ready.exists() or context.ready.is_symlink():
                ready = _json(_read(context.ready)[0])
                require(isinstance(ready, dict) and ready.get("status") == "READY" and
                        all(ready.get(k) == v for k, v in context.binding().items()) and
                        ready.get("watchdog_pid") == process.pid and
                        ready.get("watchdog_source_sha256") == expected_watchdog_sha256 and
                        ready.get("recovery_source_sha256") == context.data["recovery_source_sha256"], "READINESS_BINDING")
                actual = processes.identity(process.pid)
                require(actual and actual["start_ticks"] == ready.get("watchdog_start_ticks") and
                        actual["pgid"] == process.pid and actual["session"] == process.pid and
                        actual["state"] not in ("Z", "X"), "READINESS_PROCESS_IDENTITY")
                context.revalidate()
                require(not context.outcome.exists() and not context.outcome.is_symlink() and process.poll() is None,
                        "WATCHDOG_NO_LONGER_READY")
                return ready
            time.sleep(0.05)
        raise WatchdogError("WATCHDOG_READINESS_TIMEOUT")
    except BaseException:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watch")
    parser.add_argument("--context-sha256")
    parser.add_argument("--watchdog-sha256")
    args = parser.parse_args(argv)
    if args.watch is None:
        require(args.context_sha256 is None and args.watchdog_sha256 is None, "WATCH_ARGUMENTS_REQUIRED")
        print(json.dumps({"mode": "INSPECT_ONLY", "watchdog_source_sha256": sha(Path(__file__).read_bytes())}))
        return 0
    context = BoundContext(args.watch, args.context_sha256, args.watchdog_sha256)
    return watch(context)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except WatchdogError as exc:
        print(json.dumps({"status": "BLOCKED", "error_code": str(exc)}))
        raise SystemExit(1)

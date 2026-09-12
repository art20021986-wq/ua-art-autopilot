#!/usr/bin/env python3
"""Hold reviewed existing PA lock inodes and answer fresh bound challenges.

This is a lock proof, never a declaration that all external writers are absent.
The controller must separately prove durable platform pause AND termination of
all prior invocations (including installers queued on these locks). This helper
does not stop/start tasks, import the application, modify CRM/HTML, remove lock
files, clear its durable intent, or reopen writes after a timeout/crash.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
import pathlib
import re
import signal
import socket
import stat
import time
import uuid
from typing import Any

BASE = pathlib.Path("/home/Carix")
CONTROL = BASE / ".uaart_writer_coordination"
SCHEMA = "UA-ART-EXTERNAL-WRITER-FENCE-1"
REQUEST_SCHEMA = "UA-ART-EXTERNAL-WRITER-FENCE-REQUEST-1"
CHALLENGE_SCHEMA = "UA-ART-EXTERNAL-WRITER-FENCE-CHALLENGE-1"
TTL_SECONDS = 30
LOCK_NAMES = (
    ".start_safe.singleton.lock",
    ".task082_catalog_stage_repair.lock",
    ".task082_catalog_stage_guard.lock",
    ".task083_catalog_dedup.lock",
    ".ua_art_publish_transaction.lock",
    ".crm_db.lock",
)
SESSION_KEYS = {
    "repository", "account", "production_root", "task_id", "expected_main",
    "plan_sha256", "run_id", "run_attempt", "nonce", "epoch", "source_sha256",
}


class FenceError(RuntimeError):
    pass


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def require(condition: Any, reason: str) -> None:
    if not condition:
        raise FenceError(reason)


def safe_dir(path: pathlib.Path) -> pathlib.Path:
    require(path.is_absolute() and path.resolve() == path, "DIRECTORY_PATH")
    for part in (path, *path.parents):
        info = part.lstat()
        require(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode), "DIRECTORY_TYPE")
    return path


def read_regular(path: pathlib.Path, limit: int = 32768) -> bytes:
    safe_dir(path.parent)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= limit,
                "FILE_TYPE_OR_SIZE")
        data = os.read(fd, limit + 1)
        require(len(data) <= limit, "FILE_SIZE")
        after = path.lstat()
        require((after.st_dev, after.st_ino) == (info.st_dev, info.st_ino), "FILE_REPLACED")
        return data
    finally:
        os.close(fd)


def write_json(path: pathlib.Path, value: dict[str, Any], *, exclusive: bool = False) -> None:
    safe_dir(path.parent)
    data = canonical(value) + b"\n"
    temp = path if exclusive else path.parent / (".write-" + uuid.uuid4().hex)
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if not exclusive:
            if path.exists() or path.is_symlink():
                current = path.lstat()
                require(stat.S_ISREG(current.st_mode) and current.st_nlink == 1, "OUTPUT_TYPE")
            os.replace(temp, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if not exclusive and temp.exists():
            temp.unlink()


def validate_session(session: Any, *, source_sha256: str) -> dict[str, Any]:
    require(isinstance(session, dict) and set(session) == SESSION_KEYS, "SESSION_KEYS")
    exact = {"repository": "art20021986-wq/ua-art-autopilot", "account": "Carix",
             "production_root": "/home/Carix", "source_sha256": source_sha256}
    require(all(session.get(key) == value for key, value in exact.items()), "SESSION_IDENTITY")
    for key, length in (("expected_main", 40), ("plan_sha256", 64), ("nonce", 64)):
        require(isinstance(session[key], str) and re.fullmatch("[0-9a-f]{%d}" % length, session[key]), key.upper())
    require(isinstance(session["task_id"], str) and re.fullmatch(r"[A-Z0-9][A-Z0-9_-]{1,79}", session["task_id"]), "TASK_ID")
    require(isinstance(session["run_id"], str) and re.fullmatch(r"[1-9][0-9]{0,19}", session["run_id"]), "RUN_ID")
    require(type(session["run_attempt"]) is int and session["run_attempt"] == 1, "RUN_ATTEMPT")
    require(type(session["epoch"]) is int and 0 < session["epoch"] < 2**63, "EPOCH")
    return dict(session)


class FenceLease:
    """The alternate roots are for isolated tests; CLI roots are fixed above."""

    def __init__(self, resource_root: pathlib.Path, control_root: pathlib.Path, session: dict[str, Any]):
        self.root = safe_dir(resource_root)
        self.control = safe_dir(control_root)
        self.session = validate_session(session, source_sha256=sha(pathlib.Path(__file__).read_bytes()))
        self.directory = safe_dir(self.control / "sessions" / self.session["nonce"])
        self.instance = uuid.uuid4().hex
        self.pid = os.getpid()
        self.host = socket.gethostname()
        self.handles: list[tuple[str, int, tuple[int, int]]] = []
        self.own_fd: int | None = None
        self.intent_created = False
        self.held = False
        self.last_challenge: str | None = None
        self.used_challenges: set[str] = set()

    def _base(self, state: str) -> dict[str, Any]:
        return {"schema": SCHEMA, **self.session, "scope": "LEGACY_LOCKS_HELD_ONLY", "state": state,
                "holder_pid": self.pid, "holder_instance": self.instance, "holder_host": self.host,
                "external_writers_verified": False, "cross_host_lock_verified": False,
                "durable_intent": self.intent_created,
                "required_external_evidence": "AUTHENTICATED_PLATFORM_PAUSE_AND_ALL_PRIOR_INVOCATIONS_TERMINATED"}

    def _intent(self, state: str, *, error: str | None = None) -> None:
        value = self._base(state)
        value["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        if error:
            value["error"] = error
        write_json(self.control / "active-intent.json", value)

    def acquire(self) -> None:
        require(not self.handles and self.own_fd is None, "ALREADY_OPEN")
        fd = os.open(self.control / "coordinator.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "COORDINATOR_LOCK_TYPE")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            os.close(fd)
            raise
        self.own_fd = fd
        try:
            # Refuse stale, terminal or active intents alike. Only the separately
            # reviewed terminal controller may archive them after platform readback.
            write_json(self.control / "active-intent.json", self._base("ACQUIRING"), exclusive=True)
            self.intent_created = True
            self._intent("ACQUIRING")
            for name in LOCK_NAMES:
                path = self.root / name
                handle = os.open(path, os.O_RDWR | os.O_NOFOLLOW)  # Never O_CREAT.
                try:
                    info = os.fstat(handle)
                    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "RESOURCE_LOCK_TYPE:" + name)
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    identity = (info.st_dev, info.st_ino)
                    self.handles.append((name, handle, identity))
                except BaseException:
                    os.close(handle)
                    raise
            self._check()
            self.held = True
            self._intent("HELD")
        except BaseException as exc:
            cleanup_error = None
            try:
                if self.intent_created:
                    self._intent("FAILED", error=type(exc).__name__)
            except BaseException as error:
                cleanup_error = error
            try:
                self._unlock()
            except BaseException as error:
                cleanup_error = cleanup_error or error
            if cleanup_error is not None:
                raise exc from cleanup_error
            raise

    def _check(self) -> list[dict[str, Any]]:
        require(self.own_fd is not None and len(self.handles) == len(LOCK_NAMES), "LOCK_SET_INCOMPLETE")
        require(os.getpid() == self.pid, "INHERITED_HOLDER")
        safe_dir(self.root)
        safe_dir(self.control)
        safe_dir(self.directory)
        info = os.fstat(self.own_fd)
        current = (self.control / "coordinator.lock").lstat()
        require(stat.S_ISREG(current.st_mode) and current.st_nlink == 1 and
                (current.st_dev, current.st_ino) == (info.st_dev, info.st_ino), "COORDINATOR_LOCK_REPLACED")
        locks = []
        for name, handle, identity in self.handles:
            path = self.root / name
            current, opened = path.lstat(), os.fstat(handle)
            require(stat.S_ISREG(current.st_mode) and current.st_nlink == 1 and
                    (current.st_dev, current.st_ino) == identity == (opened.st_dev, opened.st_ino),
                    "RESOURCE_LOCK_REPLACED:" + name)
            locks.append({"path": "/home/Carix/" + name, "device": identity[0], "inode": identity[1]})
        intent = json.loads(read_regular(self.control / "active-intent.json"))
        require(intent.get("holder_instance") == self.instance and
                all(intent.get(key) == value for key, value in self.session.items()) and
                intent.get("state") in {"ACQUIRING", "HELD"}, "INTENT_CHANGED")
        return locks

    def challenge(self, value: Any) -> dict[str, Any]:
        require(self.held, "NOT_HELD")
        require(isinstance(value, dict) and set(value) == {"schema", "session", "command", "challenge"}, "CHALLENGE_KEYS")
        require(value.get("schema") == CHALLENGE_SCHEMA and value.get("session") == self.session, "CHALLENGE_BINDING")
        challenge = value.get("challenge")
        require(isinstance(challenge, str) and re.fullmatch(r"[0-9a-f]{64}", challenge), "CHALLENGE_FORMAT")
        require(challenge not in self.used_challenges, "CHALLENGE_REPLAY")
        require(len(self.used_challenges) < 4096, "CHALLENGE_LIMIT")
        require(value.get("command") in {"PROBE", "RELEASE"}, "CHALLENGE_COMMAND")
        locks = self._check()
        now = dt.datetime.now(dt.timezone.utc)
        receipt = {**self._base("HELD"), "challenge": challenge, "issued_at": now.isoformat(),
                   "expires_at": (now + dt.timedelta(seconds=TTL_SECONDS)).isoformat(),
                   "ttl_seconds": TTL_SECONDS, "locks": locks, "lock_manifest_sha256": sha(canonical(locks))}
        self.last_challenge = challenge
        self.used_challenges.add(challenge)
        if value["command"] == "RELEASE":
            self.close()
            receipt.update(state="RELEASED", locks_released=True, expires_at=now.isoformat(), ttl_seconds=0)
        return receipt

    def _unlock(self) -> None:
        errors = []
        for _name, fd, _identity in reversed(self.handles):
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except BaseException as error:
                errors.append(error)
            try:
                os.close(fd)
            except BaseException as error:
                errors.append(error)
        self.handles.clear()
        if self.own_fd is not None:
            try:
                fcntl.flock(self.own_fd, fcntl.LOCK_UN)
            except BaseException as error:
                errors.append(error)
            try:
                os.close(self.own_fd)
            except BaseException as error:
                errors.append(error)
            self.own_fd = None
        self.held = False
        if errors:
            raise errors[0]

    def close(self) -> None:
        if self.own_fd is None:
            return
        cleanup_error = None
        try:
            if self.intent_created:
                self._intent("RELEASING")
        except BaseException as error:
            cleanup_error = error
        try:
            self._unlock()
        except BaseException as error:
            cleanup_error = cleanup_error or error
        if cleanup_error is not None:
            raise cleanup_error
        if self.intent_created:
            self._intent("RELEASED")  # Persist; never archive/unpause here.


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    args = parser.parse_args()
    path = pathlib.Path(args.request)
    expected = CONTROL / "sessions" / path.parent.name / "request.json"
    require(path == expected and re.fullmatch(r"[0-9a-f]{64}", path.parent.name), "REQUEST_PATH")
    request = json.loads(read_regular(path))
    require(isinstance(request, dict) and set(request) == {"schema", "session"} and
            request["schema"] == REQUEST_SCHEMA, "REQUEST_SCHEMA")
    require(request["session"].get("nonce") == path.parent.name, "REQUEST_NONCE")
    lease = FenceLease(BASE, CONTROL, request["session"])
    stopping = False

    def stop(_signum: int, _frame: Any) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    lease.acquire()
    try:
        while not stopping and lease.held:
            lease._check()
            try:
                command = json.loads(read_regular(lease.directory / "challenge.json"))
            except FileNotFoundError:
                command = None
            except (ValueError, UnicodeDecodeError):
                command = None  # An interrupted Files API upload is not proof.
            if command is not None and command.get("challenge") != lease.last_challenge:
                response = lease.challenge(command)
                write_json(lease.directory / "response.json", response)
            time.sleep(0.2)
    finally:
        lease.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

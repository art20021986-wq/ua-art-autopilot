#!/usr/bin/env python3
"""Run pinned synthetic coordination tests on PA; never touch application data.

The launcher reads only its own frozen bundle and creates a unique run directory.
The child applies a Python audit guard before test imports. This is an audited
trusted-code test harness, not an OS sandbox for hostile/native-extension code.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import io
import json
import multiprocessing
import multiprocessing.queues
import multiprocessing.synchronize
import os
from pathlib import Path
import signal
import socket
import stat
import subprocess
import sys
import sysconfig
import tempfile
import time
import unittest
import urllib.error
import urllib.request
import uuid

STAGE = Path("/home/Carix/writer_coordination_gate_20260909")
BUNDLE_FILES = {
    "server_fence.py", "test_server_fence.py", "platform_control.py",
    "tests/test_platform_control.py", "coordination_server_gate.py",
}


def sha(value):
    return hashlib.sha256(value).hexdigest()


def checked_directory(path):
    if not path.is_absolute() or path.resolve() != path:
        raise RuntimeError("STAGE_DIRECTORY_PATH")
    for ancestor in (path, *path.parents):
        info = ancestor.lstat()
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
            raise RuntimeError("STAGE_DIRECTORY_TYPE")


def file_snapshot(path):
    checked_directory(path.parent)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 2 * 1024 * 1024:
            raise RuntimeError("BUNDLE_FILE_TYPE_OR_SIZE")
        with os.fdopen(os.dup(fd), "rb") as stream:
            data = stream.read()
        after = os.fstat(fd)
        if (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise RuntimeError("BUNDLE_FILE_CHANGED")
        return {"sha256": sha(data), "bytes": len(data), "mtime_ns": after.st_mtime_ns}
    finally:
        os.close(fd)


def verify_bundle(bundle):
    checked_directory(bundle)
    manifest_info = file_snapshot(bundle / "bundle-manifest.json")
    manifest_bytes = (bundle / "bundle-manifest.json").read_bytes()
    if sha(manifest_bytes) != manifest_info["sha256"]:
        raise RuntimeError("BUNDLE_MANIFEST_CHANGED")
    manifest = json.loads(manifest_bytes)
    if manifest.get("schema") != "UA-ART-WRITER-COORDINATION-TEST-BUNDLE-1" or set(manifest.get("files", {})) != BUNDLE_FILES:
        raise RuntimeError("BUNDLE_MANIFEST_SCOPE")
    actual_files = {p.relative_to(bundle).as_posix() for p in bundle.rglob("*") if p.is_file()}
    if actual_files != BUNDLE_FILES | {"bundle-manifest.json"}:
        raise RuntimeError("BUNDLE_FILE_SET")
    snapshots = {name: file_snapshot(bundle / name) for name in sorted(BUNDLE_FILES)}
    if any(item["sha256"] != manifest["files"][name] for name, item in snapshots.items()):
        raise RuntimeError("BUNDLE_FILE_SHA")
    if set(manifest.get("test_counts", {})) != {"test_server_fence.py", "test_platform_control.py"}:
        raise RuntimeError("BUNDLE_TEST_COUNT_SCHEMA")
    if any(type(value) is not int or value <= 0 for value in manifest["test_counts"].values()):
        raise RuntimeError("BUNDLE_TEST_COUNTS")
    return manifest, snapshots


def run_tests(bundle, output):
    """Also callable in a disposable local QA child with explicitly supplied roots."""
    checked_directory(bundle)
    checked_directory(output)
    manifest, before = verify_bundle(bundle)
    temporary = output / "tmp"
    temporary.mkdir(mode=0o700)
    tempfile.tempdir = str(temporary)
    os.environ["TMPDIR"] = str(temporary)
    os.chdir(output)
    stdlib_roots = {Path(sysconfig.get_path(name)).resolve() for name in ("stdlib", "platstdlib")}
    read_roots = {bundle, output, *stdlib_roots}
    counters = {"blocked_network": 0, "blocked_subprocess": 0, "blocked_read": 0, "blocked_write": 0}

    def normalized(value, dir_fd=None):
        if isinstance(value, int):
            return None
        path = Path(os.fsdecode(value))
        if not path.is_absolute():
            base = Path(os.readlink("/proc/self/fd/" + str(dir_fd))) if dir_fd is not None and dir_fd >= 0 else Path.cwd()
            path = base / path
        return path.resolve()

    def under(path, roots):
        return any(path == root or root in path.parents for root in roots)

    def path_check(value, writing, dir_fd=None):
        path = normalized(value, dir_fd)
        if path is None or path == Path("/dev/null"):
            return
        if not under(path, {output} if writing else read_roots):
            counter = "blocked_write" if writing else "blocked_read"
            counters[counter] += 1
            raise RuntimeError("TEST_IO_GUARD_" + counter.upper())

    def audit(event, args):
        if event in {"socket.connect", "socket.connect_ex", "socket.bind", "socket.sendto", "socket.getaddrinfo",
                     "socket.gethostbyname", "socket.gethostbyaddr", "socket.getnameinfo"}:
            counters["blocked_network"] += 1
            raise RuntimeError("TEST_NETWORK_FORBIDDEN")
        if event in {"subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.posix_spawnp"}:
            counters["blocked_subprocess"] += 1
            raise RuntimeError("TEST_SUBPROCESS_FORBIDDEN")
        if event == "open":
            mode, flags = args[1], args[2]
            writing = bool(isinstance(mode, str) and any(c in mode for c in "wax+")) or bool(
                isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            path_check(args[0], writing)
        elif event in {"os.mkdir", "os.remove", "os.rmdir", "os.chmod", "os.chown", "os.utime", "os.truncate"}:
            index = {"os.mkdir": 2, "os.remove": 1, "os.rmdir": 1, "os.chmod": 2, "os.chown": 3, "os.utime": 3}.get(event)
            directory_fd = args[index] if index is not None and len(args) > index else None
            path_check(args[0], True, directory_fd)
        elif event in {"os.rename", "os.link"}:
            path_check(args[0], True, args[2] if len(args) > 2 else None)
            path_check(args[1], True, args[3] if len(args) > 3 else None)
        elif event == "os.symlink":
            destination = normalized(args[1])
            path_check(destination, True)
            target = Path(os.fsdecode(args[0]))
            path_check(target if target.is_absolute() else destination.parent / target, True)
        elif event in {"os.listdir", "os.scandir"}:
            path_check(args[0], False)
        elif event == "os.chdir":
            path_check(args[0], False)
        elif event == "os.kill":
            if args[0] not in {process.pid for process in multiprocessing.active_children()}:
                raise RuntimeError("TEST_SIGNAL_TARGET_FORBIDDEN")

    sys.addaudithook(audit)
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    stream = io.StringIO()
    suite = unittest.TestSuite()
    suite.addTests(unittest.TestLoader().discover(str(bundle), pattern="test_server_fence.py"))
    suite.addTests(unittest.TestLoader().discover(str(bundle / "tests"), pattern="test_platform_control.py"))
    expected = sum(manifest["test_counts"].values())
    discovered = suite.countTestCases()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    unchanged = all(file_snapshot(bundle / name) == previous for name, previous in before.items())
    report = {
        "schema": "UA-ART-WRITER-COORDINATION-SERVER-TEST-1",
        "status": "PASS" if result.wasSuccessful() and result.testsRun == expected == discovered and not result.skipped
                  and unchanged and not any(counters.values()) else "FAIL",
        "scope": "ISOLATED_SYNTHETIC_LOCKS_AND_FAKE_PLATFORM_API",
        "python_version": sys.version,
        "started_at": started, "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "tests": result.testsRun, "expected_tests": expected, "test_groups": manifest["test_counts"],
        "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped),
        "io_guard": counters, "bundle_inputs_unchanged": unchanged,
        "bundle_sha256": sha((bundle / "bundle-manifest.json").read_bytes()),
        "source_sha256": manifest["files"], "production_changed": False,
        "real_task_api_called": False, "production_lock_files_opened": False,
        "external_writers_verified": False, "cross_host_lock_verified": False,
        "overall_gate_b": "NOT_EVALUATED",
        "guard_limit": "Python audit guard over reviewed code; native temporary multiprocessing IPC is not an application write",
    }
    (output / "tests.log").write_text(stream.getvalue())
    (output / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


def main():
    bundle = Path(__file__).resolve().parent
    checked_directory(STAGE)
    if bundle != STAGE / "bundle-v1":
        raise RuntimeError("SERVER_STAGE_PATH_MISMATCH")
    manifest, before = verify_bundle(bundle)
    if len(sys.argv) == 3 and sys.argv[1] == "--child":
        output = Path(sys.argv[2])
        if output.parent != STAGE or not output.name.startswith("run-"):
            raise RuntimeError("CHILD_OUTPUT_SCOPE")
        return run_tests(bundle, output)
    if len(sys.argv) != 1:
        raise RuntimeError("UNEXPECTED_ARGUMENTS")
    if sys.version_info[:2] != (3, 10):
        raise RuntimeError("PYTHON310_REQUIRED")
    output = STAGE / ("run-" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    output.mkdir(mode=0o700)
    child = subprocess.run([sys.executable, "-I", "-B", str(bundle / "coordination_server_gate.py"), "--child", str(output)],
        cwd=bundle, env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True, text=True, timeout=90)
    (output / "launcher.log").write_text(child.stdout + child.stderr)
    if not (output / "result.json").is_file():
        print(child.stdout + child.stderr)
        raise RuntimeError("SERVER_TEST_RESULT_MISSING")
    report = json.loads((output / "result.json").read_text())
    unchanged = all(file_snapshot(bundle / name) == previous for name, previous in before.items())
    summary = {
        "schema": "UA-ART-WRITER-COORDINATION-SERVER-SUMMARY-1", "python_version": sys.version,
        "status": "PASS" if child.returncode == 0 and report["status"] == "PASS" and unchanged else "FAIL",
        "scope": report["scope"], "tests": report["tests"], "failures": report["failures"],
        "errors": report["errors"], "skipped": report["skipped"], "io_guard": report["io_guard"],
        "bundle_inputs_unchanged": unchanged, "production_changed": False,
        "real_task_api_called": False, "production_lock_files_opened": False,
        "external_writers_verified": False, "overall_gate_b": "NOT_EVALUATED",
        "result_path": str(output / "result.json"), "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    (output / "server-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

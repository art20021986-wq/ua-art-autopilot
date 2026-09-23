#!/usr/bin/env python3
"""Isolated PythonAnywhere allocator gate; no application top-level imports.

Run with Python 3.10 -I -B after extracting the reviewed ZIP at REQUIRED_STAGE.
Python audit hooks bound trusted Python I/O; not a sandbox for hostile native
extensions. All tested source is manifest/hash pinned and uses only stdlib.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import stat
import subprocess
import sys
import sysconfig
import tempfile
import threading
import time
import traceback
import unittest
from urllib.parse import unquote, urlsplit

REQUIRED_STAGE = Path("/home/Carix/spec_allocator_gate_20260909")
PACKAGE = Path(__file__).absolute().parents[2]
EXPECTED_SOURCES = {
    "cars_schema.py": "1dd5d950eb4514901ca51911b4c5f89481263956ceea28f30e1fa2888cdd8d73",
    "db.py": "b732a5c731d85cb4c9b1cfddb2fc20961b75230d64e29563a5b5ac328d62c086",
    "ai_filter.py": "7dfd84497c6d3823cd7df54834cb18aecdbc645544ca9709a88c6363a2d35cb6",
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inside(path, root):
    return path == root or root in path.parents


def canonical(path):
    path = Path(path).absolute()
    if path.resolve() != path or any(part.is_symlink() for part in (path, *path.parents)):
        raise RuntimeError("NONCANONICAL_OR_SYMLINK_PATH")
    return path


def verify_package():
    manifest = json.loads((PACKAGE / "allocator-gate-manifest.json").read_text())
    if manifest["source_sha256"] != EXPECTED_SOURCES:
        raise RuntimeError("PACKAGE_SOURCE_ALLOWLIST_CHANGED")
    for relative, expected in manifest["files"].items():
        path = canonical(PACKAGE / relative)
        if not inside(path, PACKAGE) or digest(path.read_bytes()) != expected["sha256"]:
            raise RuntimeError("PACKAGE_FILE_SHA_MISMATCH:" + relative)
    return manifest


def install_guard(stage, sources, allowed_processes):
    libraries = {Path(sysconfig.get_path(name)).resolve() for name in ("stdlib", "platstdlib")}
    counts = {"outside_read": 0, "outside_write": 0, "network": 0, "process_blocked": 0,
              "process_allowed": 0}

    def check(value, write=False, directory_fd=None):
        if value is None:
            return
        if isinstance(value, int):
            if value in (0, 1, 2):
                return
            value = os.readlink("/proc/self/fd/" + str(value))
            if value.startswith("pipe:["):
                return
        path = Path(os.fsdecode(value))
        if not path.is_absolute() and directory_fd not in (None, -1, -100):
            path = Path(os.readlink("/proc/self/fd/" + str(directory_fd))) / path
        path = path.absolute().resolve()
        if inside(path, stage):
            return
        if not write and (path in sources or any(inside(path, root) for root in libraries)):
            return
        kind = "outside_write" if write else "outside_read"
        counts[kind] += 1
        raise PermissionError("ALLOCATOR_GATE_" + kind.upper())

    def audit(event, args):
        if event.startswith("socket."):
            counts["network"] += 1
            raise PermissionError("ALLOCATOR_GATE_NETWORK_FORBIDDEN")
        if event == "subprocess.Popen":
            executable, argv, cwd, env = args
            candidate = tuple(argv)
            expected_env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
                            "TMPDIR": str(Path(cwd) / "tmp")} if cwd is not None else None
            if (candidate not in allowed_processes or allowed_processes[candidate] <= 0
                    or executable != sys.executable or cwd is None or not inside(Path(cwd).resolve(), stage)
                    or env != expected_env):
                counts["process_blocked"] += 1
                raise PermissionError("ALLOCATOR_GATE_PROCESS_FORBIDDEN")
            allowed_processes[candidate] -= 1
            counts["process_allowed"] += 1
        elif event in {"os.system", "os.posix_spawn", "os.fork", "os.forkpty", "pty.spawn", "os.exec"}:
            counts["process_blocked"] += 1
            raise PermissionError("ALLOCATOR_GATE_PROCESS_FORBIDDEN")
        elif event == "open":
            value, mode, flags = args
            check(value, bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)))
        elif event in {"os.listdir", "os.scandir"}:
            check(args[0])
        elif event in {"os.remove", "os.rmdir"}:
            check(args[0], True, args[1] if len(args) > 1 else None)
        elif event == "os.mkdir":
            check(args[0], True, args[2] if len(args) > 2 else None)
        elif event in {"os.rename", "os.link"}:
            check(args[0], event == "os.rename", args[2] if len(args) > 2 else None)
            check(args[1], True, args[3] if len(args) > 3 else None)
        elif event in {"os.symlink", "os.kill", "os.killpg"}:
            raise PermissionError("ALLOCATOR_GATE_MUTATION_FORBIDDEN")
        elif event in {"os.chmod", "os.chown", "os.utime", "os.truncate", "os.chdir"}:
            check(args[0], True)
        elif event == "sqlite3.connect":
            value = os.fsdecode(os.fspath(args[0]))
            if value != ":memory:":
                if value.startswith("file:"):
                    value = unquote(urlsplit(value).path)
                check(value, True)
        elif event in {"compile", "exec"}:
            filename = args[1] if event == "compile" else getattr(args[0], "co_filename", "")
            if filename and not str(filename).startswith("<"):
                check(filename)

    sys.addaudithook(audit)
    return counts


def source_snapshot(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise RuntimeError("SOURCE_NOT_REGULAR")
        data = handle.read(4 * 1024 * 1024 + 1)
        after = os.fstat(handle.fileno())
    if len(data) > 4 * 1024 * 1024 or (before.st_size, before.st_mtime_ns, before.st_ino) != (
            after.st_size, after.st_mtime_ns, after.st_ino):
        raise RuntimeError("SOURCE_CHANGED_DURING_READ")
    return data, {"sha256": digest(data), "bytes": after.st_size, "mtime_ns": after.st_mtime_ns,
                  "inode": after.st_ino, "device": after.st_dev}


def reviewed_child_code(test_path):
    tree = ast.parse(test_path.read_text())
    function = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
                    and node.name == "test_concurrent_processes_use_same_persisted_sequence")
    assignments = [node for node in function.body if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == "code" for target in node.targets)]
    if len(assignments) != 1 or not isinstance(assignments[0].value, ast.Constant):
        raise RuntimeError("CHILD_TEST_CODE_CHANGED")
    return assignments[0].value.value


def child(run, script, runtime, database):
    stage = canonical(PACKAGE)
    verify_package()
    for path in (run, script, runtime, database):
        if not inside(canonical(path), stage):
            raise RuntimeError("CHILD_PATH_OUTSIDE_STAGE")
    counts = install_guard(stage, set(), {})
    os.chdir(run)
    code = reviewed_child_code(PACKAGE / "cloud/spec_auto10_restore/tests/test_car_number_allocator.py")
    if script.read_text() != code:
        raise RuntimeError("CHILD_CODE_SHA_MISMATCH")
    sys.argv = [str(script), str(runtime), str(database)]
    exec(compile(code, str(script), "exec"), {"__name__": "__main__"})
    if any(counts.values()):
        raise RuntimeError("CHILD_GUARD_VIOLATION")


def run_gate(stage, source_root):
    stage, source_root = canonical(stage), canonical(source_root)
    if stage != PACKAGE or (stage != REQUIRED_STAGE and os.environ.get("UA_ALLOCATOR_GATE_LOCAL_PREFLIGHT") != "1"):
        raise RuntimeError("WRONG_STAGE")
    if stage == REQUIRED_STAGE and (source_root != Path("/home/Carix") or sys.version_info[:2] != (3, 10)):
        raise RuntimeError("PYTHONANYWHERE_SOURCE_AND_PYTHON310_REQUIRED")
    manifest = verify_package()
    sources = {name: canonical(source_root / name) for name in EXPECTED_SOURCES}
    run = stage / ("run-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + str(os.getpid()))
    allowed_processes = {}
    counts = install_guard(stage, set(sources.values()), allowed_processes)
    run.mkdir(mode=0o700)
    (run / "tmp").mkdir(mode=0o700)
    (run / "sources").mkdir(mode=0o700)
    os.chdir(run)
    os.environ["TMPDIR"] = str(run / "tmp")
    tempfile.tempdir = str(run / "tmp")
    sys.dont_write_bytecode = True
    before = {}
    for name, path in sources.items():
        data, before[name] = source_snapshot(path)
        if before[name]["sha256"] != EXPECTED_SOURCES[name]:
            raise RuntimeError("PRODUCTION_SOURCE_SHA_CHANGED:" + name)
        (run / "sources" / name).write_bytes(data)
    for variable, name in (("UA_ART_ALLOCATOR_SCHEMA", "cars_schema.py"), ("UA_ART_ALLOCATOR_DB", "db.py"),
                           ("UA_ART_ALLOCATOR_AI_FILTER", "ai_filter.py")):
        os.environ[variable] = str(run / "sources" / name)

    test_path = PACKAGE / "cloud/spec_auto10_restore/tests/test_car_number_allocator.py"
    runtime = PACKAGE / "cloud/spec_auto10_restore/runtime"
    code = reviewed_child_code(test_path)
    script = run / "concurrent-child.py"
    script.write_text(code)
    original_popen = subprocess.Popen

    def guarded_popen(argv, **kwargs):
        if (not isinstance(argv, list) or len(argv) != 5 or argv[:2] != [sys.executable, "-c"]
                or argv[2] != code or Path(argv[3]) != runtime or not inside(canonical(argv[4]), run / "tmp")
                or kwargs != {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "text": True}):
            raise PermissionError("UNREVIEWED_TEST_SUBPROCESS")
        command = [sys.executable, "-I", "-B", str(Path(__file__).absolute()), "--child", str(run),
                   str(script), str(runtime), argv[4]]
        key = tuple(command)
        allowed_processes[key] = allowed_processes.get(key, 0) + 1
        child_environment = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
                             "TMPDIR": str(run / "tmp")}
        return original_popen(command, cwd=str(run), env=child_environment, **kwargs)

    subprocess.Popen = guarded_popen
    log = io.StringIO()
    started = time.monotonic()
    try:
        suite = unittest.defaultTestLoader.discover(str(test_path.parent), pattern=test_path.name)
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    finally:
        subprocess.Popen = original_popen
    after = {name: source_snapshot(path)[1] for name, path in sources.items()}
    unchanged = before == after
    imported_applications = sorted(name for name in ("db", "cars_schema", "ai_filter", "team_bot") if name in sys.modules)
    report = {"scope": "ISOLATED_ALLOCATOR_ACTUAL_SOURCE_TESTS", "python": sys.version,
              "status": "PASS" if (result.wasSuccessful() and result.testsRun == 26 and not result.skipped
                  and unchanged and not imported_applications and counts["process_allowed"] == 3
                  and not any(value for name, value in counts.items() if name != "process_allowed")) else "FAIL",
              "tests": {"run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
                        "skipped": len(result.skipped), "duration_seconds": round(time.monotonic() - started, 4)},
              "source_before": before, "source_after": after, "production_sources_bytes_and_mtime_unchanged": unchanged,
              "guard": counts, "imported_application_modules": imported_applications,
              "package_files": manifest["files"], "production_changed": False, "live_publication_proven": False}
    (run / "allocator-tests.log").write_text(log.getvalue())
    (run / "allocator-gate-result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "result": str(run / "allocator-gate-result.json"),
                      "tests": report["tests"], "guard": counts, "production_sources_unchanged": unchanged}))
    return 0 if report["status"] == "PASS" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path("/home/Carix"))
    parser.add_argument("--child", nargs=4, type=Path)
    args = parser.parse_args()
    if args.child:
        child(*args.child)
        return 0
    return run_gate(PACKAGE, args.source_root)


if __name__ == "__main__":
    raise SystemExit(main())

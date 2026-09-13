#!/usr/bin/env python3
"""Pinned read-only input capture and isolated PythonAnywhere publisher test.

The child receives relocated source copies and synthetic CRM/spec data. This
launcher never imports production modules and never changes the active site.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

STAGE = Path("/home/Carix/spec_publisher_gate_20260909")
SOURCE = Path("/home/Carix")
CANDIDATE = Path("/home/Carix/spec_retry_v8_20260909/run-20260909T075717207121Z/cloud/spec_auto10_restore/runtime")
GOLDEN_SHA256 = "546d5c642801cd714d81451412cb584f07dbbd58264a09f57c27b0e2d05b2dd3"


def snapshot(path):
    if path.is_symlink():
        raise RuntimeError("SOURCE_SYMLINK:" + path.name)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > 4 * 1024 * 1024:
            raise RuntimeError("SOURCE_TYPE_OR_SIZE:" + path.name)
        with os.fdopen(os.dup(descriptor), "rb") as handle:
            data = handle.read()
        after = os.fstat(descriptor)
        if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
            raise RuntimeError("SOURCE_CHANGED_DURING_READ:" + path.name)
        return {"sha256": hashlib.sha256(data).hexdigest(), "mtime_ns": after.st_mtime_ns, "bytes": len(data)}
    finally:
        os.close(descriptor)


def main():
    bundle = Path(__file__).resolve().parent
    if STAGE.is_symlink() or STAGE.resolve() != STAGE or bundle.parent != STAGE or bundle.name != "bundle-v2":
        raise RuntimeError("PUBLISHER_STAGE_PATH_MISMATCH")
    manifest = json.loads((bundle / "bundle-manifest.json").read_text())
    for name, expected in manifest["files"].items():
        if name.startswith("/") or ".." in Path(name).parts:
            raise RuntimeError("BUNDLE_MANIFEST_PATH")
        if snapshot(bundle / name)["sha256"] != expected:
            raise RuntimeError("BUNDLE_SHA_MISMATCH:" + name)
    current = json.loads((bundle / "current-manifest.json").read_text())
    candidate = json.loads((bundle / "candidate-manifest.json").read_text())
    watched = {}
    for base, names in [(SOURCE, current), (CANDIDATE, candidate)]:
        for name, expected in names.items():
            if "/" in name or not name.endswith(".py"):
                raise RuntimeError("MODULE_NAME_INVALID")
            path = base / name
            watched[path] = snapshot(path)
            if watched[path]["sha256"] != expected["sha256"]:
                raise RuntimeError("RUNTIME_INPUT_SHA_MISMATCH:" + name)
    golden = SOURCE / "catalog_design_golden.html"
    watched[golden] = snapshot(golden)
    if watched[golden]["sha256"] != GOLDEN_SHA256:
        raise RuntimeError("GOLDEN_SHA_MISMATCH")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = STAGE / ("run-" + stamp)
    environment = {"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"}
    tests = subprocess.run([sys.executable, "-I", "-B", "-m", "unittest", "discover",
                            "-s", str(bundle / "tests"), "-p", "test_full_publisher_rehearsal.py", "-v"],
                           cwd=bundle, env=environment, capture_output=True, text=True, timeout=45)
    if tests.returncode:
        print(tests.stdout + tests.stderr)
        raise RuntimeError("PUBLISHER_GUARD_TESTS_FAILED")
    command = [sys.executable, "-I", "-B", str(bundle / "full_publisher_rehearsal.py"),
               "--current", str(SOURCE), "--candidate", str(CANDIDATE), "--golden", str(golden),
               "--current-manifest", str(bundle / "current-manifest.json"),
               "--candidate-manifest", str(bundle / "candidate-manifest.json"),
               "--golden-sha256", GOLDEN_SHA256, "--output", str(output),
               "--master-shell-patch", "--public-contract-patch"]
    child = subprocess.run(command, cwd=bundle, env=environment, capture_output=True, text=True, timeout=120)
    if not output.is_dir() or output.is_symlink():
        print(child.stdout + child.stderr)
        raise RuntimeError("PUBLISHER_CHILD_OUTPUT_MISSING")
    report = json.loads((output / "result.json").read_text())
    unchanged = all(snapshot(path) == expected for path, expected in watched.items())
    summary = {"status": "PASS" if child.returncode == 0 and report["status"] == "PASS" and unchanged else "FAIL",
               "scope": "PYTHON310_ISOLATED_FULL_PUBLISHER_SYNTHETIC_DATA",
               "production_changed": False, "runtime_input_bytes_and_mtime_unchanged": unchanged,
               "watched_input_files": len(watched), "python_version": sys.version,
               "guard_unit_tests": {"returncode": tests.returncode, "count": 8},
               "publisher_report": str(output / "result.json"), "io_guard": report.get("io_guard"),
               "primary_pages_validated": len([item for item in report.get("checks", []) if item["check"] == "primary_spec_and_single_vin"]),
               "repeat": report.get("repeat"),
               "nonvacuous_rollback": report.get("fault_rollback", {}).get("status"),
               "wrong_page_controls": report.get("public_contract_negative_controls", {}).get("status"),
               "overall_gate_b": "NOT_EVALUATED", "updated_at_utc": datetime.now(timezone.utc).isoformat()}
    (output / "guard-tests.log").write_text(tests.stdout + tests.stderr)
    (output / "launcher.log").write_text(child.stdout + child.stderr)
    (output / "server-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

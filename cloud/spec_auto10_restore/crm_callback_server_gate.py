#!/usr/bin/env python3
"""Bounded PA rehearsal of actual CRM callback registration and edit repair.

Two isolated runs prove the frozen bug and the repaired behavior. No application
module is imported from production; only three pinned dependencies are read.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

STAGE = Path("/home/Carix/spec_crm_callback_gate_20260909")
SOURCE = Path("/home/Carix")
MANIFEST_SHA = "12afce821b784771a2a8a0415cc289f5e713d53aabedf0ed3e2747a8c4d4e136"
PATCHER_SHA = "97e1f170301d26403e115962392587f141be40a97b94acae412e3caeec8611f1"
RUNNERS = {"crm_callback_cycle.py", "crm_callback_server_gate.py", "repair_crm_edit_session.py",
           "complete17_cycle.py", "complete15_cycle.py", "full_publisher_rehearsal.py"}


def snapshot(path):
    if path.is_symlink() or path.resolve() != path.absolute():
        raise RuntimeError("NONCANONICAL_INPUT:" + path.name)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > 4 * 1024 * 1024:
            raise RuntimeError("INPUT_TYPE_OR_SIZE:" + path.name)
        with os.fdopen(os.dup(descriptor), "rb") as handle:
            data = handle.read()
        after = os.fstat(descriptor)
        linked = path.lstat()
        identity = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)
        if identity(before) != identity(after) or identity(after) != identity(linked):
            raise RuntimeError("INPUT_CHANGED_DURING_READ:" + path.name)
        return {"sha256": hashlib.sha256(data).hexdigest(), "identity": list(identity(after))}
    finally:
        os.close(descriptor)


def main():
    bundle = Path(__file__).absolute().parent
    if STAGE.is_symlink() or STAGE.resolve() != STAGE or bundle != STAGE / "bundle-v1":
        raise RuntimeError("CRM_CALLBACK_STAGE_PATH_MISMATCH")
    if sys.version_info[:2] != (3, 10):
        raise RuntimeError("SERVER_PYTHON310_REQUIRED")
    manifest = json.loads((bundle / "bundle-manifest.json").read_text())
    candidate_manifest = bundle / "candidate" / "manifest.json"
    if snapshot(candidate_manifest)["sha256"] != MANIFEST_SHA:
        raise RuntimeError("FINAL17_V2_MANIFEST_MISMATCH")
    candidate = json.loads(candidate_manifest.read_text())
    expected_names = {"candidate/" + name for name in candidate["files"]} | {"candidate/manifest.json"} | RUNNERS
    if len(candidate["files"]) != 17 or set(manifest["files"]) != expected_names:
        raise RuntimeError("BUNDLE_EXACT_FILE_SET_REQUIRED")
    disk = {str(path.relative_to(bundle)) for path in bundle.rglob("*") if not path.is_dir()}
    if disk != expected_names | {"bundle-manifest.json"}:
        raise RuntimeError("BUNDLE_EXTRA_OR_MISSING_FILE")
    watched = {bundle / "bundle-manifest.json": snapshot(bundle / "bundle-manifest.json")}
    for name, expected in manifest["files"].items():
        path = bundle / name
        watched[path] = snapshot(path)
        if watched[path]["sha256"] != expected:
            raise RuntimeError("BUNDLE_SHA_MISMATCH:" + name)
    if manifest["files"]["repair_crm_edit_session.py"] != PATCHER_SHA:
        raise RuntimeError("UI_REPAIR_PATCHER_CHANGED")
    for name, expected in candidate["execution_dependency_pins"].items():
        path = SOURCE / name
        watched[path] = snapshot(path)
        if watched[path]["sha256"] != expected:
            raise RuntimeError("LIVE_DEPENDENCY_CHANGED:" + name)
    run = STAGE / ("run-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    run.mkdir(mode=0o700)
    results = {}
    for phase, expected in (("original", "KNOWN_UI_BUG_REPRODUCED"), ("repaired", "PASS")):
        output = run / phase
        command = [sys.executable, "-I", "-B", str(bundle / "crm_callback_cycle.py"),
                   "--candidate", str(bundle / "candidate"), "--dependencies", str(SOURCE),
                   "--golden", str(SOURCE / "catalog_design_golden.html"), "--output", str(output)]
        if phase == "repaired":
            command += ["--ui-patch", str(bundle / "repair_crm_edit_session.py"), "--ui-patch-sha", PATCHER_SHA]
        try:
            child = subprocess.run(command, cwd=bundle, env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"},
                                   capture_output=True, text=True, timeout=90)
        except subprocess.TimeoutExpired:
            results[phase] = {"status": "FAIL", "error": "CALLBACK_REHEARSAL_TIMEOUT"}
            break
        (run / (phase + "-launcher.log")).write_text(child.stdout + child.stderr)
        if not output.is_dir() or output.is_symlink() or not (output / "result.json").is_file():
            results[phase] = {"status": "FAIL", "error": "CALLBACK_RESULT_MISSING", "returncode": child.returncode}
            break
        report = json.loads((output / "result.json").read_text())
        counters = report.get("io_guard")
        okay = child.returncode == 0 and report.get("status") == expected and isinstance(counters, dict) and not any(counters.values())
        results[phase] = {"status": "PASS" if okay else "FAIL", "reported_status": report.get("status"),
                          "report": str(output / "result.json"), "report_sha256": snapshot(output / "result.json")["sha256"],
                          "io_guard": counters, "error": report.get("error")}
        if not okay:
            break
    unchanged = all(snapshot(path) == before for path, before in watched.items())
    summary = {"status": "PASS" if len(results) == 2 and all(result["status"] == "PASS" for result in results.values()) and unchanged else "FAIL",
               "scope": "PYTHON310_ACTUAL_CRM_CALLBACKS_WITH_FAKE_TELEGRAM_TRANSPORT", "gate_b": "NOT_EVALUATED",
               "production_changed": False, "input_bytes_mtimes_inodes_unchanged": unchanged,
               "watched_files": len(watched), "live_dependency_files": 3, "candidate_manifest_sha256": MANIFEST_SHA,
               "repair_patcher_sha256": PATCHER_SHA, "python_version": sys.version, "runs": results,
               "completed_at_utc": datetime.now(timezone.utc).isoformat()}
    (run / "server-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

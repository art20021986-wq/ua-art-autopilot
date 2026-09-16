#!/usr/bin/env python3
"""Run the frozen final15 synthetic cycle on PA; no installation or restart."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

STAGE = Path("/home/Carix/spec_complete15_cycle_gate_20260909")
SOURCE = Path("/home/Carix")
MANIFEST_SHA = "c4f75a818156e29426c9d601552ab0de56663e965233f2a56c01f5aaa111de07"


def snapshot(path):
    if path.is_symlink() or path.resolve() != path.absolute():
        raise RuntimeError("NONCANONICAL_INPUT:" + path.name)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > 4 * 1024 * 1024:
            raise RuntimeError("SOURCE_TYPE_OR_SIZE:" + path.name)
        with os.fdopen(os.dup(descriptor), "rb") as handle:
            data = handle.read()
        after = os.fstat(descriptor)
        linked = path.lstat()
        identity = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)
        if identity(before) != identity(after) or identity(after) != identity(linked):
            raise RuntimeError("INPUT_REPLACED_OR_CHANGED:" + path.name)
        return {"sha256": hashlib.sha256(data).hexdigest(), "identity": list(identity(after))}
    finally:
        os.close(descriptor)


def main():
    bundle = Path(__file__).absolute().parent
    if STAGE.is_symlink() or STAGE.resolve() != STAGE or bundle != STAGE / "bundle-v1":
        raise RuntimeError("COMPLETE15_STAGE_PATH_MISMATCH")
    if sys.version_info[:2] != (3, 10):
        raise RuntimeError("SERVER_PYTHON310_REQUIRED")
    manifest = json.loads((bundle / "bundle-manifest.json").read_text())
    candidate_manifest = bundle / "candidate" / "manifest.json"
    if snapshot(candidate_manifest)["sha256"] != MANIFEST_SHA:
        raise RuntimeError("FINAL15_MANIFEST_MISMATCH")
    candidate = json.loads(candidate_manifest.read_text())
    expected_names = {"candidate/" + name for name in candidate["files"]}
    expected_names.update({"candidate/manifest.json", "complete15_cycle.py", "full_publisher_rehearsal.py", "complete15_server_gate.py"})
    if set(manifest["files"]) != expected_names:
        raise RuntimeError("BUNDLE_EXACT_FILE_SET_REQUIRED")
    disk_names = {str(path.relative_to(bundle)) for path in bundle.rglob("*") if not path.is_dir()}
    if disk_names != expected_names | {"bundle-manifest.json"}:
        raise RuntimeError("BUNDLE_EXTRA_OR_MISSING_FILE")
    watched = {}
    for name, expected in manifest["files"].items():
        path = bundle / name
        watched[path] = snapshot(path)
        if watched[path]["sha256"] != expected:
            raise RuntimeError("BUNDLE_SHA_MISMATCH:" + name)
    for name, expected in candidate["execution_dependency_pins"].items():
        path = SOURCE / name
        watched[path] = snapshot(path)
        if watched[path]["sha256"] != expected:
            raise RuntimeError("LIVE_DEPENDENCY_CHANGED:" + name)
    output = STAGE / ("run-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    command = [sys.executable, "-I", "-B", str(bundle / "complete15_cycle.py"),
               "--candidate", str(bundle / "candidate"), "--dependencies", str(SOURCE),
               "--golden", str(SOURCE / "catalog_design_golden.html"), "--output", str(output)]
    try:
        child = subprocess.run(command, cwd=bundle, env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"},
                               capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired as exc:
        print(json.dumps({"status": "FAIL", "error": "COMBINED_CYCLE_TIMEOUT", "production_changed": False,
                          "output": str(output), "overall_gate_b": "NOT_EVALUATED"}))
        return 1
    if not output.is_dir() or output.is_symlink() or not (output / "result.json").is_file():
        print(child.stdout + child.stderr)
        raise RuntimeError("COMBINED_CYCLE_RESULT_MISSING")
    report = json.loads((output / "result.json").read_text())
    unchanged = all(snapshot(path) == before for path, before in watched.items())
    retired_present = [folder + "/" + name for folder in ("video", "site")
                       for name in ("UA-0002.html", "UA-0002-diag.html")
                       if (output / "runtime" / folder / name).exists()]
    summary = {"status": "PASS" if child.returncode == 0 and report.get("status") == "PASS" and unchanged and not retired_present else "FAIL",
               "scope": "PYTHON310_FINAL15_COMBINED_SYNTHETIC_CYCLE", "overall_gate_b": "NOT_EVALUATED",
               "production_changed": False, "input_bytes_mtimes_inodes_unchanged": unchanged,
               "watched_files": len(watched), "live_dependency_files": 3, "candidate_manifest_sha256": MANIFEST_SHA,
               "python_version": sys.version, "io_guard": report.get("io_guard"),
               "publisher": report.get("publisher", {}).get("status"),
               "rollback": report.get("publisher", {}).get("fault_rollback", {}).get("status"),
               "lifecycle": report.get("lifecycle", {}).get("status"),
               "next_created_uid": report.get("lifecycle", {}).get("next_created_uid"),
               "post_child_retired_pages_present": retired_present,
               "report": str(output / "result.json"), "error": report.get("error"),
               "completed_at_utc": datetime.now(timezone.utc).isoformat()}
    (output / "launcher.log").write_text(child.stdout + child.stderr)
    (output / "server-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

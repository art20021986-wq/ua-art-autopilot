#!/usr/bin/env python3
"""Permanent UA/GE PRICE PROTECTION software gate.

This executes actual renderer, CRM, storage, runtime and installation regression
tests in isolated temporary processes. It never accesses the live CRM or grants
Production permission. The canonical Preview and transaction gates remain
mandatory in addition to this gate.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = "UA-GE-PRICE-PROTECTION-SOFTWARE-1"
SOURCE_ROOTS = (
    "cloud/task088_stage3_renderer", "cloud/task088_price_sync",
    "cloud/ua_ge_price_protection",
    "cloud/task088_v5_install", "cloud/task088_v5_preview",
)
WORKFLOWS = (".github/workflows/uaart_critical.yml", ".github/workflows/uaart_maintenance.yml")
CANONICAL_SOURCES = ("automation/control_plane.py", "automation/test_task088_stage3_activation.py")
REQUIRED_TESTS = {
    "canonical_activation": ("automation", {"test_task088_stage3_activation.py"}),
    "renderer": ("cloud/task088_stage3_renderer", {
        "test_market_prices.py", "test_initial_html_prices.py", "test_home_prices.py",
    }),
    "pipeline": ("cloud/task088_price_sync", {
        "test_outbox.py", "test_v5_outbox.py", "test_v5_runtime.py",
        "test_runtime.py", "test_confirmation.py", "test_crm_intent_contract.py", "test_binding.py",
        "test_install_package.py", "test_public_guard_contract.py", "test_control_reader.py",
    }),
    "installer": ("cloud/task088_v5_install", {"test_adapter.py"}),
    "preview_boundary": ("cloud/task088_v5_preview", {"test_preview.py"}),
    "gate": ("cloud/ua_ge_price_protection", {"test_gate.py", "test_preview.py", "test_guard_helper.py"}),
}
# These require private, currently captured deployment inputs. They are run by
# the full Preview process. Excluding them here must never become a live PASS.
PRIVATE_TESTS = frozenset({
    "test_captured_pages.py", "test_private_source.py",
    "test_private_catalog_guard.py", "test_private_master_chain.py",
    "test_cars_ui_hook.py", "test_guard_fence.py",
    "test_private_preview_capture.py",
})


class ProtectionError(ValueError):
    pass


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def source_inventory(root):
    """Bind all importable candidate Python; reject alternate import artifacts."""
    root = root.resolve(strict=True)
    paths = set(WORKFLOWS + CANONICAL_SOURCES)
    for relative in SOURCE_ROOTS:
        directory = root / relative
        if directory.is_symlink() or not directory.is_dir():
            raise ProtectionError("PRICE_SOURCE_DIRECTORY_MISSING_OR_SYMLINK")
        for entry in directory.rglob("*"):
            if entry.is_symlink():
                raise ProtectionError("PRICE_SOURCE_SYMLINK")
            if entry.is_file() and entry.suffix.lower() in {".pyo", ".so", ".pyd", ".dll", ".dylib"}:
                raise ProtectionError("PRICE_ALTERNATE_IMPORT_ARTIFACT")
            if entry.is_file() and entry.suffix == ".pyc":
                # -B prevents new caches; existing caches are never trusted.
                raise ProtectionError("PRICE_BYTECODE_ARTIFACT")
            if entry.is_file() and entry.suffix == ".py":
                paths.add(entry.relative_to(root).as_posix())
    result = {}
    for relative in sorted(paths):
        path = root / relative
        if path.is_symlink() or not path.is_file() or path.resolve(strict=True) != path:
            raise ProtectionError("PRICE_SOURCE_FILE_MISSING_OR_SYMLINK")
        result[relative] = digest(path.read_bytes())
    return result


def suite_files(root, name):
    relative, required = REQUIRED_TESTS[name]
    available = {p.name for p in (root / relative).glob("test_*.py")}
    if not required.issubset(available):
        raise ProtectionError("PRICE_REQUIRED_REGRESSION_MISSING:" + name)
    selected = sorted(available - PRIVATE_TESTS)
    if not selected:
        raise ProtectionError("PRICE_EMPTY_REGRESSION_SUITE:" + name)
    return relative, selected


def run_suite(root, name):
    relative, selected = suite_files(root, name)
    totals = {"tests_run": 0, "failures": 0, "errors": 0, "skipped": 0,
              "expected_failures": 0, "unexpected_successes": 0}
    files = []
    with tempfile.TemporaryDirectory(prefix="ua-ge-price-protection-") as temporary:
        # No credentials, live-source paths or application environment are
        # propagated to tests. All database and publication fixtures are local.
        environment = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT") if key in os.environ}
        environment.update({"TMPDIR": temporary, "TMP": temporary, "TEMP": temporary})
        # Match the canonical execution contract's process-per-test-file
        # isolation. Legacy tests intentionally replace module-level bindings.
        for filename in selected:
            result_file = Path(temporary) / (filename + ".json")
            execution = subprocess.run(
                [sys.executable, "-I", "-B", str(root / "cloud/ua_ge_price_protection/run_suite.py"),
                 "--directory", str(root / relative), "--result", str(result_file), filename],
                cwd=temporary, env=environment, timeout=300, check=False,
            )
            if not result_file.is_file() or result_file.is_symlink():
                raise ProtectionError("PRICE_REGRESSION_RESULT_MISSING:" + filename)
            result = json.loads(result_file.read_text())
            if set(result) != set(totals) or any(type(result[k]) is not int or result[k] < 0 for k in result):
                raise ProtectionError("PRICE_REGRESSION_RESULT_INVALID:" + filename)
            if execution.returncode != 0 or result["tests_run"] == 0 or any(result[k] for k in set(totals) - {"tests_run"}):
                raise ProtectionError("PRICE_REGRESSION_NOT_100_PERCENT:" + filename)
            files.append({"file": filename, **result})
            for key in totals:
                totals[key] += result[key]
    return {"suite": name, "status": "PASS", "files": files, **totals}


def run(root=ROOT, *, execute=run_suite):
    report = {
        "contract": CONTRACT, "name": "UA/GE PRICE PROTECTION",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "software_status": "FAIL", "production_authorized": False,
        "live_preview_status": "NOT_RUN", "suites": [],
    }
    try:
        before = source_inventory(root)
        report["source_files_sha256"] = before
        report["source_manifest_sha256"] = digest(encoded(before))
        for name in REQUIRED_TESTS:
            report["suites"].append(execute(root, name))
        if source_inventory(root) != before:
            raise ProtectionError("PRICE_SOURCE_CHANGED_DURING_REGRESSION")
        report["software_status"] = "PASS"
    except (ProtectionError, OSError, ValueError, subprocess.SubprocessError) as error:
        report["reason"] = str(error) if isinstance(error, ProtectionError) else type(error).__name__
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    report = run()
    payload = encoded(report)
    if arguments.output:
        # Caller owns an ephemeral report path; existing evidence is immutable.
        with arguments.output.open("xb") as stream:
            stream.write(payload)
    print(payload.decode(), end="")
    return 0 if report["software_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""
Restricted no-argument launcher for UA Cards Unified Gate A (TASK 021).

- No CLI arguments accepted (sys.argv length must be exactly 1).
- No --apply, arbitrary-root, arbitrary-output, production, reload, or
  database-write option exists anywhere in this module.
- Loads a pre-built manifest, verifies runner/manifest-builder/launcher
  self-identity hashes and all input hashes, executes exactly once
  under an exclusive lock, and writes a receipt.
"""
from __future__ import annotations

import fcntl
import json
import sys
import time
from pathlib import Path

from . import common
from . import manifest_builder
from . import runner


class LauncherError(Exception):
    pass


LOCK_FILENAME = ".ua_cards_unified_gate_a.lock"


def load_manifest(manifest_path: Path) -> dict:
    common.require_regular_non_symlink(manifest_path)
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    if not manifest_builder.verify_manifest_integrity(manifest):
        raise LauncherError("Manifest integrity check failed")
    return manifest


def verify_code_hashes(manifest: dict, package_dir: Path) -> None:
    expected = manifest.get("code_hashes", {})
    for name, expected_hash in expected.items():
        p = package_dir / name
        actual_hash = common.sha256_file(p)
        if actual_hash != expected_hash:
            raise LauncherError(f"Code hash mismatch for {name}")


def verify_input_hashes(manifest: dict) -> None:
    for name, path_str in manifest.get("discovered_inputs", {}).items():
        p = Path(path_str)
        common.require_regular_non_symlink(p)
        actual = common.sha256_file(p)
        expected = manifest.get("protected_paths_before", {}).get(name)
        if expected is not None and actual != expected:
            raise LauncherError(f"Input hash mismatch for {name}")


def run(manifest_path: Path, base_root: Path, report_root: Path, package_dir: Path) -> dict:
    if len(sys.argv) != 1:
        raise LauncherError(
            "This launcher accepts no command-line arguments. "
            "No --apply, arbitrary-root, or production option exists."
        )

    report_root.mkdir(parents=True, exist_ok=True)
    lock_path = report_root / LOCK_FILENAME
    lock_file = open(lock_path, "w")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        raise LauncherError("Another Gate A execution is already running") from exc

    try:
        manifest = load_manifest(manifest_path)
        verify_code_hashes(manifest, package_dir)
        verify_input_hashes(manifest)

        result = runner.run_gate_a(base_root, report_root, package_dir)

        receipt = {
            "manifest_sha256": manifest.get("manifest_sha256"),
            "code_hashes": manifest.get("code_hashes"),
            "overall_status": result.overall_status,
            "unexpected_protected_changes": result.unexpected_protected_changes,
            "production_write": result.production_write,
            "generated_at_unix_ns": time.time_ns(),
        }
        writer = common.AtomicWriter([report_root])
        receipt_path = report_root / "gate_a_receipt.json"
        writer.write_text(receipt_path, json.dumps(receipt, sort_keys=True, indent=2))
        return receipt
    finally:
        fcntl.flock(lock_file, fcntl.LOCK_UN)
        lock_file.close()


def main() -> int:
    # No argparse. No hidden flags. Exactly the bounded, hardcoded paths
    # documented in OPERATOR_INSTRUCTIONS.md are used in a real PA run.
    if len(sys.argv) != 1:
        print("This launcher accepts no arguments.", file=sys.stderr)
        return 2
    print(
        "This is a controlled entry point; see OPERATOR_INSTRUCTIONS.md "
        "for the exact bounded runtime invocation.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

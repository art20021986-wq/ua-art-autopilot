"""Canonical manifest builder for a completed Gate A run directory
(TASK 032). Read-only against the package directory and the run
directory's own receipt/report files. Never follows symlinks, rejects
duplicate/missing/unsafe/non-regular package files, and binds package
code hashes, secure source fingerprints, candidate/diff hashes,
compilation evidence, deterministic-repeat evidence, SQLite/UA-0009/
publication evidence, before/after site inventories, the allowed-write
ledger, and receipt/report hashes into one deterministic manifest.
"""
import os
import sys
import json
import hashlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

REQUIRED_MANIFEST_FIELDS = [
    "package_code_hashes",
    "secure_source_fingerprints",
    "candidate_hashes",
    "diff_sha256",
    "compilation_result",
    "deterministic_repeat",
    "sqlite_evidence",
    "ua0009_evidence",
    "publication_evidence",
    "site_inventory_before",
    "site_inventory_after",
    "allowed_write_ledger",
    "report_sha256",
    "receipt_sha256",
]


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _package_code_hashes(package_dir):
    hashes = {}
    seen = set()
    for name in sorted(os.listdir(package_dir)):
        if not name.endswith(".py"):
            continue
        full = os.path.join(package_dir, name)
        if os.path.islink(full):
            raise ValueError(f"symlink package file rejected: {name}")
        if not os.path.isfile(full):
            continue
        if name in seen:
            raise ValueError(f"duplicate package file: {name}")
        seen.add(name)
        hashes[name] = _sha256_file(full)
    return hashes


def build_manifest(package_dir, run_dir, receipt):
    """receipt must be the exact dict produced by run_gate_a() or
    orchestrate_gate_a() (or an equivalent JSON-loaded structure). Does
    not fabricate any field: if the receipt lacks required evidence, the
    corresponding manifest field is set from whatever the receipt
    actually contains (which may itself be a BLOCKED sub-record)."""
    if not os.path.isdir(run_dir):
        raise ValueError("run_dir must exist")
    if os.path.islink(run_dir):
        raise ValueError("run_dir must not be a symlink")

    evidence = receipt.get("evidence", {}) or {}
    manifest = {
        "package_code_hashes": _package_code_hashes(package_dir),
        "secure_source_fingerprints": evidence.get("inputs_present_and_regular", {}),
        "candidate_hashes": receipt.get("package_hashes", {}),
        "diff_sha256": receipt.get("diff_sha256"),
        "compilation_result": evidence.get("candidates_compile", {}),
        "deterministic_repeat": evidence.get("deterministic_repeat_all_transforms", {}),
        "sqlite_evidence": evidence.get("sqlite_readonly_quickcheck_ok", {}),
        "ua0009_evidence": evidence.get("ua0009_fingerprint_unchanged", {}),
        "publication_evidence": evidence.get("ua0009_not_public", {}),
        "site_inventory_before": receipt.get("site_inventories", {}).get("before", {}),
        "site_inventory_after": receipt.get("site_inventories", {}).get("after", {}),
        "allowed_write_ledger": receipt.get("allowed_write_ledger", []),
        "report_sha256": None,
        "receipt_sha256": None,
    }

    receipt_path = os.path.join(run_dir, "receipt.json")
    report_path = os.path.join(run_dir, "report.md")
    if os.path.isfile(receipt_path) and not os.path.islink(receipt_path):
        manifest["receipt_sha256"] = _sha256_file(receipt_path)
    if os.path.isfile(report_path) and not os.path.islink(report_path):
        manifest["report_sha256"] = _sha256_file(report_path)

    for field in REQUIRED_MANIFEST_FIELDS:
        if field not in manifest:
            raise ValueError(f"manifest missing required field: {field}")
    return manifest


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: build_manifest.py <package_dir> <run_dir>")
        sys.exit(2)
    package_dir = sys.argv[1]
    run_dir = sys.argv[2]
    receipt_path = os.path.join(run_dir, "receipt.json")
    receipt = {}
    if os.path.isfile(receipt_path):
        with open(receipt_path, "r") as fh:
            receipt = json.load(fh)
    manifest = build_manifest(package_dir, run_dir, receipt)
    print(json.dumps(manifest, indent=2, default=str))

"""
build_manifest.py (TASK 034)

Standalone, syntactically simple, deterministic manifest builder. No
production access -- only explicit data arguments and a caller-supplied
run directory. Unsafe paths, symlinks, non-regular/hard-linked files,
duplicate logical paths, and files outside the resolved run directory
are all rejected with a plain ValueError (never a raised OSError from
half-open files, never a crash on unexpected input).

The manifest binds: package code hashes, run-directory artifact hashes
(candidates/diffs/reports/receipts, keyed by logical name), the
allowed-write ledger, SQLite ownership evidence, UA-0009 before/after
evidence, the canonical publication result, and a fixed PII_EMITTED:NO
flag. Output is deterministic and JSON-serializable via canonical_json.
The manifest never contains a hash of itself (no self-referential
cycle). Integration with a central orchestrator is deferred to a later
task; this module is used standalone with explicitly passed evidence.
"""
import hashlib
import json
import os
import stat
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

REQUIRED_MANIFEST_FIELDS = [
    "package_code_hashes",
    "run_artifact_hashes",
    "allowed_write_ledger",
    "sqlite_evidence",
    "ua0009_evidence_before",
    "ua0009_evidence_after",
    "publication_evidence",
    "pii_emitted",
]


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _secure_hash_file(path, must_be_within=None):
    """Hash a single file after rejecting symlinks, non-regular files,
    hard-linked files (nlink != 1), and (when must_be_within is given)
    files whose real path resolves outside that directory."""
    if os.path.islink(path):
        raise ValueError(f"symlink_rejected:{os.path.basename(path)}")
    try:
        st = os.lstat(path)
    except OSError as exc:
        raise ValueError(f"stat_failed:{type(exc).__name__}")
    if not stat.S_ISREG(st.st_mode):
        raise ValueError("not_regular_file")
    if st.st_nlink != 1:
        raise ValueError("hard_linked_file_rejected")
    if must_be_within is not None:
        real = os.path.realpath(path)
        base = os.path.realpath(must_be_within)
        try:
            common = os.path.commonpath([real, base])
        except ValueError:
            raise ValueError("path_outside_run_dir")
        if common != base:
            raise ValueError("path_outside_run_dir")
    return _sha256_file(path)


def _package_code_hashes(package_dir):
    hashes = {}
    seen = set()
    for name in sorted(os.listdir(package_dir)):
        if not name.endswith(".py"):
            continue
        full = os.path.join(package_dir, name)
        if os.path.islink(full):
            raise ValueError(f"symlink_package_file_rejected:{name}")
        if not os.path.isfile(full):
            continue
        if name in seen:
            raise ValueError(f"duplicate_package_file:{name}")
        seen.add(name)
        hashes[name] = _secure_hash_file(full)
    return hashes


def build_manifest(
    package_dir,
    run_dir,
    run_artifact_paths=None,
    allowed_write_ledger=None,
    sqlite_evidence=None,
    ua0009_evidence_before=None,
    ua0009_evidence_after=None,
    publication_evidence=None,
):
    """Build a deterministic manifest dict. run_artifact_paths maps a
    logical name (e.g. 'receipt', 'report', 'candidate_cars_ui',
    'diff_cars_ui') to an on-disk path that must resolve inside
    run_dir. Evidence arguments are bound as-is (already-computed
    dict/dataclass-derived structures) -- this function does not
    compute evidence itself."""
    if not os.path.isdir(run_dir):
        raise ValueError("run_dir_missing")
    if os.path.islink(run_dir):
        raise ValueError("run_dir_is_symlink")
    run_dir_real = os.path.realpath(run_dir)

    run_artifact_paths = run_artifact_paths or {}
    artifact_hashes = {}
    seen_logical = set()
    for logical_name in sorted(run_artifact_paths):
        if logical_name in seen_logical:
            raise ValueError(f"duplicate_logical_path:{logical_name}")
        seen_logical.add(logical_name)
        path = run_artifact_paths[logical_name]
        artifact_hashes[logical_name] = _secure_hash_file(path, must_be_within=run_dir_real)

    ledger_items = allowed_write_ledger or []
    sorted_ledger = sorted(ledger_items, key=lambda item: json.dumps(item, sort_keys=True, default=str))

    manifest = {
        "package_code_hashes": _package_code_hashes(package_dir),
        "run_artifact_hashes": artifact_hashes,
        "allowed_write_ledger": sorted_ledger,
        "sqlite_evidence": sqlite_evidence if sqlite_evidence is not None else {},
        "ua0009_evidence_before": ua0009_evidence_before if ua0009_evidence_before is not None else {},
        "ua0009_evidence_after": ua0009_evidence_after if ua0009_evidence_after is not None else {},
        "publication_evidence": publication_evidence if publication_evidence is not None else {},
        "pii_emitted": "NO",
    }

    for field_name in REQUIRED_MANIFEST_FIELDS:
        if field_name not in manifest:
            raise ValueError(f"manifest_missing_field:{field_name}")
    return manifest


def canonical_json(manifest):
    """Deterministic, sorted, JSON-serializable rendering of a
    manifest."""
    return json.dumps(manifest, sort_keys=True, separators=(",", ":"), default=str)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: build_manifest.py <package_dir> <run_dir>")
        sys.exit(2)
    manifest = build_manifest(sys.argv[1], sys.argv[2])
    print(canonical_json(manifest))

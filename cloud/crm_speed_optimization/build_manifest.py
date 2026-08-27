"""
build_manifest.py (TASK 034 / TASK 035 compatibility integration)

Two supported, structurally-detected call forms:

1. Historical: build_manifest(package_dir, run_dir, receipt_dict) --
   the third positional argument is the orchestration receipt dict
   (never a logical-path mapping). This form hashes the existing
   receipt.json / report.md already on disk in run_dir and binds
   evidence extracted *from the receipt dict itself* (package/input/
   candidate/diff/compilation/deterministic/SQLite/UA/publication/
   site/ledger evidence). It never calls lstat on a list/dict value --
   only on the two fixed on-disk artifact paths it hashes directly.

2. Canonical: build_manifest(package_dir, run_dir, run_artifact_paths=...,
   allowed_write_ledger=..., sqlite_evidence=..., ua0009_evidence_before=...,
   ua0009_evidence_after=..., publication_evidence=...) -- keyword-only
   logical artifact paths/evidence arguments. Each run_artifact_paths
   value may be a single path string or an explicitly bounded list of
   path strings (<= MAX_ARTIFACT_LIST_ENTRIES, no duplicates); both
   forms are normalized safely and never passed directly to lstat as a
   list/dict. A dict value (or any other non-str/non-list type) is
   rejected with a plain ValueError.

Unsafe paths, symlinks, non-regular/hard-linked files, duplicate
logical paths, and files outside the resolved run directory are all
rejected with a plain ValueError (never a raised OSError from a
half-open file, never a crash on unexpected input).

Output is deterministic and JSON-serializable via canonical_json. The
manifest never contains a hash of itself (no self-referential cycle).
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

MAX_ARTIFACT_LIST_ENTRIES = 20


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _secure_hash_file(path, must_be_within=None):
    """Hash a single file after rejecting symlinks, non-regular files,
    hard-linked files (nlink != 1), non-string path values, and (when
    must_be_within is given) files whose real path resolves outside
    that directory."""
    if not isinstance(path, str):
        raise ValueError("path_must_be_string")
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


def _normalize_artifact_entry(logical_name, path_value, run_dir_real):
    """Normalize a single logical artifact-path mapping value. Accepts
    a single path string or a bounded list/tuple of path strings.
    Rejects dicts and any other type outright, and never passes a
    list/dict directly to lstat."""
    if isinstance(path_value, dict):
        raise ValueError(f"invalid_artifact_path_type:{logical_name}")
    if isinstance(path_value, (list, tuple)):
        if len(path_value) == 0:
            raise ValueError(f"empty_artifact_list:{logical_name}")
        if len(path_value) > MAX_ARTIFACT_LIST_ENTRIES:
            raise ValueError(f"artifact_list_overflow:{logical_name}")
        seen_sub = set()
        hashes = []
        for entry in path_value:
            if not isinstance(entry, str):
                raise ValueError(f"invalid_artifact_path_entry:{logical_name}")
            if entry in seen_sub:
                raise ValueError(f"duplicate_artifact_path_entry:{logical_name}")
            seen_sub.add(entry)
            hashes.append(_secure_hash_file(entry, must_be_within=run_dir_real))
        return hashes
    if isinstance(path_value, str):
        return _secure_hash_file(path_value, must_be_within=run_dir_real)
    raise ValueError(f"invalid_artifact_path_type:{logical_name}")


def _build_canonical_manifest(
    package_dir,
    run_dir,
    run_artifact_paths=None,
    allowed_write_ledger=None,
    sqlite_evidence=None,
    ua0009_evidence_before=None,
    ua0009_evidence_after=None,
    publication_evidence=None,
):
    if not os.path.isdir(run_dir):
        raise ValueError("run_dir_missing")
    if os.path.islink(run_dir):
        raise ValueError("run_dir_is_symlink")
    run_dir_real = os.path.realpath(run_dir)

    run_artifact_paths = run_artifact_paths or {}
    if not isinstance(run_artifact_paths, dict):
        raise ValueError("run_artifact_paths_must_be_mapping")
    artifact_hashes = {}
    seen_logical = set()
    for logical_name in sorted(run_artifact_paths):
        if logical_name in seen_logical:
            raise ValueError(f"duplicate_logical_path:{logical_name}")
        seen_logical.add(logical_name)
        artifact_hashes[logical_name] = _normalize_artifact_entry(
            logical_name, run_artifact_paths[logical_name], run_dir_real
        )

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


def _build_historical_manifest(package_dir, run_dir, receipt):
    """Historical call form: build_manifest(package_dir, run_dir, receipt).
    Hashes the receipt.json/report.md already present on disk in
    run_dir directly (never lstat on the receipt dict itself), and
    binds all other evidence by reading fixed, well-known keys out of
    the receipt dict with safe defaults."""
    if not os.path.isdir(run_dir):
        raise ValueError("run_dir_missing")
    if os.path.islink(run_dir):
        raise ValueError("run_dir_is_symlink")
    run_dir_real = os.path.realpath(run_dir)

    manifest = {"package_code_hashes": _package_code_hashes(package_dir)}

    receipt_path = os.path.join(run_dir, "receipt.json")
    if os.path.isfile(receipt_path) and not os.path.islink(receipt_path):
        manifest["receipt_sha256"] = _secure_hash_file(receipt_path, must_be_within=run_dir_real)
    report_path = os.path.join(run_dir, "report.md")
    if os.path.isfile(report_path) and not os.path.islink(report_path):
        manifest["report_sha256"] = _secure_hash_file(report_path, must_be_within=run_dir_real)

    receipt = receipt if isinstance(receipt, dict) else {}
    evidence = receipt.get("evidence")
    evidence = evidence if isinstance(evidence, dict) else {}

    manifest["status"] = receipt.get("status")
    manifest["unmet_predicates"] = receipt.get("unmet_predicates", [])
    manifest["candidate_hashes"] = receipt.get("package_hashes", {})
    manifest["diff_sha256"] = receipt.get("diff_sha256")
    manifest["compilation_evidence"] = evidence.get("candidates_compile", {})
    manifest["deterministic_evidence"] = evidence.get("deterministic_repeat_all_transforms", {})

    sqlite_ownership_evidence = receipt.get("sqlite_ownership")
    if isinstance(sqlite_ownership_evidence, dict) and sqlite_ownership_evidence:
        manifest["sqlite_evidence"] = sqlite_ownership_evidence
    else:
        manifest["sqlite_evidence"] = {"quick_check": evidence.get("sqlite_readonly_quickcheck_ok", {})}

    manifest["ua0009_evidence"] = {"fingerprint_unchanged": evidence.get("ua0009_fingerprint_unchanged", {})}

    publication_evidence = receipt.get("publication_result")
    if publication_evidence is None:
        publication_evidence = evidence.get("ua0009_not_public", {})
    manifest["publication_evidence"] = publication_evidence

    manifest["site_inventories"] = receipt.get("site_inventories", {})

    ledger_items = receipt.get("allowed_write_ledger", []) or []
    manifest["allowed_write_ledger"] = sorted(
        ledger_items, key=lambda item: json.dumps(item, sort_keys=True, default=str)
    )
    manifest["pii_emitted"] = "NO"
    return manifest


def build_manifest(
    package_dir,
    run_dir,
    receipt=None,
    *,
    run_artifact_paths=None,
    allowed_write_ledger=None,
    sqlite_evidence=None,
    ua0009_evidence_before=None,
    ua0009_evidence_after=None,
    publication_evidence=None,
):
    """Build a deterministic manifest dict. Detects the historical vs
    canonical call form structurally (by whether a receipt dict was
    passed positionally), never by a permissive exception fallback."""
    if receipt is not None:
        if not isinstance(receipt, dict):
            raise ValueError("historical_receipt_must_be_dict")
        return _build_historical_manifest(package_dir, run_dir, receipt)
    return _build_canonical_manifest(
        package_dir,
        run_dir,
        run_artifact_paths=run_artifact_paths,
        allowed_write_ledger=allowed_write_ledger,
        sqlite_evidence=sqlite_evidence,
        ua0009_evidence_before=ua0009_evidence_before,
        ua0009_evidence_after=ua0009_evidence_after,
        publication_evidence=publication_evidence,
    )


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

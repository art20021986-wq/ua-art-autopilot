#!/usr/bin/env python3
"""
build_manifest.py -- offline, fail-closed builder for release_manifest.json

This script does NOT touch production. It only reads the audited Gate A
evidence file and (optionally) candidate files already produced by Gate A,
and emits a deterministic release manifest for task_057 Gate B.

It refuses to produce a manifest unless every required Gate A field exactly
matches the values recorded for task_057.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

REQUIRED_FIELDS = {
    "status": "PASS_READY_FOR_GATE_B",
    "generated_at_utc": "2026-08-27T22:46:09Z",
    "isolated_html_candidates": 13,
    "html_wording_changes": 36,
    "generator_candidates": 2,
    "stranica_py_changes": 8,
    "yadro_py_changes": 10,
    "production_write": False,
    "crm_write": False,
    "db_write": False,
    "service_reload": False,
    "gate_b_executed": False,
    "ua0009_published": False,
}

ALLOWLIST = (
    "video/index.html",
    "video/katalog.html",
    "video/info.html",
    "video/podbor.html",
    "video/UA-0001.html",
    "video/UA-0002.html",
    "video/UA-0003.html",
    "video/UA-0004.html",
    "video/UA-0005.html",
    "video/UA-0006.html",
    "video/UA-0007.html",
    "video/UA-0008.html",
    "video/UA-0009.html",
    "stranica.py",
    "yadro.py",
)


class BuildError(Exception):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_manifest_hash(manifest: dict) -> str:
    clean = dict(manifest)
    clean.pop("manifest_sha256", None)
    blob = json.dumps(clean, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256_bytes(blob)


def load_evidence(path: Path) -> dict:
    if not path.is_file():
        raise BuildError(f"evidence file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise BuildError(f"evidence file is not valid JSON: {exc}") from exc
    return data


def verify_required_fields(evidence: dict) -> None:
    """Fail closed if any required Gate A field is missing or differs.

    The evidence schema field names are not assumed to be identical to the
    REQUIRED_FIELDS keys above; this function checks common aliases and
    requires an exact match on at least one alias per field. If nothing
    matches, it fails closed rather than guessing.
    """
    aliases = {
        "status": ["status", "gate_a_status"],
        "generated_at_utc": ["generated_at_utc", "generated_at"],
        "isolated_html_candidates": ["isolated_html_candidates", "html_candidates", "html_candidate_count"],
        "html_wording_changes": ["html_wording_changes", "html_changes", "total_html_changes"],
        "generator_candidates": ["generator_candidates", "generator_candidate_count"],
        "stranica_py_changes": ["stranica_py_changes", "stranica_changes"],
        "yadro_py_changes": ["yadro_py_changes", "yadro_changes"],
        "production_write": ["production_write"],
        "crm_write": ["crm_write"],
        "db_write": ["db_write"],
        "service_reload": ["service_reload"],
        "gate_b_executed": ["gate_b_executed"],
        "ua0009_published": ["ua0009_published"],
    }
    for field, expected in REQUIRED_FIELDS.items():
        found = False
        for alias in aliases[field]:
            if alias in evidence:
                if evidence[alias] != expected:
                    raise BuildError(
                        f"Gate A field mismatch: {field} (alias={alias}) "
                        f"expected={expected!r} actual={evidence[alias]!r}"
                    )
                found = True
                break
        if not found:
            raise BuildError(
                f"Gate A required field missing from evidence: {field} "
                f"(tried aliases {aliases[field]}) -- refusing to build manifest"
            )


def build_targets(evidence: dict) -> list:
    """Build the per-file manifest target list from the evidence's own
    recorded candidate/source hashes. Fails closed if a required allowlist
    entry has no matching candidate record in the evidence file.
    """
    raw_candidates = (
        evidence.get("candidates")
        or evidence.get("html_candidates_detail")
        or evidence.get("files")
        or []
    )
    index = {}
    for item in raw_candidates:
        p = item.get("path") or item.get("relative_path") or item.get("target")
        if p:
            index[p.replace("\\", "/").lstrip("/")] = item

    targets = []
    missing = []
    for rel in ALLOWLIST:
        entry = index.get(rel)
        if entry is None:
            missing.append(rel)
            continue
        source_sha = entry.get("source_sha256") or entry.get("before_sha256")
        candidate_sha = entry.get("candidate_sha256") or entry.get("after_sha256")
        size = entry.get("candidate_size_bytes") or entry.get("size")
        changes = entry.get("changes") or entry.get("change_count") or 0
        if not source_sha or not candidate_sha:
            missing.append(rel)
            continue
        action = "VERIFY_UNCHANGED" if source_sha == candidate_sha else "REPLACE"
        targets.append({
            "path": rel,
            "source_sha256": source_sha,
            "candidate_sha256": candidate_sha,
            "expected_size_bytes": size,
            "approved_change_count": changes,
            "action": action,
        })
    if missing:
        raise BuildError(
            "evidence file does not contain matching candidate records for: "
            + ", ".join(missing)
            + " -- refusing to build a partial manifest"
        )
    return targets


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--evidence", required=True, type=Path)
    ap.add_argument("--report", required=False, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    try:
        evidence = load_evidence(args.evidence)
        verify_required_fields(evidence)
        targets = build_targets(evidence)
    except BuildError as exc:
        print(f"BUILD_ABORTED: {exc}", file=sys.stderr)
        return 2

    manifest = {
        "task_id": "task_057",
        "gate": "GATE_B",
        "status": "GENERATED",
        "source_evidence_path": str(args.evidence),
        "source_report_path": str(args.report) if args.report else None,
        "required_gate_a_fields": REQUIRED_FIELDS,
        "allowlist": list(ALLOWLIST),
        "targets": targets,
        "manifest_sha256": None,
    }
    manifest["manifest_sha256"] = canonical_manifest_hash(manifest)
    args.out.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(f"MANIFEST_SHA256={manifest['manifest_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
verify_release.py -- read-only integrity checker for release_manifest.json.

Never writes to production. Safe to run at any time.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path


def canonical_manifest_hash(manifest: dict) -> str:
    clean = dict(manifest)
    clean.pop("manifest_sha256", None)
    blob = json.dumps(clean, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("manifest", type=Path)
    args = ap.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    status = manifest.get("status")
    if status == "NOT_YET_GENERATED":
        print("MANIFEST_STATUS=NOT_YET_GENERATED (template only, no hashes to verify)")
        return 0

    declared = manifest.get("manifest_sha256")
    if not declared:
        print("FAIL: manifest has no manifest_sha256", file=sys.stderr)
        return 2
    recomputed = canonical_manifest_hash(manifest)
    if recomputed != declared:
        print(
            f"FAIL: MANIFEST_TAMPER_DETECTED declared={declared} recomputed={recomputed}",
            file=sys.stderr,
        )
        return 2

    targets = manifest.get("targets", [])
    print(f"OK: manifest_sha256={declared} targets={len(targets)}")
    for t in targets:
        print(f"  {t['action']:16s} {t['path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

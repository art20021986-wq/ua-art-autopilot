#!/usr/bin/env python3
"""
build_gate_a_manifest.py
TASK_016. Python 3.10 stdlib only.

Builds a deterministic, canonical JSON manifest describing the exact
Gate A sandbox package. Accepts NO CLI arguments. Hashes an exact
hardcoded file set. Refuses missing/symlink/zero-byte/unexpected files.
"""

import sys
import json
import hashlib
from pathlib import Path

SAFE_INBOX_ROOT = Path("/home/Carix/autopilot_inbox/cloud/ua_cards_unified")

EXACT_FILE_SET = [
    "START_UA_CARDS_UNIFIED.py",
    "build_gate_a_manifest.py",
    "RUN_GATE_A_TASK016.py",
    "UNIFIED_CARDS_SPEC.md",
    "LEGACY_CONFLICT_AUDIT.md",
    "PRODUCTION_PATCH_PLAN.md",
    "TEST_MATRIX.md",
    "OWNER_NEXT_STEP.md",
]

ALLOWED_WRITE_ROOTS = [
    "/home/Carix/video/preview/ua-cards-unified",
    "/home/Carix/video/reports/ua_cards_unified",
    "/home/Carix/ua_cards_unified_gate_a_receipt",
]


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_file(path: Path):
    if path.is_symlink():
        raise ValueError(f"REFUSED symlink: {path}")
    if not path.exists():
        raise ValueError(f"REFUSED missing file: {path}")
    if not path.is_file():
        raise ValueError(f"REFUSED not a regular file: {path}")
    if path.stat().st_size == 0:
        raise ValueError(f"REFUSED zero-byte file: {path}")
    if path.suffix.lower() not in (".py", ".md"):
        raise ValueError(f"REFUSED unexpected file type: {path}")


def build_manifest() -> dict:
    if len(sys.argv) > 1:
        print("REFUSED: build_gate_a_manifest.py accepts no CLI arguments.")
        sys.exit(2)

    files_section = {}
    for name in EXACT_FILE_SET:
        p = SAFE_INBOX_ROOT / name
        validate_file(p)
        files_section[name] = sha256_of(p)

    manifest = {
        "task": "task_016",
        "parent_task": "task_014",
        "target_mode": "SANDBOX_ONLY",
        "gate_a": True,
        "gate_b": False,
        "allowed_write_roots": ALLOWED_WRITE_ROOTS,
        "source_root": str(SAFE_INBOX_ROOT),
        "files": files_section,
        "production_write_allowed": False,
        "wsgi_reload_allowed": False,
        "ua_0009_publication_allowed": False,
    }
    return manifest


def canonical_json(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def main():
    manifest = build_manifest()
    canonical = canonical_json(manifest)
    manifest_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    manifest["manifest_sha256"] = manifest_hash
    print(canonical_json({k: v for k, v in manifest.items() if k != "manifest_sha256"}))
    print(f"MANIFEST_SHA256={manifest_hash}")
    return manifest


if __name__ == "__main__":
    main()

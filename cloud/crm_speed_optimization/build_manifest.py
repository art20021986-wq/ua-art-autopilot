#!/usr/bin/env python3
"""Builds a deterministic manifest of this package's own file hashes so the
receipt can bind evidence to exact code that produced it. Does not touch
production. Read-only over cloud/crm_speed_optimization/."""

from __future__ import annotations

import hashlib
import json
import os
import sys

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))

MANAGED_FILES = [
    "RUN_GATE_A_CRM_SPEED.py",
    "crm_speed_gate_a.py",
    "build_manifest.py",
    "verify_gate_a.py",
    "test_crm_speed_gate_a.py",
    "TEST_MATRIX.md",
    "OPERATOR_INSTRUCTIONS.md",
    "ROLLBACK.md",
    "cloud_report_020.md",
]


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest() -> dict:
    manifest = {}
    for name in MANAGED_FILES:
        path = os.path.join(PACKAGE_DIR, name)
        if os.path.exists(path):
            manifest[name] = sha256_file(path)
        else:
            manifest[name] = None
    return manifest


def main() -> int:
    manifest = build_manifest()
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

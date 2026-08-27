"""
build_manifest.py

Deterministic manifest generation for a Gate A run directory, binding the
receipt to the exact package code hashes and any produced artifacts.
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Dict, List

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def hash_package_code(package_dir: str = PACKAGE_DIR) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for name in sorted(os.listdir(package_dir)):
        if name.endswith(".py"):
            full = os.path.join(package_dir, name)
            if os.path.isfile(full) and not os.path.islink(full):
                out[name] = _sha256_file(full)
    return out


def build_run_manifest(run_dir: str) -> dict:
    entries: List[dict] = []
    for root, _dirs, files in os.walk(run_dir):
        for fname in sorted(files):
            full = os.path.join(root, fname)
            if os.path.islink(full):
                continue
            rel = os.path.relpath(full, run_dir)
            entries.append({"path": rel, "sha256": _sha256_file(full),
                             "size": os.path.getsize(full)})
    entries.sort(key=lambda e: e["path"])
    combined = "\n".join(f"{e['path']}:{e['sha256']}" for e in entries)
    manifest_sha256 = hashlib.sha256(combined.encode("utf-8")).hexdigest()
    return {
        "run_dir": run_dir,
        "entries": entries,
        "manifest_sha256": manifest_sha256,
        "package_code_hashes": hash_package_code(),
    }


def write_manifest(run_dir: str, out_path: str) -> dict:
    manifest = build_run_manifest(run_dir)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
    return manifest


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("usage: build_manifest.py <run_dir> <out_manifest_json>")
        raise SystemExit(2)
    write_manifest(sys.argv[1], sys.argv[2])

"""Builds a deterministic manifest of package code hashes and run output
hashes for one Gate A run. Read-only against the package directory; writes
only when explicitly invoked with a run directory to inspect."""
import os
import sys
import json
import hashlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(package_dir, run_dir=None):
    manifest = {"package_files": {}, "run_outputs": {}}
    for name in sorted(os.listdir(package_dir)):
        full = os.path.join(package_dir, name)
        if name.endswith(".py") and os.path.isfile(full):
            manifest["package_files"][name] = _sha256_file(full)
    if run_dir and os.path.isdir(run_dir):
        for root, _dirs, files in os.walk(run_dir):
            for name in sorted(files):
                path = os.path.join(root, name)
                manifest["run_outputs"][os.path.relpath(path, run_dir)] = _sha256_file(path)
    return manifest


if __name__ == "__main__":
    package_dir = os.path.dirname(os.path.abspath(__file__))
    run_dir = sys.argv[1] if len(sys.argv) > 1 else None
    print(json.dumps(build_manifest(package_dir, run_dir), indent=2))

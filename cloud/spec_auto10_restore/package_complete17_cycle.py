#!/usr/bin/env python3
"""Deterministic private server rehearsal ZIP; no deployment behavior."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import zipfile

MANIFEST_SHA = "12afce821b784771a2a8a0415cc289f5e713d53aabedf0ed3e2747a8c4d4e136"
FROZEN_HELPERS = {
    "complete15_cycle.py": "d6449d1c53a65d02371d00bab78cb3cf5fe7231d644964f312ce915dd1bf851d",
    "full_publisher_rehearsal.py": "8f8597a64c85f8b34ad36bc9855606b0bf8d45de5b3bcce9e5ea2b0d6bcd2f4f",
}
RUNNERS = tuple(FROZEN_HELPERS) + ("complete17_cycle.py", "complete17_server_gate.py")


def read(path):
    if path.is_symlink() or path.resolve() != path.absolute() or not path.is_file():
        raise RuntimeError("PACKAGE_NONCANONICAL_INPUT")
    before = path.stat()
    data = path.read_bytes()
    after = path.stat()
    identity = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)
    if identity(before) != identity(after):
        raise RuntimeError("PACKAGE_INPUT_CHANGED_DURING_READ")
    return data


def build(candidate, output):
    base = Path(__file__).absolute().parent
    candidate = candidate.absolute()
    raw = read(candidate / "manifest.json")
    if hashlib.sha256(raw).hexdigest() != MANIFEST_SHA:
        raise RuntimeError("FINAL17_MANIFEST_MISMATCH")
    manifest = json.loads(raw)
    disk = {str(path.relative_to(candidate)) for path in candidate.rglob("*") if not path.is_dir()}
    if len(manifest["files"]) != 17 or disk != set(manifest["files"]) | {"manifest.json"}:
        raise RuntimeError("FINAL17_EXACT_FILE_SET_REQUIRED")
    files = {"candidate/manifest.json": raw}
    for name, entry in manifest["files"].items():
        data = read(candidate / name)
        if hashlib.sha256(data).hexdigest() != entry["after_sha256"]:
            raise RuntimeError("CANDIDATE_SHA_MISMATCH:" + name)
        compile(data, name, "exec")
        files["candidate/" + name] = data
    for name in RUNNERS:
        data = read(base / name)
        if name in FROZEN_HELPERS and hashlib.sha256(data).hexdigest() != FROZEN_HELPERS[name]:
            raise RuntimeError("FROZEN_HELPER_CHANGED:" + name)
        compile(data, name, "exec")
        if name not in FROZEN_HELPERS:
            bound = [node.value.value for node in ast.parse(data).body
                     if isinstance(node, ast.Assign) and len(node.targets) == 1
                     and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "MANIFEST_SHA"
                     and isinstance(node.value, ast.Constant)]
            if bound != [MANIFEST_SHA]:
                raise RuntimeError("RUNNER_CANDIDATE_PIN_MISMATCH:" + name)
        files[name] = data
    package = {"scope": "FINAL17_SYNTHETIC_SERVER_REHEARSAL_ONLY", "production_changed": False,
               "overall_gate_b": "NOT_EVALUATED", "candidate_manifest_sha256": MANIFEST_SHA,
               "files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
    files["bundle-manifest.json"] = (json.dumps(package, sort_keys=True, indent=2) + "\n").encode()
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            entry = zipfile.ZipInfo(name, date_time=(2026, 9, 9, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o600 << 16
            archive.writestr(entry, data)
    return {"file": str(output.absolute()), "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "bytes": output.stat().st_size, "members": len(files), **package}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.candidate, args.output), indent=2))


if __name__ == "__main__":
    main()

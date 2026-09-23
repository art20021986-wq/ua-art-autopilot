#!/usr/bin/env python3
"""Build deterministic private PA rehearsal ZIP; never include this ZIP in Git."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

MANIFEST_SHA = "c4f75a818156e29426c9d601552ab0de56663e965233f2a56c01f5aaa111de07"
HELPER_SHA = "8f8597a64c85f8b34ad36bc9855606b0bf8d45de5b3bcce9e5ea2b0d6bcd2f4f"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    base = Path(__file__).absolute().parent
    candidate = args.candidate.absolute()
    manifest_path = candidate / "manifest.json"
    if manifest_path.is_symlink():
        raise RuntimeError("MANIFEST_SYMLINK")
    data = manifest_path.read_bytes()
    if hashlib.sha256(data).hexdigest() != MANIFEST_SHA:
        raise RuntimeError("FINAL15_MANIFEST_MISMATCH")
    manifest = json.loads(data)
    if set(path.name for path in candidate.iterdir()) != set(manifest["files"]) | {"manifest.json"}:
        raise RuntimeError("FINAL15_EXACT_FILE_SET_REQUIRED")
    files = {"candidate/manifest.json": data}
    for name, entry in manifest["files"].items():
        path = candidate / name
        if path.is_symlink() or path.resolve() != path.absolute():
            raise RuntimeError("CANDIDATE_PATH_INVALID")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != entry["after_sha256"]:
            raise RuntimeError("CANDIDATE_SHA_MISMATCH:" + name)
        files["candidate/" + name] = data
    for name in ("complete15_cycle.py", "complete15_server_gate.py", "full_publisher_rehearsal.py"):
        data = (base / name).read_bytes()
        if name == "full_publisher_rehearsal.py" and hashlib.sha256(data).hexdigest() != HELPER_SHA:
            raise RuntimeError("FROZEN_HELPER_CHANGED")
        compile(data, name, "exec")
        files[name] = data
    package = {"scope": "FINAL15_SYNTHETIC_SERVER_REHEARSAL_ONLY", "production_changed": False,
               "candidate_manifest_sha256": MANIFEST_SHA,
               "files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
    files["bundle-manifest.json"] = (json.dumps(package, sort_keys=True, indent=2) + "\n").encode()
    with zipfile.ZipFile(args.output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            entry = zipfile.ZipInfo(name, date_time=(2026, 9, 9, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o600 << 16
            archive.writestr(entry, data)
    print(json.dumps({"file": str(args.output.absolute()), "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
                      "bytes": args.output.stat().st_size, "members": len(files), "files": package["files"]}, indent=2))


if __name__ == "__main__":
    main()

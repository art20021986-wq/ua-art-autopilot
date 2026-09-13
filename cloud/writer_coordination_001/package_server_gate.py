#!/usr/bin/env python3
"""Build the deterministic, pinned six-file isolated PA test ZIP."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

FILES = {
    "coordination_server_gate.py": "7f27b63b5b5e0f2a3aa01fe3c78524288e1069cb89c675b9f164cf62ce92bcab",
    "platform_control.py": "82489cd9dd20331ea90b668138c12f5c594a1e40df186f7170fd7b783ce612d9",
    "server_fence.py": "199a8744b3dd335899adcac92c52e30c462d7b471898d6b94a7ba944b9f05b85",
    "test_server_fence.py": "73a28acd8098ac31392db02d164eba8a5543fe9b0040cd662ad4ae7882518115",
    "tests/test_platform_control.py": "22340c357c2490513e90e7cc1c0f71c858880480caa924abfe36ce8638a38119",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    source = Path(__file__).resolve().parent
    output = Path(args.output).absolute()
    if output.is_symlink() or output.exists() or not output.parent.is_dir():
        raise RuntimeError("PACKAGE_OUTPUT_MUST_BE_NEW")
    contents = {}
    for name, expected in FILES.items():
        path = source / name
        if path.resolve() != path or path.is_symlink() or not path.is_file():
            raise RuntimeError("PACKAGE_SOURCE_PATH")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise RuntimeError("PACKAGE_SOURCE_SHA:" + name)
        compile(data, name, "exec")
        contents[name] = data
    manifest = {"schema": "UA-ART-WRITER-COORDINATION-TEST-BUNDLE-1", "files": FILES,
                "test_counts": {"test_server_fence.py": 19, "test_platform_control.py": 36}}
    contents["bundle-manifest.json"] = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(contents.items()):
            item = zipfile.ZipInfo(name, date_time=(2026, 9, 9, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            item.external_attr = 0o100600 << 16
            archive.writestr(item, data)
    print(json.dumps({"path": str(output), "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                      "bytes": output.stat().st_size, "members": sorted(contents)}, sort_keys=True))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Build the deterministic, pinned five-file isolated PA test ZIP."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

FILES = {
    "code_handoff_v2.py": "08e013756a1ffe89043904efeb878d1d7318d67cdb5c628573f3b26cb454fc55",
    "handoff_v2_server_gate.py": "3e4407e6c6980ae87daace9e9c7cca96e700a8579cd0f11db91d0797c7f05995",
    "server_fence.py": "199a8744b3dd335899adcac92c52e30c462d7b471898d6b94a7ba944b9f05b85",
    "test_code_handoff_v2.py": "c16251f23fd956b95b0dc81f98e69e1a70eac96f6eaa5c347f1598f3e304c367"
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
    manifest = {"schema": "UA-ART-CODE-HANDOFF-V2-TEST-BUNDLE-1", "files": FILES,
                "test_counts": {"test_code_handoff_v2.py": 23}}
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

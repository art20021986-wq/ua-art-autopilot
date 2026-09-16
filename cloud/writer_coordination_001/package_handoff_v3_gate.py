#!/usr/bin/env python3
"""Build the deterministic, pinned five-file isolated PA test ZIP."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

FILES = {
    "code_handoff_v3.py": "200ca169be01cb12bf6cdaa8425acdb2279e1bfc6fd9306d51300148043f9ed1",
    "handoff_v3_server_gate.py": "2a2d2b5462edb280e134d94598bae12255608ed761033ef725cbde1c658cec85",
    "server_fence.py": "199a8744b3dd335899adcac92c52e30c462d7b471898d6b94a7ba944b9f05b85",
    "test_code_handoff_v3.py": "e24b11ae630b976c9cd794893172035ead72510dd8a8b530fc5b317963b208f7"
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
    manifest = {"schema": "UA-ART-CODE-HANDOFF-V3-TEST-BUNDLE-2", "files": FILES,
                "test_counts": {"test_code_handoff_v3.py": 30}}
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

#!/usr/bin/env python3
"""Build the deterministic, pinned four-file isolated PA test ZIP."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

FILES = {
    "analytics_server_gate.py": "9999f43434dbc65c0fe69c773c26668d6a3c323b698abf6df5252278c07d088c",
    "patch_analytics_writer.py": "58e62afbc8458f273b605b06b222552ff07d83d9fd375c5891685045a070e2e5",
    "tests/test_analytics_writer.py": "64892d7695c8a675510eb5c80db13a2e0b3ccbdadc9d818d38b0922847f88981"
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
    manifest = {"schema": "UA-ART-ANALYTICS-WRITER-TEST-BUNDLE-1", "files": FILES,
                "test_counts": {"test_analytics_writer.py": 13}}
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

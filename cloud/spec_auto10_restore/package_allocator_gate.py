#!/usr/bin/env python3
"""Build only the reviewed allocator test bundle, never production source bytes."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

HERE = Path(__file__).resolve().parent
FILES = ("allocator_server_gate.py", "allocator_integration.py", "runtime/car_number_allocator.py",
         "tests/test_car_number_allocator.py")


def build(output):
    evidence = json.loads((HERE / "evidence/card-number-recovery.json").read_text())
    members = {"cloud/spec_auto10_restore/" + name: (HERE / name).read_bytes() for name in FILES}
    digest = lambda data: hashlib.sha256(data).hexdigest()
    for name, expected in (("allocator_integration.py", evidence["patcher_sha256"]),
                           ("runtime/car_number_allocator.py", evidence["candidate_sha256"]["car_number_allocator.py"]),
                           ("tests/test_car_number_allocator.py", evidence["test_file_sha256"])):
        if digest(members["cloud/spec_auto10_restore/" + name]) != expected:
            raise RuntimeError("FROZEN_CODE_CHANGED:" + name)
    manifest = {"contract": "UA-ART-SPEC-AUTO-10-RESTORE-001:ALLOCATOR-SERVER-GATE:1",
                "required_stage": "/home/Carix/spec_allocator_gate_20260909",
                "entrypoint": "cloud/spec_auto10_restore/allocator_server_gate.py",
                "source_sha256": evidence["source_sha256"],
                "files": {name: {"sha256": digest(data), "bytes": len(data)} for name, data in members.items()},
                "contains_production_source": False, "executes_application_imports": False,
                "expected_tests": 26, "expected_guarded_children": 3}
    members["allocator-gate-manifest.json"] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    with Path(output).open("xb") as handle:
        with zipfile.ZipFile(handle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in sorted(members.items()):
                item = zipfile.ZipInfo(name, date_time=(2026, 9, 9, 0, 0, 0))
                item.compress_type = zipfile.ZIP_DEFLATED
                item.external_attr = 0o100600 << 16
                archive.writestr(item, data)
    return {"path": str(output), "sha256": digest(Path(output).read_bytes()), "members": len(members),
            "server_executed": False, "manifest": manifest}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.output), indent=2))

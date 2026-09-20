#!/usr/bin/env python3
"""Offline point4 candidate composition; sanitised hashes only in evidence.

Never imports captured production modules, executes an installer, accesses a
database/network, changes inputs, or issues approval. Historical inputs are
deliberate and are not evidence about current production state.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()


def read(path, expected=None):
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("REGULAR_INPUT_REQUIRED:" + str(path))
    data = path.read_bytes()
    if expected is not None and digest(data) != expected:
        raise RuntimeError("INPUT_HASH_MISMATCH:" + str(path))
    return data


def write_new(path, data):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    if read(path) != data:
        raise RuntimeError("WRITE_READBACK_FAILED:" + str(path))


def record(path, value):
    write_new(path, json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True).encode() + b"\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--historical-inputs", type=Path, required=True)
    parser.add_argument("--routing-inputs", type=Path, required=True)
    parser.add_argument("--dependency-inputs", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo, evidence, output = (value.resolve() for value in (args.repository, args.evidence, args.output))
    if output.exists():
        raise RuntimeError("NEW_PRIVATE_OUTPUT_DIRECTORY_REQUIRED")
    sys.dont_write_bytecode = True
    cloud = repo / "cloud"
    roots = [cloud / name for name in ("task088_price_sync", "task088_stage3_renderer", "task088_autopilot_owner_policy", "task088_v5_writer_fence")]
    public_pins = {str(p.relative_to(repo)): digest(read(p)) for root in roots for p in root.glob("*.py")}
    # Persist the reason and exact public code pins BEFORE generation.
    record(evidence / "COMBINED_BUILD_INTENT.json", {
        "contract": "PR114-POINT4-OFFLINE-FULL-CANDIDATE-INTENT-1",
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "reason": "Point4 lacks an actual full candidate composed from exact retained private inputs using the current canonical build_candidates. This scoped generation closes that evidence gap; historical suites are not repeated.",
        "application_code_modified_by_this_script": False,
        "private_output": str(output),
        "historical_inputs_only": True,
        "public_code_sha256": public_pins,
        "script_sha256": digest(read(Path(__file__))),
    })

    acceptance = cloud / "task088_v5_acceptance"
    compressed = acceptance / "resume_20260915/preflight_retry/completed_report.json.gz.b64"
    historical_raw = gzip.decompress(base64.b64decode(read(compressed, "26c3641e83bf1ce634c0d9cb6cd13c4a377a976a304d2e2bbff853dd69c5b5d8")))
    if digest(historical_raw) != "f5d1a56840288a012d334fd8f3362194d90cc86dc81877cf69ed0328e4c30fc7":
        raise RuntimeError("HISTORICAL_REPORT_HASH_MISMATCH")
    historical = json.loads(historical_raw)
    point3_path = cloud / "task088_v5_writer_fence/handoff006_evidence/emergency007_point3/CANDIDATE_MANIFEST.json"
    point3_raw = read(point3_path, "3a4843722a7c8c4186d3c6eef3e17f09e8cf87affe5f4d303183b9d15560acc4")
    point3 = json.loads(point3_raw)
    routing_path = acceptance / "route_observations.json"
    routing_raw = read(routing_path, "91688089f048d7181fb719a533f90f028c736aa9146dd55ea14350b69bee9e35")
    routing = json.loads(routing_raw)
    for name, pin in routing["source_sha256"].items():
        read(args.routing_inputs / name, pin)

    source_bytes = {name: read(args.historical_inputs / name, entry["before_sha256"])
                    for name, entry in historical["sources"].items()}
    dependency_bytes = {name: read(args.historical_inputs / name, pin)
                        for name, pin in historical["dependencies"].items()}
    for name, pin in point3["dependency_before_sha256"].items():
        data = read(args.dependency_inputs / name, pin)
        (source_bytes if name == "ua_spec_permanent.py" else dependency_bytes)[name] = data
    html_bytes = {name: read(args.historical_inputs / name, entry["before_sha256"])
                  for name, entry in historical["html"].items()}
    rows_raw = read(args.historical_inputs / "published_price_rows.json", "e57ce6c38ee14cffe0be0be9d4895427713b9678a8d82926e8a43b4e9976409a")
    rows = json.loads(rows_raw)
    identity = [{key: row.get(key) for key in ("id", "auto_number", "published", "status", "price_uah", "price_georgia")} for row in rows]
    if digest(canonical(identity)) != historical["database"]["published_sha256"]:
        raise RuntimeError("PUBLISHED_IDENTITY_HASH_MISMATCH")
    if sorted(row["auto_number"] for row in rows) != historical["database"]["published_codes"]:
        raise RuntimeError("PUBLISHED_SET_MISMATCH")

    # Fail closed on accidental external side effects. Only public builder
    # modules are imported; captured module bytes are patch/compile inputs.
    def audit(event, arguments):
        if event.startswith("socket.") or event in {"subprocess.Popen", "os.system", "sqlite3.connect"}:
            raise RuntimeError("OFFLINE_BUILD_FORBIDDEN_EVENT:" + event)
    sys.addaudithook(audit)
    sys.path[:0] = [str(path) for path in roots]
    from build_preflight_bundle import package_mapping
    from install_package import MODULES, SOURCES, DEPENDENCIES, build_candidates, candidate_manifest
    if set(source_bytes) != SOURCES or set(dependency_bytes) != DEPENDENCIES:
        raise RuntimeError("SOURCE_DEPENDENCY_CLOSURE_MISMATCH")
    mapping = package_mapping(repo)
    module_bytes = {name: read(mapping[name]) for name in MODULES}
    candidate = build_candidates(source_bytes, html_bytes, rows, module_bytes,
        dependency_files=dependency_bytes, homepage_policy=historical["homepage_policy"], routing=routing)
    compiled = []
    for name in sorted(SOURCES | MODULES):
        compile(candidate[name], name, "exec")
        compiled.append(name)
    for relative, pin in public_pins.items():
        read(repo / relative, pin)
    private_roots = [args.historical_inputs.resolve(), args.routing_inputs.resolve(), args.dependency_inputs.resolve(), output]
    for module in list(sys.modules.values()):
        path = getattr(module, "__file__", None)
        if path and any(Path(path).resolve().is_relative_to(root) for root in private_roots):
            raise RuntimeError("PRIVATE_MODULE_IMPORTED")

    comparisons = {}
    for name, old in historical["candidate_files"].items():
        new_hash = digest(candidate[name])
        comparisons[name] = {"historical_after_sha256": old["after_sha256"],
                             "candidate_after_sha256": new_hash, "matches": new_hash == old["after_sha256"]}
    html_mismatches = [name for name in html_bytes if not comparisons[name]["matches"]]
    if html_mismatches:
        raise RuntimeError("HISTORICAL_HTML_OUTPUT_MISMATCH:" + ",".join(html_mismatches))
    before = {name: entry["before_sha256"] for name, entry in historical["candidate_files"].items()}
    before["ua_spec_permanent.py"] = point3["dependency_before_sha256"]["ua_spec_permanent.py"]
    # New runtime module presence cannot be inferred from history. Nulls below
    # are OFFLINE-only manifest placeholders, explicitly disallowed for install.
    for name in candidate.keys() - before.keys():
        before[name] = None
    manifest = candidate_manifest(candidate, before)
    output.mkdir(mode=0o700)
    for name, data in sorted(candidate.items()):
        write_new(output / name, data)
    record(evidence / "COMBINED_CANDIDATE_MANIFEST.json", {
        "contract": "PR114-POINT4-HISTORICAL-OFFLINE-CANDIDATE-1",
        "installation_authority": False,
        "current_live_before_images_verified": False,
        "new_runtime_before_images": "UNKNOWN_AT_CURRENT_SERVER_NULL_IS_OFFLINE_PLACEHOLDER_ONLY",
        "candidate_manifest_sha256": digest(canonical(manifest)),
        "candidate_files": manifest,
    })
    record(evidence / "COMBINED_HISTORICAL_COMPARISON.json", comparisons)
    changed = sorted(name for name, entry in comparisons.items() if not entry["matches"])
    added = sorted(candidate.keys() - historical["candidate_files"].keys())
    report = {
        "contract": "PR114-POINT4-COMPOSED-CANDIDATE-IMPACT-1",
        "status": "PASS_OFFLINE_CANDIDATE_COMPOSITION_AND_HTML_IDENTITY",
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "private_candidate_directory": str(output),
        "candidate_files": len(candidate), "source_files": len(SOURCES), "module_files": len(MODULES),
        "html_files": len(html_bytes), "compiled_without_execution": compiled,
        "historical_published_count": len(rows), "historical_published_identity_sha256": digest(canonical(identity)),
        "historical_report_sha256": digest(historical_raw), "point3_manifest_sha256": digest(point3_raw),
        "routing_sha256": digest(routing_raw), "homepage_policy": historical["homepage_policy"],
        "input_pins_matched": {"sources": len(source_bytes), "dependencies": len(dependency_bytes), "html": len(html_bytes), "routing": len(routing["source_sha256"]), "published_rows": 1},
        "source_input_sha256": {name:digest(data) for name,data in sorted(source_bytes.items())},
        "dependency_input_sha256": {name:digest(data) for name,data in sorted(dependency_bytes.items())},
        "public_code_sha256": public_pins,
        "historical_candidate_comparison": {"compared": len(comparisons), "matched": sum(v["matches"] for v in comparisons.values()), "changed": changed, "added": added, "html_matched": len(html_bytes), "html_mismatches": html_mismatches},
        "candidate_manifest_sha256": digest(canonical(manifest)),
        "source_generation": "Actual canonical composition of 7 exact sources succeeded; all 17 Python outputs compile. Behavioural source-generation acceptance requires independent review and already-scoped integration evidence.",
        "no_unrelated_diff": "All 40 HTML output bytes equal historical accepted candidate. Non-HTML changes and new files are explicitly enumerated for independent review.",
        "preview_applicability": "Historical published-set and HTML identity only; final historical Preview evidence must be assessed separately. No current production published-set or freshness assertion.",
        "current_runtime_claim": False, "production_written": False, "private_modules_imported": False,
        "historical_test_suites_rerun": False, "gate_issued": False,
        "script_sha256": digest(read(Path(__file__))),
    }
    record(evidence / "COMBINED_CANDIDATE_IMPACT.json", report)
    print(json.dumps({key:report[key] for key in ("status", "candidate_files", "candidate_manifest_sha256", "historical_candidate_comparison")}))


if __name__ == "__main__":
    main()

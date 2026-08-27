"""
Deterministic manifest builder for UA Cards Unified Gate A (TASK 021).

Accepts no arbitrary paths from the command line. Only bounded values
assembled by the caller (runner/launcher) may be included. No path in
this module is derived from user-supplied CLI arguments.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import common

SELF_MODULE_NAMES = [
    "runner.py", "preflight.py", "manifest_builder.py",
    "launcher.py", "verifier.py", "common.py",
]


def _self_hashes(package_dir: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for name in SELF_MODULE_NAMES:
        p = package_dir / name
        if p.exists():
            hashes[name] = common.sha256_file(p)
    return hashes


def build_manifest(
    task_id: str,
    source_provenance: str,
    discovered_inputs: dict[str, str],
    protected_paths_before: dict[str, str],
    write_roots: list[str],
    planned_outputs: list[str],
    package_dir: Path,
    execution_id: str = "",
    final_output_root: str = "",
) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "task_id": task_id,
        "source_provenance": source_provenance,
        "discovered_inputs": dict(sorted(discovered_inputs.items())),
        "protected_paths_before": dict(sorted(protected_paths_before.items())),
        "write_roots_allowlist": sorted(write_roots),
        "planned_outputs": sorted(planned_outputs),
        "code_hashes": _self_hashes(package_dir),
        "target_mode": "GATE_A_REPORT_PREVIEW_ONLY",
        "gate_a": True,
        "gate_b": False,
    }
    if execution_id:
        manifest["execution_id"] = execution_id
    if final_output_root:
        manifest["final_output_root"] = final_output_root
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    manifest["manifest_sha256"] = common.sha256_bytes(canonical.encode("utf-8"))
    return manifest


def serialize_manifest(manifest: dict[str, Any]) -> str:
    return json.dumps(manifest, sort_keys=True, indent=2)


def manifest_content_hash(manifest: dict[str, Any]) -> str:
    without_self_hash = {k: v for k, v in manifest.items() if k != "manifest_sha256"}
    canonical = json.dumps(without_self_hash, sort_keys=True, separators=(",", ":"))
    return common.sha256_bytes(canonical.encode("utf-8"))


def verify_manifest_integrity(manifest: dict[str, Any]) -> bool:
    expected = manifest.get("manifest_sha256")
    actual = manifest_content_hash(manifest)
    return expected == actual

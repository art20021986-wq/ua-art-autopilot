#!/usr/bin/env python3
"""Read live UA ART inputs and build isolated ferry-wording candidates.

The only writes are below the fixed PythonAnywhere safe-inbox candidate root.
Production HTML/Python, CRM, services, schedules and web-app configuration are
read-only. The CLI has no arguments and cannot be retargeted by environment.
"""

import datetime as dt
import hashlib
import json
import os
import pathlib
import tempfile

import discover
import transform

MODE = "FERRY_GATE_A_READONLY_INPUTS_ISOLATED_CANDIDATES"
SOURCE_ROOT = "/home/Carix"
SAFE_ROOT = "/home/Carix/autopilot_inbox/cloud/task_047_ferry_discovery"
CANDIDATE_ROOT = SAFE_ROOT + "/gate_a_candidates"
MAX_CANDIDATE_BYTES = 20 * 1024 * 1024


class GateABlocked(RuntimeError):
    pass


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _base_receipt():
    return {
        "mode": MODE,
        "status": "BLOCKED",
        "source_root": SOURCE_ROOT,
        "candidate_root": CANDIDATE_ROOT,
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).replace(
            microsecond=0
        ).isoformat().replace("+00:00", "Z"),
        "production_write": False,
        "crm_write": False,
        "db_write": False,
        "service_reload": False,
        "gate_b_executed": False,
        "ua0009_published": False,
        "unexpected_protected_changes": 0,
        "production_sources_unchanged": False,
        "discovery_reasons": [],
        "candidates": [],
        "generator_candidates": [],
        "python_sources": [],
        "crm": {},
        "errors": [],
    }


def _ensure_safe_candidate_root(candidate_root, enforce_fixed):
    absolute = os.path.abspath(candidate_root)
    if enforce_fixed and absolute != CANDIDATE_ROOT:
        raise GateABlocked("candidate_root_not_fixed")
    allowed = SAFE_ROOT if enforce_fixed else os.path.dirname(absolute)
    allowed_absolute = os.path.abspath(allowed)
    if not os.path.isdir(allowed_absolute):
        raise GateABlocked("safe_root_missing")
    if os.path.realpath(allowed_absolute) != allowed_absolute:
        raise GateABlocked("safe_root_not_canonical")
    allowed_real = os.path.realpath(allowed)
    os.makedirs(absolute, exist_ok=True)
    candidate_real = os.path.realpath(absolute)
    if os.path.commonpath([allowed_real, candidate_real]) != allowed_real:
        raise GateABlocked("candidate_root_escape")
    current = pathlib.Path(absolute)
    while True:
        if current.is_symlink():
            raise GateABlocked("candidate_root_symlink")
        if str(current) == allowed or current == current.parent:
            break
        current = current.parent
    return absolute


def _candidate_path(candidate_root, rel_path):
    pure = pathlib.PurePosixPath(rel_path)
    if pure.is_absolute() or ".." in pure.parts or not pure.parts:
        raise GateABlocked("candidate_relative_path_invalid")
    root_real = os.path.realpath(candidate_root)
    current = pathlib.Path(candidate_root)
    for part in pure.parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise GateABlocked("candidate_parent_symlink")
        try:
            current.mkdir()
        except FileExistsError:
            if not current.is_dir() or current.is_symlink():
                raise GateABlocked("candidate_parent_not_directory")
    target = os.path.join(candidate_root, *pure.parts)
    parent = str(current)
    parent_real = os.path.realpath(parent)
    if os.path.commonpath([root_real, parent_real]) != root_real:
        raise GateABlocked("candidate_path_escape")
    current = pathlib.Path(parent)
    root_path = pathlib.Path(candidate_root)
    while True:
        if current.is_symlink():
            raise GateABlocked("candidate_parent_symlink")
        if current == root_path or current == current.parent:
            break
        current = current.parent
    return target


def _atomic_write(path, data):
    if not 0 <= len(data) <= MAX_CANDIDATE_BYTES:
        raise GateABlocked("candidate_size_out_of_bounds")
    directory = os.path.dirname(path)
    handle = tempfile.NamedTemporaryFile(
        mode="wb", dir=directory, prefix=".ferry-gate-a-", suffix=".tmp",
        delete=False,
    )
    temporary = handle.name
    try:
        with handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _safe_occurrence(item):
    return {
        key: item.get(key)
        for key in (
            "language", "form", "context", "before", "after",
            "classification", "action",
        )
    }


def _run_gate_a(source_root, candidate_root, enforce_fixed):
    receipt = _base_receipt()
    receipt["source_root"] = source_root
    receipt["candidate_root"] = candidate_root
    try:
        candidate_root = _ensure_safe_candidate_root(candidate_root, enforce_fixed)
        discovery = discover.run_discovery(source_root)
        receipt["discovery_reasons"] = list(discovery.get("reasons", []))
        crm = discovery.get("crm", {})
        receipt["crm"] = {
            "status": crm.get("status"),
            "table": crm.get("table"),
            "id_column": crm.get("id_column"),
            "container_column": crm.get("container_column"),
            "id_count": len(crm.get("results", {})) if isinstance(crm.get("results"), dict) else 0,
            "sha256": crm.get("sha256"),
        }

        for rel_path, result in sorted(discovery.get("python", {}).items()):
            for occurrence in result.get("occurrences", []):
                receipt["python_sources"].append({
                    key: value for key, value in {
                        "path": rel_path,
                        "source_sha256": result.get("sha256"),
                        "line": occurrence.get("line"),
                        "column": occurrence.get("column"),
                        "end_line": occurrence.get("end_line"),
                        "end_column": occurrence.get("end_column"),
                        "before": occurrence.get("before"),
                        "classification": occurrence.get("classification"),
                        "action": occurrence.get("action"),
                        "literal_sha256": occurrence.get("literal_sha256"),
                        "literal_length": occurrence.get("literal_length"),
                        "assignment": occurrence.get("assignment"),
                        "role": occurrence.get("role"),
                        "dict_key": occurrence.get("dict_key"),
                        "call": occurrence.get("call"),
                        "keyword": occurrence.get("keyword"),
                        "function": occurrence.get("function"),
                        "class": occurrence.get("class"),
                        "structural_changes": occurrence.get("structural_changes"),
                        "structural_ambiguous": occurrence.get("structural_ambiguous"),
                        "structural_contexts": occurrence.get("structural_contexts"),
                    }.items()
                })

        if discovery.get("status") != "OK":
            receipt["errors"] = ["discovery_blocked"]
            return receipt

        source_hashes = {}
        for rel_path, result in sorted(discovery.get("python", {}).items()):
            user_facing = [
                item for item in result.get("occurrences", [])
                if item.get("classification") == "USER_FACING"
            ]
            if not user_facing:
                continue
            meta, raw = discover._safe_read_file_bytes(source_root, rel_path)
            if meta.get("status") != "OK" or raw is None:
                raise GateABlocked("generator_source_read_failed")
            source_hashes[rel_path] = meta["sha256"]
            source_text = raw.decode("utf-8", errors="strict")
            try:
                candidate_text, changes = discover.transform_python_source(
                    source_text, rel_path
                )
                second_text, second_changes = discover.transform_python_source(
                    candidate_text, rel_path
                )
            except discover.PythonTransformBlocked as exc:
                raise GateABlocked("generator_transform_blocked:" + str(exc))
            if candidate_text == source_text or not changes:
                raise GateABlocked("generator_candidate_has_no_changes")
            if second_text != candidate_text or second_changes:
                raise GateABlocked("generator_candidate_not_idempotent")
            candidate_bytes = candidate_text.encode("utf-8")
            candidate_rel = "python/" + rel_path
            target = _candidate_path(candidate_root, candidate_rel)
            _atomic_write(target, candidate_bytes)
            persisted = pathlib.Path(target).read_bytes()
            if persisted != candidate_bytes:
                raise GateABlocked("generator_candidate_readback_mismatch")
            receipt["generator_candidates"].append({
                "path": rel_path,
                "candidate_path": os.path.join(CANDIDATE_ROOT, candidate_rel),
                "source_sha256": meta["sha256"],
                "candidate_sha256": sha256_bytes(candidate_bytes),
                "source_size": len(raw),
                "candidate_size": len(candidate_bytes),
                "changes": sum(item["replacements"] for item in changes),
                "occurrences": changes,
            })

        for rel_path in discover.REGISTRY["video_pages"]:
            meta, raw = discover._safe_read_file_bytes(source_root, rel_path)
            if meta.get("status") != "OK" or raw is None:
                raise GateABlocked("required_source_read_failed")
            source_hashes[rel_path] = meta["sha256"]
            source_text = raw.decode("utf-8", errors="strict")
            candidate_text, occurrences = transform.transform_document(source_text)
            ambiguous = [
                item for item in occurrences
                if item.get("classification") == "AMBIGUOUS"
            ]
            if ambiguous:
                raise GateABlocked("required_source_ambiguous")
            second_text, second_occurrences = transform.transform_document(candidate_text)
            if second_text != candidate_text or any(
                item.get("action") == "APPLIED" for item in second_occurrences
            ):
                raise GateABlocked("candidate_not_idempotent")
            candidate_bytes = candidate_text.encode("utf-8")
            target = _candidate_path(candidate_root, rel_path)
            _atomic_write(target, candidate_bytes)
            persisted = pathlib.Path(target).read_bytes()
            if persisted != candidate_bytes:
                raise GateABlocked("candidate_readback_mismatch")
            receipt["candidates"].append({
                "path": rel_path,
                "candidate_path": os.path.join(CANDIDATE_ROOT, rel_path),
                "source_sha256": meta["sha256"],
                "candidate_sha256": sha256_bytes(candidate_bytes),
                "source_size": len(raw),
                "candidate_size": len(candidate_bytes),
                "changes": sum(
                    1 for item in occurrences if item.get("action") == "APPLIED"
                ),
                "occurrences": [_safe_occurrence(item) for item in occurrences],
            })

        for rel_path, before_sha in source_hashes.items():
            after, _raw = discover._safe_read_file_bytes(source_root, rel_path)
            if after.get("status") != "OK" or after.get("sha256") != before_sha:
                raise GateABlocked("production_source_changed_during_gate_a")

        receipt["production_sources_unchanged"] = True
        receipt["status"] = (
            "PASS_READY_FOR_GATE_B" if receipt["generator_candidates"] else "PASS"
        )
        receipt["errors"] = []
        return receipt
    except GateABlocked as exc:
        receipt["errors"] = [str(exc)]
        return receipt
    except (OSError, UnicodeError, ValueError, TypeError):
        receipt["errors"] = ["gate_a_io_or_validation_failure"]
        return receipt


def run_gate_a():
    return _run_gate_a(SOURCE_ROOT, CANDIDATE_ROOT, True)


def main():
    receipt = run_gate_a()
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if receipt["status"] in {"PASS", "PASS_READY_FOR_GATE_B"} else 2


if __name__ == "__main__":
    raise SystemExit(main())

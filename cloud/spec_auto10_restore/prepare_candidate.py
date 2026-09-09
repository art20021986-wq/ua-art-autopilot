#!/usr/bin/env python3
"""Compile an offline candidate from an explicitly selected source snapshot.

Usage:
    python prepare_candidate.py --source /tmp/spec-snapshot --output /tmp/spec-candidate

The snapshot must be flattened: ua_additional_spec.py, publikaciya.py,
publish_transaction_guard.py and cars_ui.py directly inside --source. The
active server's nested guard path has not been verified; this tool deliberately
does not search, infer or install a nested layout. Preserve original provenance
and verify actual module bindings separately at Gate B.

No application module is imported or executed. No network, database, worker,
installation, service restart or deployment operation is performed. All ten
candidate modules are compiled in memory before any output is published. Input
files are read only. The new directory is published atomically without replacing
an existing output (Linux renameat2 / RENAME_NOREPLACE is required).
"""
from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile


HERE = Path(__file__).resolve().parent
RUNTIME = HERE / "runtime"
SNAPSHOT_FILES = (
    "ua_additional_spec.py", "publikaciya.py",
    "publish_transaction_guard.py", "cars_ui.py",
)
RUNTIME_FILES = (
    "vin_spec_service.py", "source_policy.py", "profile_library.py", "spec_publication.py",
    "card_shell.py", "card_lifecycle.py",
)
MAX_MODULE_BYTES = 4 * 1024 * 1024


class CandidateError(RuntimeError):
    pass


def _no_symlinks(path: Path) -> Path:
    absolute = Path(os.path.abspath(path))
    for component in (absolute, *absolute.parents):
        if component.is_symlink():
            raise CandidateError("SYMLINK_FORBIDDEN:" + str(component))
    return absolute


def _read(path: Path) -> bytes:
    _no_symlinks(path)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise CandidateError("REGULAR_FILE_REQUIRED:" + path.name)
        data = handle.read(MAX_MODULE_BYTES + 1)
    if len(data) > MAX_MODULE_BYTES:
        raise CandidateError("MODULE_TOO_LARGE:" + path.name)
    return data


def _source_text(data: bytes, name: str) -> str:
    try:
        source = data.decode("utf-8")
        compile(source, name, "exec")
        return source
    except (UnicodeError, SyntaxError, ValueError) as exc:
        raise CandidateError("SOURCE_NOT_UTF8_PYTHON:" + name) from exc


def _patch_functions():
    # This is the pure source-transform module, never an application module.
    path = _no_symlinks(HERE / "integration.py")
    specification = importlib.util.spec_from_file_location("ua_auto10_candidate_integration", path)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    lifecycle_spec = importlib.util.spec_from_file_location(
        "ua_auto10_candidate_lifecycle", _no_symlinks(HERE / "lifecycle_integration.py"))
    lifecycle = importlib.util.module_from_spec(lifecycle_spec)
    lifecycle_spec.loader.exec_module(lifecycle)
    return {
        "ua_additional_spec.py": module.patch_additional_spec,
        "publikaciya.py": module.patch_publisher,
        "publish_transaction_guard.py": lambda source: lifecycle.patch_publish_transaction_guard(
            module.patch_publish_transaction_guard(source)),
        "cars_ui.py": lambda source: lifecycle.patch_cars_ui(module.patch_cars_ui(source)),
    }


def _rename_new_directory(source: Path, output: Path) -> None:
    # Unlike os.rename/os.replace, this cannot replace a directory created by
    # another process after the initial output-existence check.
    library = ctypes.CDLL(None, use_errno=True)
    rename = getattr(library, "renameat2", None)
    if rename is None:
        raise CandidateError("ATOMIC_NOREPLACE_RENAME_UNAVAILABLE")
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    result = rename(-100, os.fsencode(source), -100, os.fsencode(output), 1)
    if result:
        number = ctypes.get_errno()
        if number == errno.EEXIST:
            raise CandidateError("OUTPUT_ALREADY_EXISTS")
        raise OSError(number, os.strerror(number), str(output))


def prepare(source: Path, output: Path) -> dict:
    source = _no_symlinks(source)
    output = _no_symlinks(output)
    if not source.is_dir():
        raise CandidateError("SOURCE_DIRECTORY_MISSING")
    if source == output or source in output.parents or output in source.parents:
        raise CandidateError("SOURCE_OUTPUT_OVERLAP")
    if output.exists():
        raise CandidateError("OUTPUT_ALREADY_EXISTS")
    if not output.parent.is_dir():
        raise CandidateError("OUTPUT_PARENT_MISSING")
    runtime = _no_symlinks(RUNTIME)
    if runtime == output or runtime in output.parents or output in runtime.parents:
        raise CandidateError("RUNTIME_OUTPUT_OVERLAP")

    missing = [name for name in SNAPSHOT_FILES if not (source / name).exists()]
    if missing:
        raise CandidateError("FLATTENED_SNAPSHOT_FILES_MISSING:" + ",".join(missing))
    inputs = {name: (source / name, _read(source / name)) for name in SNAPSHOT_FILES}
    inputs.update({name: (runtime / name, _read(runtime / name)) for name in RUNTIME_FILES})
    patchers = _patch_functions()
    candidate = {}
    before_after = {}
    for name, (path, data) in inputs.items():
        text = _source_text(data, name)
        if name in patchers:
            try:
                text = patchers[name](text)
            except RuntimeError as exc:
                raise CandidateError("INTEGRATION_REJECTED:" + name + ":" + str(exc)) from exc
        # Byte-identical runtime copy, including trailing newline and encoding.
        compiled_data = text.encode("utf-8") if name in patchers else data
        _source_text(compiled_data, "candidate/" + name)
        candidate[name] = compiled_data
        before_after[name] = {
            "input_kind": "snapshot" if name in patchers else "runtime_bundle",
            "before_sha256": hashlib.sha256(data).hexdigest(),
            "after_sha256": hashlib.sha256(compiled_data).hexdigest(),
            "changed": data != compiled_data,
        }
    manifest = {
        "contract_id": "UA-ART-SPEC-AUTO-10-RESTORE-001-v1.0",
        "status": "OFFLINE_CANDIDATE_COMPILED",
        "production_changed": False,
        "runtime_verified": False,
        "source_layout": "flattened_explicit_snapshot",
        "module_count": len(candidate),
        "files": before_after,
        "gate_b_remaining": [
            "Verify consistent source snapshot and current process module bindings.",
            "Map flattened modules to reviewed actual installation paths.",
            "Validate current canonical data, every publication path and rollback route.",
            "Close Gate B and use the existing authorized production/recovery route; owner's placement command is recorded.",
        ],
    }
    # Recheck input bytes before publishing, without trusting a changing source.
    for name, (path, data) in inputs.items():
        if _read(path) != data:
            raise CandidateError("INPUT_CHANGED_DURING_PREPARATION:" + name)

    stage = Path(tempfile.mkdtemp(prefix=".spec-candidate-", dir=output.parent))
    try:
        for name, data in candidate.items():
            (stage / name).write_bytes(data)
        (stage / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _no_symlinks(output)
        _rename_new_directory(stage, output)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Flattened read-only source snapshot")
    parser.add_argument("--output", type=Path, required=True, help="New candidate directory outside source")
    args = parser.parse_args()
    try:
        manifest = prepare(args.source, args.output)
    except (CandidateError, OSError) as exc:
        print(json.dumps({"status": "FAILED", "error": str(exc), "production_changed": False}))
        return 1
    print(json.dumps({"status": manifest["status"], "output": str(args.output.absolute()),
                      "module_count": manifest["module_count"], "production_changed": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

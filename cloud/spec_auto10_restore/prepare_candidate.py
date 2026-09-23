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
files are read only. Where supported, renameat2 publishes the whole directory
without replacing an existing output. Otherwise an exclusively claimed directory
receives complete hard-linked files and manifest.json last. Consumers must call
verify_candidate(): directory visibility alone does not establish readiness.
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
UNSUPPORTED_RENAME_ERRORS = {errno.EINVAL, errno.ENOSYS, errno.ENOTSUP, errno.EOPNOTSUPP}
CONTRACT_ID = "UA-ART-SPEC-AUTO-10-RESTORE-001-v1.0"


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
        raise OSError(errno.ENOSYS, "ATOMIC_NOREPLACE_RENAME_UNAVAILABLE", str(output))
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    result = rename(-100, os.fsencode(source), -100, os.fsencode(output), 1)
    if result:
        number = ctypes.get_errno()
        if number == errno.EEXIST:
            raise CandidateError("OUTPUT_ALREADY_EXISTS")
        raise OSError(number, os.strerror(number), str(output))


def _identity(item):
    return item.st_dev, item.st_ino


def _open_directory(path):
    """Open each directory component without following a substituted symlink."""
    absolute = _no_symlinks(Path(path))
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open(absolute.anchor, flags)
    try:
        for name in absolute.parts[1:]:
            child = os.open(name, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _read_at(directory_fd, name):
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=directory_fd)
    with os.fdopen(descriptor, "rb") as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise CandidateError("REGULAR_FILE_REQUIRED:" + name)
        data = handle.read(MAX_MODULE_BYTES + 1)
        after = os.fstat(handle.fileno())
    if len(data) > MAX_MODULE_BYTES:
        raise CandidateError("MODULE_TOO_LARGE:" + name)
    if (_identity(before), before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            _identity(after), after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise CandidateError("CANDIDATE_FILE_CHANGED:" + name)
    return data, after


def _path_still_owned(parent_fd, name, identity):
    try:
        current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    return stat.S_ISDIR(current.st_mode) and _identity(current) == identity


def _publish_manifest_last(stage, output, manifest):
    """No overwrite fallback; cleanup is bounded to our linked file inodes."""
    manifest["publication_mode"] = "manifest_last"
    manifest_data = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    parent_fd = _open_directory(output.parent)
    stage_fd = _open_directory(stage)
    output_fd = None
    claimed_identity = None
    created = []
    try:
        # Stage belongs to this preparation and has never been exposed as ready.
        descriptor = os.open("manifest.json", os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW,
                             dir_fd=stage_fd)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(manifest_data)
            handle.flush()
            os.fsync(handle.fileno())
        names = sorted(set(SNAPSHOT_FILES + RUNTIME_FILES)) + ["manifest.json"]
        if set(os.listdir(stage_fd)) != set(names):
            raise CandidateError("STAGE_FILE_SET_INVALID")
        stage_identities = {}
        for name in names:
            data, info = _read_at(stage_fd, name)
            expected = hashlib.sha256(manifest_data).hexdigest() if name == "manifest.json" else manifest["files"][name]["after_sha256"]
            if hashlib.sha256(data).hexdigest() != expected:
                raise CandidateError("STAGE_HASH_MISMATCH:" + name)
            stage_identities[name] = _identity(info)
            descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=stage_fd)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        try:
            os.mkdir(output.name, mode=0o700, dir_fd=parent_fd)
        except FileExistsError as exc:
            raise CandidateError("OUTPUT_ALREADY_EXISTS") from exc
        claimed = os.stat(output.name, dir_fd=parent_fd, follow_symlinks=False)
        claimed_identity = _identity(claimed)
        output_fd = os.open(output.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=parent_fd)
        if _identity(os.fstat(output_fd)) != claimed_identity:
            raise CandidateError("OUTPUT_DIRECTORY_REPLACED")
        for name in names:
            if not _path_still_owned(parent_fd, output.name, claimed_identity):
                raise CandidateError("OUTPUT_DIRECTORY_REPLACED")
            if name == "manifest.json":
                # Persist data entries before the single readiness marker.
                os.fsync(output_fd)
                os.fsync(parent_fd)
            os.link(name, name, src_dir_fd=stage_fd, dst_dir_fd=output_fd,
                    follow_symlinks=False)
            created.append((name, stage_identities[name]))
            linked = os.stat(name, dir_fd=output_fd, follow_symlinks=False)
            if not stat.S_ISREG(linked.st_mode) or _identity(linked) != stage_identities[name]:
                raise CandidateError("OUTPUT_FILE_REPLACED:" + name)
        if not _path_still_owned(parent_fd, output.name, claimed_identity):
            raise CandidateError("OUTPUT_DIRECTORY_REPLACED")
        os.fsync(output_fd)
        os.fsync(parent_fd)
    except BaseException:
        # Remove readiness first. A replacement directory/file belongs to the
        # competing writer and is never traversed or removed by path recursion.
        if output_fd is not None:
            for name, identity in reversed(created):
                try:
                    current = os.stat(name, dir_fd=output_fd, follow_symlinks=False)
                    if stat.S_ISREG(current.st_mode) and _identity(current) == identity:
                        os.unlink(name, dir_fd=output_fd)
                except FileNotFoundError:
                    pass
            if claimed_identity is not None and _path_still_owned(parent_fd, output.name, claimed_identity):
                try:
                    os.rmdir(output.name, dir_fd=parent_fd)
                except OSError as cleanup_error:
                    if cleanup_error.errno not in {errno.ENOTEMPTY, errno.EEXIST, errno.ENOENT}:
                        raise
        raise
    finally:
        if output_fd is not None:
            os.close(output_fd)
        os.close(stage_fd)
        os.close(parent_fd)


def _publish_directory(stage, output, manifest):
    try:
        _rename_new_directory(stage, output)
    except OSError as exc:
        if exc.errno not in UNSUPPORTED_RENAME_ERRORS:
            raise
        _publish_manifest_last(stage, output, manifest)


def verify_candidate(output: Path) -> dict:
    """Read-only readiness check: manifest, exact file set, hashes and compilation."""
    output = _no_symlinks(Path(output))
    directory_fd = _open_directory(output)
    try:
        expected_names = set(SNAPSHOT_FILES + RUNTIME_FILES) | {"manifest.json"}
        if set(os.listdir(directory_fd)) != expected_names:
            raise CandidateError("CANDIDATE_NOT_READY_OR_FILE_SET_INVALID")
        data, manifest_info = _read_at(directory_fd, "manifest.json")
        try:
            manifest = json.loads(data)
        except (UnicodeError, ValueError) as exc:
            raise CandidateError("CANDIDATE_MANIFEST_INVALID") from exc
        if (not isinstance(manifest, dict)
                or manifest.get("contract_id") != CONTRACT_ID
                or manifest.get("status") != "OFFLINE_CANDIDATE_COMPILED"
                or manifest.get("production_changed") is not False
                or manifest.get("module_count") != len(expected_names) - 1
                or manifest.get("publication_mode") not in {"directory_atomic", "manifest_last"}
                or not isinstance(manifest.get("files"), dict)
                or set(manifest["files"]) != expected_names - {"manifest.json"}):
            raise CandidateError("CANDIDATE_MANIFEST_INVALID")
        observed_files = {}
        for name in sorted(expected_names - {"manifest.json"}):
            contents, info = _read_at(directory_fd, name)
            observed_files[name] = (_identity(info), info.st_size, info.st_mtime_ns, info.st_ctime_ns)
            item = manifest["files"][name]
            if not isinstance(item, dict) or hashlib.sha256(contents).hexdigest() != item.get("after_sha256"):
                raise CandidateError("CANDIDATE_HASH_MISMATCH:" + name)
            _source_text(contents, "candidate/" + name)
        for name, observed in observed_files.items():
            info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode) or observed != (
                    _identity(info), info.st_size, info.st_mtime_ns, info.st_ctime_ns):
                raise CandidateError("CANDIDATE_CHANGED_DURING_VERIFICATION:" + name)
        final_manifest, final_info = _read_at(directory_fd, "manifest.json")
        if (final_manifest != data or _identity(final_info) != _identity(manifest_info)
                or set(os.listdir(directory_fd)) != expected_names
                or _identity(os.stat(output, follow_symlinks=False)) != _identity(os.fstat(directory_fd))):
            raise CandidateError("CANDIDATE_CHANGED_DURING_VERIFICATION")
        return manifest
    finally:
        os.close(directory_fd)


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
        "contract_id": CONTRACT_ID,
        "status": "OFFLINE_CANDIDATE_COMPILED",
        "production_changed": False,
        "runtime_verified": False,
        "source_layout": "flattened_explicit_snapshot",
        "module_count": len(candidate),
        "publication_mode": "directory_atomic",
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
        _publish_directory(stage, output, manifest)
        if verify_candidate(output) != manifest:
            raise CandidateError("CANDIDATE_REPORT_READBACK_MISMATCH")
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

#!/usr/bin/env python3
"""Pure final15 + two coordinated external writers; never an installer.

Exact nested deployment paths are preserved. A new exclusive output receives
its manifest last; failed assembly is incomplete and must never be installed.
No candidate application is imported and no active service/DB is touched.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import types

HERE = Path(__file__).resolve().parent
BASE_HELPER_SHA = "38db5dbf9c5c6432665735cb3f6c238ac72c6c5306c6b8f34f59e0fa8432f23a"
BASE_MANIFEST_SHA = "c4f75a818156e29426c9d601552ab0de56663e965233f2a56c01f5aaa111de07"
BASE_SERVER_RESULT_SHA = "f34de54adcee18d25a0214b5ed6844e05a963e46e2a47fc0aecd4b0861637d02"
TASK083_TARGET = "autopilot_inbox/cloud/task_083_catalog_dedup/installer.py"
WRITERS = {
    "analitika_wsgi.py": {
        "source_sha256": "a73be46099596322dcd607ecadd56140d45483a5ad38f1c1a0a0e395cfc8bc94",
        "output_sha256": "cb6fc54ae832eb768eb70f2815e010db46e15614ef1864acc3dd0d843386fc23",
        "patcher_sha256": "58e62afbc8458f273b605b06b222552ff07d83d9fd375c5891685045a070e2e5",
        "function": "patch",
    },
    TASK083_TARGET: {
        "source_sha256": "13dbcbced164c73bb1767fee6d35ca9597c14b552baaeb31ebbf90cad70b1b46",
        "output_sha256": "13b61a13b73f4a029b01fa0f3c071ab8d4790b656d8fa5f37876e92ac5231684",
        "patcher_sha256": "6857483c3ee21fddb326278fe3ab3aa8eee85ebb82de9ff4048d59db14d870d2",
        "function": "patch",
    },
}
LIMITATIONS = [
    "Final15 synthetic server PASS applies only to inherited fifteen bytes, not the combined seventeen-file candidate.",
    "Combined17 execution, live writer drain/fence, active worker/source10 and production publication remain unverified.",
    "No application import, deployment, WSGI reload, scheduled-task mutation, HALT change or database write.",
]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path, expected=None):
    path = Path(os.path.abspath(path))
    if any(value.is_symlink() for value in (path, *path.parents)):
        raise RuntimeError("SYMLINK_FORBIDDEN")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > 4 * 1024 * 1024:
            raise RuntimeError("INPUT_TYPE_OR_SIZE")
        with os.fdopen(os.dup(descriptor), "rb") as handle:
            data = handle.read()
        after = os.fstat(descriptor)
        signature = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
        if signature(before) != signature(after) or signature(after) != signature(path.lstat()):
            raise RuntimeError("INPUT_CHANGED_DURING_READ")
        if expected is not None and sha(data) != expected:
            raise RuntimeError("INPUT_SHA_MISMATCH:" + path.name)
        return data, signature(after)
    finally:
        os.close(descriptor)


def load_pure(path, expected):
    data, identity = read(path, expected)
    module = types.ModuleType("complete17_pure_helper")
    module.__file__ = str(path)
    exec(compile(data, str(path), "exec"), module.__dict__)
    return module, (Path(path), data, identity)


def recheck(inputs):
    for path, data, identity in inputs:
        if read(path, sha(data)) != (data, identity):
            raise RuntimeError("INPUT_CHANGED_DURING_ASSEMBLY:" + path.name)


def tree_files(root):
    found = set()
    def visit(directory, prefix=""):
        for item in os.scandir(directory):
            name = prefix + item.name
            if item.is_symlink():
                raise RuntimeError("OUTPUT_SYMLINK_FORBIDDEN")
            if item.is_dir(follow_symlinks=False):
                visit(Path(item.path), name + "/")
            elif item.is_file(follow_symlinks=False):
                found.add(name)
            else:
                raise RuntimeError("OUTPUT_FILE_TYPE_INVALID")
    visit(root)
    return found


def expected_manifest(base_manifest):
    entries = {name: {"before_sha256": entry["before_sha256"], "after_sha256": entry["after_sha256"],
                      "scope": "INHERITED_FINAL15_BYTES"} for name, entry in base_manifest["files"].items()}
    for target, pins in WRITERS.items():
        entries[target] = {"before_sha256": pins["source_sha256"], "after_sha256": pins["output_sha256"],
                           "scope": "EXTERNAL_WRITER_COORDINATION_PATCH"}
    return {"candidate_id": "UA-ART-SPEC-AUTO10-COMPLETE-17-V1", "contract_id": base_manifest["contract_id"],
            "status": "OFFLINE_COMPLETE17_COMPILED", "module_count": 17, "publication_mode": "manifest_last",
            "production_changed": False, "application_imported": False, "overall_gate_b": "NOT_EVALUATED",
            "combined17_execution": "NOT_RUN", "base_manifest_sha256": BASE_MANIFEST_SHA,
            "inherited_final15_server_result_sha256": BASE_SERVER_RESULT_SHA,
            "execution_dependency_pins": base_manifest["execution_dependency_pins"],
            "base_helper_sha256": BASE_HELPER_SHA, "writer_pins": WRITERS,
            "target_root": "/home/Carix", "files": entries, "limitations": LIMITATIONS}


def verify(output, base_candidate):
    base_data, _ = read(Path(base_candidate) / "manifest.json", BASE_MANIFEST_SHA)
    expected = expected_manifest(json.loads(base_data))
    output = Path(os.path.abspath(output))
    if set(WRITERS) != {"analitika_wsgi.py", TASK083_TARGET} or len(expected["files"]) != 17:
        raise RuntimeError("WRITER_PINS_NOT_FROZEN")
    if tree_files(output) != set(expected["files"]) | {"manifest.json"}:
        raise RuntimeError("EXACT17_FILE_SET_REQUIRED")
    raw, signature = read(output / "manifest.json")
    if json.loads(raw) != expected:
        raise RuntimeError("MANIFEST_SCOPE_OR_PROVENANCE_MISMATCH")
    observed = [(output / "manifest.json", raw, signature)]
    for name, entry in expected["files"].items():
        data, identity = read(output / name, entry["after_sha256"])
        compile(data, name, "exec")
        observed.append((output / name, data, identity))
    recheck(observed)
    if tree_files(output) != set(expected["files"]) | {"manifest.json"}:
        raise RuntimeError("OUTPUT_CHANGED_DURING_VERIFICATION")
    return expected


def prepare(base_candidate, sources, patchers, output):
    if set(WRITERS) != {"analitika_wsgi.py", TASK083_TARGET}:
        raise RuntimeError("WRITER_PINS_NOT_FROZEN")
    if set(sources) != set(WRITERS) or set(patchers) != set(WRITERS):
        raise RuntimeError("EXACT_WRITER_MAPPING_REQUIRED")
    base_candidate, output = Path(os.path.abspath(base_candidate)), Path(os.path.abspath(output))
    if output.exists() or output.is_symlink():
        raise RuntimeError("OUTPUT_ALREADY_EXISTS")
    if any(value.is_symlink() for value in (output.parent, *output.parent.parents)):
        raise RuntimeError("SYMLINK_FORBIDDEN")
    input_roots = {base_candidate, HERE} | {Path(os.path.abspath(path)).parent for path in list(sources.values()) + list(patchers.values())}
    if any(output == root or root in output.parents or output in root.parents for root in input_roots):
        raise RuntimeError("INPUT_OUTPUT_OVERLAP")
    base_helper, helper_input = load_pure(HERE / "complete_candidate.py", BASE_HELPER_SHA)
    base_manifest_data, identity = read(base_candidate / "manifest.json", BASE_MANIFEST_SHA)
    base_manifest = base_helper.verify_candidate(base_candidate)
    inputs = [helper_input, (base_candidate / "manifest.json", base_manifest_data, identity)]
    files = {}
    for name, entry in base_manifest["files"].items():
        data, identity = read(base_candidate / name, entry["after_sha256"])
        inputs.append((base_candidate / name, data, identity))
        files[name] = data
    for target, pins in WRITERS.items():
        path = Path(sources[target])
        data, identity = read(path, pins["source_sha256"])
        inputs.append((path, data, identity))
        patcher, binding = load_pure(Path(patchers[target]), pins["patcher_sha256"])
        inputs.append(binding)
        changed = getattr(patcher, pins["function"])(data)
        if not isinstance(changed, bytes) or sha(changed) != pins["output_sha256"]:
            raise RuntimeError("PATCHED_OUTPUT_SHA_MISMATCH:" + target)
        files[target] = changed
    for name, data in files.items():
        compile(data, name, "exec")
    manifest = expected_manifest(base_manifest)
    recheck(inputs)
    parent_fd = os.open(output.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    root_fd = None
    owned = None
    try:
        os.mkdir(output.name, mode=0o700, dir_fd=parent_fd)
        root_fd = os.open(output.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
        owned = os.fstat(root_fd)
        marker_identity = None
        def binding_ok():
            linked = os.stat(output.name, dir_fd=parent_fd, follow_symlinks=False)
            if (linked.st_dev, linked.st_ino) != (owned.st_dev, owned.st_ino):
                raise RuntimeError("OUTPUT_DIRECTORY_REPLACED")
        def write_exclusive(name, data):
            nonlocal marker_identity
            binding_ok()
            parts = Path(name).parts
            fd = os.dup(root_fd)
            try:
                for folder in parts[:-1]:
                    try:
                        os.mkdir(folder, mode=0o700, dir_fd=fd)
                        os.fsync(fd)
                    except FileExistsError:
                        pass
                    nxt = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    os.close(fd)
                    fd = nxt
                writer = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
                if name == "manifest.json":
                    marker = os.fstat(writer)
                    marker_identity = (marker.st_dev, marker.st_ino)
                with os.fdopen(writer, "wb") as handle:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                    written = os.fstat(handle.fileno())
                os.fsync(fd)
            finally:
                os.close(fd)
            binding_ok()
            return (written.st_dev, written.st_ino)
        for name, data in sorted(files.items()):
            write_exclusive(name, data)
        recheck(inputs)
        if tree_files(output) != set(files):
            raise RuntimeError("OUTPUT_FILE_SET_CHANGED_BEFORE_MANIFEST")
        for name, data in files.items():
            read(output / name, sha(data))
        try:
            marker_identity = write_exclusive("manifest.json", (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode())
            os.fsync(root_fd)
            os.fsync(parent_fd)
            recheck(inputs)
            result = verify(output, base_candidate)
            binding_ok()
            return result
        except BaseException:
            # Only invalidate our own readiness marker; never remove an output
            # directory or someone else's replacement files.
            if marker_identity is not None:
                marker = os.stat("manifest.json", dir_fd=root_fd, follow_symlinks=False)
                if (marker.st_dev, marker.st_ino) == marker_identity:
                    os.unlink("manifest.json", dir_fd=root_fd)
                    os.fsync(root_fd)
            raise
    finally:
        if root_fd is not None:
            os.close(root_fd)
        os.close(parent_fd)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-candidate", required=True, type=Path)
    parser.add_argument("--inputs-json", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.verify:
        result = verify(args.output, args.base_candidate)
    else:
        inputs = json.loads(args.inputs_json.read_text())
        result = prepare(args.base_candidate, inputs["sources"], inputs["patchers"], args.output)
    print(json.dumps({"status": result["status"], "module_count": 17, "production_changed": False,
                      "combined17_execution": "NOT_RUN", "overall_gate_b": "NOT_EVALUATED",
                      "manifest_sha256": sha((args.output / "manifest.json").read_bytes())}))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Pure follow-up to frozen17: canonical analytics ownership and VIN binding.

No application imports or production mutation. Creates only an exclusive,
previously absent output; manifest is the last readiness marker.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import stat
import types

HERE = Path(__file__).resolve().parent
BASE_MANIFEST_SHA = "d800e55813b6edc24322f7021e924dd0052915f07414b42bd02f0a7c234522f5"
BASE_HELPER_SHA = "ea0265bee0fc3b19fe5df6096dfb7f0676cce07a405bcaf34abfd26050ebdc24"
PATCHES = {
    "analitika_wsgi.py": {
        "helper": "repair_analytics_shell.py", "function": "patch_analytics_shell", "input_kind": "bytes",
        "helper_sha256": "184976fe95978be2d7de64455bfc40e83a3fb541c4029a084662b0d1358a0135",
        "input_sha256": "cb6fc54ae832eb768eb70f2815e010db46e15614ef1864acc3dd0d843386fc23",
        "output_sha256": "76cb2e6141b262e558acc7e96804afacc312a6cb3971cd623eef921e086d7761",
        "scope": "OPTIONAL_ANALYTICS_PRESERVES_PUBLISHER_OWNED_SHELL",
    },
    "source_policy.py": {
        "helper": "repair_vpic_identity.py", "function": "patch_vpic_identity", "input_kind": "str",
        "helper_sha256": "22829322363c6622fd477c5746b047e73f0c5bc8f36137b58db39f233ce0d654",
        "input_sha256": "e9590c1630a8c81bcacf05d620e273a341aaf407f39c3a1bd184258c17ce3f0d",
        "output_sha256": "8f6d010242ab7df297fe0ad2ee35233d80c7f5005ffaef669d8332caba9fffd2",
        "scope": "REJECT_FOREIGN_OR_MISSING_RETURNED_VIN",
    },
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load_base():
    path = HERE / "complete17_candidate.py"
    if path.is_symlink() or path.resolve() != path.absolute():
        raise RuntimeError("BASE_HELPER_PATH_INVALID")
    data = path.read_bytes()
    if sha(data) != BASE_HELPER_SHA:
        raise RuntimeError("BASE_HELPER_CHANGED")
    module = types.ModuleType("frozen17_assembler")
    module.__file__ = str(path)
    exec(compile(data, str(path), "exec"), module.__dict__)
    return module


def expected_manifest(base):
    manifest = copy.deepcopy(base)
    manifest.update({"candidate_id": "UA-ART-SPEC-AUTO10-COMPLETE-17-V2",
                     "status": "OFFLINE_COMPLETE17_REFINED_COMPILED",
                     "refined_base_manifest_sha256": BASE_MANIFEST_SHA,
                     "refined_base_helper_sha256": BASE_HELPER_SHA,
                     "followup_patches": PATCHES,
                     "combined17_execution": "NOT_RUN", "overall_gate_b": "NOT_EVALUATED"})
    for name, pin in PATCHES.items():
        manifest["files"][name]["after_sha256"] = pin["output_sha256"]
        manifest["files"][name]["scope"] = pin["scope"]
    analytics = manifest["writer_pins"]["analitika_wsgi.py"]
    analytics["prior_coordinated_output_sha256"] = analytics["output_sha256"]
    analytics["output_sha256"] = PATCHES["analitika_wsgi.py"]["output_sha256"]
    analytics["followup_helper_sha256"] = PATCHES["analitika_wsgi.py"]["helper_sha256"]
    manifest["limitations"] = [
        "Historical final15 PASS and frozen17-v1 analytics failure remain separate evidence; neither certifies this refined candidate.",
        "This assembly imports only pinned pure patchers, not CRM/site/worker applications.",
        "Combined17 execution, legacy writer drain/handoff, live source10 acceptance, worker and production publication require separate evidence.",
        "No production installation, WSGI reload, scheduled-task mutation, HALT change or live database write.",
    ]
    return manifest


def inspect(base17, base15):
    helper = load_base()
    raw, identity = helper.read(base17 / "manifest.json", BASE_MANIFEST_SHA)
    base = helper.verify(base17, base15)
    inputs = [(base17 / "manifest.json", raw, identity)]
    files = {}
    for name, entry in base["files"].items():
        data, identity = helper.read(base17 / name, entry["after_sha256"])
        inputs.append((base17 / name, data, identity))
        files[name] = data
    for name, pin in PATCHES.items():
        patcher, binding = helper.load_pure(HERE / pin["helper"], pin["helper_sha256"])
        inputs.append(binding)
        if sha(files[name]) != pin["input_sha256"]:
            raise RuntimeError("FOLLOWUP_INPUT_SHA_MISMATCH:" + name)
        data = files[name] if pin["input_kind"] == "bytes" else files[name].decode()
        changed = getattr(patcher, pin["function"])(data)
        if isinstance(changed, str):
            changed = changed.encode()
        if not isinstance(changed, bytes) or sha(changed) != pin["output_sha256"]:
            raise RuntimeError("FOLLOWUP_OUTPUT_SHA_MISMATCH:" + name)
        files[name] = changed
    helper.recheck(inputs)
    return helper, inputs, files, expected_manifest(base)


def verify(output, base17, base15):
    helper, inputs, files, expected = inspect(base17, base15)
    if helper.tree_files(output) != set(files) | {"manifest.json"}:
        raise RuntimeError("REFINED17_EXACT_FILE_SET_REQUIRED")
    raw, identity = helper.read(output / "manifest.json")
    if json.loads(raw) != expected:
        raise RuntimeError("REFINED17_MANIFEST_MISMATCH")
    observed = [(output / "manifest.json", raw, identity)]
    for name, data in files.items():
        actual, identity = helper.read(output / name, sha(data))
        compile(actual, name, "exec")
        observed.append((output / name, actual, identity))
    helper.recheck(inputs + observed)
    return expected


def prepare(base17, base15, output):
    helper, inputs, files, manifest = inspect(base17, base15)
    if output.exists() or output.is_symlink() or any(path.is_symlink() for path in (output.parent, *output.parent.parents)):
        raise RuntimeError("OUTPUT_MUST_BE_NEW_CANONICAL_DIRECTORY")
    for source in (base17, base15, HERE):
        if source == output or source in output.parents or output in source.parents:
            raise RuntimeError("INPUT_OUTPUT_OVERLAP")
    for name, data in files.items():
        compile(data, name, "exec")
    parent = os.open(output.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    directory = None
    marker = None
    try:
        os.mkdir(output.name, 0o700, dir_fd=parent)
        directory = os.open(output.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        identity = os.fstat(directory)
        def binding():
            current = os.stat(output.name, dir_fd=parent, follow_symlinks=False)
            if (current.st_dev, current.st_ino) != (identity.st_dev, identity.st_ino):
                raise RuntimeError("OUTPUT_DIRECTORY_REPLACED")
        def write(name, data):
            nonlocal marker
            binding()
            descriptor = os.dup(directory)
            try:
                parts = Path(name).parts
                for part in parts[:-1]:
                    try:
                        os.mkdir(part, 0o700, dir_fd=descriptor)
                    except FileExistsError:
                        pass
                    following = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
                    os.close(descriptor)
                    descriptor = following
                writer = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=descriptor)
                if name == "manifest.json":
                    opened = os.fstat(writer)
                    marker = (opened.st_dev, opened.st_ino)
                with os.fdopen(writer, "wb") as handle:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            binding()
        for name, data in sorted(files.items()):
            write(name, data)
        helper.recheck(inputs)
        if helper.tree_files(output) != set(files):
            raise RuntimeError("OUTPUT_SET_CHANGED_BEFORE_MANIFEST")
        for name, data in files.items():
            helper.read(output / name, sha(data))
        write("manifest.json", (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode())
        os.fsync(directory)
        os.fsync(parent)
        verify(output, base17, base15)
        binding()
        return manifest
    except BaseException:
        if directory is not None and marker is not None:
            current = os.stat("manifest.json", dir_fd=directory, follow_symlinks=False)
            if (current.st_dev, current.st_ino) == marker:
                os.unlink("manifest.json", dir_fd=directory)
                os.fsync(directory)
        raise
    finally:
        if directory is not None:
            os.close(directory)
        os.close(parent)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base17", required=True, type=Path)
    parser.add_argument("--base15", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    base17, base15, output = (value.absolute() for value in (args.base17, args.base15, args.output))
    manifest = verify(output, base17, base15) if args.verify else prepare(base17, base15, output)
    print(json.dumps({"status": manifest["status"], "production_changed": False, "overall_gate_b": "NOT_EVALUATED",
                      "module_count": 17, "manifest_sha256": sha((output / "manifest.json").read_bytes())}))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Pure final17 v3 assembly: exact v2 plus the proven CRM edit-session repair.

No application imports, services, database writes or installation. Historical
combined v2 and callback-delta receipts remain distinct evidence scopes.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import types

HERE = Path(__file__).resolve().parent
BASE_MANIFEST_SHA = "12afce821b784771a2a8a0415cc289f5e713d53aabedf0ed3e2747a8c4d4e136"
IO_HELPER_SHA = "ea0265bee0fc3b19fe5df6096dfb7f0676cce07a405bcaf34abfd26050ebdc24"
PATCHER_SHA = "97e1f170301d26403e115962392587f141be40a97b94acae412e3caeec8611f1"
SOURCE_UI_SHA = "32dfec40ca2e6badfab222fd811fa710c52708fc0ff6bad80cbce79c0df5a0ec"
PATCHED_UI_SHA = "57ad5acc340d412aa9d95e1ef56c7de85d4346ad6bbc755fda311763f3637a42"
RECEIPTS = {
    "combined_v2": {"report": "complete17-v2-server-result.json", "report_sha256": "613f8cb1a5ddbe07c9719f816e4725f58d3645adefd6d4c033abfc713cc8ab78",
                    "summary": "complete17-v2-server-server-summary.json", "summary_sha256": "5d5d856d0d308413491f624e38c5d3142db2886239e3037f7c5d08035ed95672"},
    "callback_delta": {"report": "crm-callback-server-repaired-result.json", "report_sha256": "a5d9362d8b388fc16aefbebec92c4253b9c4ee1e02515bd5c9f51cb04e4615ca",
                       "summary": "crm-callback-server-summary.json", "summary_sha256": "ca61f4a83936b236986272ca384d4e9b8c1722fe83eea63030a99de469a85ad4"},
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load_io():
    path = HERE / "complete17_candidate.py"
    if path.is_symlink() or path.resolve() != path.absolute():
        raise RuntimeError("IO_HELPER_PATH_INVALID")
    data = path.read_bytes()
    if sha(data) != IO_HELPER_SHA:
        raise RuntimeError("IO_HELPER_CHANGED")
    module = types.ModuleType("frozen17_io")
    module.__file__ = str(path)
    exec(compile(data, str(path), "exec"), module.__dict__)
    return module


def inspect(base, evidence):
    helper = load_io()
    raw, identity = helper.read(base / "manifest.json", BASE_MANIFEST_SHA)
    manifest = json.loads(raw)
    if len(manifest["files"]) != 17 or helper.tree_files(base) != set(manifest["files"]) | {"manifest.json"}:
        raise RuntimeError("BASE17_EXACT_FILE_SET_REQUIRED")
    observed, files = [(base / "manifest.json", raw, identity)], {}
    for name, entry in manifest["files"].items():
        data, identity = helper.read(base / name, entry["after_sha256"])
        observed.append((base / name, data, identity))
        files[name] = data
    patcher, binding = helper.load_pure(HERE / "repair_crm_edit_session.py", PATCHER_SHA)
    observed.append(binding)
    if sha(files["cars_ui.py"]) != SOURCE_UI_SHA:
        raise RuntimeError("CRM_REPAIR_INPUT_MISMATCH")
    files["cars_ui.py"] = patcher.patch_source(files["cars_ui.py"])
    if sha(files["cars_ui.py"]) != PATCHED_UI_SHA:
        raise RuntimeError("CRM_REPAIR_OUTPUT_MISMATCH")
    receipts = {}
    for key, pin in RECEIPTS.items():
        pair = {}
        for kind in ("report", "summary"):
            expected = pin[kind + "_sha256"]
            if len(expected) != 64:
                raise RuntimeError("SERVER_RECEIPT_READBACK_REQUIRED:" + key)
            raw, identity = helper.read(evidence / pin[kind], expected)
            observed.append((evidence / pin[kind], raw, identity))
            pair[kind] = json.loads(raw)
            if pair[kind].get("status") != "PASS" or pair[kind].get("production_changed") is not False:
                raise RuntimeError("SERVER_RECEIPT_SCOPE_INVALID:" + key)
        report, summary = pair["report"], pair["summary"]
        if report.get("inputs", {}).get("manifest_sha256") != BASE_MANIFEST_SHA or summary.get("candidate_manifest_sha256") != BASE_MANIFEST_SHA:
            raise RuntimeError("SERVER_RECEIPT_BASE_MISMATCH:" + key)
        if summary.get("input_bytes_mtimes_inodes_unchanged") is not True or any(report.get("io_guard", {}).values()):
            raise RuntimeError("SERVER_RECEIPT_INPUT_OR_IO_FAILURE:" + key)
        if key == "combined_v2" and summary.get("report_sha256") != pin["report_sha256"]:
            raise RuntimeError("COMBINED_SERVER_RECEIPT_DIGEST_MISMATCH")
        if key == "callback_delta":
            patched = report.get("ui_patch", {})
            if patched.get("patcher_sha256") != PATCHER_SHA or patched.get("before_sha256") != SOURCE_UI_SHA or patched.get("after_sha256") != PATCHED_UI_SHA:
                raise RuntimeError("CALLBACK_SERVER_PATCH_BINDING_MISMATCH")
            run = summary.get("runs", {}).get("repaired", {})
            if run.get("status") != "PASS" or run.get("report_sha256") != pin["report_sha256"]:
                raise RuntimeError("CALLBACK_SERVER_RECEIPT_DIGEST_MISMATCH")
        receipts[key] = {"status": "PASS", "report_sha256": pin["report_sha256"], "summary_sha256": pin["summary_sha256"],
                         "input_candidate_manifest_sha256": BASE_MANIFEST_SHA}
    for name, data in files.items():
        compile(data, name, "exec")
    result = copy.deepcopy(manifest)
    result.update({"candidate_id": "UA-ART-SPEC-AUTO10-COMPLETE-17-V3", "status": "OFFLINE_COMPLETE17_CRM_REPAIRED_COMPILED",
                   "crm_base_manifest_sha256": BASE_MANIFEST_SHA, "crm_repair_patcher_sha256": PATCHER_SHA,
                   "changed_from_v2": ["cars_ui.py"], "unchanged_from_v2_count": 16,
                   "combined17_execution": "V3_BYTE_COMPOSITION_WITH_SEPARATE_V2_AND_CALLBACK_DELTA_RECEIPTS",
                   "overall_gate_b": "NOT_EVALUATED", "execution_evidence": receipts,
                   "candidate_file_closure_sha256": sha(json.dumps({name: sha(data) for name, data in files.items()}, sort_keys=True, separators=(",", ":")).encode())})
    result["files"]["cars_ui.py"].update({"after_sha256": PATCHED_UI_SHA, "scope": "CRM_CANCEL_RETIRES_PREVIOUS_TEXT_EDITOR"})
    result["followup_patches"]["cars_ui.py"] = {"helper": "repair_crm_edit_session.py", "helper_sha256": PATCHER_SHA,
                                               "function": "patch_source", "input_kind": "bytes", "input_sha256": SOURCE_UI_SHA,
                                               "output_sha256": PATCHED_UI_SHA, "scope": "CRM_CANCEL_RETIRES_PREVIOUS_TEXT_EDITOR"}
    receipts["combined_v2"]["scope"] = "Historical complete v2 runtime; 16 unchanged module bytes are inherited, its old cars_ui is superseded."
    receipts["callback_delta"]["scope"] = "Exact v2 closure with only cars_ui replaced; actual registration, callbacks, SQLite and publisher with fake Telegram and local public reader."
    result["limitations"] = [
        "This is exact byte composition, not a new run of the unchanged combined17 cycle or a claim of overall Gate B.",
        "Two distinct read-back Python 3.10 server receipts bind the base runtime and the one-module callback repair.",
        "Actual Telegram transport, external registrar modules, worker timing and live source10 remain separately unverified.",
        "Legacy writer drain/handoff, production installation, UA-0017/UA-0018 publication and real public read-back are not established here.",
        "Assembly imports only pinned pure helpers and compiles candidate bytes; no active application, service or database is touched.",
    ]
    helper.recheck(observed)
    return helper, observed, files, result


def verify(output, base, evidence):
    output, base, evidence = (Path(os.path.abspath(value)) for value in (output, base, evidence))
    helper, inputs, files, expected = inspect(base, evidence)
    if helper.tree_files(output) != set(files) | {"manifest.json"}:
        raise RuntimeError("CRM17_EXACT_FILE_SET_REQUIRED")
    raw, identity = helper.read(output / "manifest.json")
    if json.loads(raw) != expected:
        raise RuntimeError("CRM17_MANIFEST_MISMATCH")
    observed = [(output / "manifest.json", raw, identity)]
    for name, data in files.items():
        raw, identity = helper.read(output / name, sha(data))
        observed.append((output / name, raw, identity))
    helper.recheck(inputs + observed)
    if helper.tree_files(output) != set(files) | {"manifest.json"}:
        raise RuntimeError("OUTPUT_CHANGED_DURING_VERIFICATION")
    return expected


def prepare(base, evidence, output):
    base, evidence, output = (Path(os.path.abspath(value)) for value in (base, evidence, output))
    helper, inputs, files, manifest = inspect(base, evidence)
    if output.exists() or output.is_symlink() or any(path.is_symlink() for path in (output.parent, *output.parent.parents)):
        raise RuntimeError("OUTPUT_MUST_BE_NEW_CANONICAL_DIRECTORY")
    if any(source == output or source in output.parents or output in source.parents for source in (base, evidence, HERE)):
        raise RuntimeError("INPUT_OUTPUT_OVERLAP")
    parent = os.open(output.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    directory, marker = None, None
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
                        os.fsync(descriptor)
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
        verify(output, base, evidence)
        binding()
        return manifest
    except BaseException:
        if directory is not None and marker is not None:
            try:
                current = os.stat("manifest.json", dir_fd=directory, follow_symlinks=False)
                if (current.st_dev, current.st_ino) == marker:
                    os.unlink("manifest.json", dir_fd=directory)
                    os.fsync(directory)
            except FileNotFoundError:
                pass
        raise
    finally:
        if directory is not None:
            os.close(directory)
        os.close(parent)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    base, evidence, output = (Path(os.path.abspath(value)) for value in (args.base, args.evidence, args.output))
    result = verify(output, base, evidence) if args.verify else prepare(base, evidence, output)
    print(json.dumps({"status": result["status"], "manifest_sha256": sha((output / "manifest.json").read_bytes()),
                      "candidate_file_closure_sha256": result["candidate_file_closure_sha256"], "module_count": 17,
                      "changed_from_v2": result["changed_from_v2"], "production_changed": False, "overall_gate_b": "NOT_EVALUATED"}))


if __name__ == "__main__":
    main()

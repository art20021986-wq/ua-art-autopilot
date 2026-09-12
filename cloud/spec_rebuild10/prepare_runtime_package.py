"""Assemble an inert, exact runtime source snapshot; never admit or install it.

The private archive contains existing private application sources. Only the
separate redacted manifest is suitable for a public repository. No application
module is imported, no deployment plan is authorized, and no process is started.
"""
from __future__ import annotations

import argparse
import ast
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tarfile

SCHEMA = "UA-ART-SPEC-REBUILD10-RUNTIME-PACKAGE-1"
OLD_MANIFEST_SHA256 = "14f42086fc8bc94aefc4e4c83bda50e01107c30d2ad893c00d658f60d0c64fff"
BRIDGE_NAMES = {"db.py", "cars_ui.py", "spec_publication.py", "ua_additional_spec.py"}
MAX_FILE = 4 * 1024 * 1024


def require(ok, code):
    if not ok:
        raise ValueError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":"), allow_nan=False).encode()


def read(path):
    path = Path(path).absolute()
    require(not any(p.is_symlink() for p in (path, *path.parents)), "SYMLINK_FORBIDDEN")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
                and before.st_size <= MAX_FILE, "REGULAR_BOUNDED_FILE_REQUIRED")
        with os.fdopen(os.dup(fd), "rb") as stream:
            raw = stream.read(MAX_FILE + 1)
        stamp = lambda value: (value.st_dev, value.st_ino, value.st_size,
                               value.st_mtime_ns, value.st_ctime_ns)
        require(len(raw) <= MAX_FILE and stamp(before) == stamp(os.fstat(fd))
                == stamp(path.lstat()), "SOURCE_CHANGED_DURING_READ")
        return raw
    finally:
        os.close(fd)


def path_name(name):
    require(isinstance(name, str) and name and not name.startswith("/")
            and ".." not in PurePosixPath(name).parts
            and str(PurePosixPath(name)) == name, "TARGET_PATH_INVALID")
    return name


def parsed(raw, name):
    # Match the current server's Python 3.10 grammar without executing code.
    tree = ast.parse(raw, filename=name, feature_version=(3, 10))
    compile(tree, name, "exec")
    return tree


def literal(tree, name):
    values = [node.value for node in tree.body if isinstance(node, ast.Assign)
              and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)]
    require(len(values) == 1, "EXACT_SOURCE_CONSTANT_REQUIRED:" + name)
    return ast.literal_eval(values[0])


def prepare(base_dir, bridge_dir, bootstrap_dir, module_dir, output_dir, *, version):
    require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", version or ""), "VERSION_REQUIRED")
    base, bridge, boot, module, output = [Path(p).absolute() for p in
        (base_dir, bridge_dir, bootstrap_dir, module_dir, output_dir)]
    require(not output.exists() and not output.is_symlink(), "NEW_PRIVATE_OUTPUT_DIRECTORY_REQUIRED")
    captured = {}

    def capture(path):
        raw = read(path)
        if path in captured:
            require(captured[path] == raw, "INPUT_CHANGED_DURING_ASSEMBLY")
        captured[path] = raw
        return raw

    old_raw = capture(base / "manifest.json")
    require(sha(old_raw) == OLD_MANIFEST_SHA256, "EXACT_COMPLETE17_BASE_REQUIRED")
    old = json.loads(old_raw)
    require(old["candidate_id"] == "UA-ART-SPEC-AUTO10-COMPLETE-17-V3"
            and old["module_count"] == len(old["files"]) == 17
            and old["target_root"] == "/home/Carix", "BASE_SCOPE")
    payload, groups = {}, {}
    for name, record in old["files"].items():
        path_name(name)
        raw = capture(base / name)
        require(sha(raw) == record["after_sha256"], "BASE_SOURCE_CHANGED:" + name)
        parsed(raw, name)
        payload[name], groups[name] = raw, "legacy_unchanged"

    bridge_manifest = json.loads(capture(bridge / "crm-bridge-manifest.json"))
    require(bridge_manifest["status"] == "PREPARED_NOT_INSTALLED"
            and bridge_manifest["automatic_first_publication"] is False
            and bridge_manifest["runtime_bindings"] == "NOT_CONFIGURED"
            and set(bridge_manifest["files"]) == BRIDGE_NAMES
            and set(bridge_manifest["source_pins"]) == BRIDGE_NAMES, "BRIDGE_SCOPE")
    for name in sorted(BRIDGE_NAMES):
        require(bridge_manifest["source_pins"][name] == sha(payload[name]), "BRIDGE_BASE_MISMATCH")
        raw = capture(bridge / name)
        require(sha(raw) == bridge_manifest["files"][name], "BRIDGE_CANDIDATE_CHANGED")
        parsed(raw, name)
        payload[name], groups[name] = raw, "legacy_transformed_for_rebuild10"

    bootstrap_source = capture(module / "bootstrap.py")
    runtime_pins = literal(parsed(bootstrap_source, "bootstrap.py"), "RUNTIME_PINS")
    boot_manifest = json.loads(capture(boot / "bootstrap-manifest.json"))
    require(boot_manifest["status"] == "PREPARED_NOT_LOADED"
            and boot_manifest["production_changed"] is False
            and boot_manifest["imports_executed"] is False
            and boot_manifest["automatic_first_publication"] is False
            and boot_manifest["input_source_pins"] == runtime_pins, "BOOTSTRAP_SCOPE_OR_SOURCE_CHANGED")
    for name, expected in runtime_pins.items():
        require(name in payload and sha(payload[name]) == expected, "BOOTSTRAP_RUNTIME_PIN_CHANGED:" + name)
    entrypoint_source = capture(module / "prepare_bootstrap.py")
    entrypoint = literal(parsed(entrypoint_source, "prepare_bootstrap.py"), "ENTRYPOINT").encode()
    entrypoint_raw = capture(boot / "spec_rebuild10_bootstrap.py")
    require(entrypoint_raw == entrypoint and sha(entrypoint_raw) == boot_manifest["entrypoint_sha256"],
            "BOOTSTRAP_CANDIDATE_STALE_REGENERATE")
    payload["spec_rebuild10_bootstrap.py"] = entrypoint_raw
    groups["spec_rebuild10_bootstrap.py"] = "explicit_controller_entrypoint"

    # The controller can provision approved collectors using this module even
    # though bootstrap receives its collector instances as dependencies.
    pending, completed = ["__init__", "bootstrap", "source_provisioning"], set()
    # The generated controller entrypoint can import a runtime module (e.g.
    # sync) that bootstrap itself does not import. Include that closure too.
    for node in ast.walk(parsed(entrypoint_raw, "spec_rebuild10_bootstrap.py")):
        if isinstance(node, ast.ImportFrom) and node.level == 0:
            if node.module == "spec_rebuild10":
                pending.extend(alias.name for alias in node.names)
            elif (node.module or "").startswith("spec_rebuild10."):
                pending.append(node.module.removeprefix("spec_rebuild10."))
    while pending:
        name = pending.pop()
        if name in completed:
            continue
        require(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name), "FLAT_RUNTIME_MODULE_REQUIRED")
        raw = capture(module / (name + ".py"))
        tree = parsed(raw, "spec_rebuild10/" + name + ".py")
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level:
                require(node.level == 1, "PARENT_PACKAGE_IMPORT_NOT_SUPPORTED")
                dependencies = [node.module] if node.module else [a.name for a in node.names]
                pending.extend(dependencies)
        target = "spec_rebuild10/" + name + ".py"
        payload[target], groups[target] = raw, "new_runtime_module"
        completed.add(name)
    registry = capture(module / "sources.json")
    json.loads(registry)
    payload["spec_rebuild10/sources.json"] = registry
    groups["spec_rebuild10/sources.json"] = "new_runtime_registry"

    require(all(read(path) == raw for path, raw in captured.items()), "INPUT_CHANGED_DURING_ASSEMBLY")
    records = {name: {"sha256": sha(raw), "bytes": len(raw), "group": groups[name]}
               for name, raw in sorted(payload.items())}
    counts = {group: sum(value == group for value in groups.values()) for group in sorted(set(groups.values()))}
    value = {"schema": SCHEMA, "version": version,
        "status": "PREPARED_INERT_REQUIRES_NEW_CODE_ADMISSION",
        "target_root": "/home/Carix", "file_count": len(payload), "groups": counts,
        "files": records, "unchanged_execution_dependency_pins": old["execution_dependency_pins"],
        "complete17_base_manifest_sha256": OLD_MANIFEST_SHA256,
        "assembly_inputs_sha256": {"crm_bridge_manifest": sha(captured[bridge / "crm-bridge-manifest.json"]),
            "bootstrap_manifest": sha(captured[boot / "bootstrap-manifest.json"]),
            "bootstrap_preparer": sha(entrypoint_source)},
        "code_handoff_v4_compatible": False, "new_code_installer_available": False,
        "live_preconditions": "NOT_OBSERVED_FOR_THIS_NEW_TARGET_SET",
        "application_imported": False, "production_changed": False,
        "runtime_loaded": False, "worker_started": False, "overall_gate_b": "NOT_EVALUATED",
        "authorization": "NOT_GRANTED_BY_PACKAGE",
        "automatic_first_publication": False,
        "excluded": ["CRM database", "specification database", "HTML", "media", "separate credential/configuration files", "runtime plans", "installation controller"]}
    manifest = {**value, "manifest_sha256": sha(canonical(value))}
    packed = io.BytesIO()
    with gzip.GzipFile(fileobj=packed, mode="wb", mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode="w", format=tarfile.PAX_FORMAT) as tar:
            for name, raw in sorted({**payload, "manifest.json": canonical(manifest) + b"\n"}.items()):
                info = tarfile.TarInfo(name)
                info.size, info.mode, info.mtime = len(raw), 0o600, 0
                tar.addfile(info, io.BytesIO(raw))
    archive = packed.getvalue()
    # Source edits that occur during packaging invalidate the snapshot instead
    # of producing an apparently current mixed version.
    require(all(read(path) == raw for path, raw in captured.items()), "INPUT_CHANGED_DURING_PACKAGING")
    output.mkdir(mode=0o700, parents=True)
    for name, raw in {"runtime-package.tar.gz": archive,
                      "runtime-manifest.json": canonical(manifest) + b"\n"}.items():
        with (output / name).open("xb") as stream:
            os.chmod(output / name, 0o600)
            stream.write(raw)
    report = {**manifest, "archive_sha256": sha(archive), "archive_bytes": len(archive),
              "private_archive_must_not_be_committed": True}
    with (output / "runtime-package-redacted.json").open("xb") as stream:
        os.chmod(output / "runtime-package-redacted.json", 0o600)
        stream.write(json.dumps(report, indent=2, sort_keys=True) .encode() + b"\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for name in ("base-dir", "bridge-dir", "bootstrap-dir", "module-dir", "output-dir"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    report = prepare(args.base_dir, args.bridge_dir, args.bootstrap_dir,
                     args.module_dir, args.output_dir, version=args.version)
    print(json.dumps({key: report[key] for key in ("status", "version", "file_count", "groups",
          "manifest_sha256", "archive_sha256", "code_handoff_v4_compatible")}, indent=2))
